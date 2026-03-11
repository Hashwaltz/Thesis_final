from flask import render_template, request
from flask_login import login_required
from sqlalchemy import asc
from sqlalchemy.orm import joinedload
from datetime import date

from main_app.models.hr_models import Employee, Department, Attendance
from main_app.models.payroll_models import Payroll, PayrollPeriod
from main_app.helpers.decorators import payroll_admin_required



from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp



@payroll_admin_bp.route('/department/<int:department_id>/employees')
@payroll_admin_required
@login_required
def department_employees(department_id):

    today = date.today()

    # ---------- Period Filter ----------
    period_id = request.args.get("period_id", type=int)

    payroll_periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    # Default period = latest period near today
    if period_id:
        period = PayrollPeriod.query.get(period_id)
    else:
        period = PayrollPeriod.query.filter(
            PayrollPeriod.start_date <= today
        ).order_by(
            PayrollPeriod.start_date.desc()
        ).first()

    if not period and payroll_periods:
        period = payroll_periods[0]

    # ---------- Department ----------
    department = Department.query.get_or_404(department_id)

    # ---------- Employees in Department ----------
    employees = Employee.query.options(
        joinedload(Employee.employment_type),
        joinedload(Employee.department)
    ).filter(
        Employee.department_id == department_id,
        Employee.status == "Active"
    ).order_by(
        asc(Employee.last_name),
        asc(Employee.first_name)
    ).all()

    # ---------- Payroll Computation ----------
    employee_rows = []
    department_total = 0

    for emp in employees:

        payroll = Payroll.query.filter_by(
            employee_id=emp.id,
            payroll_period_id=period.id
        ).first()

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
        "payroll/admin/department/department_employees.html",

        department=department,
        payroll_periods=payroll_periods,
        selected_period=period,

        employee_rows=employee_rows,
        department_total=round(department_total, 2)
    )