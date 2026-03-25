from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user

from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Leave, Employee, LeaveType

from main_app.blueprints.hr_system.routes.admin import hr_admin_bp

# ------------------------- Leaves -------------------------
@hr_admin_bp.route('/leaves')
@admin_required
@login_required
def view_leaves():
    page = request.args.get('page', 1, type=int)

    status_filter = request.args.get('status', '')
    employee_filter = request.args.get('employee', '')
    leave_type_filter = request.args.get('leave_type', '')

    employees = Employee.query.order_by(Employee.last_name.asc()).all()
    leave_types = LeaveType.query.order_by(LeaveType.name.asc()).all()

    query = Leave.query

    if status_filter:
        query = query.filter(Leave.status == status_filter)

    if employee_filter:
        query = query.filter(Leave.employee_id == employee_filter)

    if leave_type_filter:
        query = query.filter(Leave.leave_type_id == leave_type_filter)

    leaves = query.order_by(Leave.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template(
        'hr/admin/leaves/view_leaves.html',
        leaves=leaves,
        employees=employees,
        status_filter=status_filter,
        employee_filter=employee_filter,
        leave_type_filter=leave_type_filter,
        leave_types=leave_types
    )