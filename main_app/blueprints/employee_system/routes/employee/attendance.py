
from flask import Blueprint, render_template, flash, url_for, redirect, request
from flask_login import login_required, current_user
from main_app.models.hr_models import Employee, Attendance, LeaveCredit
from main_app.models.payroll_models import Payslip
from main_app.helpers.decorators import employee_required
from datetime import datetime


from main_app.blueprints.employee_system.routes.employee import employee_bp 



# =======================
# ---------------- ATTENDANCE ----------------
@employee_bp.route('/attendance')
@login_required
@employee_required
def attendance():
    
    employee = current_user.employee_profile
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('employee_auth_bp.logout'))

    page = request.args.get('page', 1, type=int)
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    status_filter = request.args.get('status_filter', '')

    query = Attendance.query.filter_by(employee_id=employee.id)

    # Apply date filters
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date >= start_date)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date <= end_date)
    except ValueError:
        flash('Invalid date format. Use YYYY-MM-DD.', 'error')

    # Apply status filter
    if status_filter:
        query = query.filter_by(status=status_filter)

    attendances = query.order_by(Attendance.date.desc())\
                       .paginate(page=page, per_page=20, error_out=False)

    summary = {
        'present': sum(1 for a in attendances.items if a.status == 'Present'),
        'absent': sum(1 for a in attendances.items if a.status == 'Absent'),
        'late': sum(1 for a in attendances.items if a.status == 'Late'),
        'half_day': sum(1 for a in attendances.items if a.status == 'Half Day')
    }

    return render_template(
        'employee/attendance.html',
        attendances=attendances,
        employee=employee,
        start_date_filter=start_date_str,
        end_date_filter=end_date_str,
        status_filter=status_filter,
        summary=summary
    )
