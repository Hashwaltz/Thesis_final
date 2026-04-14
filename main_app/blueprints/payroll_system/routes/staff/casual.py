from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime, time
from sqlalchemy import and_

from main_app.extensions import db
from main_app.models.hr_models import (
    Employee, Attendance, LeaveCredit, LeaveType, Department, Leave,
    EmployeeShift, Shift, LeaveCreditHistory
)
from main_app.models.payroll_models import (
    Payroll, PayrollPeriod, Loan, PayrollDeduction, LoanPayment
)

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

CASUAL_ID = 3
ALLOWED_LOAN_PROVIDERS_1_15 = {"GSIS", "MENPC"}
ALLOWED_LOAN_PROVIDERS_16_31 = {"MENPC", "Pag-IBIG", "SSS"}
DEFAULT_SHIFT_START = time(8, 0, 0)


# ========================= HELPERS =========================

def safe_float(value):
    try:
        return float(value) if value not in (None, '', 'None') else 0.0
    except (TypeError, ValueError):
        return 0.0


def is_second_half(period):
    return period.start_date.day >= 16


def compute_philhealth(gross_pay):
    if gross_pay <= 10000:
        return 250, 250
    total = round(gross_pay * 0.05, 2)
    return round(total / 2, 2), round(total / 2, 2)


def compute_pagibig(monthly_salary):
    if monthly_salary <= 1500:
        rate = 0.01
    else:
        rate = 0.02
    employee = monthly_salary * rate
    employer = monthly_salary * rate
    employee = min(employee, 200)
    employer = min(employer, 200)
    return round(employee, 2), round(employer, 2)


def resolve_pagibig(monthly_salary, form_value):
    computed_emp, _ = compute_pagibig(monthly_salary)
    if form_value is None:
        return computed_emp
    value_str = str(form_value).strip()
    if value_str == "":
        return computed_emp
    value = safe_float(value_str)
    if value == 0:
        return 0
    return min(value, computed_emp * 1.5)


def get_shift_start_for_date(employee, date):
    """Get official shift start time for an employee on a specific date."""
    daily_shift = EmployeeShift.query.filter_by(
        employee_id=employee.id,
        date=date,
        status="active"
    ).first()
    if daily_shift and daily_shift.shift:
        return daily_shift.shift.start_time
    if hasattr(employee, 'shift') and employee.shift:
        return employee.shift.start_time
    return DEFAULT_SHIFT_START


def compute_late_seconds_from_attendance(employee, period):
    """Calculate total late seconds from attendance records."""
    if not employee or not period:
        return 0
    
    attendances = Attendance.query.filter(
        Attendance.employee_id == employee.id,
        Attendance.date.between(period.start_date, period.end_date)
    ).all()
    
    total_late_seconds = 0
    for att in attendances:
        if not att.time_in:
            continue
        official_start = get_shift_start_for_date(employee, att.date)
        if att.time_in > official_start:
            att_dt = datetime.combine(att.date, att.time_in)
            official_dt = datetime.combine(att.date, official_start)
            delta = att_dt - official_dt
            total_late_seconds += int(delta.total_seconds())
    
    return total_late_seconds


def format_seconds_to_hms(seconds):
    """Convert seconds to HH:MM:SS format."""
    hours = seconds // 3600
    remaining = seconds % 3600
    minutes = remaining // 60
    secs = remaining % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}", hours, minutes, secs


def compute_late_deduction_amount(total_seconds, hourly_rate):
    """Calculate monetary deduction from late seconds."""
    return round((total_seconds * hourly_rate / 3600.0), 2)


def get_leave_credit_info(employee_id, leave_type_name):
    """Get leave credit info without modifying anything."""
    leave_type = LeaveType.query.filter_by(name=leave_type_name).first()
    if not leave_type:
        return {"balance": 0.0, "total": 0.0, "used": 0.0, "exists": False}
    
    credit = LeaveCredit.query.filter_by(
        employee_id=employee_id,
        leave_type_id=leave_type.id
    ).first()
    
    if not credit:
        return {"balance": 0.0, "total": 0.0, "used": 0.0, "exists": False}
    
    balance = max(0.0, credit.total_credits - credit.used_credits)
    return {
        "balance": round(balance, 3),
        "total": round(credit.total_credits, 3),
        "used": round(credit.used_credits, 3),
        "exists": True,
        "credit_id": credit.id,
        "leave_type_id": leave_type.id
    }


def calculate_credit_application(late_amount, daily_rate, vl_info, sl_info):
    """
    Calculate how credits WOULD be applied (preview only - no DB changes).
    Returns dict with what WOULD happen if user chooses to apply credits.
    """
    if daily_rate <= 0:
        return {
            "would_apply": False,
            "vl_to_use": 0, "sl_to_use": 0,
            "credits_value": 0, "remaining_deduction": late_amount
        }
    
    late_days_equiv = late_amount / daily_rate
    remaining = late_days_equiv
    vl_to_use = 0.0
    sl_to_use = 0.0
    
    if remaining > 0 and vl_info["balance"] > 0:
        vl_to_use = min(remaining, vl_info["balance"])
        remaining -= vl_to_use
    
    if remaining > 0 and sl_info["balance"] > 0:
        sl_to_use = min(remaining, sl_info["balance"])
        remaining -= sl_to_use
    
    credits_value = round((vl_to_use + sl_to_use) * daily_rate, 2)
    remaining_deduction = round(remaining * daily_rate, 2)
    
    return {
        "would_apply": (vl_to_use + sl_to_use) > 0,
        "vl_to_use": round(vl_to_use, 3),
        "sl_to_use": round(sl_to_use, 3),
        "credits_value": credits_value,
        "remaining_deduction": remaining_deduction,
        "late_days_equiv": round(late_days_equiv, 3),
        "remaining_days": round(remaining, 3)
    }


def actually_deduct_credits(employee_id, vl_to_use, sl_to_use, period):
    """
    Actually deduct credits from database and record history.
    NOTE: LeaveCreditHistory model does NOT have 'remarks' column.
    """
    if vl_to_use > 0:
        vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
        if vl_type:
            credit = LeaveCredit.query.filter_by(
                employee_id=employee_id,
                leave_type_id=vl_type.id
            ).first()
            if credit:
                credit.used_credits += vl_to_use
                history = LeaveCreditHistory(
                    employee_id=employee_id,
                    leave_type_id=vl_type.id,
                    earned=0,
                    used=vl_to_use,
                    month=f"{period.start_date.month}-{period.start_date.year}"
                )
                db.session.add(history)
    
    if sl_to_use > 0:
        sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
        if sl_type:
            credit = LeaveCredit.query.filter_by(
                employee_id=employee_id,
                leave_type_id=sl_type.id
            ).first()
            if credit:
                credit.used_credits += sl_to_use
                history = LeaveCreditHistory(
                    employee_id=employee_id,
                    leave_type_id=sl_type.id,
                    earned=0,
                    used=sl_to_use,
                    month=f"{period.start_date.month}-{period.start_date.year}"
                )
                db.session.add(history)


def get_paid_leave_days_for_period(employee_id, period):
    """
    Get paid leave days from approved leaves with max_paid_days limit.
    Returns: (paid_days, unpaid_days, leave_details_list)
    """
    leaves = Leave.query.filter(
        Leave.employee_id == employee_id,
        Leave.status == "Approved",
        Leave.end_date >= period.start_date,
        Leave.start_date <= period.end_date
    ).all()
    
    total_paid_days = 0.0
    total_unpaid_days = 0.0
    leave_details = []
    
    for leave in leaves:
        leave_type = leave.leave_type
        
        # Only process leave types with paid day limits (Maternity, Paternity, etc.)
        if not leave_type or not leave_type.max_paid_days:
            continue
            
        # Calculate overlapping days with payroll period
        overlap_start = max(leave.start_date, period.start_date)
        overlap_end = min(leave.end_date, period.end_date)
        
        if overlap_end < overlap_start:
            continue
            
        # Count calendar days
        overlapping_days = (overlap_end - overlap_start).days + 1
        
        # Track remaining paid days for this leave type
        remaining_paid = leave_type.max_paid_days - (leave.paid_days or 0)
        
        # Allocate paid vs unpaid
        paid_for_period = min(overlapping_days, remaining_paid)
        unpaid_for_period = max(0, overlapping_days - paid_for_period)
        
        total_paid_days += paid_for_period
        total_unpaid_days += unpaid_for_period
        
        leave_details.append({
            "leave_type": leave_type.name,
            "paid_days": paid_for_period,
            "unpaid_days": unpaid_for_period,
            "total_overlapping": overlapping_days
        })
    
    return round(total_paid_days, 3), round(total_unpaid_days, 3), leave_details


# ========================= SELECT DEPARTMENT =========================

@payroll_staff_bp.route("/select-department/<int:period_id>") 
@login_required 
@staff_required 
def select_department(period_id): 
    period = PayrollPeriod.query.get_or_404(period_id)
    departments = Department.query.order_by(Department.name).all()
    department_status = {}

    for dept in departments:
        has_payroll = Payroll.query.join(Employee).filter(
            Payroll.payroll_period_id == period.id,
            Employee.department_id == dept.id,
            Employee.employment_type_id == CASUAL_ID
        ).first()
        department_status[dept.id] = bool(has_payroll)

    return render_template(
        "payroll/staff/casual/select_department.html",
        period=period,
        departments=departments,
        department_status=department_status
    )


# ========================= PREVIEW =========================

@payroll_staff_bp.route("/preview/<int:period_id>/<int:department_id>")
@login_required
@staff_required
def preview_department_payroll(period_id, department_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    if period.status == "Locked":
        flash("Payroll already processed for this period.", "warning")
        return redirect(url_for("payroll_staff_bp.select_department", period_id=period.id))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == CASUAL_ID
    ).all()

    payroll_data = []
    second_half = is_second_half(period)

    for emp in employees:
        # --- ATTENDANCE: Days Worked ---
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date.between(period.start_date, period.end_date)
        ).all()

        present_from_attendance = sum(1 for a in attendances if a.status in ("Present", "Late"))
        absent_from_attendance = sum(1 for a in attendances if a.status == "Absent")
        
        # --- ✅ STATUTORY PAID LEAVE (Maternity, Paternity, etc.) ---
        paid_leave_days, unpaid_leave_days, leave_details = get_paid_leave_days_for_period(emp.id, period)
        
        # Combine: paid leave counts as worked days; unpaid portion counts as absent
        present_days = present_from_attendance + paid_leave_days
        absent_days = absent_from_attendance + unpaid_leave_days
        
        # Fallback estimation if attendance data is sparse
        if absent_days == 0 and present_days > 0:
            expected_days = 22  # Adjust based on your work calendar
            absent_days = max(expected_days - present_days, 0)

        # --- VL/SL CREDITS (ONLY for attendance-based absences, NOT statutory leaves) ---
        vl_info = get_leave_credit_info(emp.id, "Vacation Leave")
        sl_info = get_leave_credit_info(emp.id, "Sick Leave")
        
        # Credits apply ONLY to attendance absences (not statutory unpaid days)
        remaining_vl_sl = vl_info["balance"] + sl_info["balance"]
        credits_applied_absent = min(absent_from_attendance, remaining_vl_sl)
        uncovered_days = max(absent_from_attendance - credits_applied_absent, 0) + unpaid_leave_days

        # --- EARNINGS ---
        daily_rate = emp.salary or 0
        hourly_rate = daily_rate / 8.0 if daily_rate else 0.0
        
        # ✅ Paid leave days count toward basic pay (8 hours each)
        basic_pay = present_days * daily_rate
        allowance_total = sum(a.amount for a in (getattr(emp, "allowances", []) or []))
        gross_pay = basic_pay + allowance_total
        awop_amount = round(uncovered_days * daily_rate, 2)

        # --- LATE/UNDERTIME CALCULATION ---
        total_late_seconds = compute_late_seconds_from_attendance(emp, period)
        late_formatted, late_hrs, late_mins, late_secs = format_seconds_to_hms(total_late_seconds)
        late_deduction_original = compute_late_deduction_amount(total_late_seconds, hourly_rate)
        
        # --- PREVIEW: Credit application for late deduction ---
        credit_preview = calculate_credit_application(
            late_deduction_original, daily_rate, vl_info, sl_info
        )
        
        deductions = []

        # 1ST HALF DEDUCTIONS
        if not second_half:
            deductions.append({
                "key": "sss", "name": "SSS",
                "employee_share": safe_float(getattr(emp, "sss_rss", 0)),
                "employer_share": 0, "editable": True, "type": "statutory"
            })
            phic_emp, phic_gov = compute_philhealth(gross_pay)
            deductions.append({
                "key": "philhealth", "name": "PhilHealth",
                "employee_share": phic_emp, "employer_share": phic_gov,
                "editable": True, "gov_visible": True, "type": "statutory"
            })
            allowed = ALLOWED_LOAN_PROVIDERS_1_15
        else:
            computed_sss = safe_float(getattr(emp, "sss_rss", 0))
            deductions.append({
                "key": "sss", "name": "SSS",
                "employee_share": computed_sss, "employer_share": 0, "editable": True, "type": "statutory"
            })
            computed_pagibig_emp, _ = compute_pagibig(gross_pay*2) if 'compute_pagibig' in globals() else (0,0)
            deductions.append({
                "key": "pagibig", "name": "Pag-IBIG",
                "employee_share": computed_pagibig_emp, "employer_share": 0, "editable": True, "type": "statutory"
            })
            allowed = ALLOWED_LOAN_PROVIDERS_16_31

        # AWOP DEDUCTION
        deductions.append({
            "key": "awop", "name": "Absence Without Pay",
            "employee_share": awop_amount, "employer_share": 0, "editable": True,
            "daily_rate": daily_rate, "uncovered_days": uncovered_days,
            "credits_used": credits_applied_absent, "total_absent": absent_days, "type": "awop"
        })

        # LATE/UNDERTIME DEDUCTION
        if late_deduction_original > 0 or late_formatted != "00:00:00":
            deductions.append({
                "key": "late_deduction",
                "name": f"Undertime/Late ({late_formatted})",
                "employee_share": late_deduction_original,
                "employer_share": 0,
                "editable": False,
                "type": "late",
                "late_hours": late_hrs,
                "late_minutes": late_mins,
                "late_seconds": late_secs,
                "late_formatted": late_formatted,
                "late_amount_original": late_deduction_original,
                "vl_balance": vl_info["balance"],
                "vl_total": vl_info["total"],
                "vl_used": vl_info["used"],
                "sl_balance": sl_info["balance"],
                "sl_total": sl_info["total"],
                "sl_used": sl_info["used"],
                "credit_preview": credit_preview,
                "daily_rate": daily_rate,
                "hourly_rate": hourly_rate
            })

        # LOANS
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()
        for loan in loans:
            if loan.provider not in allowed: 
                continue
            deductions.append({
                "key": f"loan_{loan.id}",
                "name": f"{loan.provider} - {loan.loan_type}",
                "employee_share": loan.monthly_payment or 0, "employer_share": 0,
                "loan_id": loan.id, "editable": True, "type": "loan"
            })

        payroll = Payroll()
        payroll.days_worked = present_days
        payroll.basic_salary = basic_pay
        payroll.allowance_total = allowance_total
        payroll.gross_pay = gross_pay

        payroll_data.append({
            "employee": emp, 
            "payroll": payroll, 
            "deductions": deductions,
            "late_info": {
                "original": late_deduction_original,
                "formatted": late_formatted,
                "vl_balance": vl_info["balance"],
                "sl_balance": sl_info["balance"],
                "preview_value": credit_preview["credits_value"],
                "preview_remaining": credit_preview["remaining_deduction"]
            },
            # ✅ Statutory leave summary for template
            "statutory_leaves": leave_details,
            "paid_leave_days": paid_leave_days,
            "unpaid_leave_days": unpaid_leave_days
        })

    template = "payroll/staff/casual/16-31_preview.html" if second_half else "payroll/staff/casual/1-15_preview.html"
    return render_template(template, period=period, department=department, payroll_data=payroll_data)


# ========================= PROCESS =========================

@payroll_staff_bp.route("/process/<int:period_id>/<int:department_id>", methods=["POST"])
@login_required
@staff_required
def process_department_payroll(period_id, department_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)
    employees = Employee.query.filter(
        Employee.status == "Active", Employee.department_id == department.id,
        Employee.employment_type_id == CASUAL_ID
    ).all()
    second_half = is_second_half(period)

    for emp in employees:
        # --- ✅ STATUTORY PAID LEAVE CALCULATION ---
        paid_leave_days, unpaid_leave_days, _ = get_paid_leave_days_for_period(emp.id, period)
        
        # Get attendance-based days
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date.between(period.start_date, period.end_date)
        ).all()
        present_from_attendance = sum(1 for a in attendances if a.status in ("Present", "Late"))
        absent_from_attendance = sum(1 for a in attendances if a.status == "Absent")
        
        # Combine for payroll calculation
        days_worked = present_from_attendance + paid_leave_days
        absent_days = absent_from_attendance + unpaid_leave_days
        
        # Get form values
        days_worked_form = safe_float(request.form.get(f"days_worked_{emp.id}", days_worked))
        allowance_total = safe_float(request.form.get(f"allowance_total_{emp.id}"))
        overtime_pay = safe_float(request.form.get(f"overtime_pay_{emp.id}"))

        daily_rate = emp.salary or 0
        hourly_rate = daily_rate / 8.0 if daily_rate else 0.0
        basic_pay = days_worked_form * daily_rate
        gross_pay = basic_pay + allowance_total + overtime_pay

        payroll = Payroll(
            employee_id=emp.id, payroll_period_id=period.id, days_worked=days_worked_form,
            hours_worked=days_worked_form * 8, basic_salary=basic_pay, allowance_total=allowance_total,
            gross_pay=gross_pay, total_deductions=0, net_pay=0, status="Processed"
        )
        db.session.add(payroll)
        db.session.flush()

        deduction_total = 0

        # GOV DEDUCTIONS
        if not second_half:
            sss = safe_float(request.form.get(f"sss_{emp.id}"))
            deduction_total += sss
            db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="SSS", employee_share=sss, employer_share=0, ec=0))

            phic = safe_float(request.form.get(f"philhealth_{emp.id}"))
            deduction_total += phic
            db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="PhilHealth", employee_share=phic, employer_share=0, ec=0))
            allowed = ALLOWED_LOAN_PROVIDERS_1_15
        else:
            sss = safe_float(request.form.get(f"sss_{emp.id}"))
            deduction_total += sss
            db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="SSS", employee_share=sss, employer_share=0, ec=0))

            pagibig = resolve_pagibig(gross_pay*2, request.form.get(f"pagibig_{emp.id}"))
            deduction_total += pagibig
            db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="Pag-IBIG", employee_share=pagibig, employer_share=0, ec=0))
            allowed = ALLOWED_LOAN_PROVIDERS_16_31

        # AWOP - Only for attendance absences + statutory unpaid days
        awop = safe_float(request.form.get(f"awop_{emp.id}"))
        if awop > 0:
            deduction_total += awop
            db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="Absence Without Pay", employee_share=awop, employer_share=0, ec=0))

        # LATE/UNDERTIME: Check if user opted to apply VL/SL credits
        apply_credits = request.form.get(f"apply_late_credits_{emp.id}") == "true"
        
        total_late_seconds = compute_late_seconds_from_attendance(emp, period)
        late_formatted, late_hrs, late_mins, late_secs = format_seconds_to_hms(total_late_seconds)
        late_deduction_original = compute_late_deduction_amount(total_late_seconds, hourly_rate)
        
        if late_deduction_original > 0:
            if apply_credits:
                vl_info = get_leave_credit_info(emp.id, "Vacation Leave")
                sl_info = get_leave_credit_info(emp.id, "Sick Leave")
                
                credit_calc = calculate_credit_application(
                    late_deduction_original, daily_rate, vl_info, sl_info
                )
                
                if credit_calc["vl_to_use"] > 0 or credit_calc["sl_to_use"] > 0:
                    actually_deduct_credits(
                        emp.id,
                        credit_calc["vl_to_use"],
                        credit_calc["sl_to_use"],
                        period
                    )
                
                late_final = credit_calc["remaining_deduction"]
                
                if late_final > 0:
                    deduction_total += late_final
                    db.session.add(PayrollDeduction(
                        payroll_id=payroll.id,
                        deduction_name=f"Undertime/Late ({late_formatted}) - After Credits",
                        employee_share=late_final,
                        employer_share=0,
                        ec=0
                    ))
                else:
                    db.session.add(PayrollDeduction(
                        payroll_id=payroll.id,
                        deduction_name=f"Undertime/Late ({late_formatted}) - Fully Covered by Credits",
                        employee_share=0,
                        employer_share=0,
                        ec=0
                    ))
            else:
                deduction_total += late_deduction_original
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name=f"Undertime/Late ({late_formatted})",
                    employee_share=late_deduction_original,
                    employer_share=0,
                    ec=0
                ))

        # LOANS
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()
        for loan in loans:
            if loan.provider not in allowed: 
                continue
            val = safe_float(request.form.get(f"loan_{loan.id}"))
            deduction_total += val
            db.session.add(LoanPayment(
                loan_id=loan.id, 
                payroll_id=payroll.id, 
                amount_paid=val,
                remaining_balance=max((loan.remaining_balance or 0) - val, 0),
                payment_date=period.pay_date
            ))

        payroll.total_deductions = round(deduction_total, 2)
        payroll.net_pay = round(gross_pay - deduction_total, 2)

    db.session.commit()
    flash(f"✅ Payroll processed for {department.name} successfully.", "success")
    return redirect(url_for("payroll_staff_bp.select_department", period_id=period.id))