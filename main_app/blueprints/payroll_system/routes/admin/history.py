from main_app.extensions import db
from main_app.utils import payroll_admin_required
from main_app.models.hr_models import Employee, Department, Attendance
from main_app.models.payroll_models import Payroll, PayrollPeriod
from main_app.extensions import db
from main_app.deductions import compute_regular_withholding_tax

from flask_login import login_required
from flask import render_template, redirect, request, flash, url_for
from datetime import datetime, timedelta

from . import payroll_admin_bp




# Employee Payroll History
@payroll_admin_bp.route('/employees/<int:employee_id>/payroll-history')
@payroll_admin_required
@login_required
def view_employee_payroll_history(employee_id):
    # Get employee or return 404
    employee = Employee.query.get_or_404(employee_id)

    # Fetch payroll records for this employee
    payroll_records = (
        Payroll.query.join(Employee, Payroll.employee_id == Employee.id)
        .filter(Employee.id == employee.id)
        .order_by(Payroll.created_at.desc())
        .all()
    )

    return render_template(
        "payroll/admin/payroll_employee_history.html",
        employee=employee,
        payroll_records=payroll_records
    )

@payroll_admin_bp.route('/payroll-periods/<int:period_id>/history')
@payroll_admin_required
@login_required
def payroll_period_history(period_id):
    # Get payroll period or 404
    period = PayrollPeriod.query.get_or_404(period_id)

    # Fetch all payrolls for this period using the correct column
    payroll_records = (
        Payroll.query.join(Employee)
        .filter(Payroll.pay_period_id == period.id)  # <-- corrected
        .order_by(Employee.last_name)
        .all()
    )

    return render_template(
        "payroll/admin/payroll_periods_history.html",
        period=period,
        payroll_records=payroll_records
    )


