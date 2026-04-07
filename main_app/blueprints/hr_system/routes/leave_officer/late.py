from flask import request, render_template
from flask_login import login_required
from datetime import datetime, time, date
import calendar

from main_app.extensions import db
from main_app.models.hr_models import Employee
from main_app.helpers.decorators import leave_officer_required
from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp

HOUR_TO_DAY = 0.125
MINUTE_TO_DAY = 0.002


@leave_officer_bp.route("/late-computation", methods=["GET"])
@login_required
@leave_officer_required
def late_computation():
    month = request.args.get("month", type=int, default=datetime.now().month)
    year = request.args.get("year", type=int, default=datetime.now().year)
    days_in_month = calendar.monthrange(year, month)[1]
    
    # Employee search filter
    employee_search = request.args.get("employee_search", type=str, default="").strip()
    
    # Filter employees by search query if provided
    employees_query = Employee.query
    if employee_search:
        employees_query = employees_query.filter(
            db.or_(
                Employee.first_name.ilike(f"%{employee_search}%"),
                Employee.last_name.ilike(f"%{employee_search}%"),
                Employee.middle_name.ilike(f"%{employee_search}%") if hasattr(Employee, 'middle_name') else False
            )
        )
    employees = employees_query.order_by(Employee.last_name).all()
    
    selected_employee_id = request.args.get("employee_id", type=int)

    summary = {}
    data = []

    month_names = [
        "January","February","March","April","May","June",
        "July","August","September","October","November","December"
    ]
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # 8-hour workday in seconds
    SECONDS_PER_DAY = 480 * 60  # 28800
    SEC_TO_DAY_RATE = MINUTE_TO_DAY / 60.0

    if selected_employee_id:
        emp = Employee.query.get(selected_employee_id)
        if emp:
            attendances = {
                att.date.day: att for att in emp.attendances
                if att.date.month == month and att.date.year == year
            }

            total_late_seconds = 0.0
            total_undertime_seconds = 0.0
            row_days = {}

            for d in range(1, days_in_month + 1):
                att = attendances.get(d)
                late_seconds = 0.0
                undertime_seconds = 0.0

                current_date = date(year, month, d)
                weekday_name = weekdays[current_date.weekday()]

                time_in_str = "-"
                time_out_str = "-"

                if att:
                    # Late calculation (after 8:00 AM)
                    if att.time_in and att.time_in > time(8, 0):
                        late_seconds = (datetime.combine(att.date, att.time_in) -
                                        datetime.combine(att.date, time(8,0))).total_seconds()
                        if late_seconds < 0: late_seconds = 0.0

                    if att.time_in:
                        time_in_str = att.time_in.strftime("%H:%M:%S")

                    # Undertime calculation (before 5:00 PM)
                    if att.time_out and att.time_out < time(17, 0):
                        undertime_seconds = (datetime.combine(att.date, time(17,0)) -
                                             datetime.combine(att.date, att.time_out)).total_seconds()
                        if undertime_seconds < 0: undertime_seconds = 0.0

                    if att.time_out:
                        time_out_str = att.time_out.strftime("%H:%M:%S")

                    total_late_seconds += late_seconds
                    total_undertime_seconds += undertime_seconds

                # Store for calendar (display in minutes)
                row_days[d] = {
                    "time_in": time_in_str,
                    "late": round(late_seconds / 60, 2),
                    "time_out": time_out_str,
                    "undertime": round(undertime_seconds / 60, 2),
                    "weekday": weekday_name
                }

            # Overall calculation (preserves seconds)
            overall_seconds = total_late_seconds + total_undertime_seconds
            overall_mins = int(overall_seconds // 60)
            overall_secs = int(round(overall_seconds % 60))

            # Prepare summary cards
            summary = {
                "total_late_minutes": round(total_late_seconds / 60, 2),
                "days_late": round(total_late_seconds / SECONDS_PER_DAY, 2),
                "late_deduction": round(total_late_seconds * SEC_TO_DAY_RATE, 2),
                
                "total_undertime_minutes": round(total_undertime_seconds / 60, 2),
                "days_undertime": round(total_undertime_seconds / SECONDS_PER_DAY, 2),
                "undertime_deduction": round(total_undertime_seconds * SEC_TO_DAY_RATE, 2),
                
                "overall_time_str": f"{overall_mins} min {overall_secs} sec",
                "overall_minutes": round(overall_seconds / 60, 2),
                "overall_days": round(overall_seconds / SECONDS_PER_DAY, 2),
                "overall_deduction": round(overall_seconds * SEC_TO_DAY_RATE, 2)
            }

            data.append({
                "employee": emp,
                "days": row_days
            })

    return render_template(
        "hr/leave_officer/late_computation.html",
        employees=employees,
        selected_employee_id=selected_employee_id,
        employee_search=employee_search,  # Pass search term to template
        month=month,
        year=year,
        days_in_month=days_in_month,
        summary=summary,
        data=data,
        month_names=month_names
    )