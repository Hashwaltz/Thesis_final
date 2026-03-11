from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from types import SimpleNamespace
from collections import defaultdict
from datetime import date
from calendar import monthrange, monthcalendar

from main_app.extensions import db
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
   

# ----------------- EDIT PASSWORD ROUTE FOR DEPT HEAD -----------------
@hr_head_bp.route('/edit_password', methods=['GET', 'POST'])
@login_required
@dept_head_required
def edit_password():
    if request.method == 'POST':
        new_password = request.form.get('password', '').strip()
        if not new_password:
            flash("⚠️ Password cannot be empty.", "warning")
            return redirect(url_for('hr_head_bp.edit_password'))

        # Update password directly (no hashing)
        current_user.password = new_password
        db.session.commit()

        flash("✅ Password successfully updated.", "success")
        return redirect(url_for('hr_head_bp.edit_password'))

    # GET request → show the form
    return render_template('hr/head/edit_profile.html')  # create this template
