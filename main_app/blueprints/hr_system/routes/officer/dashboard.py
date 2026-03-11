from flask import render_template, request, current_app, url_for, flash, redirect, jsonify
from flask_sqlalchemy import pagination
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from calendar import month_name

from main_app.extensions import db
from main_app.models.user import User
from main_app.models.hr_models import Attendance, Employee, Leave
from main_app.helpers.decorators import hr_officer_required
from main_app.helpers.utils import get_current_month_range

from main_app.blueprints.hr_system.routes.officer import hr_officer_bp



@hr_officer_bp.route("/officer-dashboard")
@login_required
@hr_officer_required
def hr_dashboard():

    page = request.page = request.args.get("page", 1, type=int)

    employees = Employee.query.paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    today = datetime.now().date()
    now = datetime.now()

    # ============================
    # FILTER MONTH / YEAR
    # ============================

    month = request.args.get("month", now.month, type=int)
    year = request.args.get("year", now.year, type=int)

    # ============================
    # INFO BOX DATA
    # ============================

    today_attendance_records = Attendance.query.filter_by(date=today).all()

    present_count_today = sum(
        1 for r in today_attendance_records if r.status == "Present"
    )

    absent_count_today = sum(
        1 for r in today_attendance_records if r.status == "Absent"
    )

    total_active_employees = Employee.query.filter_by(status="Active").count() or 0

    # ============================
    # CALENDAR ENGINE
    # ============================

    calendar_data = {}

    start_date = datetime(year, month, 1).date()

    # Compute month end
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)

    attendance_records = Attendance.query.filter(
        Attendance.date.between(start_date, end_date)
    ).all()

    # Build calendar aggregation
    for record in attendance_records:

        day = record.date.day

        if day not in calendar_data:
            calendar_data[day] = {
                "present": 0,
                "late": 0,
                "absent": 0,
                "details": []
            }

        status = record.status

        if status == "Present":
            calendar_data[day]["present"] += 1
        elif status == "Late":
            calendar_data[day]["late"] += 1
        elif status == "Absent":
            calendar_data[day]["absent"] += 1

        # Optional detail list (for modal zoom)
        employee = record.employee

        time_value = getattr(record, "time_in", None)

        if hasattr(time_value, "strftime"):
            time_value = time_value.strftime("%H:%M:%S")
        else:
            time_value = str(time_value) if time_value else ""

        calendar_data[day]["details"].append({
            "name": employee.get_full_name() if employee else "",
            "status": status,
            "time": time_value
        })

    # ============================
    # REMINDERS
    # ============================

    reminders = []

    pending_leaves_count = Leave.query.filter_by(status="Pending").count()

    if pending_leaves_count > 0:
        reminders.append(
            f"You have {pending_leaves_count} pending leave requests."
        )


    month = request.args.get("month", datetime.now().month, type=int)
    year = request.args.get("year", datetime.now().year, type=int)

    current_month_year = f"{month_name[month]} {year}"
    # ============================
    # TEMPLATE RENDER
    # ============================

    return render_template(
        "hr/officer/officer_dashboard.html",

        present_count=present_count_today,
        absent_count=absent_count_today,
        total_users=total_active_employees,

        employees=employees,

        calendar_data=calendar_data,

        current_month=month,
        current_year=year,
        current_month_year=current_month_year,

        reminders=reminders
    )

@hr_officer_bp.route('/profile', methods=['GET'])
@login_required
@hr_officer_required
def profile():
    user = current_user
    employee = user.employee_profile

    age = None
    working_duration = None
    if employee:
        if employee.date_of_birth:
            today = date.today()
            age = today.year - employee.date_of_birth.year - ((today.month, today.day) < (employee.date_of_birth.month, employee.date_of_birth.day))
        working_duration = employee.get_working_duration()

    return render_template(
        "hr/officer/profile.html",
        user=user,
        employee=employee,
        age=age,
        working_duration=working_duration
    )


@hr_officer_bp.route('/profile/edit', methods=['POST'])
@login_required
@hr_officer_required
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

    try:
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Profile updated successfully.'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating officer profile: {e}")
        return jsonify({'status': 'error', 'message': 'An error occurred. Please try again.'}), 500