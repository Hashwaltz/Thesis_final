from flask import render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import date, timedelta
import calendar

from main_app.models.hr_models import LeaveCredit, Leave, LeaveType, LeaveCreditHistory, Attendance
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



# Add these imports at the top if missing
from collections import defaultdict
from datetime import datetime, time, timedelta
import calendar

# ... [keep your existing helper functions: count_work_days, ensure_leave_history] ...

# =========================================================
# 🆕 HELPER: Get Monthly Late Summary (for display + deduction)
# =========================================================
def get_monthly_late_summary(employee_id, year, month):
    """Returns late records for display + total deduction amount."""
    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)
    
    attendances = Attendance.query.filter(
        Attendance.employee_id == employee_id,
        Attendance.date >= month_start,
        Attendance.date <= month_end,
        Attendance.status.in_(['Present', 'Late'])
    ).order_by(Attendance.date).all()
    
    late_records = []
    total_late_seconds = 0.0
    
    for att in attendances:
        if att.time_in and att.time_in > time(8, 0):
            late_seconds = (datetime.combine(att.date, att.time_in) - 
                           datetime.combine(att.date, time(8, 0))).total_seconds()
            if late_seconds > 0:
                total_late_seconds += late_seconds
                late_mins = int(late_seconds // 60)
                late_secs = int(round(late_seconds % 60))
                late_records.append({
                    "date": att.date.strftime("%Y-%m-%d"),
                    "time_in": att.time_in.strftime("%I:%M %p"),
                    "late_display": f"{late_mins}m {late_secs}s"
                })
    
    # Calculate deduction using your dictionary logic
    late_per_minutes = {
        1: .002, 2: .004, 3: .006, 4: .008, 5: .010, 6: .012, 7: .015, 8: .017,
        # ... [include your full dictionary here] ...
        60: .125
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
    
    return late_records, monthly_deduction


# =========================================================
# 🆕 HELPER: Calculate Net Credits After VL-First Deduction
# =========================================================
def calculate_net_credits_display(earned_credit, late_deduction, employee_id):
    """Calculates net VL/SL balances after applying late deduction (VL first, then SL)."""
    vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
    sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
    
    result = {
        "vl_net": earned_credit,
        "sl_net": earned_credit,
        "vl_deducted": 0,
        "sl_deducted": 0,
        "unapplied": 0
    }
    
    if late_deduction <= 0 or not vl_type:
        return result
    
    remaining = late_deduction
    
    # Deduct from VL first
    vl_credit = LeaveCredit.query.filter_by(
        employee_id=employee_id, leave_type_id=vl_type.id
    ).first()
    if vl_credit:
        vl_available = max(0, vl_credit.total_credits - vl_credit.used_credits)
        vl_deduct = min(remaining, vl_available)
        result["vl_deducted"] = round(vl_deduct, 3)
        result["vl_net"] = round(max(0, earned_credit - vl_deduct), 3)
        remaining -= vl_deduct
    
    # Deduct remaining from SL
    if remaining > 0 and sl_type:
        sl_credit = LeaveCredit.query.filter_by(
            employee_id=employee_id, leave_type_id=sl_type.id
        ).first()
        if sl_credit:
            sl_available = max(0, sl_credit.total_credits - sl_credit.used_credits)
            sl_deduct = min(remaining, sl_available)
            result["sl_deducted"] = round(sl_deduct, 3)
            result["sl_net"] = round(max(0, earned_credit - sl_deduct), 3)
            remaining -= sl_deduct
    
    result["unapplied"] = round(max(0, remaining), 3)
    return result


# =========================================================
# 🔄 UPDATED ROUTE: Employee Leave History
# =========================================================
@employee_bp.route("/leave-history")
@login_required
@employee_required
def leave_history():
    employee = current_user.employee_profile
    if not employee:
        flash('Employee record not found.', 'error')
        return redirect(url_for('employee_auth_bp.logout'))

    leave_types = LeaveType.query.filter(
        LeaveType.name.in_(["Sick Leave", "Vacation Leave"])
    ).all()

    CREDITS_TABLE = {
        1: 0.042, 2: 0.083, 3: 0.125, 4: 0.167, 5: 0.208,
        6: 0.250, 7: 0.292, 8: 0.333, 9: 0.375, 10: 0.417,
        11: 0.458, 12: 0.500, 13: 0.542, 14: 0.583, 15: 0.625,
        16: 0.667, 17: 0.708, 18: 0.750, 19: 0.792, 20: 0.833,
        21: 0.875, 22: 0.917, 23: 0.958, 24: 1.000, 25: 1.042,
        26: 1.083, 27: 1.125, 28: 1.167, 29: 1.208, 30: 1.250
    }

    history_data = []
    annual_summary = defaultdict(lambda: {"Sick Leave": 0, "Vacation Leave": 0})
    current = employee.date_hired.replace(day=1)
    today = date.today()

    while current <= today:
        month_label = current.strftime("%b %Y")
        year, month = current.year, current.month
        
        worked_days, total_days = count_work_days(employee, year, month)
        earned_credit = CREDITS_TABLE.get(worked_days, 0)
        
        # Get late records + deduction
        late_records, monthly_late_deduction = get_monthly_late_summary(employee.id, year, month)
        
        # Get approved leave usage for this month
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        leave_usage = Leave.query.filter(
            Leave.employee_id == employee.id,
            Leave.status == "Approved",
            Leave.start_date <= month_end,
            Leave.end_date >= month_start
        ).all()
        usage_details = []
        for lv in leave_usage:
            actual_start = max(lv.start_date, month_start)
            actual_end = min(lv.end_date, month_end)
            days = (actual_end - actual_start).days + 1
            usage_details.append({
                "leave_type": lv.leave_type.name,
                "start": actual_start.strftime("%Y-%m-%d"),
                "end": actual_end.strftime("%Y-%m-%d"),
                "days": days,
                "reason": lv.reason[:40] + "..." if len(lv.reason) > 40 else lv.reason
            })

        # Calculate net credits after VL-first deduction (for display)
        net_credits = calculate_net_credits_display(earned_credit, monthly_late_deduction, employee.id)

        month_record = {
            "month": current.strftime("%B %Y"),
            "year": year,
            "worked_days": worked_days,
            "total_days": total_days,
            "earned_credit": round(earned_credit, 3),
            "late_deduction": monthly_late_deduction,
            "late_records": late_records,
            "leave_usage": usage_details,
            "net_credits": net_credits,
            "leave_data": []
        }

        for lt in leave_types:
            history = LeaveCreditHistory.query.filter_by(
                employee_id=employee.id,
                leave_type_id=lt.id,
                month=month_label
            ).first()
            
            if history:
                used = round(history.used, 3)
                remaining = round(max(0, history.earned - history.used), 3)
                month_record["leave_data"].append({
                    "leave_type": lt.name,
                    "earned": round(history.earned, 3),
                    "used": used,
                    "remaining": remaining,
                    "usage": [u for u in usage_details if u["leave_type"] == lt.name]
                })
                annual_summary[year][lt.name] += history.earned

        history_data.append(month_record)

        # Move to next month
        current = current.replace(month=current.month + 1) if current.month < 12 else current.replace(year=current.year + 1, month=1)

    # Group by year for accordion
    history_by_year = defaultdict(list)
    for rec in history_data:
        history_by_year[rec["year"]].append(rec)
    history_by_year = dict(sorted(history_by_year.items(), reverse=True))
    annual_summary = dict(sorted(annual_summary.items(), reverse=True))

    return render_template(
        "employee/leave_credits.html",
        employee=employee,
        history_by_year=history_by_year,
        annual_summary=annual_summary
    )