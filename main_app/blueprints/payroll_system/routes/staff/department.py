from flask import render_template, request
from flask_login import login_required
from datetime import date
from sqlalchemy.orm import joinedload
from sqlalchemy import asc


from main_app.helpers.decorators import staff_required
from main_app.models.payroll_models import  Payroll, PayrollPeriod
from main_app.models.hr_models import Employee, Department

from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp



@payroll_staff_bp.route("/department/<int:department_id>/employees")
@login_required
@staff_required
def department_employees(department_id):

    today = date.today()

    # ---------- Period Filter ----------

    period_id = request.args.get("period_id", type=int)

    payroll_periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    period = None

    if period_id:
        period = PayrollPeriod.query.get(period_id)

    if not period:
        period = PayrollPeriod.query.filter(
            PayrollPeriod.start_date <= today
        ).order_by(
            PayrollPeriod.start_date.desc()
        ).first()

    if not period and payroll_periods:
        period = payroll_periods[0]

    # ---------- Department ----------

    department = Department.query.get_or_404(department_id)

    # ---------- Employees ----------

    employees = Employee.query.options(
        joinedload(Employee.employment_type),
        joinedload(Employee.position)
    ).filter(
        Employee.department_id == department_id,
        Employee.status == "Active"
    ).order_by(
        asc(Employee.last_name),
        asc(Employee.first_name)
    ).all()

    # ---------- Payroll Optimization (NO N+1 QUERY ⭐)

    payroll_map = {}

    if period and employees:

        payrolls = Payroll.query.filter(
            Payroll.payroll_period_id == period.id,
            Payroll.employee_id.in_([e.id for e in employees])
        ).all()

        payroll_map = {p.employee_id: p for p in payrolls}

    # ---------- Build Employee Rows ----------

    employee_rows = []
    department_total = 0

    for emp in employees:

        payroll = payroll_map.get(emp.id)

        net_pay = payroll.net_pay if payroll else 0
        gross_pay = payroll.gross_pay if payroll else 0
        deductions = payroll.total_deductions if payroll else 0

        department_total += net_pay

        employee_rows.append({
            "name": emp.get_full_name(),
            "email": emp.email,
            "position": emp.position.name if emp.position else "-",
            "employment_type": emp.employment_type.name if emp.employment_type else "Regular",
            "gross": gross_pay,
            "deductions": deductions,
            "net": net_pay
        })

    return render_template(
        "payroll/staff/department/department_employees.html",

        department=department,
        payroll_periods=payroll_periods,
        selected_period=period,

        employee_rows=employee_rows,
        department_total=round(department_total, 2)
    )