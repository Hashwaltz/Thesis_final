from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import date, timedelta, datetime, time
import calendar
from collections import defaultdict

from main_app.models.hr_models import (
    Employee,
    LeaveType,
    JobHistory,
    Leave,
    Department,
    Attendance,
    LateComputation,
    LeaveCredit,
    LeaveCreditHistory
)
from main_app.extensions import db
from main_app.helpers.decorators import leave_officer_required
from main_app.models.services import generate_leave_history
from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp


# =========================================================
# 🆕 HELPER: APPLY LATE DEDUCTION TO CREDITS (VL-FIRST, THEN SL)
# =========================================================
def apply_late_deduction_to_credits(employee_id, year, month, late_deduction_amount):
    """
    Applies late deduction to leave credits:
    1. First deduct from Vacation Leave (VL) balance
    2. If VL is exhausted, deduct remaining from Sick Leave (SL)
    
    Returns: dict with deduction breakdown for logging/display
    """
    # Get leave types
    vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
    sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
    
    if not vl_type or not sl_type:
        return {"vl_deducted": 0, "sl_deducted": 0, "unapplied": late_deduction_amount}
    
    # Get credit records for this employee
    vl_credit = LeaveCredit.query.filter_by(
        employee_id=employee_id, 
        leave_type_id=vl_type.id
    ).first()
    sl_credit = LeaveCredit.query.filter_by(
        employee_id=employee_id, 
        leave_type_id=sl_type.id
    ).first()
    
    remaining_deduction = late_deduction_amount
    vl_deducted = 0
    sl_deducted = 0
    
    # 🔹 STEP 1: Deduct from Vacation Leave first
    if vl_credit and remaining_deduction > 0:
        vl_remaining = max(0, vl_credit.total_credits - vl_credit.used_credits)
        vl_to_deduct = min(remaining_deduction, vl_remaining)
        
        if vl_to_deduct > 0:
            vl_credit.used_credits += vl_to_deduct
            vl_deducted = vl_to_deduct
            remaining_deduction -= vl_to_deduct
    
    # 🔹 STEP 2: If deduction remains, use Sick Leave
    if sl_credit and remaining_deduction > 0:
        sl_remaining = max(0, sl_credit.total_credits - sl_credit.used_credits)
        sl_to_deduct = min(remaining_deduction, sl_remaining)
        
        if sl_to_deduct > 0:
            sl_credit.used_credits += sl_to_deduct
            sl_deducted = sl_to_deduct
            remaining_deduction -= sl_to_deduct
    
    # Commit changes if any deduction was applied
    if vl_deducted > 0 or sl_deducted > 0:
        db.session.commit()
    
    return {
        "vl_deducted": round(vl_deducted, 3),
        "sl_deducted": round(sl_deducted, 3),
        "unapplied": round(remaining_deduction, 3)
    }


# =========================================================
# 🆕 HELPER: CHECK IF LATE DEDUCTION WAS ALREADY APPLIED
# =========================================================
def is_late_deduction_applied(employee_id, year, month):
    """
    Checks if late deduction was already applied for this month.
    Uses LeaveCreditHistory to detect if used_credits exceed approved leave usage.
    """
    month_label = f"{datetime(year, month, 1).strftime('%B')} {year}"
    vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
    sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
    
    if not vl_type or not sl_type:
        return False
    
    # Get history records
    vl_history = LeaveCreditHistory.query.filter_by(
        employee_id=employee_id,
        leave_type_id=vl_type.id,
        month=month_label
    ).first()
    sl_history = LeaveCreditHistory.query.filter_by(
        employee_id=employee_id,
        leave_type_id=sl_type.id,
        month=month_label
    ).first()
    
    # Get approved leave usage for this month
    leave_usage = get_monthly_leave_usage(employee_id, year, month)
    vl_used_in_leaves = sum(u['days_used'] for u in leave_usage if u['leave_type'] == 'Vacation Leave')
    sl_used_in_leaves = sum(u['days_used'] for u in leave_usage if u['leave_type'] == 'Sick Leave')
    
    # If used_credits in history > leave usage, deduction was likely applied
    if vl_history and vl_history.used > vl_used_in_leaves:
        return True
    if sl_history and sl_history.used > sl_used_in_leaves:
        return True
    
    return False


# =========================================================
# 🆕 HELPER: CHECK EMPLOYMENT TYPE ELIGIBILITY FOR LEAVE CREDITS
# =========================================================
def is_eligible_for_leave_credits(employment_type_id):
    """
    Returns True if employment type is eligible for leave credit accrual.
    Eligible types: Regular (id=1), Casual (id=3)
    """
    return employment_type_id in [1, 3]


def get_employment_type_on_date(employee_id, check_date):
    """
    Returns the employment_type_id for an employee on a specific date
    by checking JobHistory records (handles promotions/demotions).
    """
    job_history = JobHistory.query.filter(
        JobHistory.employee_id == employee_id,
        JobHistory.effective_date <= check_date,
        db.or_(
            JobHistory.end_date == None,
            JobHistory.end_date >= check_date
        )
    ).order_by(JobHistory.effective_date.desc()).first()
    
    if job_history and job_history.employment_type_id:
        return job_history.employment_type_id
    
    # Fallback: use current employee employment_type
    employee = Employee.query.get(employee_id)
    return employee.employment_type_id if employee else None


def count_eligible_work_days(employee, year, month):
    """
    Counts worked days ONLY when employee was in eligible employment type 
    (Regular=1 or Casual=3) based on JobHistory.
    
    Returns: (eligible_worked_days, total_days_in_month)
    """
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    if employee.date_hired > start:
        start = employee.date_hired

    current = start
    eligible_worked_days = 0

    while current <= end:
        emp_type_on_date = get_employment_type_on_date(employee.id, current)
        
        if not is_eligible_for_leave_credits(emp_type_on_date):
            current += timedelta(days=1)
            continue
            
        weekday = current.weekday()
        
        if weekday in [5, 6]:  # Saturday/Sunday auto-counted
            eligible_worked_days += 1
        else:
            attendance = Attendance.query.filter_by(
                employee_id=employee.id, 
                date=current
            ).first()
            if attendance and attendance.status in ["Present", "Late"]:
                eligible_worked_days += 1
                
        current += timedelta(days=1)

    return eligible_worked_days, last_day


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
# HELPER: COUNT WORKED DAYS FROM ATTENDANCE (LEGACY - KEEP FOR REFERENCE)
# =========================================================
def count_work_days(employee, year, month):
    """Counts worked days including Sat/Sun based on attendance."""
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    if employee.date_hired > start:
        start = employee.date_hired

    current = start
    worked_days = 0

    while current <= end:
        weekday = current.weekday()
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


# =========================================================
# HELPER: GET APPROVED LEAVES FOR A MONTH
# =========================================================
def get_monthly_leave_usage(employee_id, year, month):
    """Returns approved leaves that fall within the given month."""
    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)
    
    leaves = Leave.query.filter(
        Leave.employee_id == employee_id,
        Leave.status == "Approved",
        Leave.start_date <= month_end,
        Leave.end_date >= month_start
    ).all()
    
    usage = []
    for leave in leaves:
        actual_start = max(leave.start_date, month_start)
        actual_end = min(leave.end_date, month_end)
        days_in_month = (actual_end - actual_start).days + 1
        
        usage.append({
            "leave_type": leave.leave_type.name,
            "start_date": actual_start.strftime("%Y-%m-%d"),
            "end_date": actual_end.strftime("%Y-%m-%d"),
            "days_used": days_in_month,
            "reason": leave.reason[:50] + "..." if len(leave.reason) > 50 else leave.reason
        })
    
    return usage


# =========================================================
# 🆕 HELPER: GET MONTHLY LATE SUMMARY (USING DICTIONARY FOR DEDUCTION)
# =========================================================
def get_monthly_late_summary(employee_id, year, month):
    """
    Returns:
      - late_records: List of daily late entries (for display: minutes + seconds)
      - monthly_deduction: Single deduction value calculated from TOTAL late time 
        using late_per_minutes_late_into_leave_credits dictionary
        
    Computation Example (88 minutes):
      - hours = 88 // 60 = 1 → 1 * 0.125 = 0.125
      - remaining = 88 % 60 = 28 → lookup[28] = 0.058
      - total = 0.125 + 0.058 = 0.183 credits
    """
    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)
    
    attendances = Attendance.query.filter(
        Attendance.employee_id == employee_id,
        Attendance.date >= month_start,
        Attendance.date <= month_end
    ).order_by(Attendance.date).all()
    
    late_records = []
    total_late_seconds = 0.0
    
    for att in attendances:
        late_seconds = 0.0
        
        if att.time_in and att.time_in > time(8, 0):
            late_seconds = (datetime.combine(att.date, att.time_in) -
                           datetime.combine(att.date, time(8, 0))).total_seconds()
            if late_seconds < 0:
                late_seconds = 0.0
            total_late_seconds += late_seconds
        
        if late_seconds > 0:
            late_mins = int(late_seconds // 60)
            late_secs = int(round(late_seconds % 60))
            late_records.append({
                "date": att.date.strftime("%Y-%m-%d"),
                "time_in": att.time_in.strftime("%I:%M:%S %p") if att.time_in else "N/A",
                "late_minutes": late_mins,
                "late_seconds": late_secs,
                "late_display": f"{late_mins} min {late_secs} sec",
                "day_equivalent": 0
            })
    
    # 🎯 DEDUCTION USING DICTIONARY ONLY
    total_late_minutes = int(round(total_late_seconds / 60.0))
    
    if total_late_minutes <= 0:
        monthly_deduction = 0.0
    elif total_late_minutes <= 60:
        monthly_deduction = late_per_minutes_late_into_leave_credits.get(total_late_minutes, 0)
    else:
        full_hours = total_late_minutes // 60
        remaining_mins = total_late_minutes % 60
        hourly_deduction = full_hours * late_per_minutes_late_into_leave_credits[60]  # 60 mins = 1 hour = 0.125
        minute_deduction = late_per_minutes_late_into_leave_credits.get(remaining_mins, 0) if remaining_mins > 0 else 0
        monthly_deduction = round(hourly_deduction + minute_deduction, 3)
    
    return late_records, monthly_deduction


# =========================================================
# 🆕 HELPER: CALCULATE NET CREDITS AFTER VL-FIRST DEDUCTION (FOR DISPLAY)
# =========================================================
def calculate_net_credits_after_deduction(employee_id, earned_credit, late_deduction):
    """
    Calculates net remaining credits per leave type after applying late deduction
    with VL-first, then SL fallback logic. For DISPLAY purposes only.
    
    Returns dict with VL/SL earned, deducted, and net values.
    """
    vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
    sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
    
    result = {
        "vl_earned": earned_credit,
        "sl_earned": earned_credit,
        "vl_deducted": 0,
        "sl_deducted": 0,
        "vl_net": earned_credit,
        "sl_net": earned_credit,
        "unapplied_deduction": 0
    }
    
    if late_deduction <= 0 or not vl_type:
        return result
    
    remaining_deduction = late_deduction
    
    # 🔹 Deduct from VL first
    if vl_type:
        vl_credit = LeaveCredit.query.filter_by(
            employee_id=employee_id, leave_type_id=vl_type.id
        ).first()
        if vl_credit:
            vl_available = max(0, vl_credit.total_credits - vl_credit.used_credits)
            vl_deduct = min(remaining_deduction, vl_available)
            result["vl_deducted"] = round(vl_deduct, 3)
            result["vl_net"] = round(max(0, result["vl_earned"] - vl_deduct), 3)
            remaining_deduction -= vl_deduct
    
    # 🔹 Deduct remaining from SL
    if remaining_deduction > 0 and sl_type:
        sl_credit = LeaveCredit.query.filter_by(
            employee_id=employee_id, leave_type_id=sl_type.id
        ).first()
        if sl_credit:
            sl_available = max(0, sl_credit.total_credits - sl_credit.used_credits)
            sl_deduct = min(remaining_deduction, sl_available)
            result["sl_deducted"] = round(sl_deduct, 3)
            result["sl_net"] = round(max(0, result["sl_earned"] - sl_deduct), 3)
            remaining_deduction -= sl_deduct
    
    result["unapplied_deduction"] = round(max(0, remaining_deduction), 3)
    return result


# =========================================================
# 🆕 ROUTE: MANUALLY APPLY LATE DEDUCTION FOR A MONTH
# =========================================================
@leave_officer_bp.route("/history/<int:employee_id>/<int:year>/<int:month>/apply-late-deduction", methods=["POST"])
@login_required
@leave_officer_required
def apply_monthly_late_deduction(employee_id, year, month):
    """
    Manually apply late deduction for a specific month.
    Uses VL-first, then SL fallback logic.
    Computation: hours * 0.125 + remaining_minutes lookup
    """
    employee = Employee.query.get_or_404(employee_id)
    month_label = f"{datetime(year, month, 1).strftime('%B')} {year}"
    
    # 🔹 Recalculate late deduction using dictionary logic
    late_records, monthly_late_deduction = get_monthly_late_summary(employee.id, year, month)
    
    if monthly_late_deduction <= 0:
        flash("ℹ️ No late deduction to apply for this month.", "info")
        return redirect(url_for("leave_officer.view_leave_history", employee_id=employee_id))
    
    # 🔹 Check if already applied (prevent double-deduction)
    if is_late_deduction_applied(employee_id, year, month):
        flash(f"⚠️ Late deduction for {month_label} was already applied.", "warning")
        return redirect(url_for("leave_officer.view_leave_history", employee_id=employee_id))
    
    # 🔹 Apply deduction using VL-first logic
    deduction_breakdown = apply_late_deduction_to_credits(
        employee.id, year, month, monthly_late_deduction
    )
    
    # 🔹 Update LeaveCreditHistory to reflect the deduction
    vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
    sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
    
    if vl_type and deduction_breakdown['vl_deducted'] > 0:
        vl_history = LeaveCreditHistory.query.filter_by(
            employee_id=employee_id,
            leave_type_id=vl_type.id,
            month=month_label
        ).first()
        if vl_history:
            vl_history.used += deduction_breakdown['vl_deducted']
    
    if sl_type and deduction_breakdown['sl_deducted'] > 0:
        sl_history = LeaveCreditHistory.query.filter_by(
            employee_id=employee_id,
            leave_type_id=sl_type.id,
            month=month_label
        ).first()
        if sl_history:
            sl_history.used += deduction_breakdown['sl_deducted']
    
    db.session.commit()
    
    # 🔹 Build flash message
    unapplied_msg = f", Unapplied: {deduction_breakdown['unapplied']}" if deduction_breakdown['unapplied'] > 0 else ""
    flash(
        f"✅ Late deduction of {monthly_late_deduction} credits applied for {month_label}.<br>"
        f"📋 Breakdown: VL: -{deduction_breakdown['vl_deducted']}, "
        f"SL: -{deduction_breakdown['sl_deducted']}{unapplied_msg}",
        "success"
    )
    
    return redirect(url_for("leave_officer.view_leave_history", employee_id=employee_id))


# =========================================================
# LEAVE CREDIT HISTORY VIEW (MAIN ROUTE)
# =========================================================
@leave_officer_bp.route("/history/<int:employee_id>")
@login_required
@leave_officer_required
def view_leave_history(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    
    # Generate/update leave history in database (does NOT auto-apply late deductions anymore)
    generate_leave_history(employee)

    leave_types = LeaveType.query.filter(
        LeaveType.name.in_(["Sick Leave", "Vacation Leave"])
    ).all()

    history_data = []
    annual_summary = defaultdict(lambda: {"Sick Leave": 0, "Vacation Leave": 0})

    current = employee.date_hired.replace(day=1)
    today = date.today()

    while current <= today:
        month_label = current.strftime("%b %Y")
        year, month = current.year, current.month
        
        # 🔄 Use eligibility-aware work day counter
        worked_days, total_days = count_eligible_work_days(employee, year, month)
        earned_credit = CREDITS_TABLE.get(worked_days, 0)

        # 🆕 Get late records + deduction amount (for display & manual application)
        late_records, monthly_late_deduction = get_monthly_late_summary(employee.id, year, month)
        leave_usage = get_monthly_leave_usage(employee.id, year, month)

        # 🎯 CHECK IF DEDUCTION WAS ALREADY APPLIED
        deduction_already_applied = is_late_deduction_applied(employee.id, year, month)
        
        # 🎯 CALCULATE NET CREDITS FOR DISPLAY (VL-first logic) - only if not yet applied
        if deduction_already_applied:
            # If already applied, fetch actual values from history
            net_credits = {
                "vl_net": earned_credit,
                "sl_net": earned_credit,
                "vl_deducted": 0,
                "sl_deducted": 0,
                "unapplied_deduction": 0
            }
            deduction_breakdown = {"from_vl": 0, "from_sl": 0, "unapplied": 0}
        else:
            # Show what WOULD be deducted if applied now
            net_credits = calculate_net_credits_after_deduction(
                employee.id, earned_credit, monthly_late_deduction
            )
            deduction_breakdown = {
                "from_vl": net_credits["vl_deducted"],
                "from_sl": net_credits["sl_deducted"],
                "unapplied": net_credits["unapplied_deduction"]
            }

        month_record = {
            "month": current.strftime("%B %Y"),
            "year": year,
            "month_num": month,
            "worked_days": worked_days,
            "total_days": total_days,
            "earned_credit": earned_credit,
            "late_deduction": monthly_late_deduction,
            "late_deduction_pending": monthly_late_deduction > 0 and not deduction_already_applied,
            "late_deduction_applied": deduction_already_applied,
            # 🆕 Net credits after VL-first deduction
            "vl_net_credit": net_credits["vl_net"],
            "sl_net_credit": net_credits["sl_net"],
            "deduction_breakdown": deduction_breakdown,
            "leave_usage": leave_usage,
            "late_deductions": late_records,
            "leave_data": []
        }

        for leave_type in leave_types:
            history = next(
                (h for h in employee.leave_credit_history
                 if h.leave_type_id == leave_type.id and h.month == month_label),
                None
            )

            if history:
                # Calculate remaining based on stored history
                remaining = round(max(0, history.earned - history.used), 3)
                
                month_record["leave_data"].append({
                    "leave_type": leave_type.name,
                    "earned": history.earned,
                    "used": history.used,
                    "remaining": remaining,
                    "usage_details": [l for l in leave_usage if l["leave_type"] == leave_type.name]
                })
                annual_summary[year][leave_type.name] += history.earned

        history_data.append(month_record)

        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    history_by_year = {}
    for record in history_data:
        history_by_year.setdefault(record["year"], []).append(record)

    history_by_year = dict(sorted(history_by_year.items(), reverse=True))
    sorted_annual = dict(sorted(annual_summary.items(), reverse=True))

    return render_template(
        "hr/leave_officer/history/leave_history.html",
        employee=employee,
        history_by_year=history_by_year,
        annual_summary=sorted_annual
    )