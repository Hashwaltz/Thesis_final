from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance, LeaveCredit, Department
from main_app.models.payroll_models import Payroll, PayrollPeriod, Loan, PayrollDeduction

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

REGULAR_ID = 1


# ========================= HELPERS =========================

def safe_float(value):
    try:
        return float(value)
    except:
        return 0.0


def compute_ctw(gross, is_daily):
    return gross * (0.05 if is_daily else 0.10)


def compute_gmp_pt(gross):
    return gross * 0.02



@payroll_staff_bp.route("/regular/select-department/<int:period_id>")
@login_required
@staff_required
def regular_select_department(period_id):

    period = PayrollPeriod.query.get_or_404(period_id)
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "payroll/staff/regular/select_department.html",
        period=period,
        departments=departments
    )



@payroll_staff_bp.route("/regular/preview/<int:period_id>/<int:department_id>")
@login_required
@staff_required
def preview_regular_payroll(period_id, department_id):

    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    if period.status == "Locked":
        flash("Payroll already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.regular_select_department", period_id=period.id))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == REGULAR_ID
    ).all()

    payroll_data = []

    for emp in employees:

        leave_used = sum(lc.used_credits for lc in LeaveCredit.query.filter_by(employee_id=emp.id))

        worked_days = max(22 - leave_used, 0)

        monthly_salary = emp.salary or 0
        daily_rate = monthly_salary / 22

        basic_pay = daily_rate * worked_days

        allowance_total = sum(a.amount for a in getattr(emp, "employee_allowances", []))

        gross_pay = basic_pay + allowance_total

        # Adjustment (1–15 cutoff earnings)
        adjustment_pay = 0

        # ================= DEDUCTIONS =================
        deductions = []

        # Editable GOV deductions
        deductions.append({"key": "sss", "name": "SSS", "employee_share": 0, "editable": True})
        deductions.append({"key": "philhealth", "name": "PhilHealth", "employee_share": 0, "editable": True})
        deductions.append({"key": "pagibig", "name": "Pag-IBIG", "employee_share": 0, "editable": True})
        deductions.append({"key": "gsis", "name": "GSIS", "employee_share": 0, "editable": True})

        # Loans
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()
        for loan in loans:
            deductions.append({
                "key": f"loan_{loan.id}",
                "name": f"{loan.provider} - {loan.loan_type}",
                "employee_share": loan.monthly_payment or 0,
                "editable": True,
                "loan_id": loan.id
            })

        payroll_data.append({
            "employee": emp,
            "days_worked": worked_days,
            "basic_pay": basic_pay,
            "allowance_total": allowance_total,
            "gross_pay": gross_pay,
            "adjustment_pay": adjustment_pay,
            "deductions": deductions
        })

    return render_template(
        "payroll/staff/regular/payroll_preview.html",
        period=period,
        department=department,
        payroll_data=payroll_data
    )


@payroll_staff_bp.route("/regular/process/<int:period_id>/<int:department_id>", methods=["POST"])
@login_required
@staff_required
def process_regular_payroll(period_id, department_id):

    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == REGULAR_ID
    ).all()

    for emp in employees:

        leave_used = sum(lc.used_credits for lc in LeaveCredit.query.filter_by(employee_id=emp.id))
        worked_days = max(22 - leave_used, 0)

        monthly_salary = emp.salary or 0
        daily_rate = monthly_salary / 22

        basic_pay = daily_rate * worked_days

        allowance_total = safe_float(request.form.get(f"allowance_{emp.id}", 0))
        adjustment_pay = safe_float(request.form.get(f"adjustment_{emp.id}", 0))

        gross_pay = basic_pay + allowance_total + adjustment_pay

        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            days_worked=worked_days,
            basic_salary=basic_pay,
            allowance_total=allowance_total,
            gross_pay=gross_pay,
            status="Processed"
        )

        db.session.add(payroll)
        db.session.flush()

        total_deductions = 0

        # ================= GOV DEDUCTIONS =================

        sss = safe_float(request.form.get(f"sss_{emp.id}"))
        philhealth = safe_float(request.form.get(f"philhealth_{emp.id}"))
        pagibig = safe_float(request.form.get(f"pagibig_{emp.id}"))
        gsis = safe_float(request.form.get(f"gsis_{emp.id}"))

        total_deductions += sss + philhealth + pagibig + gsis

        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="SSS", employee_share=sss))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="PhilHealth", employee_share=philhealth))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="Pag-IBIG", employee_share=pagibig))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="GSIS", employee_share=gsis))

        # ================= TAXES =================

        is_daily_tax = request.form.get(f"ctw_{emp.id}") == "on"

        ctw_tax = compute_ctw(gross_pay, is_daily_tax)
        gmp_pt_tax = compute_gmp_pt(gross_pay)

        total_deductions += ctw_tax + gmp_pt_tax

        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="CTW Tax", employee_share=ctw_tax))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="GMP-PT", employee_share=gmp_pt_tax))

        # ================= LOANS =================

        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()

        for loan in loans:
            val = safe_float(request.form.get(f"loan_{loan.id}", 0))
            total_deductions += val

            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name=f"{loan.provider} Loan",
                employee_share=val
            ))

        # ================= FINAL =================

        payroll.total_deductions = total_deductions
        payroll.net_pay = gross_pay - total_deductions



    db.session.commit()

    flash("Regular payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.view_payrolls"))