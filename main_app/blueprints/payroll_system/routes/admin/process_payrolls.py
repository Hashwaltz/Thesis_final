
from main_app.models.hr_models import Employee, Department, Attendance
from main_app.models.payroll_models import Payroll, PayrollPeriod
from main_app.utils import payroll_admin_required
from main_app.extensions import db
from main_app.deductions import compute_regular_withholding_tax

from flask import render_template, request, url_for, flash, redirect
from flask_login import login_required
from sqlalchemy import asc
from datetime import datetime, timedelta

from . import payroll_admin_bp



@payroll_admin_bp.route('/department/<int:department_id>/employees')
@payroll_admin_required
@login_required
def department_employees(department_id):
    department = Department.query.get_or_404(department_id)
    
    # Correct query
    employees = Employee.query.filter_by(
        status="Active",
        department_id=department_id
    ).order_by(
        asc(Employee.last_name), asc(Employee.first_name)
    ).all()

    return render_template(
        'payroll/admin/payroll_process/employee_list.html',
        employees=employees,
        department=department
    )


