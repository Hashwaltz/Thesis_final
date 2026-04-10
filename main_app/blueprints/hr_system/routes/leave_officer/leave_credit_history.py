from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from datetime import date, timedelta, datetime, time
import calendar
from collections import defaultdict
from sqlalchemy import func

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
# 🔥 REMOVED: from main_app.models.services import generate_leave_history
from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp


# =========================================================
# 🆕 HELPER: APPLY LATE DEDUCTION TO CREDITS (VL-FIRST, THEN SL)
# =========================================================
def apply_late_deduction_to_credits(employee_id, year, month, late_deduction_amount):
    """
    Applies late deduction to leave credits:
    1. First deduct from Vacation Leave (VL) balance
    2. If VL is exhausted, deduct remaining from Sick Leave (SL)
    """
    vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
    sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
    
    if not vl_type or not sl_type:
        return {"vl_deducted": 0, "sl_deducted": 0, "unapplied": late_deduction_amount}
    
    remaining_deduction = late_deduction_amount
    vl_deducted = 0
    sl_deducted = 0
    
    # STEP 1: Deduct from Vacation Leave first
    if remaining_deduction > 0 and vl_type:
        vl_credit = LeaveCredit.query.filter_by(
            employee_id=employee_id, 
            leave_type_id=vl_type.id
        ).first()
        
        if not vl_credit:
            vl_credit = LeaveCredit(
                employee_id=employee_id,
                leave_type_id=vl_type.id,
                total_credits=0,
                used_credits=0
            )
            db.session.add(vl_credit)
        
        vl_remaining = max(0, vl_credit.total_credits - vl_credit.used_credits)
        vl_to_deduct = min(remaining_deduction, vl_remaining)
        
        if vl_to_deduct > 0:
            vl_credit.used_credits += vl_to_deduct
            vl_deducted = vl_to_deduct
            remaining_deduction -= vl_to_deduct
    
    # STEP 2: If deduction remains, use Sick Leave
    if remaining_deduction > 0 and sl_type:
        sl_credit = LeaveCredit.query.filter_by(
            employee_id=employee_id, 
            leave_type_id=sl_type.id
        ).first()
        
        if not sl_credit:
            sl_credit = LeaveCredit(
                employee_id=employee_id,
                leave_type_id=sl_type.id,
                total_credits=0,
                used_credits=0
            )
            db.session.add(sl_credit)
        
        sl_remaining = max(0, sl_credit.total_credits - sl_credit.used_credits)
        sl_to_deduct = min(remaining_deduction, sl_remaining)
        
        if sl_to_deduct > 0:
            sl_credit.used_credits += sl_to_deduct
            sl_deducted = sl_to_deduct
            remaining_deduction -= sl_to_deduct
    
    if vl_deducted > 0 or sl_deducted > 0:
        db.session.commit()
    
    return {
        "vl_deducted": round(vl_deducted, 3),
        "sl_deducted": round(sl_deducted, 3),
        "unapplied": round(remaining_deduction, 3)
    }


# =========================================================
# HELPER: CHECK EMPLOYMENT TYPE ELIGIBILITY
# =========================================================
def is_eligible_for_leave_credits(employment_type_id):
    """
    Returns True if employment type is eligible for leave credits.
    🔥 UPDATED: Add more IDs here if needed (e.g., 2 for Part-Time)
    """
    # Current: 1=Regular, 3=Contractual (adjust based on your EmploymentType table)
    return employment_type_id in [1, 2, 3]  # 🔥 Added 2 for flexibility


def get_employment_type_on_date(employee_id, check_date):
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
    
    employee = Employee.query.get(employee_id)
    return employee.employment_type_id if employee else None


# 🔥 FINAL FIX: count_eligible_work_days - Flexible attendance + weekend logic
def count_eligible_work_days(employee, year, month):
    """
    Count eligible work days for leave credit calculation.
    
    POLICY:
    - If employee has ZERO valid attendance records for the entire month → 0 credits
    - If employee has AT LEAST ONE valid attendance record → count:
      * All weekdays with ANY attendance record (time_in is not NULL)
      * ALL weekends (Sat/Sun) in the month
    """
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    if employee.date_hired > start:
        start = employee.date_hired

    current = start
    has_any_valid_attendance = False

    # 🔥 PHASE 1: Check if employee has at least one valid attendance record
    while current <= end:
        emp_type_on_date = get_employment_type_on_date(employee.id, current)
        
        if not is_eligible_for_leave_credits(emp_type_on_date):
            current += timedelta(days=1)
            continue
        
        # 🔥 FLEXIBLE: Check for ANY attendance with time_in (no strict status filter)
        attendance = Attendance.query.filter(
            Attendance.employee_id == employee.id,
            Attendance.date == current,
            Attendance.time_in.isnot(None)
        ).first()
        
        if attendance and attendance.time_in:
            has_any_valid_attendance = True
            break  # Found at least one valid record
        
        current += timedelta(days=1)
    
    # 🔥 If no valid attendance at all for the month, return 0 worked days
    if not has_any_valid_attendance:
        return 0, last_day
    
    # 🔥 PHASE 2: Count eligible days (including weekends)
    current = start
    eligible_worked_days = 0
    
    while current <= end:
        emp_type_on_date = get_employment_type_on_date(employee.id, current)
        
        if not is_eligible_for_leave_credits(emp_type_on_date):
            current += timedelta(days=1)
            continue
        
        weekday = current.weekday()
        
        # 🔥 If weekend (Sat=5, Sun=6), count as worked day (since employee has attendance)
        if weekday in [5, 6]:
            eligible_worked_days += 1
        else:
            # Weekday: count if there's ANY attendance record with time_in
            attendance = Attendance.query.filter(
                Attendance.employee_id == employee.id,
                Attendance.date == current,
                Attendance.time_in.isnot(None)
            ).first()
            
            if attendance and attendance.time_in:
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
# LEAVE CREDIT TABLE
# =========================================================
CREDITS_TABLE = {
    1: 0.042, 2: 0.083, 3: 0.125, 4: 0.167, 5: 0.208,
    6: 0.250, 7: 0.292, 8: 0.333, 9: 0.375, 10: 0.417,
    11: 0.458, 12: 0.500, 13: 0.542, 14: 0.583, 15: 0.625,
    16: 0.667, 17: 0.708, 18: 0.750, 19: 0.792, 20: 0.833,
    21: 0.875, 22: 0.917, 23: 0.958, 24: 1.000, 25: 1.042,
    26: 1.083, 27: 1.125, 28: 1.167, 29: 1.208, 30: 1.250
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
# HELPER: GET MONTHLY LATE SUMMARY
# =========================================================
def get_monthly_late_summary(employee_id, year, month):
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
    
    total_late_minutes = int(round(total_late_seconds / 60.0))
    
    if total_late_minutes <= 0:
        monthly_deduction = 0.0
    elif total_late_minutes <= 60:
        monthly_deduction = late_per_minutes_late_into_leave_credits.get(total_late_minutes, 0)
    else:
        full_hours = total_late_minutes // 60
        remaining_mins = total_late_minutes % 60
        hourly_deduction = full_hours * late_per_minutes_late_into_leave_credits[60]
        minute_deduction = late_per_minutes_late_into_leave_credits.get(remaining_mins, 0) if remaining_mins > 0 else 0
        monthly_deduction = round(hourly_deduction + minute_deduction, 3)
    
    return late_records, monthly_deduction


# =========================================================
# 🆕 ROUTE: APPLY EARNED CREDITS FOR A MONTH - 🔥 FINAL BULLETPROOF
# =========================================================
@leave_officer_bp.route("/history/<int:employee_id>/<int:year>/<int:month>/apply-credits", methods=["POST"])
@login_required
@leave_officer_required
def apply_monthly_credits(employee_id, year, month):
    employee = Employee.query.get_or_404(employee_id)
    
    month_label = f"{calendar.month_abbr[month]} {year}"
    existing_history = LeaveCreditHistory.query.filter_by(
        employee_id=employee_id,
        month=month_label
    ).first()
    
    if existing_history and existing_history.earned > 0:
        flash("⚠️ Credits already applied for this month", "warning")
        return redirect(url_for("leave_officer_bp.view_leave_history", employee_id=employee_id))
    
    # 🔥 HARD CHECK: No valid attendance = 0 credits
    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)
    
    has_valid_attendance = Attendance.query.filter(
        Attendance.employee_id == employee_id,
        Attendance.date >= month_start,
        Attendance.date <= month_end,
        Attendance.time_in.isnot(None)
    ).first()
    
    if not has_valid_attendance:
        flash(f"ℹ️ No valid attendance records for {calendar.month_name[month]} {year} — 0 credits earned", "info")
        return redirect(url_for("leave_officer_bp.view_leave_history", employee_id=employee_id))
    
    worked_days, total_days = count_eligible_work_days(employee, year, month)
    earned_credit = CREDITS_TABLE.get(worked_days, 0)
    
    if earned_credit <= 0:
        flash("ℹ️ No credits to apply (0 eligible work days)", "info")
        return redirect(url_for("leave_officer_bp.view_leave_history", employee_id=employee_id))
    
    for leave_name in ["Sick Leave", "Vacation Leave"]:
        leave_type = LeaveType.query.filter_by(name=leave_name).first()
        if not leave_type:
            continue
        
        credit = LeaveCredit.query.filter_by(
            employee_id=employee_id, 
            leave_type_id=leave_type.id
        ).first()
        
        if not credit:
            credit = LeaveCredit(
                employee_id=employee_id,
                leave_type_id=leave_type.id,
                total_credits=0,
                used_credits=0
            )
            db.session.add(credit)
        
        credit.total_credits += earned_credit
        
        history_entry = LeaveCreditHistory(
            employee_id=employee_id,
            leave_type_id=leave_type.id,
            earned=earned_credit,
            used=0,
            month=month_label
        )
        db.session.add(history_entry)
    
    db.session.commit()
    flash(f"✅ Applied {earned_credit} credits for {calendar.month_name[month]} {year}", "success")
    return redirect(url_for("leave_officer_bp.view_leave_history", employee_id=employee_id))


# =========================================================
# 🆕 ROUTE: APPLY LATE DEDUCTION FOR A MONTH
# =========================================================
@leave_officer_bp.route("/history/<int:employee_id>/<int:year>/<int:month>/apply-late-deduction", methods=["POST"])
@login_required
@leave_officer_required
def apply_late_deduction_route(employee_id, year, month):
    employee = Employee.query.get_or_404(employee_id)
    
    late_records, monthly_late_deduction = get_monthly_late_summary(employee.id, year, month)
    
    if monthly_late_deduction <= 0:
        flash("ℹ️ No late deduction to apply for this month", "info")
        return redirect(url_for("leave_officer_bp.view_leave_history", employee_id=employee_id))
    
    month_label = f"{calendar.month_abbr[month]} {year}"
    vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
    sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
    
    already_applied = False
    if vl_type and sl_type:
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
        if (vl_history and vl_history.used > 0) or (sl_history and sl_history.used > 0):
            already_applied = True
    
    if already_applied:
        flash("⚠️ Late deduction already applied for this month", "warning")
        return redirect(url_for("leave_officer_bp.view_leave_history", employee_id=employee_id))
    
    deduction_breakdown = apply_late_deduction_to_credits(
        employee_id, year, month, monthly_late_deduction
    )
    
    for leave_name, deducted_amount in [
        ("Vacation Leave", deduction_breakdown["vl_deducted"]),
        ("Sick Leave", deduction_breakdown["sl_deducted"])
    ]:
        if deducted_amount > 0:
            leave_type = LeaveType.query.filter_by(name=leave_name).first()
            if leave_type:
                history_entry = LeaveCreditHistory(
                    employee_id=employee_id,
                    leave_type_id=leave_type.id,
                    earned=0,
                    used=deducted_amount,
                    month=month_label
                )
                db.session.add(history_entry)
    
    if deduction_breakdown["unapplied"] > 0:
        fallback_type = vl_type or sl_type
        if fallback_type:
            history_entry = LeaveCreditHistory(
                employee_id=employee_id,
                leave_type_id=fallback_type.id,
                earned=0,
                used=deduction_breakdown["unapplied"],
                month=month_label
            )
            db.session.add(history_entry)
    
    db.session.commit()
    flash(f"✅ Applied late deduction of {monthly_late_deduction} credits (VL: {deduction_breakdown['vl_deducted']}, SL: {deduction_breakdown['sl_deducted']})", "success")
    return redirect(url_for("leave_officer_bp.view_leave_history", employee_id=employee_id))


# =========================================================
# 🆕 MAIN ROUTE: LEAVE CREDIT HISTORY - 🔥 FINAL BULLETPROOF
# =========================================================
@leave_officer_bp.route("/history/<int:employee_id>")
@login_required
@leave_officer_required
def view_leave_history(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    
    # 🔥 REMOVED: generate_leave_history(employee) - This was auto-applying credits incorrectly!

    leave_types = LeaveType.query.filter(
        LeaveType.name.in_(["Sick Leave", "Vacation Leave"])
    ).all()

    history_data = []
    annual_summary = defaultdict(lambda: {"Sick Leave": 0, "Vacation Leave": 0})
    
    # 🔥 FIX: Calculate ALL-TIME SUMMARY from LeaveCreditHistory table
    all_time_summary = {}
    for lt in leave_types:
        total_earned = db.session.query(func.sum(LeaveCreditHistory.earned)).filter_by(
            employee_id=employee_id,
            leave_type_id=lt.id
        ).scalar() or 0
        
        total_used = db.session.query(func.sum(LeaveCreditHistory.used)).filter_by(
            employee_id=employee_id,
            leave_type_id=lt.id
        ).scalar() or 0
        
        all_time_summary[lt.name] = {
            "earned": round(total_earned, 3),
            "used": round(total_used, 3),
            "remaining": round(max(0, total_earned - total_used), 3)
        }

    current = employee.date_hired.replace(day=1)
    today = date.today()

    while current <= today:
        month_label = current.strftime("%b %Y")
        year, month = current.year, current.month
        
        # 🔥 STEP 1: Check attendance FIRST before any calculation
        month_start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)
        
        has_valid_attendance = Attendance.query.filter(
            Attendance.employee_id == employee.id,
            Attendance.date >= month_start,
            Attendance.date <= month_end,
            Attendance.time_in.isnot(None)
        ).first()
        
        # 🔥 STEP 2: If no attendance, skip credit calculation entirely
        if not has_valid_attendance:
            worked_days = 0
            earned_credit = 0  # Force zero
        else:
            worked_days, total_days = count_eligible_work_days(employee, year, month)
            earned_credit = CREDITS_TABLE.get(worked_days, 0)

        late_records, monthly_late_deduction = get_monthly_late_summary(employee.id, year, month)
        leave_usage = get_monthly_leave_usage(employee.id, year, month)

        # 🔥 FIX: Get monthly data - SUM ALL history entries for this month/type
        month_history = {}
        for lt in leave_types:
            history_entries = LeaveCreditHistory.query.filter_by(
                employee_id=employee_id,
                leave_type_id=lt.id,
                month=month_label
            ).all()
            
            total_earned = sum(h.earned for h in history_entries)
            total_used = sum(h.used for h in history_entries)
            
            month_history[lt.name] = {
                "earned": round(total_earned, 3),
                "used": round(total_used, 3)
            }

        # Calculate remaining for this month
        vl_hist = month_history.get("Vacation Leave", {"earned": 0, "used": 0})
        sl_hist = month_history.get("Sick Leave", {"earned": 0, "used": 0})
        
        vl_remaining = max(0, vl_hist["earned"] - vl_hist["used"])
        sl_remaining = max(0, sl_hist["earned"] - sl_hist["used"])

        # 🔥 FIX: Check if ANY used > 0 (credits applied OR late deducted)
        credits_already_applied = vl_hist["earned"] > 0 or sl_hist["earned"] > 0
        late_already_applied = vl_hist["used"] > 0 or sl_hist["used"] > 0

        total_late_seconds = sum(
            (late['late_minutes'] * 60) + late['late_seconds'] 
            for late in late_records
        )
        total_late_minutes_display = f"{total_late_seconds // 60} min {total_late_seconds % 60} sec"
        total_late_minutes_float = round(total_late_seconds / 60.0, 1)

        month_record = {
            "month": current.strftime("%B %Y"),
            "year": year,
            "month_num": month,
            "worked_days": worked_days,
            "total_days": last_day,
            "earned_credit": round(earned_credit, 3),
            "late_deduction": round(monthly_late_deduction, 3),
            "leave_usage": leave_usage,
            "late_deductions": late_records,
            "leave_data": [
                {
                    "leave_type": "Vacation Leave",
                    "earned": vl_hist["earned"],
                    "used": vl_hist["used"],
                    "remaining": vl_remaining,
                    "usage_details": [l for l in leave_usage if l["leave_type"] == "Vacation Leave"]
                },
                {
                    "leave_type": "Sick Leave",
                    "earned": sl_hist["earned"],
                    "used": sl_hist["used"],
                    "remaining": sl_remaining,
                    "usage_details": [l for l in leave_usage if l["leave_type"] == "Sick Leave"]
                }
            ],
            "credits_applied": credits_already_applied,
            "late_applied": late_already_applied,
            # 🔥 FINAL: Only allow applying if: credit > 0 AND not applied AND has attendance
            "can_apply_credits": earned_credit > 0 and not credits_already_applied and has_valid_attendance,
            "can_apply_late": monthly_late_deduction > 0 and not late_already_applied,
            "total_late_seconds": total_late_seconds,
            "total_late_minutes_display": total_late_minutes_display,
            "total_late_minutes_float": total_late_minutes_float,
            # 🔥 Flag for UI to show warning on historical data
            "history_mismatch": credits_already_applied and earned_credit == 0 and vl_hist["earned"] > 0
        }

        for lt in leave_types:
            annual_summary[year][lt.name] += month_history.get(lt.name, {}).get("earned", 0)

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
        annual_summary=sorted_annual,
        all_time_summary=all_time_summary
    )