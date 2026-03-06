from flask import request, render_template
from flask_login import login_required
from sqlalchemy import func


from main_app.extensions import db
from main_app.models.hr_models import Department, Leave, LeaveType, Employee
from main_app.helpers.decorators import leave_officer_required


from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp


@leave_officer_bp.route('/leave_report', methods=['GET'])
@login_required
@leave_officer_required

def leave_report():
    # --- Get filters from request ---
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department_id = request.args.get('department_id', type=int)

    # --- Base query for leave records ---
    query = Leave.query.join(Employee).join(Employee.department).join(Leave.leave_type)

    # --- Apply filters ---
    if start_date:
        query = query.filter(Leave.start_date >= start_date)
    if end_date:
        query = query.filter(Leave.end_date <= end_date)
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    leave_data = query.order_by(Leave.start_date.desc()).all()

    # --- Compute insights ---
    total_leaves = len(leave_data)
    avg_days_per_leave = round(sum(lv.days_requested for lv in leave_data) / total_leaves, 2) if total_leaves else 0

    # Most common leave type
    most_common_leave_type = None
    if leave_data:
        leave_type_counts = db.session.query(
            Leave.leave_type_id, func.count(Leave.id)
        ).group_by(Leave.leave_type_id).all()
        if leave_type_counts:
            # Get leave_type_id with max count
            most_common_id = max(leave_type_counts, key=lambda x: x[1])[0]
            most_common_leave_type = LeaveType.query.get(most_common_id).name

    # Department-wise summary
    dept_summary = {}
    departments = Department.query.all()
    for dept in departments:
        dept_leaves = [lv for lv in leave_data if lv.employee.department_id == dept.id]
        total = len(dept_leaves)
        avg_days = round(sum(lv.days_requested for lv in dept_leaves)/total, 2) if total else 0
        dept_summary[dept.name] = {"total": total, "avg_days": avg_days}

    return render_template(
        'hr/leave_officer/leave_report.html',
        leave_data=leave_data,
        start_date=start_date,
        end_date=end_date,
        department_id=department_id,
        total_leaves=total_leaves,
        avg_days_per_leave=avg_days_per_leave,
        most_common_leave_type=most_common_leave_type,
        dept_summary=dept_summary,
        departments=departments
    )

