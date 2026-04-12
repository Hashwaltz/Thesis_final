from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import and_
from datetime import datetime, time

from main_app.extensions import db
from main_app.models.hr_models import (
    Employee, Attendance, LeaveCredit, Department, Leave, 
    LeaveType, LeaveCreditHistory, EmployeeShift, Shift
)
from main_app.models.payroll_models import (
    Payroll, PayrollPeriod, Loan, PayrollDeduction, 
    EmployeeDeduction, Deduction
)

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

REGULAR_ID = 1
WORKING_DAYS_PER_MONTH = 22
DEFAULT_SHIFT_START = time(8, 0, 0)

# GSIS Configuration (adjust based on your policy)
GSIS_FIXED_RATE = 900.00  # Default fixed monthly contribution
GSIS_PERCENTAGE_RATE = 0.03  # 3% of basic salary (alternative method)
GSIS_USE_PERCENTAGE = False  # Set True to use percentage instead of fixed


# ========================= HELPERS =========================

def safe_float(value):
    try:
        return float(value) if value not in (None, '', 'None') else 0.0
    except (ValueError, TypeError):
        return 0.0


def late_time_to_day_equivalent(hours=0, minutes=0, seconds=0):
    """
    Convert late time to day equivalent for leave credit deduction.
    Uses Excel-equivalent constants: 1hr=0.125 day, 1min=0.002 day
    """
    total_minutes = minutes + (seconds / 60.0)
    day_equiv = (hours * 0.125) + (total_minutes * 0.002)
    return round(day_equiv, 3)


def get_shift_start_for_date(employee, date):
    """Get official shift start time for an employee on a specific date."""
    daily_shift = EmployeeShift.query.filter_by(
        employee_id=employee.id, date=date, status="active"
    ).first()
    if daily_shift and daily_shift.shift:
        return daily_shift.shift.start_time
    if hasattr(employee, 'shift') and employee.shift:
        return employee.shift.start_time
    return DEFAULT_SHIFT_START


def compute_late_from_attendance(employee, period, apply_credits=False):
    """
    Calculate total late time from Attendance.time_in with optional credit application.
    
    Returns dict with deduction amount, time breakdown, and credit application details.
    """
    if not employee or not period:
        return {
            'deduction_amount': 0.0, 'hours': 0, 'minutes': 0, 'seconds': 0,
            'formatted': "00:00:00", 'day_equivalent': 0,
            'credits_applied': 0, 'vl_used': 0, 'sl_used': 0,
            'remaining_day_equiv': 0, 'remaining_amount': 0
        }
    
    daily_rate = employee.salary or 0
    hourly_rate = daily_rate / 8.0 if daily_rate else 0.0
    
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
            total_late_seconds += int((att_dt - official_dt).total_seconds())
    
    # Convert to components
    hours = total_late_seconds // 3600
    remaining = total_late_seconds % 3600
    minutes = remaining // 60
    seconds = remaining % 60
    formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    # Calculate day equivalent and full monetary deduction
    day_equiv = late_time_to_day_equivalent(hours, minutes, seconds)
    full_deduction = round(
        (hours * hourly_rate) + 
        (minutes * hourly_rate / 60.0) + 
        (seconds * hourly_rate / 3600.0), 2
    )
    
    # Default return (no credit application)
    result = {
        'deduction_amount': full_deduction,
        'hours': hours, 'minutes': minutes, 'seconds': seconds,
        'formatted': formatted,
        'day_equivalent': day_equiv,
        'credits_applied': 0, 'vl_used': 0, 'sl_used': 0,
        'remaining_day_equiv': day_equiv, 'remaining_amount': full_deduction
    }
    
    # Apply credits if requested
    if apply_credits and day_equiv > 0:
        credit_result = _apply_credits_to_late(employee, day_equiv, period)
        result.update({
            'deduction_amount': credit_result['remaining_amount'],
            'credits_applied': credit_result['credits_applied'],
            'vl_used': credit_result['vl_used'],
            'sl_used': credit_result['sl_used'],
            'remaining_day_equiv': credit_result['remaining_day_equiv'],
            'remaining_amount': credit_result['remaining_amount']
        })
    
    return result


def _apply_credits_to_late(employee, late_day_equiv, period):
    """
    Internal: Apply VL→SL credits to offset late deduction.
    Returns dict with applied credits and remaining deduction.
    """
    if late_day_equiv <= 0:
        return {
            'credits_applied': 0, 'vl_used': 0, 'sl_used': 0,
            'remaining_day_equiv': 0, 'remaining_amount': 0
        }
    
    daily_rate = employee.salary or 0
    remaining_late = late_day_equiv
    vl_used = sl_used = 0
    
    # Get leave types
    vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
    sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
    
    # STEP 1: Apply Vacation Leave first
    if remaining_late > 0 and vl_type:
        vl_credit = LeaveCredit.query.filter_by(
            employee_id=employee.id, leave_type_id=vl_type.id
        ).first()
        if vl_credit:
            vl_available = max(0, vl_credit.total_credits - vl_credit.used_credits)
            vl_to_use = min(remaining_late, vl_available)
            if vl_to_use > 0:
                vl_used = vl_to_use
                remaining_late -= vl_to_use
    
    # STEP 2: Apply Sick Leave if late time remains
    if remaining_late > 0 and sl_type:
        sl_credit = LeaveCredit.query.filter_by(
            employee_id=employee.id, leave_type_id=sl_type.id
        ).first()
        if sl_credit:
            sl_available = max(0, sl_credit.total_credits - sl_credit.used_credits)
            sl_to_use = min(remaining_late, sl_available)
            if sl_to_use > 0:
                sl_used = sl_to_use
                remaining_late -= sl_to_use
    
    # Calculate monetary value of remaining late time
    remaining_amount = round(remaining_late * daily_rate, 2)
    
    return {
        'credits_applied': round(vl_used + sl_used, 3),
        'vl_used': round(vl_used, 3),
        'sl_used': round(sl_used, 3),
        'remaining_day_equiv': round(remaining_late, 3),
        'remaining_amount': remaining_amount
    }


def compute_ctw(gross, is_daily):
    """CTW: 5% if daily rate applies, else 10%"""
    return gross * (0.05 if is_daily else 0.10)


def compute_gmp_pt(gross):
    """GMP-PT: Fixed 2% of gross"""
    return gross * 0.02


def compute_philhealth(gross):
    """PhilHealth: 2.5% of gross, min ₱250"""
    if gross <= 10000:
        return 250.00, 250.00
    total = round(gross * 0.05, 2)
    return total / 2, total / 2


def compute_gsis(monthly_salary, use_percentage=GSIS_USE_PERCENTAGE):
    """
    GSIS: Fixed amount OR percentage of basic salary.
    
    Args:
        monthly_salary: Employee's monthly basic salary
        use_percentage: If True, use GSIS_PERCENTAGE_RATE; else use GSIS_FIXED_RATE
    
    Returns:
        tuple: (employee_share, employer_share)
    """
    if use_percentage:
        # Percentage-based: e.g., 3% of salary
        emp_share = monthly_salary * GSIS_PERCENTAGE_RATE
    else:
        # Fixed amount: e.g., ₱900/month
        emp_share = GSIS_FIXED_RATE
    
    # Employer share typically matches employee share for GSIS
    employer_share = emp_share
    
    return round(emp_share, 2), round(employer_share, 2)


def get_employee_leave_credits(emp_id):
    """Get total available leave credits for employee"""
    credits = LeaveCredit.query.filter_by(employee_id=emp_id).all()
    return sum(max(0, c.total_credits - c.used_credits) for c in credits)


# ========================= SELECT DEPARTMENT =========================

@payroll_staff_bp.route("/regular/select-department/<int:period_id>")
@login_required
@staff_required
def regular_select_department(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    departments = Department.query.order_by(Department.name).all()

    # Check which departments already have processed payroll
    dept_status = {}
    for dept in departments:
        has_processed = Payroll.query.join(Employee).filter(
            Payroll.payroll_period_id == period.id,
            Payroll.status == "Processed",
            Employee.department_id == dept.id,
            Employee.employment_type_id == REGULAR_ID
        ).first()
        dept_status[dept.id] = "processed" if has_processed else "pending"

    return render_template(
        "payroll/staff/regular/select_department.html",
        period=period,
        departments=departments,
        dept_status=dept_status
    )

# ========================= PREVIEW =========================

@payroll_staff_bp.route("/regular/preview/<int:period_id>/<int:department_id>")
@login_required
@staff_required
def preview_regular_payroll(period_id, department_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    if period.status == "Locked":
        flash("Payroll period is locked.", "warning")
        return redirect(url_for("payroll_staff_bp.regular_select_department", period_id=period.id))

    # Check if already processed
    existing = Payroll.query.join(Employee).filter(
        Payroll.payroll_period_id == period.id,
        Payroll.status == "Processed",
        Employee.department_id == department.id,
        Employee.employment_type_id == REGULAR_ID
    ).first()
    
    if existing:
        flash("This department's payroll was already processed.", "info")
        return redirect(url_for("payroll_staff_bp.regular_select_department", period_id=period.id))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == REGULAR_ID
    ).all()

    payroll_data = []

    for emp in employees:
        monthly_salary = emp.salary or 0
        daily_rate = monthly_salary / WORKING_DAYS_PER_MONTH
        
        # ================= ATTENDANCE & LEAVE =================
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date.between(period.start_date, period.end_date)
        ).all()
        
        present_days = sum(1 for a in attendances if a.status in ("Present", "Late"))
        absent_days = sum(1 for a in attendances if a.status == "Absent")
        
        # Get approved leaves in period
        leaves = Leave.query.filter(
            Leave.employee_id == emp.id,
            Leave.start_date <= period.end_date,
            Leave.end_date >= period.start_date,
            Leave.status == "Approved"
        ).all()
        
        leave_days_in_period = 0
        for leave in leaves:
            start = max(leave.start_date, period.start_date)
            end = min(leave.end_date, period.end_date)
            if start <= end:
                leave_days_in_period += (end - start).days + 1
        
        # Leave credits (for display/reference only - NOT applied to AWOP)
        leave_credits = LeaveCredit.query.filter_by(employee_id=emp.id).all()
        total_credits = sum(lc.total_credits for lc in leave_credits)
        used_credits = sum(lc.used_credits for lc in leave_credits)
        remaining_credits = max(total_credits - used_credits, 0)
        
        # ✅ AWOP calculation: daily_rate × absent_days (NO credits applied)
        # Credits are ONLY applied to late/undertime deductions, not absences
        awop_amount = round(absent_days * daily_rate, 2)
        uncovered_days = absent_days  # All absences are billable as AWOP
        
        # Earnings
        basic_pay = daily_rate * present_days
        allowance_total = sum(
            ea.allowance.amount for ea in emp.employee_allowances 
            if ea.active and ea.allowance
        )
        adjustment_pay = 0
        gross_pay = basic_pay + allowance_total + adjustment_pay
        
        # ================= DEDUCTIONS =================
        deductions = []
        
        # SSS
        sss_ded = EmployeeDeduction.query.filter_by(
            employee_id=emp.id,
            deduction_id=Deduction.query.filter_by(name="SSS").first().id if Deduction.query.filter_by(name="SSS").first() else None
        ).filter_by(active=True).first()
        sss_value = sss_ded.override_amount if sss_ded and sss_ded.override_amount else (getattr(emp, "sss_contribution", 0) or 0)
        
        deductions.append({
            "key": "sss", "name": "SSS", "employee_share": sss_value, 
            "editable": True, "auto_value": sss_value, "type": "fixed",
            "source": "employee_deduction"
        })
        
        # PhilHealth
        phic_ded = EmployeeDeduction.query.filter_by(
            employee_id=emp.id,
            deduction_id=Deduction.query.filter_by(name="PhilHealth").first().id if Deduction.query.filter_by(name="PhilHealth").first() else None
        ).filter_by(active=True).first()
        phic_value = phic_ded.override_amount if phic_ded and phic_ded.override_amount else None
        
        if phic_value is None:
            phic_emp, phic_gov = compute_philhealth(gross_pay)
            phic_value = phic_emp
        else:
            phic_emp, phic_gov = phic_value, 0
        
        deductions.append({
            "key": "philhealth", "name": "PhilHealth", "employee_share": phic_value,
            "editable": True, "auto_rate": 0.025, "type": "percentage", "gross_dependent": True,
            "employer_share": phic_gov, "source": "employee_deduction_or_computed"
        })
        
        # Pag-IBIG
        pagibig_ded = EmployeeDeduction.query.filter_by(
            employee_id=emp.id,
            deduction_id=Deduction.query.filter_by(name="Pag-IBIG").first().id if Deduction.query.filter_by(name="Pag-IBIG").first() else None
        ).filter_by(active=True).first()
        pagibig_value = pagibig_ded.override_amount if pagibig_ded and pagibig_ded.override_amount else (getattr(emp, "pagibig_contribution", 100) or 100)
        
        deductions.append({
            "key": "pagibig", "name": "Pag-IBIG", "employee_share": pagibig_value,
            "editable": True, "auto_value": pagibig_value, "type": "fixed",
            "source": "employee_deduction"
        })
        
        # ✅ GSIS with Auto-Compute
        gsis_ded = EmployeeDeduction.query.filter_by(
            employee_id=emp.id,
            deduction_id=Deduction.query.filter_by(name="GSIS").first().id if Deduction.query.filter_by(name="GSIS").first() else None
        ).filter_by(active=True).first()
        
        # Check if there's an override value
        gsis_override = gsis_ded.override_amount if gsis_ded and gsis_ded.override_amount else None
        
        if gsis_override is not None:
            # Use stored override value
            gsis_value = gsis_override
            gsis_gov = 0
            gsis_auto_info = f"Override: ₱{gsis_value:,.2f}"
        else:
            # Auto-compute based on configuration
            gsis_emp, gsis_gov = compute_gsis(monthly_salary)
            gsis_value = gsis_emp
            gsis_auto_info = f"{'3% of salary' if GSIS_USE_PERCENTAGE else f'Fixed: ₱{GSIS_FIXED_RATE:,.2f}'}"
        
        deductions.append({
            "key": "gsis", "name": "GSIS", "employee_share": gsis_value,
            "editable": True, "auto_value": gsis_value, "type": "fixed_or_percentage",
            "employer_share": gsis_gov, "source": "auto_computed_or_override",
            "auto_info": gsis_auto_info  # For display in template
        })
        
        # ✅ AWOP with NO credit application (credits only for late deductions)
        deductions.append({
            "key": "awop", 
            "name": "Absence Without Pay", 
            "employee_share": awop_amount,
            "editable": True, 
            "auto_value": awop_amount, 
            "type": "awop",
            "daily_rate": daily_rate, 
            "total_absent_days": absent_days,
            "credits_applied": 0,           # ✅ Explicitly zero - credits don't apply to AWOP
            "uncovered_days": absent_days,  # ✅ All absences = AWOP days
            "calculation": f"{absent_days} × ₱{daily_rate:,.2f} = ₱{awop_amount:,.2f}",
            "source": "attendance_records"
        })
        
        # ✅ LATE/UNDERTIME DEDUCTION WITH CREDIT APPLICATION (credits ONLY apply here)
        late_result = compute_late_from_attendance(emp, period, apply_credits=True)
        
        # Calculate original deduction amount from day_equivalent × daily_rate
        original_late_amount = round(late_result['day_equivalent'] * daily_rate, 2)
        
        # Only add late deduction if there's actual late time recorded
        if late_result['hours'] > 0 or late_result['minutes'] > 0 or late_result['seconds'] > 0:
            deductions.append({
                "key": "late_deduction",
                "name": f"Undertime/Late ({late_result['formatted']})",
                "employee_share": late_result['deduction_amount'],
                "employer_share": 0,
                "editable": False,  # 🔒 Read-only - auto-calculated
                "type": "late",
                # Time breakdown for display
                "late_hours": late_result['hours'],
                "late_minutes": late_result['minutes'],
                "late_seconds": late_result['seconds'],
                "late_formatted": late_result['formatted'],
                # Credit application details (VL→SL)
                "credits_applied": late_result['credits_applied'],
                "vl_used": late_result['vl_used'],
                "sl_used": late_result['sl_used'],
                "original_day_equiv": late_result['day_equivalent'],
                "remaining_day_equiv": late_result['remaining_day_equiv'],
                "daily_rate": daily_rate,
                "original_amount": original_late_amount
            })
        
        # Loans
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()
        for loan in loans:
            deductions.append({
                "key": f"loan_{loan.id}",
                "name": f"{loan.provider} - {loan.loan_type}",
                "employee_share": loan.monthly_payment or 0,
                "editable": True,
                "auto_value": loan.monthly_payment or 0,
                "type": "loan",
                "loan_id": loan.id,
                "source": "loan_table"
            })
        
        # Pass data to template
        payroll_data.append({
            "employee": emp,
            "days_worked": present_days,
            "leave_days": leave_days_in_period,
            "absences": absent_days,
            "basic_pay": basic_pay,
            "allowance_total": allowance_total,
            "gross_pay": gross_pay,
            "adjustment_pay": adjustment_pay,
            "deductions": deductions,
            "awop_suggested": awop_amount,
            "awop_days": absent_days,  # Changed from uncovered_days
            "daily_rate": daily_rate,
            "available_credits": remaining_credits,  # For display only
            # Late deduction data for template
            "late_deduction": late_result['deduction_amount'],
            "late_formatted": late_result['formatted'],
            "late_credits_applied": late_result['credits_applied'],
            "late_vl_used": late_result['vl_used'],
            "late_sl_used": late_result['sl_used'],
            "late_original_equiv": late_result['day_equivalent'],
            "late_remaining_equiv": late_result['remaining_day_equiv'],
            "late_original_amount": original_late_amount,
            # For display
            "actual_attendance": {
                "present": present_days,
                "absent": absent_days,
                "late": sum(1 for a in attendances if a.status == "Late")
            },
            "actual_leave": {
                "days_in_period": leave_days_in_period,
                "credits_used": used_credits,
                "credits_remaining": remaining_credits
            }
        })

    return render_template(
        "payroll/staff/regular/payroll_preview.html",
        period=period,
        department=department,
        payroll_data=payroll_data
    )

# ========================= PROCESS =========================

@payroll_staff_bp.route("/regular/process/<int:period_id>/<int:department_id>", methods=["POST"])
@login_required
@staff_required
def process_regular_payroll(period_id, department_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    # Double-check not already processed
    existing = Payroll.query.join(Employee).filter(
        Payroll.payroll_period_id == period.id,
        Payroll.status == "Processed",
        Employee.department_id == department.id,
        Employee.employment_type_id == REGULAR_ID
    ).first()
    
    if existing:
        flash("This department was already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.regular_select_department", period_id=period.id))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == REGULAR_ID
    ).all()

    processed_count = 0

    for emp in employees:
        monthly_salary = emp.salary or 0
        daily_rate = monthly_salary / WORKING_DAYS_PER_MONTH

        # Get attendance for days worked
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date.between(period.start_date, period.end_date)
        ).all()
        worked_days = sum(1 for a in attendances if a.status in ("Present", "Late"))

        basic_pay = daily_rate * worked_days
        allowance_total = safe_float(request.form.get(f"allowance_{emp.id}", 0))
        overtime_pay = safe_float(request.form.get(f"overtime_{emp.id}", 0))
        
        gross_pay = monthly_salary + allowance_total + overtime_pay

        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            days_worked=worked_days,
            basic_salary=basic_pay,
            allowance_total=allowance_total,
            gross_pay=gross_pay,
            status="Processed"
        )

        db.session.add(payroll)
        db.session.flush()

        total_deductions = 0

        # Government deductions
        sss = safe_float(request.form.get(f"sss_{emp.id}", 0))
        philhealth = safe_float(request.form.get(f"philhealth_{emp.id}", 0))
        pagibig = safe_float(request.form.get(f"pagibig_{emp.id}", 0))
        gsis = safe_float(request.form.get(f"gsis_{emp.id}", 0))

        total_deductions += sss + philhealth + pagibig + gsis

        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="SSS", employee_share=round(sss, 2)))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="PhilHealth", employee_share=round(philhealth, 2)))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="Pag-IBIG", employee_share=round(pagibig, 2)))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="GSIS", employee_share=round(gsis, 2)))

        # Taxes
        ctw_tax_input = request.form.get(f"ctw_tax_{emp.id}", "").strip()
        ctw_tax = safe_float(ctw_tax_input) if ctw_tax_input else compute_ctw(gross_pay, request.form.get(f"ctw_{emp.id}") == "on")
        
        gmp_pt_tax_input = request.form.get(f"gmp_pt_tax_{emp.id}", "").strip()
        gmp_pt_tax = safe_float(gmp_pt_tax_input) if gmp_pt_tax_input else compute_gmp_pt(gross_pay)

        total_deductions += ctw_tax + gmp_pt_tax

        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="CTW Tax", employee_share=round(ctw_tax, 2)))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="GMP-PT", employee_share=round(gmp_pt_tax, 2)))

        # Loans
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()
        for loan in loans:
            val = safe_float(request.form.get(f"loan_{loan.id}", 0))
            total_deductions += val
            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name=f"{loan.provider} Loan",
                employee_share=round(val, 2)
            ))

        # AWOP
        awop = safe_float(request.form.get(f"awop_{emp.id}", 0))
        if awop > 0:
            total_deductions += awop
            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name="Absence Without Pay",
                employee_share=round(awop, 2)
            ))

        # ✅ LATE/UNDERTIME DEDUCTION WITH CREDIT APPLICATION & PERSISTENCE
        late_result = compute_late_from_attendance(emp, period, apply_credits=True)
        
        if late_result['deduction_amount'] > 0:
            total_deductions += late_result['deduction_amount']
            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name=f"Undertime/Late ({late_result['formatted']})",
                employee_share=round(late_result['deduction_amount'], 2),
                employer_share=0,
                ec=0
            ))
        
        # 🎯 PERSIST LEAVE CREDIT USAGE IF APPLIED TO LATE
        if late_result['credits_applied'] > 0:
            vl_type = LeaveType.query.filter_by(name="Vacation Leave").first()
            sl_type = LeaveType.query.filter_by(name="Sick Leave").first()
            
            if late_result['vl_used'] > 0 and vl_type:
                vl_credit = LeaveCredit.query.filter_by(employee_id=emp.id, leave_type_id=vl_type.id).first()
                if vl_credit:
                    vl_credit.used_credits += late_result['vl_used']
                    history = LeaveCreditHistory(
                        employee_id=emp.id,
                        leave_type_id=vl_type.id,
                        earned=0,
                        used=late_result['vl_used'],
                        month=f"{period.start_date.month}-{period.start_date.year}"
                    )
                    db.session.add(history)
            
            if late_result['sl_used'] > 0 and sl_type:
                sl_credit = LeaveCredit.query.filter_by(employee_id=emp.id, leave_type_id=sl_type.id).first()
                if sl_credit:
                    sl_credit.used_credits += late_result['sl_used']
                    history = LeaveCreditHistory(
                        employee_id=emp.id,
                        leave_type_id=sl_type.id,
                        earned=0,
                        used=late_result['sl_used'],
                        month=f"{period.start_date.month}-{period.start_date.year}"
                    )
                    db.session.add(history)

        # Finalize payroll
        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(gross_pay - total_deductions, 2)
        
        processed_count += 1

    # ✅ MARK DEPARTMENT AS PROCESSED FOR THIS PERIOD
    db.session.commit()
    
    flash(f"✅ Processed payroll for {processed_count} employee(s) in {department.name}. Department marked as processed.", "success")
    return redirect(url_for("payroll_staff_bp.regular_select_department", period_id=period.id))