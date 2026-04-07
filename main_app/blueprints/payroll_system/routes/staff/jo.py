from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import extract

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance, LeaveCredit, Department
from main_app.models.payroll_models import Payroll, PayrollPeriod, Loan, PayrollDeduction, LoanPayment

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

JOB_ORDER_ID = 5

# ========================= CONSTANTS =========================
ALLOWED_LOAN_1_15 = {"Pag-IBIG", "MENPC"}
ALLOWED_LOAN_16_END = {"Pag-IBIG", "MENPC", "SSS"}

# ========================= HELPERS =========================

def safe_float(value):
    try:
        return float(value)
    except:
        return 0.0


def is_second_half(period):
    return period.start_date.day >= 16


def compute_philhealth(gross):
    if gross <= 10000:
        return 250, 250
    total = round(gross * 0.05, 2)
    return total / 2, total / 2


def compute_withholding_tax(gross):
    return round(gross * 0.02, 2)


# ========================= SELECT DEPARTMENT =========================

@payroll_staff_bp.route("/jo/select-department/<int:period_id>")
@login_required
@staff_required
def jo_select_department(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    departments = Department.query.order_by(Department.name).all()

    department_status = {}

    for dept in departments:
        has_payroll = Payroll.query.join(Employee).filter(
            Payroll.payroll_period_id == period.id,
            Employee.department_id == dept.id,
            Employee.employment_type_id == 5  # assuming JO ≠ CASUAL_ID
        ).first()

        department_status[dept.id] = bool(has_payroll)

    return render_template(
        "payroll/staff/jo/select_department.html",
        period=period,
        departments=departments,
        department_status=department_status
    )

# ========================= PREVIEW =========================

@payroll_staff_bp.route("/jo/preview/<int:period_id>/<int:department_id>")
@login_required
@staff_required
def preview_jo_payroll(period_id, department_id):

    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    if period.status == "Locked":
        flash("Payroll already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.jo_select_department", period_id=period.id))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == JOB_ORDER_ID
    ).all()

    second_half = is_second_half(period)
    payroll_data = []
    for emp in employees:

        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date.between(period.start_date, period.end_date)
        ).all()

        worked_days = sum(1 for a in attendances if a.status in ("Present", "Late"))
        worked_days = max(worked_days, 0)

        daily_rate = emp.salary or 0
        basic_pay = worked_days * daily_rate
        
        # ✅ FETCH EXISTING OVERTIME (from saved payroll or default to 0)
        existing_payroll = Payroll.query.filter_by(
            employee_id=emp.id,
            payroll_period_id=period.id
        ).first()
        
        overtime_pay = existing_payroll.overtime_pay if existing_payroll and existing_payroll.overtime_pay else 0
        gross_pay = basic_pay + overtime_pay

        deductions = []
        total_deductions = 0

        # ======================================================
        # 1–15 HALF
        # ======================================================
        if not second_half:
            sss = getattr(emp, "sss_rss", 0) or 0
            phic_emp, phic_gov = compute_philhealth(gross_pay)

            deductions.append({
                "key": "sss",
                "name": "SSS",
                "employee_share": sss,
                "employer_share": 0,
                "editable": True
            })

            deductions.append({
                "key": "philhealth",
                "name": "PhilHealth",
                "employee_share": phic_emp,
                "employer_share": 0,
                "editable": True
            })

            total_deductions += sss + phic_emp
            allowed_loans = ALLOWED_LOAN_1_15

        # ======================================================
        # 16–END HALF
        # ======================================================
        else:
            # ✅ Get SSS from form if editing existing, else from employee record
            sss = safe_float(request.form.get(f"sss_{emp.id}")) if existing_payroll else (getattr(emp, "sss_rss", 0) or 0)
            phic_emp, phic_gov = compute_philhealth(gross_pay)
            
            first_half_period = PayrollPeriod.query.filter(
                extract('month', PayrollPeriod.start_date) == period.start_date.month,
                extract('year', PayrollPeriod.start_date) == period.start_date.year,
                extract('day', PayrollPeriod.start_date) == 1,
                extract('day', PayrollPeriod.end_date) == 15
            ).first()

            previous_payroll = None
            if first_half_period:
                previous_payroll = Payroll.query.filter_by(
                    employee_id=emp.id,
                    payroll_period_id=first_half_period.id
                ).first()

            current_tax = compute_withholding_tax(gross_pay)
            previous_gross = previous_payroll.gross_pay if previous_payroll else 0
            previous_tax = compute_withholding_tax(previous_gross)

            if sss > 0:
                deductions.append({
                    "key": "sss",
                    "name": "SSS",
                    "employee_share": sss,
                    "employer_share": 0,
                    "editable": True
                })
                total_deductions += sss

            if phic_emp > 0:
                deductions.append({
                    "key": "philhealth",
                    "name": "PhilHealth",
                    "employee_share": phic_emp,
                    "employer_share": phic_gov,
                    "editable": False
                })
                total_deductions += phic_emp

            if previous_tax > 0:
                deductions.append({
                    "key": "tax_prev",
                    "name": "Withholding Tax (1–15)",
                    "employee_share": previous_tax,
                    "employer_share": 0,
                    "editable": False
                })
                total_deductions += previous_tax

            if current_tax > 0:
                deductions.append({
                    "key": "tax_curr",
                    "name": "Withholding Tax (16–End)",
                    "employee_share": current_tax,
                    "employer_share": 0,
                    "editable": False
                })
                total_deductions += current_tax

            allowed_loans = ALLOWED_LOAN_16_END

        # ================= LOANS =================
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()

        for loan in loans:
            if loan.provider not in allowed_loans:
                continue

            deductions.append({
                "key": f"loan_{loan.id}",
                "name": f"{loan.provider} - {loan.loan_type}",
                "employee_share": loan.monthly_payment or 0,
                "employer_share": 0,
                "loan_id": loan.id,
                "editable": True
            })
            total_deductions += loan.monthly_payment or 0

        # ✅ BUILD PAYROLL OBJECT WITH OVERTIME
        payroll = Payroll()
        payroll.days_worked = worked_days
        payroll.basic_salary = basic_pay
        payroll.gross_pay = gross_pay

        payroll_data.append({
            "employee": emp,
            "payroll": payroll,
            "deductions": deductions,
            "overtime_pay": overtime_pay
        })
    template = (
        "payroll/staff/jo/16_end_preview.html"
        if second_half else
        "payroll/staff/jo/1_15_preview.html"
    )

    return render_template(
        template,
        period=period,
        department=department,
        payroll_data=payroll_data
    )


# ========================= PROCESS =========================
@payroll_staff_bp.route("/jo/process/<int:period_id>/<int:department_id>", methods=["POST"])
@login_required
@staff_required
def process_jo_payroll(period_id, department_id):

    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == JOB_ORDER_ID
    ).all()

    second_half = is_second_half(period)

    for emp in employees:

        days_worked = safe_float(request.form.get(f"days_worked_{emp.id}"))
        overtime_pay = safe_float(request.form.get(f"overtime_{emp.id}"))
        daily_rate = emp.salary or 0
        basic_pay = days_worked * daily_rate
        gross_pay = basic_pay + overtime_pay


        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            days_worked=days_worked,
            hours_worked=days_worked * 8,
            basic_salary=gross_pay,
            allowance_total=0,
            gross_pay=gross_pay,
            total_deductions=0,
            net_pay=0,
            status="Processed"
        )

        db.session.add(payroll)
        db.session.flush()

        total_deductions = 0

        # ================= 1–15 =================
        if not second_half:

            sss = safe_float(request.form.get(f"sss_{emp.id}"))

            if sss > 0:
                total_deductions += sss
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name="SSS",
                    employee_share=sss
                ))

            phic_emp, phic_gov = compute_philhealth(gross_pay)

            phic_emp = safe_float(request.form.get(f"philhealth_{emp.id}"))  # get submitted/edited value

            if phic_emp > 0:
                total_deductions += phic_emp
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name="PhilHealth",
                    employee_share=phic_emp
                ))
            

            awop = safe_float(request.form.get(f"awop_{emp.id}"))
            if awop > 0:
                total_deductions += awop
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name="Absence Without Pay",
                    employee_share=awop
                ))


            allowed_loans = ALLOWED_LOAN_1_15

        # ================= 16–END =================
        else:

            sss = safe_float(request.form.get(f"sss_{emp.id}"))
            phic_emp, phic_gov = compute_philhealth(gross_pay)

            # 🔍 GET 1–15 PERIOD (same month/year)
            first_half_period = PayrollPeriod.query.filter(
                extract('month', PayrollPeriod.start_date) == period.start_date.month,
                extract('year', PayrollPeriod.start_date) == period.start_date.year,
                extract('day', PayrollPeriod.start_date) == 1,
                extract('day', PayrollPeriod.end_date) == 15
            ).first()

            previous_payroll = None
            if first_half_period:
                previous_payroll = Payroll.query.filter_by(
                    employee_id=emp.id,
                    payroll_period_id=first_half_period.id
                ).first()

            # 🧠 TAX COMPUTATION
            current_tax = compute_withholding_tax(gross_pay)

            previous_gross = previous_payroll.gross_pay if previous_payroll else 0
            previous_tax = compute_withholding_tax(previous_gross)

            # ================= ADD DEDUCTIONS =================

            # SSS
            if sss > 0:
                total_deductions += sss
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name="SSS",
                    employee_share=sss
                ))

            # PHILHEALTH
            if phic_emp > 0:
                total_deductions += phic_emp
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name="PhilHealth",
                    employee_share=phic_emp
                ))

            # TAX (1–15)
            if previous_tax > 0:
                total_deductions += previous_tax
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name="Withholding Tax (1–15)",
                    employee_share=previous_tax
                ))

            # TAX (16–END)
            if current_tax > 0:
                total_deductions += current_tax
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name="Withholding Tax (16–End)",
                    employee_share=current_tax
                ))

            awop = safe_float(request.form.get(f"awop_{emp.id}"))
            if awop > 0:
                total_deductions += awop
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name="Absence Without Pay",
                    employee_share=awop
                ))

            allowed_loans = ALLOWED_LOAN_16_END

        # ================= LOANS =================
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()

        for loan in loans:
            if loan.provider not in allowed_loans:
                continue

            val = safe_float(request.form.get(f"loan_{loan.id}"))

            if val > 0:
                total_deductions += val

                remaining = (loan.remaining_balance or 0) - val
                remaining = max(remaining, 0)
                loan.remaining_balance = remaining  

                db.session.add(LoanPayment(
                    loan_id=loan.id,
                    payroll_id=payroll.id,
                    amount_paid=val
                ))

        # ================= FINAL COMPUTE =================
        payroll.total_deductions = total_deductions
        payroll.net_pay = gross_pay - total_deductions

    db.session.commit()

    flash("JO Payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.jo_select_department", period_id=period.id))