from flask import request, render_template
from flask_login import login_required
from datetime import datetime
import calendar


from main_app.extensions import db
from main_app.models.hr_models import Department, Leave, LeaveType, Employee
from main_app.helpers.decorators import leave_officer_required


from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp


@leave_officer_bp.route("/late-computation", methods=["GET"])
@login_required
@leave_officer_required
def late_computation():
    # ----------------------------
    # FILTERS
    # ----------------------------
    month = request.args.get("month", type=int, default=datetime.now().month)
    year = request.args.get("year", type=int, default=datetime.now().year)

    days_in_month = calendar.monthrange(year, month)[1]

    # ----------------------------
    # DATA (replace with real logic)
    # ----------------------------
    employees = Employee.query.all()

    data = []
    for emp in employees:
        row = {
            "employee": emp,
            "total_late_minutes": 0,
            "total_undertime_minutes": 0,
            "days": {}
        }

        # SAMPLE empty day data (prevents template errors)
        for d in range(1, days_in_month + 1):
            row["days"][d] = {
                "time_in": "-",
                "late": "-",
                "time_out": "-",
                "undertime": "-"
            }

        data.append(row)

    # ----------------------------
    return render_template(
        "hr/leave_officer/late_computation.html",
        data=data,
        month=month,
        year=year,
        days_in_month=days_in_month,
        datetime=datetime
    )    
