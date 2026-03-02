from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from types import SimpleNamespace

from main_app.extensions import db
from main_app.models.hr_models import Department, Employee, Leave
from main_app.helpers.decorators import dept_head_required
from main_app.helpers.utils import get_department_attendance_summary, get_current_month_range

from main_app.blueprints.hr_system.routes.head import hr_head_bp


@hr_head_bp.route('/head-dashboard')
@login_required
@dept_head_required
def dashboard():
    """Department Head Dashboard"""

    # Determine department
    department = None
    if current_user.department_id:
        department = Department.query.get(current_user.department_id)
    else:
        department = Department.query.filter_by(head_id=current_user.id).first()

    # Not assigned yet
    if not department:
        return render_template(
            'hr/head/head_dashboard.html',
            not_assigned=True,
            department=None,
            total_employees=0,
            recent_leaves=[],
            attendance_summary=SimpleNamespace(
                total_present=0,
                total_absent=0,
                total_late=0,
                dates=[],
                present_counts=[],
                absent_counts=[],
                late_counts=[]
            ),
            reminders=[],
            notes=[]
        )

    # Update user's department_id if missing
    if not current_user.department_id:
        current_user.department_id = department.id
        db.session.commit()

    # Employees
    department_employees = Employee.query.filter_by(department_id=department.id, status="Active").all()
    total_employees = len(department_employees)

    # Recent leaves (with employee relationship loaded)
    recent_leaves = (
        Leave.query
        .join(Employee)
        .options(db.joinedload(Leave.employee))
        .filter(Employee.department_id == department.id)
        .order_by(Leave.created_at.desc())
        .limit(5)
        .all()
    )

    # Attendance summary
    start_date, end_date = get_current_month_range()
    summary_raw = get_department_attendance_summary(department.id, start_date, end_date)

    attendance_summary = SimpleNamespace(
        total_present=summary_raw.get('total_present', 0),
        total_absent=summary_raw.get('total_absent', 0),
        total_late=summary_raw.get('total_late', 0),
        dates=[d.strftime("%Y-%m-%d") for d in summary_raw.get('dates', [])],
        present_counts=list(summary_raw.get('present_counts', [])),
        absent_counts=list(summary_raw.get('absent_counts', [])),
        late_counts=list(summary_raw.get('late_counts', []))
    )

    # Dummy reminders and notes
    reminders = ["Submit monthly report", "Approve leave requests"]
    notes = ["Team meeting on Friday", "Prepare onboarding documents"]

    return render_template(
        'hr/head/head_dashboard.html',
        not_assigned=False,
        department=department,
        total_employees=total_employees,
        recent_leaves=recent_leaves,
        attendance_summary=attendance_summary,
        reminders=reminders,
        notes=notes
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
