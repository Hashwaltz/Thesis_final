from flask import render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import date, timedelta
import calendar

from main_app.models.hr_models import Employee, LeaveType, LeaveCreditHistory, Attendance
from main_app.extensions import db
from main_app.helpers.decorators import employee_required

from main_app.blueprints.employee_system.routes.employee import employee_bp


# =========================================================
# HELPER: Count worked days
# =========================================================
def count_work_days(employee, year, month):
    """Count worked days including Sat/Sun based on attendance."""

    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    if employee.date_hired > start:
        start = employee.date_hired

    current = start
    worked_days = 0

    while current <= end:

        weekday = current.weekday()

        if weekday in [5, 6]:  # Sat/Sun counted as worked
            worked_days += 1

        else:
            att = Attendance.query.filter_by(
                employee_id=employee.id,
                date=current
            ).first()

            if att and att.status in ["Present", "Late"]:
                worked_days += 1

        current += timedelta(days=1)

    return worked_days, last_day


# =========================================================
# HELPER: Ensure Leave History Exists
# =========================================================
def ensure_leave_history(employee, leave_type, month_label, earned_credit):

    history = LeaveCreditHistory.query.filter_by(
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        month=month_label
    ).first()

    if not history:

        history = LeaveCreditHistory(
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            earned=earned_credit,
            used=0,
            month=month_label
        )

        db.session.add(history)
        db.session.commit()

    return history


# =========================================================
# Employee Leave History Route
# =========================================================
@employee_bp.route("/leave-history")
@login_required
@employee_required
def leave_history():

    employee = current_user.employee_profile

    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('employee_auth_bp.logout'))

    start = employee.date_hired.replace(day=1)
    today = date.today()
    current = start

    leave_types = LeaveType.query.filter(
        LeaveType.name.in_(["Sick Leave", "Vacation Leave"])
    ).all()

    history_data = []

    # Civil Service leave credit table
    CREDITS_TABLE = {
        1: 0.042, 2: 0.083, 3: 0.125, 4: 0.167, 5: 0.208,
        6: 0.250, 7: 0.292, 8: 0.333, 9: 0.375, 10: 0.417,
        11: 0.458, 12: 0.500, 13: 0.542, 14: 0.583, 15: 0.625,
        16: 0.667, 17: 0.708, 18: 0.750, 19: 0.792, 20: 0.833,
        21: 0.875, 22: 0.917, 23: 0.958, 24: 1.000, 25: 1.042,
        26: 1.083, 27: 1.125, 28: 1.167, 29: 1.208, 30: 1.250
    }

    while current <= today:

        month_label = current.strftime("%b %Y")
        year = current.year
        month = current.month

        worked_days, total_days = count_work_days(employee, year, month)

        earned_credit = CREDITS_TABLE.get(worked_days, 0)

        month_record = {
            "month": current.strftime("%B %Y"),
            "worked_days": worked_days,
            "total_days": total_days,
            "leave_data": []
        }

        for leave_type in leave_types:

            history = ensure_leave_history(
                employee,
                leave_type,
                month_label,
                earned_credit
            )

            month_record["leave_data"].append({
                "leave_type": leave_type.name,
                "earned": round(history.earned, 3),
                "used": round(history.used, 3),
                "remaining": round(history.earned - history.used, 3)
            })

        history_data.append(month_record)

        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return render_template(
        "employee/leave_credits.html",
        employee=employee,
        history_data=history_data
    )