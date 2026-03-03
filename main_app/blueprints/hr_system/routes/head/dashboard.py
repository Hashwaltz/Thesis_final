from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from types import SimpleNamespace
from collections import defaultdict

from main_app.extensions import db
from main_app.models.hr_models import Department, Employee, Attendance
from main_app.helpers.decorators import dept_head_required
from main_app.helpers.utils import get_department_attendance_summary, get_current_month_range

from main_app.blueprints.hr_system.routes.head import hr_head_bp

@hr_head_bp.route('/head-dashboard')
@login_required
@dept_head_required
def dashboard():
    """Department Head Dashboard"""

    # -----------------------------
    # 1️⃣ Determine Department
    # -----------------------------
    department = None

    if current_user.department_id:
        department = Department.query.get(current_user.department_id)
    else:
        department = Department.query.filter_by(head_id=current_user.id).first()

    if not department:
        return render_template(
            'hr/head/head_dashboard.html',
            not_assigned=True,
            department=None,
            total_employees=0,
            attendance_events=[],
            attendance_details={},
            attendance_summary=SimpleNamespace(
                total_present=0,
                total_absent=0,
                total_late=0
            )
        )

    if not current_user.department_id:
        current_user.department_id = department.id
        db.session.commit()

    # -----------------------------
    # 2️⃣ Employees
    # -----------------------------
    department_employees = Employee.query.filter_by(
        department_id=department.id,
        status="Active",
        archived=False
    ).all()

    total_employees = len(department_employees)

    # -----------------------------
    # 3️⃣ Get Monthly Attendance
    # -----------------------------
    start_date, end_date = get_current_month_range()

    attendances = (
        Attendance.query
        .join(Employee)
        .filter(
            Employee.department_id == department.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        )
        .all()
    )

    attendance_details = defaultdict(list)
    daily_summary = defaultdict(lambda: {"Present": 0, "Absent": 0, "Late": 0})

    total_present = 0
    total_absent = 0
    total_late = 0

    for record in attendances:
        date_str = record.date.strftime("%Y-%m-%d")

        status = record.status
        if status not in ["Present", "Absent", "Late"]:
            continue

        daily_summary[date_str][status] += 1

        if status == "Present":
            total_present += 1
        elif status == "Absent":
            total_absent += 1
        elif status == "Late":
            total_late += 1

        attendance_details[date_str].append({
            "name": record.employee.get_full_name(),
            "status": status,
            "time_in": record.time_in.strftime("%I:%M %p") if record.time_in else None,
            "time_out": record.time_out.strftime("%I:%M %p") if record.time_out else None
        })

    # -----------------------------
    # 4️⃣ Convert to Calendar Events
    # -----------------------------
    attendance_events = []

    for date_str, counts in daily_summary.items():

        total_day = counts["Present"] + counts["Absent"] + counts["Late"]

        # Color priority logic
        if counts["Absent"] > 0:
            color = "#dc2626"
        elif counts["Late"] > 0:
            color = "#f59e0b"
        else:
            color = "#16a34a"

        attendance_events.append({
            "title": f"{counts['Present']}P / {counts['Absent']}A / {counts['Late']}L",
            "start": date_str,
            "color": color
        })

    attendance_summary = SimpleNamespace(
        total_present=total_present,
        total_absent=total_absent,
        total_late=total_late
    )

    return render_template(
        "hr/head/head_dashboard.html",
        not_assigned=False,
        department=department,
        total_employees=total_employees,
        attendance_events=attendance_events,
        attendance_details=dict(attendance_details),
        attendance_summary=attendance_summary
    )





# ----------------- EDIT PASSWORD ROUTE FOR DEPT HEAD -----------------
@hr_head_bp.route('/edit_password', methods=['GET', 'POST'])
@login_required
@dept_head_required
def edit_password():
    if request.method == 'POST':
        new_password = request.form.get('password', '').strip()
        if not new_password:
            flash("⚠️ Password cannot be empty.", "warning")
            return redirect(url_for('dept_head.edit_password'))

        # Update password directly (no hashing)
        current_user.password = new_password
        db.session.commit()

        flash("✅ Password successfully updated.", "success")
        return redirect(url_for('dept_head.edit_password'))

    # GET request → show the form
    return render_template('hr/head/edit_profile.html')  # create this template
