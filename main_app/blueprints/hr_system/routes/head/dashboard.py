from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from types import SimpleNamespace
from collections import defaultdict
from datetime import date
from calendar import monthrange, monthcalendar

from main_app.extensions import db
from main_app.models.user import User
from main_app.models.hr_models import Department, Employee, Attendance, Leave
from main_app.helpers.decorators import dept_head_required
from main_app.helpers.utils import get_department_attendance_summary, get_current_month_range

from main_app.blueprints.hr_system.routes.head import hr_head_bp



@hr_head_bp.route('/head-dashboard')
@login_required
@dept_head_required
def dashboard():
    """Department Head Dashboard with Date Picker"""

    from calendar import Calendar, monthrange
    from datetime import date
    from types import SimpleNamespace
    from collections import defaultdict

    # ===============================
    # Determine Department
    # ===============================
    department = None
    if current_user.department_id:
        department = Department.query.get(current_user.department_id)
    else:
        department = Department.query.filter_by(head_id=current_user.id).first()

    if not department:
        return render_template("hr/head/head_dashboard.html", not_assigned=True)

    if not current_user.department_id:
        current_user.department_id = department.id
        db.session.commit()

    # ===============================
    # Load Employees
    # ===============================
    department_employees = Employee.query.filter_by(
        department_id=department.id,
        status="Active",
        archived=False
    ).all()
    total_employees = len(department_employees)

    # ===============================
    # Date Filter
    # ===============================
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month

    # Correct month overflow
    if month > 12:
        month = 1
        year += 1
    elif month < 1:
        month = 12
        year -= 1

    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])
    
    import calendar
    month_name = calendar.month_name[month]

    # ===============================
    # Attendance Query
    # ===============================
    attendances = (
        Attendance.query
        .options(db.joinedload(Attendance.employee))
        .join(Employee)
        .filter(
            Employee.department_id == department.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        )
        .all()
    )

    # Ensure keys match actual status names
    VALID_STATUSES = ["Present", "Absent", "Late", "On Leave"]
    calendar_summary = defaultdict(lambda: {status: 0 for status in VALID_STATUSES})
    attendance_details = defaultdict(list)
    total_present = total_absent = total_late = 0

    for record in attendances:
        status = record.status
        if status not in VALID_STATUSES:
            continue  # ignore unexpected statuses
        date_str = record.date.strftime("%Y-%m-%d")
        calendar_summary[date_str][status] += 1
        attendance_details[date_str].append({
            "name": record.employee.get_full_name(),
            "status": status,
            "time_in": record.time_in.strftime("%I:%M %p") if record.time_in else "-",
            "time_out": record.time_out.strftime("%I:%M %p") if record.time_out else "-"
        })
        if status == "Present": total_present += 1
        elif status == "Absent": total_absent += 1
        elif status == "Late": total_late += 1

    # ===============================
    # Calendar Grid (Sunday first)
    # ===============================
    cal = Calendar(firstweekday=6)  # Sunday start
    month_days = cal.monthdayscalendar(year, month)  # list of weeks

    calendar_days = []
    for week in month_days:
        week_days = []
        for day in week:
            if day == 0:
                week_days.append(None)  # empty cell
            else:
                d = date(year, month, day)
                week_days.append(d.strftime("%Y-%m-%d"))
        calendar_days.append(week_days)

    attendance_summary_obj = SimpleNamespace(
        total_present=total_present,
        total_absent=total_absent,
        total_late=total_late
    )

    # ===============================
    # Recent Leaves
    # ===============================
    recent_leaves = Leave.query.join(Employee).filter(
        Employee.department_id == department.id
    ).order_by(Leave.created_at.desc()).limit(10).all()

    # ===============================
    # Render Template
    # ===============================
    return render_template(
        "hr/head/head_dashboard.html",
        not_assigned=False,
        department=department,
        total_employees=total_employees,
        attendance_summary=attendance_summary_obj,
        calendar_days=calendar_days,
        calendar_summary=dict(calendar_summary),
        attendance_details=dict(attendance_details),
        current_month=month,
        current_year=year,
        month_name=month_name,
        recent_leaves=recent_leaves
    )
   
# ----------------- DEPT HEAD PROFILE + EDIT PASSWORD -----------------
@hr_head_bp.route('/profile', methods=['GET'])
@login_required
@dept_head_required
def profile():
    user = current_user
    employee = user.employee_profile

    # Calculate age and working duration
    age = None
    working_duration = None
    if employee:
        if employee.date_of_birth:
            today = date.today()
            age = today.year - employee.date_of_birth.year - ((today.month, today.day) < (employee.date_of_birth.month, employee.date_of_birth.day))
        working_duration = employee.get_working_duration()

    return render_template(
        'hr/head/profile.html',
        user=user,
        employee=employee,
        age=age,
        working_duration=working_duration
    )


@hr_head_bp.route('/profile/edit', methods=['POST'])
@login_required
@dept_head_required
def edit_profile():
    user = current_user
    employee = user.employee_profile

    data = request.get_json()
    current_password = data.get('current_password')
    new_email = data.get('email')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    # Verify current password
    if current_password != user.password:
        return jsonify({'status': 'error', 'message': 'Current password is incorrect.'}), 400

    # Update email
    if new_email and new_email != user.email:
        existing_user = User.query.filter_by(email=new_email).first()
        if existing_user:
            return jsonify({'status': 'error', 'message': 'Email already in use.'}), 400
        user.email = new_email
        if employee:
            employee.email = new_email

    # Update password
    if new_password:
        if new_password != confirm_password:
            return jsonify({'status': 'error', 'message': 'Passwords do not match.'}), 400
        user.password = new_password  # plain text for now

    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Profile updated successfully.'})