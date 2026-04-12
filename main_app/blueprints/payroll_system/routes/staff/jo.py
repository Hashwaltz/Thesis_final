from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import extract
from datetime import datetime, time, timedelta

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance, Department, EmployeeShift, Shift
from main_app.models.payroll_models import Payroll, PayrollPeriod, Loan, PayrollDeduction, LoanPayment

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

JOB_ORDER_ID = 5

# ========================= CONSTANTS =========================
ALLOWED_LOAN_1_15 = {"Pag-IBIG", "MENPC"}
ALLOWED_LOAN_16_END = {"Pag-IBIG", "MENPC", "SSS"}
DEFAULT_SHIFT_START = time(8, 0, 0)   # 8:00 AM default
DEFAULT_SHIFT_END = time(17, 0, 0)    # 5:00 PM default

# ========================= HELPERS =========================

def safe_float(value):
    try:
        return float(value) if value not in (None, '', 'None') else 0.0
    except (ValueError, TypeError):
        return 0.0


def is_second_half(period):
    """Check if payroll period is 16th to end of month"""
    return period.start_date.day >= 16


def compute_philhealth(gross):
    """PhilHealth: ₱250 each if gross ≤10k, else 2.5% split"""
    if gross <= 10000:
        return 250.0, 250.0
    total = round(gross * 0.05, 2)
    return total / 2, total / 2


def compute_withholding_tax(gross):
    """Simplified withholding tax: 2% of gross"""
    return round(gross * 0.02, 2)


def get_shift_start_for_date(employee, date):
    """
    Get the official shift start time for an employee on a specific date.
    Checks EmployeeShift first, falls back to employee's default shift, then to default 8 AM.
    """
    # 1. Check for date-specific EmployeeShift assignment
    daily_shift = EmployeeShift.query.filter_by(
        employee_id=employee.id,
        date=date,
        status="active"
    ).first()
    
    if daily_shift and daily_shift.shift:
        return daily_shift.shift.start_time
    
    # 2. Fallback to employee's default shift (if stored on Employee model)
    if hasattr(employee, 'shift') and employee.shift:
        return employee.shift.start_time
    
    # 3. Final fallback: default 8:00 AM
    return DEFAULT_SHIFT_START


def compute_late_from_attendance(employee, period):
    """
    Calculates total late time DIRECTLY from Attendance.time_in.
    Uses employee's assigned shift (or default 8 AM) as official start time.
    Returns: (deduction_amount, hours, minutes, seconds, "HH:MM:SS")
    """
    if not employee or not period:
        return 0.0, 0, 0, 0, "00:00:00"
    
    daily_rate = employee.salary or 0
    hourly_rate = daily_rate / 8.0 if daily_rate else 0.0
    
    # Fetch attendance records in period
    attendances = Attendance.query.filter(
        Attendance.employee_id == employee.id,
        Attendance.date.between(period.start_date, period.end_date)
    ).all()
    
    total_late_seconds = 0
    
    for att in attendances:
        if not att.time_in:
            continue
            
        # Get official shift start for this specific date
        official_start = get_shift_start_for_date(employee, att.date)
        
        # Only count as late if time_in is after official start
        if att.time_in > official_start:
            att_dt = datetime.combine(att.date, att.time_in)
            official_dt = datetime.combine(att.date, official_start)
            delta = att_dt - official_dt
            total_late_seconds += int(delta.total_seconds())
            
    # Convert total seconds to HH:MM:SS
    hours = total_late_seconds // 3600
    remaining = total_late_seconds % 3600
    minutes = remaining // 60
    seconds = remaining % 60
    formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    # Calculate monetary deduction with second precision
    deduction = (
        (hours * hourly_rate) + 
        (minutes * hourly_rate / 60.0) + 
        (seconds * hourly_rate / 3600.0)
    )
    
    return round(deduction, 2), hours, minutes, seconds, formatted


# ========================= SELECT DEPARTMENT =========================

@payroll_staff_bp.route("/jo/select-department/<int:period_id>")
@login_required
@staff_required
def jo_select_department(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    departments = Department.query.order_by(Department.name).all()

    department_status = {}

    for dept in departments:
        has_payroll = Payroll.query.join(Employee).filter(
            Payroll.payroll_period_id == period.id,
            Employee.department_id == dept.id,
            Employee.employment_type_id == JOB_ORDER_ID
        ).first()
        department_status[dept.id] = bool(has_payroll)

    return render_template(
        "payroll/staff/JO/select_department.html",
        period=period,
        departments=departments,
        department_status=department_status
    )


@payroll_staff_bp.route("/jo/preview/<int:period_id>/<int:department_id>")
@login_required
@staff_required
def preview_jo_payroll(period_id, department_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    if period.status == "Locked":
        flash("Payroll period is locked.", "warning")
        return redirect(url_for("payroll_staff_bp.jo_select_department", period_id=period.id))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == JOB_ORDER_ID
    ).all()

    second_half = is_second_half(period)
    payroll_data = []

    for emp in employees:
        # --- ATTENDANCE: Days Worked (Present + Late) ---
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date.between(period.start_date, period.end_date)
        ).all()
        
        worked_days = sum(1 for a in attendances if a.status in ("Present", "Late"))
        worked_days = max(worked_days, 0)

        # --- EARNINGS ---
        daily_rate = emp.salary or 0
        basic_pay = worked_days * daily_rate
        
        # Fetch existing overtime if editing
        existing_payroll = Payroll.query.filter_by(
            employee_id=emp.id,
            payroll_period_id=period.id
        ).first()
        
        # Safely get overtime pay (avoid read-only property assignment later)
        overtime_pay = (existing_payroll.overtime_hours * ((emp.salary or 0)/8) * 1.25) if existing_payroll else 0
        overtime_pay = round(overtime_pay, 2)
        
        gross_pay = basic_pay + overtime_pay

        # --- LATE/UNDERTIME DEDUCTION (SHIFT-AWARE, DIRECT FROM ATTENDANCE) ---
        late_deduction, late_hrs, late_mins, late_secs, late_formatted = compute_late_from_attendance(emp, period)

        # --- DEDUCTIONS LIST ---
        deductions = []
        total_deductions = 0

        if not second_half:
            # === 1-15 HALF: SSS + PhilHealth only ===
            sss = getattr(emp, "sss_rss", 0) or 0
            phic_emp, phic_gov = compute_philhealth(gross_pay)

            deductions.append({
                "key": "sss", "name": "SSS", "employee_share": sss,
                "employer_share": 0, "editable": True, "type": "statutory"
            })
            deductions.append({
                "key": "philhealth", "name": "PhilHealth", "employee_share": phic_emp,
                "employer_share": 0, "editable": True, "type": "statutory"
            })
            total_deductions += sss + phic_emp
            allowed_loans = ALLOWED_LOAN_1_15

        else:
            # === 16-END HALF: Full deductions + tax carryover ===
            sss = safe_float(request.form.get(f"sss_{emp.id}")) if existing_payroll else (getattr(emp, "sss_rss", 0) or 0)
            phic_emp, phic_gov = compute_philhealth(gross_pay)
            
            # Fetch 1-15 period for tax carryover
            first_half_period = PayrollPeriod.query.filter(
                extract('month', PayrollPeriod.start_date) == period.start_date.month,
                extract('year', PayrollPeriod.start_date) == period.start_date.year,
                extract('day', PayrollPeriod.start_date) == 1,
                extract('day', PayrollPeriod.end_date) == 15
            ).first()

            previous_payroll = None
            if first_half_period:
                previous_payroll = Payroll.query.filter_by(
                    employee_id=emp.id,
                    payroll_period_id=first_half_period.id
                ).first()

            current_tax = compute_withholding_tax(gross_pay)
            previous_gross = previous_payroll.gross_pay if previous_payroll else 0
            previous_tax = compute_withholding_tax(previous_gross)

            if sss > 0:
                deductions.append({"key": "sss", "name": "SSS", "employee_share": sss,
                                 "employer_share": 0, "editable": True, "type": "statutory"})
                total_deductions += sss

            if phic_emp > 0:
                deductions.append({"key": "philhealth", "name": "PhilHealth", "employee_share": phic_emp,
                                 "employer_share": phic_gov, "editable": False, "type": "statutory"})
                total_deductions += phic_emp

            if previous_tax > 0:
                deductions.append({"key": "tax_prev", "name": "Withholding Tax (1–15)",
                                 "employee_share": previous_tax, "employer_share": 0,
                                 "editable": False, "type": "tax"})
                total_deductions += previous_tax

            if current_tax > 0:
                deductions.append({"key": "tax_curr", "name": "Withholding Tax (16–End)",
                                 "employee_share": current_tax, "employer_share": 0,
                                 "editable": False, "type": "tax"})
                total_deductions += current_tax

            allowed_loans = ALLOWED_LOAN_16_END

        # --- LATE/UNDERTIME DEDUCTION ENTRY ---
        if late_deduction > 0 or late_formatted != "00:00:00":
            deductions.append({
                "key": "late_deduction",
                "name": f"Undertime/Late ({late_formatted})",
                "employee_share": late_deduction,
                "employer_share": 0,
                "editable": True,
                "type": "late",
                "late_hours": late_hrs,
                "late_minutes": late_mins,
                "late_seconds": late_secs,
                "late_formatted": late_formatted
            })
            total_deductions += late_deduction

        # --- LOANS ---
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()
        for loan in loans:
            if loan.provider not in allowed_loans:
                continue
            deductions.append({
                "key": f"loan_{loan.id}",
                "name": f"{loan.provider} - {loan.loan_type}",
                "employee_share": loan.monthly_payment or 0,
                "employer_share": 0,
                "loan_id": loan.id,
                "editable": True,
                "type": "loan"
            })
            total_deductions += loan.monthly_payment or 0

        # --- BUILD PAYROLL OBJECT (for template compatibility) ---
        payroll_stub = type('PayrollStub', (), {
            'days_worked': worked_days,
            'basic_salary': basic_pay,
            'gross_pay': gross_pay,
            'total_deductions': total_deductions,
            'net_pay': gross_pay - total_deductions,
            'overtime_hours': existing_payroll.overtime_hours if existing_payroll else 0,
        })()

        payroll_data.append({
            "employee": emp,
            "payroll": payroll_stub,
            "deductions": deductions,
            "overtime_pay": overtime_pay,
            "late_deduction": late_deduction,
            "late_hours": late_hrs,
            "late_minutes": late_mins,
            "late_seconds": late_secs,
            "late_formatted": late_formatted
        })

    template = (
        "payroll/staff/JO/16_end_preview.html"
        if second_half else
        "payroll/staff/JO/1_15_preview.html"
    )

    return render_template(
        template,
        period=period,
        department=department,
        payroll_data=payroll_data
    )


# ========================= PROCESS: SAVE PAYROLL =========================

@payroll_staff_bp.route("/jo/process/<int:period_id>/<int:department_id>", methods=["POST"])
@login_required
@staff_required
def process_jo_payroll(period_id, department_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == JOB_ORDER_ID
    ).all()

    second_half = is_second_half(period)

    for emp in employees:
        # --- INPUT VALUES ---
        days_worked = safe_float(request.form.get(f"days_worked_{emp.id}"))
        overtime_pay = safe_float(request.form.get(f"overtime_{emp.id}"))
        daily_rate = emp.salary or 0
        basic_pay = days_worked * daily_rate
        gross_pay = basic_pay + overtime_pay

        # --- CREATE PAYROLL RECORD ---
        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            days_worked=days_worked,
            hours_worked=days_worked * 8,
            basic_salary=gross_pay,
            allowance_total=0,
            gross_pay=gross_pay,
            total_deductions=0,
            net_pay=0,
            status="Processed"
        )
        db.session.add(payroll)
        db.session.flush()

        total_deductions = 0

        # ================= 1–15 DEDUCTIONS =================
        if not second_half:
            sss = safe_float(request.form.get(f"sss_{emp.id}"))
            if sss > 0:
                total_deductions += sss
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id, deduction_name="SSS", employee_share=sss, employer_share=0, ec=0
                ))

            phic_emp = safe_float(request.form.get(f"philhealth_{emp.id}"))
            if phic_emp > 0:
                total_deductions += phic_emp
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id, deduction_name="PhilHealth", employee_share=phic_emp, employer_share=0, ec=0
                ))

            awop = safe_float(request.form.get(f"awop_{emp.id}"))
            if awop > 0:
                total_deductions += awop
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id, deduction_name="Absence Without Pay", employee_share=awop, employer_share=0, ec=0
                ))

            allowed_loans = ALLOWED_LOAN_1_15

        # ================= 16–END DEDUCTIONS =================
        else:
            sss = safe_float(request.form.get(f"sss_{emp.id}"))
            if sss > 0:
                total_deductions += sss
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id, deduction_name="SSS", employee_share=sss, employer_share=0, ec=0
                ))

            phic_emp, _ = compute_philhealth(gross_pay)
            if phic_emp > 0:
                total_deductions += phic_emp
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id, deduction_name="PhilHealth", employee_share=phic_emp, employer_share=0, ec=0
                ))

            first_half_period = PayrollPeriod.query.filter(
                extract('month', PayrollPeriod.start_date) == period.start_date.month,
                extract('year', PayrollPeriod.start_date) == period.start_date.year,
                extract('day', PayrollPeriod.start_date) == 1,
                extract('day', PayrollPeriod.end_date) == 15
            ).first()
            previous_payroll = Payroll.query.filter_by(
                employee_id=emp.id,
                payroll_period_id=first_half_period.id
            ).first() if first_half_period else None
            
            previous_tax = compute_withholding_tax(previous_payroll.gross_pay) if previous_payroll else 0
            if previous_tax > 0:
                total_deductions += previous_tax
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id, deduction_name="Withholding Tax (1–15)", employee_share=previous_tax, employer_share=0, ec=0
                ))

            current_tax = compute_withholding_tax(gross_pay)
            if current_tax > 0:
                total_deductions += current_tax
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id, deduction_name="Withholding Tax (16–End)", employee_share=current_tax, employer_share=0, ec=0
                ))

            awop = safe_float(request.form.get(f"awop_{emp.id}"))
            if awop > 0:
                total_deductions += awop
                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id, deduction_name="Absence Without Pay", employee_share=awop, employer_share=0, ec=0
                ))

            allowed_loans = ALLOWED_LOAN_16_END

        # ================= LATE/UNDERTIME DEDUCTION =================
        late_deduction = safe_float(request.form.get(f"late_deduction_{emp.id}"))
        if late_deduction > 0:
            total_deductions += late_deduction
            late_hrs = request.form.get(f"late_hours_{emp.id}", 0)
            late_mins = request.form.get(f"late_minutes_{emp.id}", 0)
            late_secs = request.form.get(f"late_seconds_{emp.id}", 0)
            
            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name=f"Undertime/Late Deduction ({late_hrs}h {late_mins}m {late_secs}s)",
                employee_share=late_deduction,
                employer_share=0,
                ec=0
            ))

        # ================= LOANS =================
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()
        for loan in loans:
            if loan.provider not in allowed_loans:
                continue
            val = safe_float(request.form.get(f"loan_{loan.id}"))
            if val > 0:
                total_deductions += val
                remaining = max((loan.remaining_balance or 0) - val, 0)
                loan.remaining_balance = remaining
                db.session.add(LoanPayment(
                    loan_id=loan.id,
                    payroll_id=payroll.id,
                    amount_paid=val,
                    remaining_balance=remaining,
                    payment_date=period.pay_date
                ))

        # ================= FINAL COMPUTE =================
        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(gross_pay - total_deductions, 2)

    db.session.commit()
    flash("✅ JO Payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.jo_select_department", period_id=period.id))