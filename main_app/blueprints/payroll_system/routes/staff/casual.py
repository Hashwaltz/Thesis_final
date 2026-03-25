from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance, LeaveCredit, Department
from main_app.models.payroll_models import Payroll, PayrollPeriod, Loan, PayrollDeduction, LoanPayment

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

CASUAL_ID = 3

ALLOWED_LOAN_PROVIDERS_1_15 = {"GSIS", "MENPC"}
ALLOWED_LOAN_PROVIDERS_16_31 = {"MENPC", "Pag-IBIG", "SSS"}


# ========================= HELPERS =========================

def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def is_second_half(period):
    return period.start_date.day >= 16


def compute_philhealth(gross_pay):
    if gross_pay <= 10000:
        return 250, 250
    total = round(gross_pay * 0.05, 2)
    return round(total / 2, 2), round(total / 2, 2)


def compute_sss_monthly(emp, monthly_salary):
    # SIMPLE LOGIC (you can replace with bracket later)
    total = monthly_salary * 0.045
    return round(total / 2, 2), round(total / 2, 2)


def compute_pagibig(monthly_salary):
    if monthly_salary <= 1500:
        rate = 0.01
    else:
        rate = 0.02

    employee = monthly_salary * rate
    employer = monthly_salary * rate

    # CAP RULE
    employee = min(employee, 200)
    employer = min(employer, 200)

    return round(employee, 2), round(employer, 2)


def resolve_pagibig(monthly_salary, form_value):
    computed_emp, _ = compute_pagibig(monthly_salary)

    if form_value is None:
        return computed_emp

    value_str = str(form_value).strip()

    # IMPORTANT: allow explicit 0
    if value_str == "":
        return computed_emp

    value = safe_float(value_str)

    # if user explicitly enters 0 → keep it 0
    if value == 0:
        return 0

    # safety cap
    return min(value, computed_emp * 1.5)

@payroll_staff_bp.route("/select-department/<int:period_id>") 
@login_required 
@staff_required 
def select_department(period_id): 
    period = PayrollPeriod.query.get_or_404(period_id)
    departments = Department.query.order_by(Department.name).all()

    department_status = {}

    for dept in departments:
        has_payroll = Payroll.query.join(Employee).filter(
            Payroll.payroll_period_id == period.id,
            Employee.department_id == dept.id
        ).first()

        department_status[dept.id] = bool(has_payroll)

    return render_template(
        "payroll/staff/casual/select_department.html",
        period=period,
        departments=departments,
        department_status=department_status
    )

# ========================= PREVIEW =========================

@payroll_staff_bp.route("/preview/<int:period_id>/<int:department_id>")
@login_required
@staff_required
def preview_department_payroll(period_id, department_id):

    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    if period.status == "Locked":
        flash("Payroll already processed for this period.", "warning")
        return redirect(url_for("payroll_staff_bp.select_department", period_id=period.id))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == CASUAL_ID
    ).all()

    payroll_data = []
    second_half = is_second_half(period)

    for emp in employees:

        payroll = Payroll()
        deduction_total = 0
        # ATTENDANCE
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date.between(period.start_date, period.end_date)
        ).all()

        days_worked = sum(1 for a in attendances if a.status in ("Present", "Late"))

        leave_credits = LeaveCredit.query.filter_by(employee_id=emp.id).all()
        leave_used = sum(lc.used_credits for lc in leave_credits)

        days_worked = max(days_worked - leave_used, 0)

        # PAY
        daily_rate = emp.salary or 0
        basic_pay = days_worked * daily_rate
        allowance_total = sum(a.amount for a in (getattr(emp, "allowances", []) or []))
        gross_pay = basic_pay + allowance_total

        deductions = []

        # ================= FIRST HALF =================
        if not second_half:

            # SSS
            deductions.append({
                "key": "sss",
                "name": "SSS",
                "employee_share": safe_float(getattr(emp, "sss_rss", 0)),
                "employer_share": 0,
                "editable": True
            })

            # PHILHEALTH
            phic_emp, phic_gov = compute_philhealth(gross_pay)

            deductions.append({
                "key": "philhealth",
                "name": "PhilHealth",
                "employee_share": phic_emp,
                "employer_share": phic_gov,
                "editable": True,
                "gov_visible": True
            })

            allowed = ALLOWED_LOAN_PROVIDERS_1_15

        # ================= SECOND HALF =================
        else:
            computed_sss = safe_float(getattr(emp, "sss_rss", 0))

            deductions.append({
                "key": "sss",
                "name": "SSS",
                "employee_share": computed_sss,
                "employer_share": 0,
                "editable": True
            })

            deduction_total += computed_sss
                    

            # OPTIONAL SAFETY: recompute server-side (recommended)
            computed_pagibig_emp, _ = compute_pagibig(gross_pay*2)

            # clamp to avoid abuse
            deductions.append({
                "key": "pagibig",
                "name": "Pag-IBIG",
                "employee_share": computed_pagibig_emp,  # default shown in input
                "employer_share": 0,
                "editable": True
            })

            deduction_total+= computed_pagibig_emp

            allowed = ALLOWED_LOAN_PROVIDERS_16_31

        # LOANS
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()

        for loan in loans:
            if loan.provider not in allowed:
                continue

            deductions.append({
                "key": f"loan_{loan.id}",
                "name": f"{loan.provider} - {loan.loan_type}",
                "employee_share": loan.monthly_payment or 0,
                "employer_share": 0,
                "loan_id": loan.id,
                "editable": True
            })

        payroll.days_worked = days_worked
        payroll.basic_salary = basic_pay
        payroll.allowance_total = allowance_total
        payroll.gross_pay = gross_pay

        payroll_data.append({
            "employee": emp,
            "payroll": payroll,
            "deductions": deductions
        })

    # TEMPLATE SWITCH
    template = "payroll/staff/casual/16-31_preview.html" if second_half else "payroll/staff/casual/1-15_preview.html"

    return render_template(
        template,
        period=period,
        department=department,
        payroll_data=payroll_data
    )





# ========================= PROCESS =========================

@payroll_staff_bp.route("/process/<int:period_id>/<int:department_id>", methods=["POST"])
@login_required
@staff_required
def process_department_payroll(period_id, department_id):

    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == CASUAL_ID
    ).all()

    second_half = is_second_half(period)

    for emp in employees:

        days_worked = safe_float(request.form.get(f"days_worked_{emp.id}"))
        allowance_total = safe_float(request.form.get(f"allowance_total_{emp.id}"))

        daily_rate = emp.salary or 0
        basic_pay = days_worked * daily_rate
        gross_pay = basic_pay + allowance_total

        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            days_worked=days_worked,
            hours_worked=days_worked * 8,
            basic_salary=basic_pay,
            allowance_total=allowance_total,
            gross_pay=gross_pay,
            total_deductions=0,
            net_pay=0,
            status="Processed"
        )

        db.session.add(payroll)
        db.session.flush()

        deduction_total = 0

        # ================= FIRST HALF =================
        if not second_half:

            sss = safe_float(request.form.get(f"sss_{emp.id}"))
            deduction_total += sss

            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name="SSS",
                employee_share=sss
            ))

            phic = safe_float(request.form.get(f"philhealth_{emp.id}"))
            deduction_total += phic

            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name="PhilHealth",
                employee_share=phic
            ))

            allowed = ALLOWED_LOAN_PROVIDERS_1_15

        # ================= SECOND HALF =================
        else:

            sss = safe_float(request.form.get(f"sss_{emp.id}"))
            deduction_total += sss

            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name="SSS",
                employee_share=sss
            ))

            pagibig_input = request.form.get(f"pagibig_{emp.id}")

            pagibig = resolve_pagibig(gross_pay*2, pagibig_input)

            deduction_total += pagibig

            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name="Pag-IBIG",
                employee_share=pagibig
            ))

            allowed = ALLOWED_LOAN_PROVIDERS_16_31

        # LOANS
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()

        for loan in loans:
            if loan.provider not in allowed:
                continue

            val = safe_float(request.form.get(f"loan_{loan.id}"))

            deduction_total += val

            db.session.add(LoanPayment(
                loan_id=loan.id,
                payroll_id=payroll.id,
                amount_paid=val,
                remaining_balance=(loan.remaining_balance or 0) - val
            ))

        payroll.total_deductions = deduction_total
        payroll.net_pay = gross_pay - deduction_total

    db.session.commit()

    flash(f"Payroll processed for {department.name} successfully.", "success")
    return redirect(url_for("payroll_staff_bp.select_department", period_id=period.id))