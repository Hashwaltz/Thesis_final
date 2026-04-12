from flask import Blueprint, render_template, flash, url_for, redirect, request
from flask_login import login_required, current_user
from main_app.models.hr_models import Employee, Attendance, LeaveCredit
from main_app.models.payroll_models import Payslip
from main_app.helpers.decorators import employee_required
from datetime import datetime, timedelta, time  

from main_app.blueprints.employee_system.routes.employee import employee_bp 

def calculate_worked_hours(time_in, time_out, employee_type_id):
    """
    Calculate worked hours based on employee type and work schedule rules.
    """
    if not time_in or not time_out:
        return 0.0
    
    # Only apply special rules to specific employee types
    if employee_type_id not in [1, 3, 5]:
        # ✅ FIX: Convert time objects to datetime before subtracting
        base_date = datetime.min.date()
        dt_in = datetime.combine(base_date, time_in)
        dt_out = datetime.combine(base_date, time_out)
        
        # Handle overnight shifts
        if dt_out < dt_in:
            dt_out += timedelta(days=1)
            
        delta = dt_out - dt_in
        return max(0, delta.total_seconds() / 3600)
    
    # Define schedule boundaries (using dummy date for time comparison)
    base_date = datetime.min.date()
    work_start = datetime.combine(base_date, time(8, 0))
    work_end = datetime.combine(base_date, time(17, 0))
    lunch_start = datetime.combine(base_date, time(12, 0))
    lunch_end = datetime.combine(base_date, time(13, 0))
    
    # Convert time_in/time_out to comparable datetime
    check_in = datetime.combine(base_date, time_in)
    check_out = datetime.combine(base_date, time_out)
    
    # Handle overnight shifts
    if check_out < check_in:
        check_out += timedelta(days=1)
        work_end += timedelta(days=1)
        lunch_start += timedelta(days=1)
        lunch_end += timedelta(days=1)
    
    # Clamp to work schedule window
    effective_in = max(check_in, work_start)
    effective_out = min(check_out, work_end)
    
    # If no overlap with work window, return 0
    if effective_in >= effective_out:
        return 0.0
    
    # Calculate total minutes in window
    total_minutes = (effective_out - effective_in).total_seconds() / 60
    
    # Subtract lunch break if it overlaps with worked time
    lunch_overlap_start = max(effective_in, lunch_start)
    lunch_overlap_end = min(effective_out, lunch_end)
    
    if lunch_overlap_start < lunch_overlap_end:
        lunch_minutes = (lunch_overlap_end - lunch_overlap_start).total_seconds() / 60
        total_minutes -= lunch_minutes
    
    # Convert to hours (rounded to 2 decimals)
    return round(max(0, total_minutes / 60), 2)

# ... (rest of your routes remain exactly the same)


@employee_bp.route('/attendance')
@login_required
@employee_required
def attendance():
    employee = current_user.employee_profile
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('employee_auth_bp.logout'))

    page = request.args.get('page', 1, type=int)
    start_date_str = request.args.get('start_date', '')  # Empty by default
    end_date_str = request.args.get('end_date', '')
    status_filter = request.args.get('status_filter', '')

    # Base query: ALL attendance for this employee
    query = Attendance.query.filter_by(employee_id=employee.id)

    # Apply filters ONLY if values are provided
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date >= start_date)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date <= end_date)
    except ValueError:
        flash('Invalid date format. Use YYYY-MM-DD.', 'error')
        start_date_str = end_date_str = ''  # Reset invalid dates

    if status_filter:
        query = query.filter_by(status=status_filter)

    # Paginate results (always returns something, even if empty)
    attendances = query.order_by(Attendance.date.desc())\
                       .paginate(page=page, per_page=20, error_out=False)

    # Calculate summary stats for CURRENT view (filtered or unfiltered)
    attendance_data = []
    total_hours = 0.0
    
    for att in attendances.items:
        hours = 0.0
        if att.status in ['Present', 'Late', 'Half Day'] and att.time_in and att.time_out:
            hours = calculate_worked_hours(
                att.time_in, 
                att.time_out, 
                employee.employment_type_id  # Updated field name
            )
            total_hours += hours
        attendance_data.append({'record': att, 'worked_hours': hours})
    
    summary = {
        'present': sum(1 for a in attendances.items if a.status == 'Present'),
        'absent': sum(1 for a in attendances.items if a.status == 'Absent'),
        'late': sum(1 for a in attendances.items if a.status == 'Late'),
        'half_day': sum(1 for a in attendances.items if a.status == 'Half Day'),
        'total_hours': round(total_hours, 2)
    }

    return render_template(
        'employee/attendance.html',
        attendances=attendances,
        attendance_data=attendance_data,
        employee=employee,
        start_date_filter=start_date_str,
        end_date_filter=end_date_str,
        status_filter=status_filter,
        summary=summary
    )