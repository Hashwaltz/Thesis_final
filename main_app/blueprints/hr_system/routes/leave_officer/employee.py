from datetime import date, timedelta, datetime, time
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
    LeaveCreditHistory,
    Attendance
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





late_per_hour_late_into_leave_credits = {
    1: .125, 2: .250, 3: .375, 4: .500,
    5: .625, 6: .750, 7: .875, 8: 1.000
}


late_per_minutes_late_into_leave_credits = {
    1 : .002, 2 : .004, 3 : .006, 4 : .008, 5 : .010,
    6 : .012, 7 : .015, 8 : .017, 9 : .019, 10 : .021,
    11 : .023, 12 : .025, 13 : .027, 14 : .029, 15 : .031,
    16 : .033, 17 : .035, 18 : .037, 19 : .040, 20 : .042,
    21 : .044, 22 : .046, 23 : .048, 24 : .050, 25 : .052,
    26 : .054, 27 : .056, 28 : .058, 29 : .060, 30 : .062,
    31 : .065, 32 : .067, 33 : .069, 34 : .071, 35 : .073,
    36 : .075, 37 : .077, 38 : .079, 39 : .081, 40 : .083,
    41 : .085, 42 : .087, 43 : .090, 44 : .092, 45 : .094,
    46 : .096, 47 : .098, 48 : .100, 49 : .102, 50 : .104,
    51 : .106, 52 : .108, 53 : .110, 54 : .112, 55 : .115,
    56 : .117, 57 : .119, 58 : .121, 59 : .123, 60 : .125
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



# =========================================================
# 🆕 HELPER: COMPUTE COMPREHENSIVE LEAVE CREDIT SUMMARY
# =========================================================
def compute_leave_summary(employee, year=None):
    """
    Computes a complete summary of leave credits:
    - Total earned (from worked days via CREDITS_TABLE)
    - Total used (from approved leaves)
    - Total late deductions (via late_per_minutes_late_into_leave_credits)
    - Net balance per leave type
    
    Args:
        employee: Employee object
        year: Optional int - filter summary to specific year (None = all time)
    
    Returns:
        dict with summary data for Vacation Leave and Sick Leave
    """
    leave_types = LeaveType.query.filter(
        LeaveType.name.in_(["Sick Leave", "Vacation Leave"])
    ).all()
    
    summary = {}
    
    for lt in leave_types:
        # === EARNED CREDITS ===
        earned_query = LeaveCreditHistory.query.filter_by(
            employee_id=employee.id,
            leave_type_id=lt.id
        )
        if year:
            # Filter by year extracted from month label "Jan 2024"
            earned_query = earned_query.filter(
                LeaveCreditHistory.month.ilike(f"%{year}")
            )
        total_earned = db.session.query(
            db.func.sum(LeaveCreditHistory.earned)
        ).filter(earned_query.subquery()).scalar() or 0
        
        # === USED CREDITS (from approved leaves) ===
        used_query = Leave.query.filter_by(
            employee_id=employee.id,
            leave_type_id=lt.id,
            status="Approved"
        )
        if year:
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)
            used_query = used_query.filter(
                Leave.start_date <= year_end,
                Leave.end_date >= year_start
            )
        
        total_used = 0
        leave_details = []
        for leave in used_query.all():
            # Calculate days that fall within the filter period
            if year:
                actual_start = max(leave.start_date, year_start)
                actual_end = min(leave.end_date, year_end)
            else:
                actual_start, actual_end = leave.start_date, leave.end_date
            
            days_in_period = (actual_end - actual_start).days + 1
            total_used += days_in_period
            leave_details.append({
                "id": leave.id,
                "start_date": leave.start_date.strftime("%Y-%m-%d"),
                "end_date": leave.end_date.strftime("%Y-%m-%d"),
                "days": days_in_period,
                "reason": leave.reason[:50] + "..." if len(leave.reason) > 50 else leave.reason
            })
        
        # === LATE DEDUCTIONS ===
        late_deduction_query = Attendance.query.filter_by(
            employee_id=employee.id
        )
        if year:
            late_deduction_query = late_deduction_query.filter(
                Attendance.date >= date(year, 1, 1),
                Attendance.date <= date(year, 12, 31)
            )
        
        total_late_seconds = 0
        late_details = []
        
        for att in late_deduction_query.order_by(Attendance.date).all():
            late_seconds = 0
            if att.time_in and att.time_in > time(8, 0):
                late_seconds = (datetime.combine(att.date, att.time_in) -
                               datetime.combine(att.date, time(8, 0))).total_seconds()
                late_seconds = max(0, late_seconds)
            
            if late_seconds > 0:
                total_late_seconds += late_seconds
                late_mins = int(late_seconds // 60)
                late_secs = int(round(late_seconds % 60))
                late_details.append({
                    "date": att.date.strftime("%Y-%m-%d"),
                    "time_in": att.time_in.strftime("%I:%M:%S %p"),
                    "late_display": f"{late_mins} min {late_secs} sec"
                })
        
        # Calculate deduction using your dictionary logic
        total_late_minutes = int(round(total_late_seconds / 60.0))
        if total_late_minutes <= 0:
            total_late_deduction = 0.0
        elif total_late_minutes <= 60:
            total_late_deduction = late_per_minutes_late_into_leave_credits.get(total_late_minutes, 0)
        else:
            full_hours = total_late_minutes // 60
            remaining_mins = total_late_minutes % 60
            hourly_deduction = full_hours * late_per_minutes_late_into_leave_credits[60]
            minute_deduction = late_per_minutes_late_into_leave_credits.get(remaining_mins, 0)
            total_late_deduction = round(hourly_deduction + minute_deduction, 3)
        
        # === FINAL CALCULATIONS ===
        net_balance = round(total_earned - total_used - total_late_deduction, 3)
        points_equivalent = convert_leave_to_points(max(net_balance, 0))
        
        summary[lt.name] = {
            "earned": round(total_earned, 3),
            "used": round(total_used, 3),
            "late_deduction": round(total_late_deduction, 3),
            "balance": net_balance,
            "points": points_equivalent,
            "leave_details": leave_details,
            "late_details": late_details[:10]  # Show last 10 for preview
        }
    
    return summary


# =========================================================
# 🆕 HELPER: CALCULATE TOTAL LATE DEDUCTION (ALL-TIME)
# =========================================================
def calculate_late_deduction(employee):
    """
    Calculates total late deduction in leave credits based on ALL attendance records.
    Uses late_per_minutes_late_into_leave_credits dictionary logic.
    """
    attendances = Attendance.query.filter_by(employee_id=employee.id).all()
    
    total_late_seconds = 0.0
    
    for att in attendances:
        if att.time_in and att.time_in > time(8, 0):
            late_seconds = (datetime.combine(att.date, att.time_in) -
                           datetime.combine(att.date, time(8, 0))).total_seconds()
            total_late_seconds += max(0, late_seconds)
    
    total_late_minutes = int(round(total_late_seconds / 60.0))
    
    if total_late_minutes <= 0:
        return 0.0
    elif total_late_minutes <= 60:
        return late_per_minutes_late_into_leave_credits.get(total_late_minutes, 0)
    else:
        full_hours = total_late_minutes // 60
        remaining_mins = total_late_minutes % 60
        hourly_deduction = full_hours * late_per_minutes_late_into_leave_credits[60]
        minute_deduction = late_per_minutes_late_into_leave_credits.get(remaining_mins, 0)
        return round(hourly_deduction + minute_deduction, 3)
    

# ===============================
# VIEW SINGLE EMPLOYEE WITH LEAVE
# ===============================
@leave_officer_bp.route("/employee/<int:employee_id>/view")
@login_required
@leave_officer_required
def view_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    today = date.today()

    # --- Generate history and sync credits ---
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

    # 🆕 Calculate late deduction and apply to TOTAL balance
    total_late_deduction = calculate_late_deduction(employee)
    
    # Calculate balances: late deduction subtracted from TOTAL only
    balance_vac = max(total_vac - used_vac, 0)
    balance_sick = max(total_sick - used_sick, 0)
    total_balance = max((total_vac + total_sick) - (used_vac + used_sick) - total_late_deduction, 0)

    # Point equivalents (based on individual balances for display, total for points)
    vacation_points = convert_leave_to_points(balance_vac)
    sick_points = convert_leave_to_points(balance_sick)
    total_points = convert_leave_to_points(total_balance)

    leave_table = [
        {"particulars": "Total Credits", "vacation": round(total_vac,3), "sick": round(total_sick,3), "total": round(total_vac + total_sick,3)},
        {"particulars": "Leaves Used", "vacation": round(used_vac,3), "sick": round(used_sick,3), "total": round(used_vac + used_sick,3)},
        {"particulars": "Current Balance", "vacation": round(balance_vac,3), "sick": round(balance_sick,3), "total": round(total_balance,3), "type": "balance"},
        {"particulars": "Point Equivalent", "vacation": vacation_points, "sick": sick_points, "total": round(total_points,3), "type": "points"}
    ]

    return render_template(
        "hr/leave_officer/employee.html",
        employee=employee,
        leave_table=leave_table,
        today=today,
        vacation_credit=total_vac,
        sick_credit=total_sick,
        late_deduction=total_late_deduction  # 🆕 Pass to template for optional display
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




