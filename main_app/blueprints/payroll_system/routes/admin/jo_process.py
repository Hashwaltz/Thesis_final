from main_app.extensions import db
from main_app.utils import payroll_admin_required
from main_app.models.hr_models import Employee, Department, Attendance, EmploymentType
from main_app.models.payroll_models import Payroll, PayrollPeriod
from main_app.extensions import db
from main_app.deductions import compute_regular_withholding_tax, compute_jo_withholding_tax

from flask_login import login_required
from flask import render_template, redirect, request, flash, url_for, jsonify
from datetime import datetime, timedelta


from . import payroll_admin_bp



JOB_ORDER_ID = 5
@payroll_admin_bp.route("/jo-payroll")
@payroll_admin_required
@login_required
def jo_payroll_page():
    department_id = request.args.get("department_id", type=int)

    query = Employee.query.filter(
        Employee.employment_type_id == JOB_ORDER_ID,
        Employee.status == "Active"
    )

    if department_id:
        query = query.filter(Employee.department_id == department_id)

    employees = query.all()
    payroll_periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    return render_template(
        "payroll/admin/payroll_process/jo_payroll.html",
        employees=employees,
        payroll_periods=payroll_periods
    )

@payroll_admin_bp.route("/jo/worked-days")
@payroll_admin_required
@login_required
def jo_worked_days():
    employee_id = request.args.get("employee_id", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    attendances = Attendance.query.filter(
        Attendance.employee_id == employee_id,
        Attendance.date.between(start, end)
    ).all()

    worked_days = sum(
        1 for a in attendances if a.status in ("Present", "Late")
    )

    total_days = sum(
        1 for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5
    )

    return {
        "worked_days": worked_days,
        "total_working_days": total_days
    }


@payroll_admin_bp.route("/jo-payroll/preview/<int:employee_id>")
@payroll_admin_required
@login_required
def jo_payroll_preview(employee_id):
    period_id = request.args.get("period_id", type=int)
    if not period_id:
        flash("Payroll period is required.", "danger")
        return redirect(request.referrer)

    employee = Employee.query.filter_by(
        id=employee_id,
        employment_type_id=JOB_ORDER_ID,
        status="Active"
    ).first_or_404()

    period = PayrollPeriod.query.get_or_404(period_id)

    # Calculate worked days
    attendances = Attendance.query.filter(
        Attendance.employee_id == employee.id,
        Attendance.date.between(period.start_date, period.end_date)
    ).all()

    worked_days = sum(1 for a in attendances if a.status in ("Present", "Late"))
    total_days = sum(
        1 for i in range((period.end_date - period.start_date).days + 1)
        if (period.start_date + timedelta(days=i)).weekday() < 5
    )

    # Base gross pay
    base_gross_pay = employee.salary * worked_days

    # Employee allowances
    allowance = sum(
        ea.allowance.amount for ea in employee.employee_allowances if ea.allowance.active
    )

    # Employee-specific deductions
    emp_deductions = [
        {
            "id": ed.id,
            "name": ed.deduction.name,
            "amount": ed.calculate(),
            "active": ed.active
        }
        for ed in employee.employee_deductions if ed.active
    ]

    payroll = Payroll.query.filter_by(employee_id=employee.id, payroll_period_id=period.id).first()
    payroll_exists = bool(payroll)

    return render_template(
        "payroll/admin/payroll_process/jo_process.html",
        employee=employee,
        period=period,
        worked_days=worked_days,
        total_days=total_days,
        base_gross_pay=base_gross_pay,
        allowance=allowance,
        employee_deductions=emp_deductions,
        payroll_exists=payroll_exists
    )


@payroll_admin_bp.route("/jo-payroll/save", methods=["POST"])
@payroll_admin_required
@login_required
def jo_payroll_save():
    employee_id = int(request.form["employee_id"])
    period_id = int(request.form["period_id"])
    worked_days = float(request.form["worked_days"])
    daily_rate = float(request.form["daily_rate"])

    # ✅ Compute allowance from EmployeeAllowance table
    employee = Employee.query.get_or_404(employee_id)
    allowance = sum(
        ea.allowance.amount
        for ea in employee.employee_allowances
        if ea.allowance.active
    )

    other_deductions = float(request.form.get("other_deductions", 0))

    exists = Payroll.query.filter_by(
        employee_id=employee_id,
        pay_period_id=period_id
    ).first()

    if exists:
        flash("Payroll already processed.", "warning")
        return redirect(request.referrer)

    period = PayrollPeriod.query.get_or_404(period_id)

    base_gross_pay = daily_rate * worked_days
    gross_pay = base_gross_pay + allowance

    withholding_tax = compute_jo_withholding_tax(gross_pay)
    total_deductions = withholding_tax + other_deductions
    net_pay = gross_pay - total_deductions

    payroll = Payroll(
        employee_id=employee_id,
        pay_period_id=period_id,
        pay_period_start=period.start_date,
        pay_period_end=period.end_date,

        basic_salary=base_gross_pay,
        gross_pay=gross_pay,

        other_deductions=other_deductions,
        tax_withheld=withholding_tax,

        total_deductions=total_deductions,
        net_pay=net_pay,

        status="Draft"
    )

    db.session.add(payroll)
    db.session.commit()

    flash("Job Order payroll successfully processed.", "success")
    return redirect(url_for("payroll_admin.jo_payroll_page"))
