# main_app/blueprints/employee_system/routes/employee.py

from flask import render_template, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from datetime import date, timedelta, datetime, time
import calendar
from collections import defaultdict
from sqlalchemy import func

from main_app.models.hr_models import (
    LeaveCredit, Leave, LeaveType, LeaveCreditHistory, 
    Attendance, Employee, JobHistory
)
from main_app.extensions import db
from main_app.helpers.decorators import employee_required
from main_app.blueprints.employee_system.routes.employee import employee_bp


# =========================================================
# 🔥 HELPER: Check Employment Type Eligibility (Matches Officer Panel)
# =========================================================
def is_eligible_for_leave_credits(employment_type_id):
    """Returns True if employment type is eligible for leave credits."""
    # 1=Regular, 2=Part-Time, 3=Casual (adjust per your EmploymentType table)
    return employment_type_id in [1, 2, 3]


def get_employment_type_on_date(employee_id, check_date):
    """Get employment type effective on a specific date from JobHistory."""
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
    
    # Fallback to current employee record
    employee = Employee.query.get(employee_id)
    return employee.employment_type_id if employee else None


# =========================================================
# 🔥 HELPER: Count Eligible Work Days (Matches Officer Panel EXACTLY)
# =========================================================
def count_eligible_work_days(employee, year, month):
    """
    Count eligible work days for leave credit calculation.
    
    POLICY (Matches Officer Panel):
    - If employee has ZERO valid attendance records for the entire month → 0 credits
    - If employee has AT LEAST ONE valid attendance record → count:
      * All weekdays with ANY attendance record (time_in is not NULL)
      * ALL weekends (Sat/Sun) in the month
    """
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    # Respect hire date
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
        
        # Check for ANY attendance with time_in (no strict status filter)
        attendance = Attendance.query.filter(
            Attendance.employee_id == employee.id,
            Attendance.date == current,
            Attendance.time_in.isnot(None)
        ).first()
        
        if attendance and attendance.time_in:
            has_any_valid_attendance = True
            break
        
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
        
        # Weekend (Sat=5, Sun=6) = counted as worked if employee has any attendance
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
# 🔥 HELPER: Get Monthly Late Summary (Matches Officer Panel)
# =========================================================
def get_monthly_late_summary(employee_id, year, month):
    """Returns late records for display + total deduction amount."""
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
                "time_in": att.time_in.strftime("%I:%M %p") if att.time_in else "N/A",
                "late_minutes": late_mins,
                "late_seconds": late_secs,
                "late_display": f"{late_mins}m {late_secs}s"
            })
    
    # 🔥 Same deduction table as officer panel
    late_per_minutes = {
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
    
    total_late_minutes = int(round(total_late_seconds / 60.0))
    
    if total_late_minutes <= 0:
        monthly_deduction = 0.0
    elif total_late_minutes <= 60:
        monthly_deduction = late_per_minutes.get(total_late_minutes, 0)
    else:
        full_hours = total_late_minutes // 60
        remaining_mins = total_late_minutes % 60
        monthly_deduction = round(
            full_hours * late_per_minutes[60] + 
            late_per_minutes.get(remaining_mins, 0), 3
        )
    
    return late_records, monthly_deduction, total_late_seconds


# =========================================================
# 🔥 HELPER: Get Approved Leave Usage for Month (Matches Officer)
# =========================================================
def get_monthly_leave_usage(employee_id, year, month):
    """Get approved leaves that fall within the given month."""
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
            "reason": leave.reason[:40] + "..." if len(leave.reason) > 40 else leave.reason
        })
    
    return usage


# =========================================================
# 🔄 MAIN ROUTE: Employee Leave History (ALIGNED WITH OFFICER PANEL)
# =========================================================
@employee_bp.route("/leave-history")
@login_required
@employee_required
def leave_history():
    employee = current_user.employee_profile
    if not employee:
        flash('Employee record not found.', 'error')
        return redirect(url_for('employee_auth_bp.logout'))

    # 🔥 Credit accrual table (matches officer panel exactly)
    CREDITS_TABLE = {
        1: 0.042, 2: 0.083, 3: 0.125, 4: 0.167, 5: 0.208,
        6: 0.250, 7: 0.292, 8: 0.333, 9: 0.375, 10: 0.417,
        11: 0.458, 12: 0.500, 13: 0.542, 14: 0.583, 15: 0.625,
        16: 0.667, 17: 0.708, 18: 0.750, 19: 0.792, 20: 0.833,
        21: 0.875, 22: 0.917, 23: 0.958, 24: 1.000, 25: 1.042,
        26: 1.083, 27: 1.125, 28: 1.167, 29: 1.208, 30: 1.250
    }

    leave_types = LeaveType.query.filter(
        LeaveType.name.in_(["Sick Leave", "Vacation Leave"])
    ).all()

    history_data = []
    annual_summary = defaultdict(lambda: {"Sick Leave": 0, "Vacation Leave": 0})
    
    # 🔥 Calculate ALL-TIME SUMMARY from LeaveCreditHistory (matches officer)
    all_time_summary = {}
    for lt in leave_types:
        total_earned = db.session.query(func.sum(LeaveCreditHistory.earned)).filter_by(
            employee_id=employee.id,
            leave_type_id=lt.id
        ).scalar() or 0
        
        total_used = db.session.query(func.sum(LeaveCreditHistory.used)).filter_by(
            employee_id=employee.id,
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
        
        # 🔥 STEP 1: Check attendance FIRST (matches officer logic)
        month_start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)
        
        has_valid_attendance = Attendance.query.filter(
            Attendance.employee_id == employee.id,
            Attendance.date >= month_start,
            Attendance.date <= month_end,
            Attendance.time_in.isnot(None)
        ).first()
        
        # 🔥 STEP 2: If no attendance, skip credit calculation → 0 credits
        if not has_valid_attendance:
            worked_days = 0
            earned_credit = 0
        else:
            worked_days, total_days = count_eligible_work_days(employee, year, month)
            earned_credit = CREDITS_TABLE.get(worked_days, 0)

        # Get late records + deduction
        late_records, monthly_late_deduction, total_late_seconds = get_monthly_late_summary(
            employee.id, year, month
        )
        
        # Get approved leave usage for this month
        leave_usage = get_monthly_leave_usage(employee.id, year, month)

        # 🔥 FIX: Get monthly data by SUMMING all history entries for this month/type
        month_history = {}
        for lt in leave_types:
            history_entries = LeaveCreditHistory.query.filter_by(
                employee_id=employee.id,
                leave_type_id=lt.id,
                month=month_label
            ).all()
            
            total_earned = sum(h.earned for h in history_entries)
            total_used = sum(h.used for h in history_entries)
            
            month_history[lt.name] = {
                "earned": round(total_earned, 3),
                "used": round(total_used, 3)
            }

        # Calculate remaining for display
        vl_hist = month_history.get("Vacation Leave", {"earned": 0, "used": 0})
        sl_hist = month_history.get("Sick Leave", {"earned": 0, "used": 0})
        
        vl_remaining = round(max(0, vl_hist["earned"] - vl_hist["used"]), 3)
        sl_remaining = round(max(0, sl_hist["earned"] - sl_hist["used"]), 3)

        # Format late time display
        total_late_minutes_display = f"{int(total_late_seconds // 60)}m {int(total_late_seconds % 60)}s"
        total_late_minutes_float = round(total_late_seconds / 60.0, 1)

        month_record = {
            "month": current.strftime("%B %Y"),
            "year": year,
            "month_num": month,
            "worked_days": worked_days,
            "total_days": last_day,
            "earned_credit": round(earned_credit, 3),
            "late_deduction": round(monthly_late_deduction, 3),
            "late_records": late_records,
            "leave_usage": leave_usage,
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
            "total_late_seconds": total_late_seconds,
            "total_late_minutes_display": total_late_minutes_display,
            "total_late_minutes_float": total_late_minutes_float,
            # 🔥 Read-only flags for UI display (no action buttons for employees)
            "credits_applied": vl_hist["earned"] > 0 or sl_hist["earned"] > 0,
            "late_applied": vl_hist["used"] > 0 or sl_hist["used"] > 0,
            "has_valid_attendance": bool(has_valid_attendance),
            # Flag for UI to show warning on historical data mismatch
            "history_mismatch": (vl_hist["earned"] > 0 or sl_hist["earned"] > 0) and earned_credit == 0
        }

        # Accumulate annual summary
        for lt in leave_types:
            annual_summary[year][lt.name] += month_history.get(lt.name, {}).get("earned", 0)

        history_data.append(month_record)

        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    # Group by year for accordion (newest first)
    history_by_year = {}
    for record in history_data:
        history_by_year.setdefault(record["year"], []).append(record)
    history_by_year = dict(sorted(history_by_year.items(), reverse=True))
    annual_summary = dict(sorted(annual_summary.items(), reverse=True))

    return render_template(
        "employee/leave_credits.html",
        employee=employee,
        history_by_year=history_by_year,
        annual_summary=annual_summary,
        all_time_summary=all_time_summary  # 🔥 Pass all-time summary for display
    )