
from flask import render_template
from flask_login import login_required
from datetime import datetime, timedelta


from main_app.models.hr_models import Leave, Employee
from main_app.helpers.decorators import leave_officer_required
from main_app.helpers.utils import get_current_month_range


from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp

# =========================================================
# LEAVE OFFICER DASHBOARD
# =========================================================
@leave_officer_bp.route("/dashboard")
@login_required
@leave_officer_required
def leave_dashboard():
    today = datetime.now().date()
    current_month_year = datetime.now().strftime("%B %Y")

    # --- LEAVE COUNTS ---
    pending_leaves = Leave.query.filter_by(status="Pending").count()
    approved_leaves = Leave.query.filter_by(status="Approved").count()
    rejected_leaves = Leave.query.filter_by(status="Rejected").count()

    # --- ACTIVE EMPLOYEES ---
    total_active_employees = Employee.query.filter_by(status="Active").count() or 0

    # --- REMINDERS ---
    reminders = []
    if pending_leaves > 0:
        reminders.append(
            f"You have {pending_leaves} pending leave requests to review."
        )

    # --- GRAPH DATA (CURRENT MONTH) ---
    start_date, end_date = get_current_month_range()

    monthly_leave_labels = []
    pending_data = []
    approved_data = []
    rejected_data = []

    current_date = start_date
    while current_date <= end_date:
        monthly_leave_labels.append(current_date.strftime("%b %d"))

        pending_data.append(
            Leave.query.filter(
                Leave.created_at == current_date,
                Leave.status == "Pending"
            ).count()
        )

        approved_data.append(
            Leave.query.filter(
                Leave.created_at == current_date,
                Leave.status == "Approved"
            ).count()
        )

        rejected_data.append(
            Leave.query.filter(
                Leave.created_at == current_date,
                Leave.status == "Rejected"
            ).count()
        )

        current_date += timedelta(days=1)

    return render_template(
        "hr/leave_officer/dashboard.html",
        pending_leaves=pending_leaves,
        approved_leaves=approved_leaves,
        rejected_leaves=rejected_leaves,
        total_users=total_active_employees,
        reminders=reminders,
        current_month_year=current_month_year,

        # GRAPH DATA
        monthly_leave_labels=monthly_leave_labels,
        pending_data=pending_data,
        approved_data=approved_data,
        rejected_data=rejected_data,
    )
