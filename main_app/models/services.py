# main_app/helpers/leave_utils.py
from datetime import date, timedelta
import calendar

from main_app.extensions import db
from main_app.models.hr_models import (
    Employee,
    Attendance,
    LeaveType,
    LeaveCredit,
    LeaveCreditHistory
)

# ======================================================
# CREDIT BRACKET TABLE (CSC STANDARD)
# ======================================================
CREDITS_TABLE = {
    1: 0.042, 2: 0.083, 3: 0.125, 4: 0.167, 5: 0.208,
    6: 0.250, 7: 0.292, 8: 0.333, 9: 0.375, 10: 0.417,
    11: 0.458, 12: 0.500, 13: 0.542, 14: 0.583, 15: 0.625,
    16: 0.667, 17: 0.708, 18: 0.750, 19: 0.792, 20: 0.833,
    21: 0.875, 22: 0.917, 23: 0.958, 24: 1.000, 25: 1.042,
    26: 1.083, 27: 1.125, 28: 1.167, 29: 1.208, 30: 1.250
}


# ======================================================
# COUNT WORKED DAYS BASED ON ATTENDANCE
# ======================================================
def count_work_days(employee, year, month):
    """Count workdays in month including Sat/Sun and attendance."""
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    if employee.date_hired > start:
        start = employee.date_hired

    worked_days = 0
    current = start

    while current <= end:
        weekday = current.weekday()
        if weekday in [5, 6]:
            worked_days += 1
        else:
            attendance = Attendance.query.filter_by(
                employee_id=employee.id,
                date=current
            ).first()
            if attendance and attendance.status in ["Present", "Late"]:
                worked_days += 1
        current += timedelta(days=1)

    return worked_days


# ======================================================
# COMPUTE EARNED CREDIT
# ======================================================
def compute_credit(days_worked):
    """Return leave credit based on CSC table."""
    if days_worked <= 0:
        return 0
    if days_worked > 30:
        days_worked = 30
    return CREDITS_TABLE.get(days_worked, 0)


# ======================================================
# GENERATE MONTHLY LEAVE CREDIT FOR AN EMPLOYEE
# ======================================================
def generate_employee_leave_credit(employee, year, month):
    leave_types = LeaveType.query.filter(
        LeaveType.name.in_(["Sick Leave", "Vacation Leave"])
    ).all()

    days_worked = count_work_days(employee, year, month)
    earned_credit = compute_credit(days_worked)
    month_label = f"{calendar.month_abbr[month]} {year}"

    for leave_type in leave_types:

        # Create LeaveCredit if not exists
        leave_credit = LeaveCredit.query.filter_by(
            employee_id=employee.id,
            leave_type_id=leave_type.id
        ).first()
        if not leave_credit:
            leave_credit = LeaveCredit(
                employee_id=employee.id,
                leave_type_id=leave_type.id,
                total_credits=0
            )
            db.session.add(leave_credit)

        # Add earned credit
        leave_credit.total_credits += earned_credit

        # Save history
        history = LeaveCreditHistory(
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            earned=earned_credit,
            used=0,
            month=month_label
        )
        db.session.add(history)

    db.session.commit()


# ======================================================
# GENERATE LEAVE CREDIT FOR ALL EMPLOYEES
# ======================================================
def generate_monthly_leave_credits(year, month):
    employees = Employee.query.filter_by(archived=False).all()
    for emp in employees:
        generate_employee_leave_credit(emp, year, month)


# ======================================================
# GENERATE LEAVE HISTORY FOR AN EMPLOYEE
# ======================================================
def generate_leave_history(employee):
    leave_types = LeaveType.query.filter(LeaveType.name.in_(["Sick Leave", "Vacation Leave"])).all()
    today = date.today()
    current = employee.date_hired.replace(day=1)

    while current <= today:
        month_label = current.strftime("%b %Y")
        year, month = current.year, current.month

        worked_days = count_work_days(employee, year, month)
        earned_credit = compute_credit(worked_days)

        for leave_type in leave_types:
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

        # move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    db.session.commit()


# ======================================================
# SYNC LEAVE CREDIT (FROM HISTORY TO CURRENT TOTAL)
# ======================================================
def sync_leave_credit(employee):
    leave_types = LeaveType.query.filter(LeaveType.name.in_(["Sick Leave", "Vacation Leave"])).all()

    for leave_type in leave_types:
        total = db.session.query(
            db.func.sum(LeaveCreditHistory.earned - LeaveCreditHistory.used)
        ).filter_by(employee_id=employee.id, leave_type_id=leave_type.id).scalar() or 0

        credit = LeaveCredit.query.filter_by(
            employee_id=employee.id,
            leave_type_id=leave_type.id
        ).first()

        if not credit:
            credit = LeaveCredit(
                employee_id=employee.id,
                leave_type_id=leave_type.id,
                total_credits=total
            )
            db.session.add(credit)
        else:
            credit.total_credits = total

    db.session.commit()


# ======================================================
# CONSUME LEAVE CREDIT (WHEN LEAVE IS APPROVED)
# ======================================================
def consume_leave_credit(employee_id, leave_type_id, leave_date, days_needed=1):
    remaining_days = days_needed
    used_from_months = []

    current_month = leave_date.replace(day=1)

    while remaining_days > 0:
        month_label = current_month.strftime("%b %Y")
        history = LeaveCreditHistory.query.filter_by(
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            month=month_label
        ).first()

        if history:
            available = history.earned - history.used
            if available > 0:
                use = min(available, remaining_days)
                history.used += use
                remaining_days -= use
                used_from_months.append((month_label, use))

        # Move to previous month
        if current_month.month == 1:
            current_month = current_month.replace(
                year=current_month.year - 1,
                month=12
            )
        else:
            current_month = current_month.replace(
                month=current_month.month - 1
            )

        # Stop if before hire date
        if current_month < Employee.query.get(employee_id).date_hired.replace(day=1):
            break

    db.session.commit()
    return remaining_days, used_from_months