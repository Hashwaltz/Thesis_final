from flask import render_template, request, flash, redirect, url_for,current_app,  jsonify
from flask_login import login_required, current_user
from types import SimpleNamespace
from collections import defaultdict
from datetime import date
from calendar import monthrange, monthcalendar
from flask_mail import Message
import threading
from main_app.extensions import db, mail
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
    # Date Filter (FIXED)
    # ===============================
    today = date.today()
    
    # Option A: Handle combined "YYYY-MM" format from <input type="month">
    month_param = request.args.get("month")  # e.g., "2026-03"
    
    if month_param:
        try:
            year, month = map(int, month_param.split("-"))
            # Validate reasonable range
            if not (2020 <= year <= 2030 and 1 <= month <= 12):
                raise ValueError
        except (ValueError, AttributeError):
            # Fallback to current date if parsing fails
            year, month = today.year, today.month
    else:
        # Fallback: support legacy ?year=XXX&month=XXX params
        year = request.args.get("year", type=int) or today.year
        month = request.args.get("month", type=int) or today.month

    # Correct month overflow (if manually crafted URL)
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

    # 🔐 Verify current password (plain-text comparison)
    if current_password != user.password:
        return jsonify({'status': 'error', 'message': 'Current password is incorrect.'}), 400

    # 📧 Update email if provided
    if new_email and new_email != user.email:
        existing_user = User.query.filter_by(email=new_email).first()
        if existing_user:
            return jsonify({'status': 'error', 'message': 'Email already in use.'}), 400
        user.email = new_email
        if employee:
            employee.email = new_email

    # 🔑 Update password if provided
    password_changed = False
    if new_password:
        if new_password != confirm_password:
            return jsonify({'status': 'error', 'message': 'Passwords do not match.'}), 400
        user.password = new_password  # ✅ Plain text per your request
        password_changed = True

    try:
        db.session.commit()

        # 📬 Send email notification asynchronously if password was changed
        if password_changed and user.email:
            # ✅ Pass actual app instance to avoid context errors in threads
            _send_head_password_notification(current_app._get_current_object(), user)

        return jsonify({'status': 'success', 'message': 'Profile updated successfully.'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating department head profile: {e}")
        return jsonify({'status': 'error', 'message': 'An error occurred. Please try again.'}), 500


# =====================================================
# 📧 EMAIL HELPER FUNCTIONS (Thread-Safe)
# =====================================================
def _send_head_password_notification(app, user):
    """Send password change notification - receives actual Flask app instance"""
    
    def _send_async_email(app_instance, msg):
        """Inner function that runs within proper app context"""
        with app_instance.app_context():
            try:
                mail.send(msg)
                app_instance.logger.info(f"Password notification sent to {user.email}")
            except Exception as e:
                app_instance.logger.error(f"Failed to send email to {user.email}: {str(e)}")
    
    msg = Message(
        subject="🔐 Your Password Has Been Successfully Updated",
        sender=app.config.get("MAIL_DEFAULT_SENDER", "noreply@yourdomain.com"),
        recipients=[user.email]
    )
    msg.body = f"""Hello {user.first_name or 'User'},

Your account password has been successfully updated.

🔑 New Password: {user.password}

⚠️ For your security, please keep this password confidential. If you did not request this change, contact your system administrator immediately.

Regards,
{app.config.get('APP_NAME', 'HR System')} Admin Team
"""
    # ✅ Start background thread with daemon mode and proper args
    thread = threading.Thread(target=_send_async_email, args=(app, msg))
    thread.daemon = True  # Allows app to shut down cleanly even if email is sending
    thread.start()