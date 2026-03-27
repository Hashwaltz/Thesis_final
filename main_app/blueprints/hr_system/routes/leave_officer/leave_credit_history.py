from flask import render_template, request
from flask_login import login_required
from datetime import date, timedelta
import calendar
from collections import defaultdict

from main_app.models.hr_models import (
    Employee,
    LeaveType,
    LeaveCreditHistory,
    Department,
    Attendance
)
from main_app.extensions import db
from main_app.helpers.decorators import leave_officer_required
from main_app.models.services import generate_leave_history
from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp



# =========================================================
# EMPLOYEE LIST
# =========================================================
@leave_officer_bp.route("/employees-leave-credit")
@login_required
@leave_officer_required
def list_employees():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    department = request.args.get("department", type=int)

    query = Employee.query.filter_by(archived=False, status="Active").order_by(Employee.last_name.asc())

    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%")) |
            (Employee.last_name.ilike(f"%{search}%")) |
            (Employee.employee_id.ilike(f"%{search}%"))
        )

    if department:
        query = query.filter_by(department_id=department)

    employees = query.order_by(Employee.id).paginate(page=page, per_page=10)
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "hr/leave_officer/history/employees_list.html",
        employees=employees,
        search=search,
        departments=departments,
        selected_department=department
    )

# =========================================================
# HELPER: COUNT WORKED DAYS FROM ATTENDANCE
# =========================================================
def count_work_days(employee, year, month):
    """Counts worked days including Sat/Sun based on attendance."""
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    # If hired mid-month
    if employee.date_hired > start:
        start = employee.date_hired

    current = start
    worked_days = 0

    while current <= end:
        weekday = current.weekday()
        # Sat/Sun counted as present
        if weekday in [5, 6]:
            worked_days += 1
        else:
            attendance = Attendance.query.filter_by(employee_id=employee.id, date=current).first()
            if attendance and attendance.status in ["Present", "Late"]:
                worked_days += 1
        current += timedelta(days=1)

    return worked_days, last_day

# =========================================================
# LEAVE CREDIT TABLE (Sick & Vacation)
# =========================================================
CREDITS_TABLE = {
    1: 0.042, 2: 0.083, 3: 0.125, 4: 0.167, 5: 0.208,
    6: 0.250, 7: 0.292, 8: 0.333, 9: 0.375, 10: 0.417,
    11: 0.458, 12: 0.500, 13: 0.542, 14: 0.583, 15: 0.625,
    16: 0.667, 17: 0.708, 18: 0.750, 19: 0.792, 20: 0.833,
    21: 0.875, 22: 0.917, 23: 0.958, 24: 1.000, 25: 1.042,
    26: 1.083, 27: 1.125, 28: 1.167, 29: 1.208, 30: 1.250
}

@leave_officer_bp.route("/history/<int:employee_id>")
@login_required
@leave_officer_required
def view_leave_history(employee_id):
    employee = Employee.query.get_or_404(employee_id)

    # Ensure all leave history is generated
    generate_leave_history(employee)

    leave_types = LeaveType.query.filter(
        LeaveType.name.in_(["Sick Leave", "Vacation Leave"])
    ).all()

    history_data = []

    # ✅ ANNUAL SUMMARY (NEW)
    annual_summary = defaultdict(lambda: {
        "Sick Leave": 0,
        "Vacation Leave": 0
    })

    current = employee.date_hired.replace(day=1)
    today = date.today()

    while current <= today:
        month_label = current.strftime("%b %Y")
        year, month = current.year, current.month

        # FIXED: unpack tuple correctly
        worked_days, total_days = count_work_days(employee, year, month)

        earned_credit = CREDITS_TABLE.get(worked_days, 0)

        month_record = {
            "month": current.strftime("%B %Y"),
            "worked_days": worked_days,
            "total_days": total_days,
            "leave_data": []
        }

        for leave_type in leave_types:

            history = next(
                (
                    h for h in employee.leave_credit_history
                    if h.leave_type_id == leave_type.id and h.month == month_label
                ),
                None
            )

            if history:
                # monthly data
                month_record["leave_data"].append({
                    "leave_type": leave_type.name,
                    "earned": history.earned,
                    "used": history.used,
                    "remaining": history.earned - history.used
                })

                annual_summary[current.year][leave_type.name] += history.earned

        history_data.append(month_record)

        # next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return render_template(
        "hr/leave_officer/history/leave_history.html",
        employee=employee,
        history_data=history_data,
        annual_summary=annual_summary  
    )