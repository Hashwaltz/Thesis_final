from flask import request, render_template
from flask_login import login_required
from datetime import datetime, time, date
import calendar

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance
from main_app.helpers.decorators import leave_officer_required
from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp

HOUR_TO_DAY = 0.125
MINUTE_TO_DAY = 0.002

@leave_officer_bp.route("/late-computation", methods=["GET"])
@login_required
@leave_officer_required
def late_computation():
    # ---------------- FILTERS ----------------
    month = request.args.get("month", type=int, default=datetime.now().month)
    year = request.args.get("year", type=int, default=datetime.now().year)
    days_in_month = calendar.monthrange(year, month)[1]

    employees = Employee.query.order_by(Employee.last_name).all()
    selected_employee_id = request.args.get("employee_id", type=int)

    summary = {}
    data = []

    month_names = [
        "January","February","March","April","May","June",
        "July","August","September","October","November","December"
    ]
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    if selected_employee_id:
        emp = Employee.query.get(selected_employee_id)
        if emp:
            # Filter attendances for selected month/year
            attendances = {
                att.date.day: att for att in emp.attendances
                if att.date.month == month and att.date.year == year
            }

            total_late_minutes = 0
            total_undertime_minutes = 0
            row_days = {}

            for d in range(1, days_in_month + 1):
                att = attendances.get(d)
                late_minutes = 0
                undertime_minutes = 0

                current_date = date(year, month, d)
                weekday_name = weekdays[current_date.weekday()]

                # Default strings
                time_in_str = "-"
                time_out_str = "-"

                if att:
                    # Late calculation (after 8:00 AM)
                    if att.time_in and att.time_in > time(8, 0):
                        late_minutes = int(
                            (datetime.combine(att.date, att.time_in) -
                             datetime.combine(att.date, time(8,0))).total_seconds() / 60
                        )
                    if att.time_in:
                        time_in_str = att.time_in.strftime("%H:%M:%S")

                    # Undertime calculation (before 5:00 PM)
                    if att.time_out and att.time_out < time(17, 0):
                        undertime_minutes = int(
                            (datetime.combine(att.date, time(17,0)) -
                             datetime.combine(att.date, att.time_out)).total_seconds() / 60
                        )
                    if att.time_out:
                        time_out_str = att.time_out.strftime("%H:%M:%S")

                    total_late_minutes += late_minutes
                    total_undertime_minutes += undertime_minutes

                row_days[d] = {
                    "time_in": time_in_str,
                    "late": late_minutes,
                    "time_out": time_out_str,
                    "undertime": undertime_minutes,
                    "weekday": weekday_name
                }

            # Prepare summary cards
            summary = {
                "total_late_minutes": total_late_minutes,
                "days_late": round(total_late_minutes / 480, 2),
                "late_deduction": round(total_late_minutes * MINUTE_TO_DAY, 2),
                "total_undertime_minutes": total_undertime_minutes,
                "days_undertime": round(total_undertime_minutes / 480, 2),
                "undertime_deduction": round(total_undertime_minutes * MINUTE_TO_DAY, 2),
                "overall_minutes": total_late_minutes + total_undertime_minutes,
                "overall_days": round((total_late_minutes + total_undertime_minutes)/480, 2),
                "overall_deduction": round((total_late_minutes + total_undertime_minutes)*MINUTE_TO_DAY, 2)
            }

            data.append({
                "employee": emp,
                "days": row_days
            })

    return render_template(
        "hr/leave_officer/late_computation.html",
        employees=employees,
        selected_employee_id=selected_employee_id,
        month=month,
        year=year,
        days_in_month=days_in_month,
        summary=summary,
        data=data,
        month_names=month_names
    )