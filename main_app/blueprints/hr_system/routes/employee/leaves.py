from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime

from main_app.helpers.decorators import employee_required
from main_app.models.hr_models import Leave, LeaveType
from main_app.helpers.utils import get_leave_balance, get_attendance_chart_data, get_attendance_summary
from main_app.extensions import db

from main_app.blueprints.hr_system.routes.employee import hr_employee_bp


# ---------------- LEAVES ----------------
@hr_employee_bp.route('/leaves')
@login_required
@employee_required
def leaves():
    employee = current_user.employee_profile
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('hr_auth_bp.logout'))

    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    query = Leave.query.filter_by(employee_id=employee.id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    leaves = query.order_by(Leave.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    leave_balances = {lt: get_leave_balance(employee.id, lt) for lt in
                      ['Sick', 'Vacation', 'Personal', 'Emergency', 'Maternity', 'Paternity']}

    return render_template(
        'hr/employee/employee_leaves.html',
        leaves=leaves,
        employee=employee,
        leave_balances=leave_balances,
        status_filter=status_filter
    )



"""@hr_employee_bp.route('/employee/print_leave_form/<int:leave_id>')
@login_required
@employee_required
def print_leave_form(leave_id):

    leave = Leave.query.get_or_404(leave_id)

    # Security check
    if leave.employee_id != current_user.employee_profile.id and not current_user.is_admin:
        flash("You are not authorized to print this form.", "error")
        return redirect(url_for("employee.leaves"))

    employee = leave.employee

    return generate_leave_print_pdf_route(
        leave,
        employee,
        filename_prefix="CSForm6_Leave"
    )
"""


# ---------------- REQUEST LEAVE ----------------
@hr_employee_bp.route('/employee/request_leave', methods=['GET', 'POST'])
@login_required
@employee_required
def request_leave():
    employee = current_user.employee_profile
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('hr_auth.logout'))

    if request.method == 'POST':
        leave_type_id = request.form.get('leave_type')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        reason = request.form.get('reason')

        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        days_requested = (end_date_obj - start_date_obj).days + 1

        leave = Leave(
            employee_id=employee.id,
            leave_type_id=leave_type_id,
            start_date=start_date_obj,
            end_date=end_date_obj,
            days_requested=days_requested,
            reason=reason,
            status="Pending"
        )
        db.session.add(leave)
        db.session.commit()
        flash("Leave request submitted successfully!", "success")
        return redirect(url_for('hr_employee_bp.leaves'))

    leave_types = LeaveType.query.all()
    return render_template('hr/employee/request_leave.html', leave_types=leave_types)
