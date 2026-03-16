from datetime import date, timedelta
import calendar

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required

from main_app.extensions import db
from main_app.models.hr_models import (
    Employee,
    Leave,
    Department,
    LeaveCredit,
    LeaveType,
    LeaveCreditHistory
)
from main_app.helpers.decorators import leave_officer_required
from main_app.helpers.functions import convert_leave_to_points
from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp

# ===============================
# HELPER FUNCTIONS
# ===============================
CREDITS_TABLE = {
    1: 0.042, 2: 0.083, 3: 0.125, 4: 0.167, 5: 0.208,
    6: 0.250, 7: 0.292, 8: 0.333, 9: 0.375, 10: 0.417,
    11: 0.458, 12: 0.500, 13: 0.542, 14: 0.583, 15: 0.625,
    16: 0.667, 17: 0.708, 18: 0.750, 19: 0.792, 20: 0.833,
    21: 0.875, 22: 0.917, 23: 0.958, 24: 1.000, 25: 1.042,
    26: 1.083, 27: 1.125, 28: 1.167, 29: 1.208, 30: 1.250
}

def count_work_days(employee, year, month):
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    if employee.date_hired > start:
        start = employee.date_hired

    worked_days = 0
    current = start

    while current <= end:
        weekday = current.weekday()
        # Saturday/Sunday counted automatically
        if weekday in [5, 6]:
            worked_days += 1
        else:
            attendance = employee.attendances
            # check attendance for the day
            att = next((a for a in attendance if a.date == current), None)
            if att and att.status in ["Present", "Late"]:
                worked_days += 1
        current += timedelta(days=1)

    return worked_days

def compute_credit(days_worked):
    if days_worked <= 0:
        return 0
    if days_worked > 30:
        days_worked = 30
    return CREDITS_TABLE.get(days_worked, 0)

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
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    db.session.commit()

def sync_leave_credit(employee):
    leave_types = LeaveType.query.filter(LeaveType.name.in_(["Sick Leave", "Vacation Leave"])).all()
    for leave_type in leave_types:
        total = db.session.query(
            db.func.sum(LeaveCreditHistory.earned - LeaveCreditHistory.used)
        ).filter_by(employee_id=employee.id, leave_type_id=leave_type.id).scalar() or 0

        credit = LeaveCredit.query.filter_by(employee_id=employee.id, leave_type_id=leave_type.id).first()
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

# ===============================
# VIEW EMPLOYEES
# ===============================
@leave_officer_bp.route("/employees")
@login_required
@leave_officer_required
def employees():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")
    department = request.args.get("department", "")

    query = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id.in_([1, 3])
    )

    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%")) |
            (Employee.last_name.ilike(f"%{search}%")) |
            (Employee.employee_id.ilike(f"%{search}%"))
        )

    if department:
        query = query.filter_by(department_id=department)

    query = query.order_by(Employee.last_name.asc(), Employee.first_name.asc())
    employees = query.paginate(page=page, per_page=10, error_out=False)
    departments = Department.query.all()

    return render_template(
        "hr/leave_officer/employees.html",
        employees=employees,
        search=search,
        selected_department=department,
        departments=departments,
    )

# ===============================
# VIEW SINGLE EMPLOYEE WITH LEAVE
# ===============================
@leave_officer_bp.route("/employee/<int:employee_id>/view")
@login_required
@leave_officer_required
def view_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    today = date.today()

    # --- FIX: generate history and sync credits ---
    generate_leave_history(employee)
    sync_leave_credit(employee)

    # Fetch leave types
    leave_types = LeaveType.query.filter(LeaveType.name.in_(["Vacation Leave", "Sick Leave"])).all()
    leave_type_map = {lt.name: lt.id for lt in leave_types}

    # Fetch latest leave credits
    vacation_credit = LeaveCredit.query.filter_by(employee_id=employee.id, leave_type_id=leave_type_map.get("Vacation Leave")).first()
    sick_credit = LeaveCredit.query.filter_by(employee_id=employee.id, leave_type_id=leave_type_map.get("Sick Leave")).first()

    total_vac = vacation_credit.total_credits if vacation_credit else 0
    total_sick = sick_credit.total_credits if sick_credit else 0

    # Used Leaves Computation
    used_vac = sum(l.days_requested for l in employee.leaves if l.status == "Approved" and l.leave_type_id == leave_type_map.get("Vacation Leave"))
    used_sick = sum(l.days_requested for l in employee.leaves if l.status == "Approved" and l.leave_type_id == leave_type_map.get("Sick Leave"))

    balance_vac = max(total_vac - used_vac, 0)
    balance_sick = max(total_sick - used_sick, 0)

    vacation_points = convert_leave_to_points(balance_vac)
    sick_points = convert_leave_to_points(balance_sick)

    leave_table = [
        {"particulars": "Total Credits", "vacation": round(total_vac,3), "sick": round(total_sick,3), "total": round(total_vac + total_sick,3)},
        {"particulars": "Leaves Used", "vacation": round(used_vac,3), "sick": round(used_sick,3), "total": round(used_vac + used_sick,3)},
        {"particulars": "Current Balance", "vacation": round(balance_vac,3), "sick": round(balance_sick,3), "total": round(balance_vac + balance_sick,3), "type": "balance"},
        {"particulars": "Point Equivalent", "vacation": vacation_points, "sick": sick_points, "total": round(vacation_points + sick_points,3), "type": "points"}
    ]

    return render_template(
        "hr/leave_officer/employee.html",
        employee=employee,
        leave_table=leave_table,
        today=today,
        vacation_credit=total_vac,
        sick_credit=total_sick
    )

# ===============================
# EDIT LEAVE CREDIT
# ===============================
@leave_officer_bp.route("/employee/<int:employee_id>/edit-leave-credit", methods=["POST"])
@login_required
@leave_officer_required
def edit_leave_credit(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    today = date.today()
    month_label = today.strftime("%b %Y")  # e.g., "Mar 2026"

    vacation_input = request.form.get("vacation", type=float) or 0
    sick_input = request.form.get("sick", type=float) or 0

    leave_types = LeaveType.query.filter(LeaveType.name.in_(["Vacation Leave", "Sick Leave"])).all()
    leave_type_map = {lt.name: lt.id for lt in leave_types}

    # --- Update LeaveCredit ---
    for lt_name, value in [("Vacation Leave", vacation_input), ("Sick Leave", sick_input)]:
        lt_id = leave_type_map.get(lt_name)
        credit = LeaveCredit.query.filter_by(employee_id=employee.id, leave_type_id=lt_id).first()
        if credit:
            credit.total_credits = value
        else:
            credit = LeaveCredit(employee_id=employee.id, leave_type_id=lt_id, total_credits=value)
            db.session.add(credit)

        # --- Update LeaveCreditHistory for current month ---
        history = LeaveCreditHistory.query.filter_by(employee_id=employee.id, leave_type_id=lt_id, month=month_label).first()
        if history:
            history.earned = value
        else:
            history = LeaveCreditHistory(employee_id=employee.id, leave_type_id=lt_id, earned=value, used=0, month=month_label)
            db.session.add(history)

    db.session.commit()
    flash("Leave credits updated successfully (and history synced).", "success")
    return redirect(url_for("leave_officer_bp.view_employee", employee_id=employee.id))

# ===============================
# VIEW LEAVE REQUESTS
# ===============================
@leave_officer_bp.route("/leave-requests")
@login_required
@leave_officer_required
def view_leaves():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    department_filter = request.args.get("department", "")
    search = request.args.get("search", "")

    query = Leave.query.join(Employee)

    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%")) |
            (Employee.last_name.ilike(f"%{search}%")) |
            (Employee.employee_id.ilike(f"%{search}%"))
        )

    if status_filter:
        query = query.filter(Leave.status == status_filter)

    if department_filter:
        query = query.filter(Employee.department_id == department_filter)

    query = query.order_by(Leave.created_at.desc())
    leaves = query.paginate(page=page, per_page=10, error_out=False)
    departments = Department.query.all()

    return render_template(
        "hr/leave_officer/leave_requests.html",
        leaves=leaves,
        status_filter=status_filter,
        selected_department=department_filter,
        search=search,
        departments=departments
    )