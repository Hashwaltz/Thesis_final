from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import and_

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance, LeaveCredit, Department, Leave
from main_app.models.payroll_models import Payroll, PayrollPeriod, Loan, PayrollDeduction, EmployeeDeduction, Deduction

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

REGULAR_ID = 1
WORKING_DAYS_PER_MONTH = 22  # Standard for regular employees


# ========================= HELPERS =========================

def safe_float(value):
    try:
        return float(value) if value is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


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


def get_employee_leave_credits(emp_id, month, year):
    """Get total available leave credits for employee in given month/year"""
    credits = LeaveCredit.query.filter_by(employee_id=emp_id).all()
    return sum(c.remaining_credits() for c in credits)


def compute_awop_deduction(emp, period, leave_used, worked_days):
    """
    Compute AWOP deduction based on leave policy:
    1. Use leave credits first for absences
    2. If credits exhausted, deduct from salary (AWOP)
    Returns: (awop_amount, days_deducted, credits_used)
    """
    monthly_salary = emp.salary or 0
    daily_rate = monthly_salary / WORKING_DAYS_PER_MONTH
    
    # Calculate total absences (days not worked)
    total_absences = max(WORKING_DAYS_PER_MONTH - worked_days, 0)
    
    # Get available leave credits
    available_credits = get_employee_leave_credits(emp.id, period.start_date.month, period.start_date.year)
    
    # Apply leave credits first
    credits_to_use = min(total_absences, available_credits)
    days_uncovered = max(total_absences - credits_to_use, 0)
    
    # AWOP = uncovered days × daily rate
    awop_amount = round(days_uncovered * daily_rate, 2)
    
    return awop_amount, days_uncovered, credits_to_use


# ========================= SELECT DEPARTMENT =========================

@payroll_staff_bp.route("/regular/select-department/<int:period_id>")
@login_required
@staff_required
def regular_select_department(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "payroll/staff/regular/select_department.html",
        period=period,
        departments=departments
    )


# ========================= PREVIEW =========================
@payroll_staff_bp.route("/regular/preview/<int:period_id>/<int:department_id>")
@login_required
@staff_required
def preview_regular_payroll(period_id, department_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    if period.status == "Locked":
        flash("Payroll already processed.", "warning")
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
        
        # ================= ATTENDANCE & LEAVE (ACTUAL RECORDS) =================
        # Get actual attendance records for the period
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date.between(period.start_date, period.end_date)
        ).all()
        
        # Count actual present/late days from attendance table
        present_days = sum(1 for a in attendances if a.status in ("Present", "Late"))
        absent_days = sum(1 for a in attendances if a.status == "Absent")
        
        # Get actual approved leave records that fall within the period
        leaves = Leave.query.filter(
            Leave.employee_id == emp.id,
            Leave.start_date <= period.end_date,
            Leave.end_date >= period.start_date,
            Leave.status == "Approved"
        ).all()
        
        # Calculate actual leave days used in this period
        leave_days_in_period = 0
        for leave in leaves:
            start = max(leave.start_date, period.start_date)
            end = min(leave.end_date, period.end_date)
            if start <= end:
                leave_days_in_period += (end - start).days + 1
        
        # Get actual leave credits used (from LeaveCredit table)
        leave_credits = LeaveCredit.query.filter_by(employee_id=emp.id).all()
        total_credits_used = sum(lc.used_credits for lc in leave_credits)
        total_credits_available = sum(lc.total_credits for lc in leave_credits)
        remaining_credits = max(total_credits_available - total_credits_used, 0)
        
        # ================= ACTUAL AWOP CALCULATION =================
        # AWOP = absences not covered by leave credits
        # Only count absences beyond available credits
        uncovered_absences = max(absent_days - remaining_credits, 0)
        awop_amount = round(uncovered_absences * daily_rate, 2)
        
        # ================= EARNINGS (ACTUAL VALUES) =================
        basic_pay = daily_rate * present_days
        
        # Get actual allowances from EmployeeAllowance table
        allowance_total = sum(
            ea.allowance.amount for ea in emp.employee_allowances 
            if ea.active and ea.allowance
        )
        
        adjustment_pay = 0  # Pull from actual 1-15 cutoff records if available
        
        gross_pay = basic_pay + allowance_total + adjustment_pay
        
        # ================= DEDUCTIONS (ACTUAL RECORDS) =================
        deductions = []
        
        # --- SSS: Pull from EmployeeDeduction or employee profile ---
        sss_deduction = EmployeeDeduction.query.filter_by(
            employee_id=emp.id,
            deduction_id=Deduction.query.filter_by(name="SSS").first().id if Deduction.query.filter_by(name="SSS").first() else None
        ).filter_by(active=True).first()
        sss_value = sss_deduction.override_amount if sss_deduction and sss_deduction.override_amount else (getattr(emp, "sss_contribution", 0) or 0)
        
        deductions.append({
            "key": "sss", "name": "SSS", "employee_share": sss_value, 
            "editable": True, "auto_value": sss_value, "type": "fixed",
            "source": "employee_deduction"
        })
        
        # --- PhilHealth: Pull from EmployeeDeduction or compute from actual gross ---
        philhealth_deduction = EmployeeDeduction.query.filter_by(
            employee_id=emp.id,
            deduction_id=Deduction.query.filter_by(name="PhilHealth").first().id if Deduction.query.filter_by(name="PhilHealth").first() else None
        ).filter_by(active=True).first()
        philhealth_value = philhealth_deduction.override_amount if philhealth_deduction and philhealth_deduction.override_amount else None
        
        if philhealth_value is None:
            # Compute from actual gross if no override exists
            philhealth_emp, philhealth_gov = compute_philhealth(gross_pay)
            philhealth_value = philhealth_emp
        else:
            philhealth_emp, philhealth_gov = philhealth_value, 0  # Use stored value
        
        deductions.append({
            "key": "philhealth", "name": "PhilHealth", "employee_share": philhealth_value,
            "editable": True, "auto_rate": 0.025, "type": "percentage", "gross_dependent": True,
            "employer_share": philhealth_gov, "source": "employee_deduction_or_computed"
        })
        
        # --- Pag-IBIG: Pull from EmployeeDeduction ---
        pagibig_deduction = EmployeeDeduction.query.filter_by(
            employee_id=emp.id,
            deduction_id=Deduction.query.filter_by(name="Pag-IBIG").first().id if Deduction.query.filter_by(name="Pag-IBIG").first() else None
        ).filter_by(active=True).first()
        pagibig_value = pagibig_deduction.override_amount if pagibig_deduction and pagibig_deduction.override_amount else (getattr(emp, "pagibig_contribution", 100) or 100)
        
        deductions.append({
            "key": "pagibig", "name": "Pag-IBIG", "employee_share": pagibig_value,
            "editable": True, "auto_value": pagibig_value, "type": "fixed",
            "source": "employee_deduction"
        })
        
        # --- GSIS: Pull from EmployeeDeduction ---
        gsis_deduction = EmployeeDeduction.query.filter_by(
            employee_id=emp.id,
            deduction_id=Deduction.query.filter_by(name="GSIS").first().id if Deduction.query.filter_by(name="GSIS").first() else None
        ).filter_by(active=True).first()
        gsis_value = gsis_deduction.override_amount if gsis_deduction and gsis_deduction.override_amount else (getattr(emp, "gsis_contribution", 0) or 0)
        
        deductions.append({
            "key": "gsis", "name": "GSIS", "employee_share": gsis_value,
            "editable": True, "auto_value": gsis_value, "type": "fixed",
            "source": "employee_deduction"
        })
        
        # --- AWOP: Based on ACTUAL attendance/leave records ---
        deductions.append({
            "key": "awop", "name": "Absence Without Pay", "employee_share": awop_amount,
            "editable": True, "auto_value": awop_amount, "type": "awop",
            "daily_rate": daily_rate, 
            "days_uncovered": uncovered_absences, 
            "credits_used": min(absent_days, total_credits_used),
            "actual_absent_days": absent_days,
            "actual_leave_days": leave_days_in_period,
            "remaining_credits": remaining_credits,
            "source": "attendance_and_leave_records"
        })
        
        # --- Loans: Pull actual active loans with payment amounts ---
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()
        for loan in loans:
            deductions.append({
                "key": f"loan_{loan.id}",
                "name": f"{loan.provider} - {loan.loan_type}",
                "employee_share": loan.monthly_payment or 0,  # Actual value from Loan table
                "editable": True,
                "auto_value": loan.monthly_payment or 0,
                "type": "loan",
                "loan_id": loan.id,
                "source": "loan_table"
            })
        
        # ================= PASS ACTUAL DATA TO TEMPLATE =================
        payroll_data.append({
            "employee": emp,
            "days_worked": present_days,  # Actual count from Attendance table
            "leave_days": leave_days_in_period,  # Actual count from Leave table
            "absences": absent_days,  # Actual count from Attendance table
            "basic_pay": basic_pay,  # Computed from actual present days
            "allowance_total": allowance_total,  # Actual sum from EmployeeAllowance
            "gross_pay": gross_pay,  # Computed from actual values
            "adjustment_pay": adjustment_pay,
            "deductions": deductions,
            "awop_suggested": awop_amount,  # Based on actual records
            "awop_days": uncovered_absences,
            "daily_rate": daily_rate,
            "available_credits": remaining_credits,  # Actual from LeaveCredit table
            # For display/debugging:
            "actual_attendance": {
                "present": present_days,
                "absent": absent_days,
                "late": sum(1 for a in attendances if a.status == "Late")
            },
            "actual_leave": {
                "days_in_period": leave_days_in_period,
                "credits_used": total_credits_used,
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

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.department_id == department.id,
        Employee.employment_type_id == REGULAR_ID
    ).all()

    for emp in employees:

        leave_used = sum(lc.used_credits for lc in LeaveCredit.query.filter_by(employee_id=emp.id))
        worked_days = max(22 - leave_used, 0)

        monthly_salary = emp.salary or 0
        daily_rate = monthly_salary / 22

        basic_pay = daily_rate * worked_days

        # ✅ Get form values for earnings (adjustment is display-only)
        allowance_total = safe_float(request.form.get(f"allowance_{emp.id}", 0))
        overtime_pay = safe_float(request.form.get(f"overtime_{emp.id}", 0))
        
        # ✅ Correct Gross Pay: Monthly + Allowance + Overtime (NOT adjustment)
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

        # ================= GOV DEDUCTIONS =================
        # Read from form (user can edit), fallback to 0 if empty
        sss = safe_float(request.form.get(f"sss_{emp.id}", 0))
        philhealth = safe_float(request.form.get(f"philhealth_{emp.id}", 0))
        pagibig = safe_float(request.form.get(f"pagibig_{emp.id}", 0))
        gsis = safe_float(request.form.get(f"gsis_{emp.id}", 0))

        total_deductions += sss + philhealth + pagibig + gsis

        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="SSS", employee_share=round(sss, 2)))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="PhilHealth", employee_share=round(philhealth, 2)))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="Pag-IBIG", employee_share=round(pagibig, 2)))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="GSIS", employee_share=round(gsis, 2)))

        # ================= TAXES =================
        # ✅ FIX: Read tax values from form FIRST, fallback to auto-compute if empty
        
        # CTW Tax
        ctw_tax_input = request.form.get(f"ctw_tax_{emp.id}", "").strip()
        if ctw_tax_input:
            # User manually edited - use their value
            ctw_tax = safe_float(ctw_tax_input)
        else:
            # Auto-compute based on checkbox
            is_daily_tax = request.form.get(f"ctw_{emp.id}") == "on"
            ctw_tax = compute_ctw(gross_pay, is_daily_tax)
        
        # GMP-PT Tax
        gmp_pt_tax_input = request.form.get(f"gmp_pt_tax_{emp.id}", "").strip()
        if gmp_pt_tax_input:
            # User manually edited - use their value
            gmp_pt_tax = safe_float(gmp_pt_tax_input)
        else:
            # Auto-compute (always 2% of gross)
            gmp_pt_tax = compute_gmp_pt(gross_pay)

        total_deductions += ctw_tax + gmp_pt_tax

        # ✅ Round to 2 decimals before saving to avoid float precision issues
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="CTW Tax", employee_share=round(ctw_tax, 2)))
        db.session.add(PayrollDeduction(payroll_id=payroll.id, deduction_name="GMP-PT", employee_share=round(gmp_pt_tax, 2)))

        # ================= LOANS =================
        loans = Loan.query.filter_by(employee_id=emp.id, active=True).all()

        for loan in loans:
            val = safe_float(request.form.get(f"loan_{loan.id}", 0))
            total_deductions += val

            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name=f"{loan.provider} Loan",
                employee_share=round(val, 2)
            ))

        # ================= ABSENCE WITHOUT PAY =================
        awop = safe_float(request.form.get(f"awop_{emp.id}", 0))
        if awop > 0:
            total_deductions += awop
            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name="Absence Without Pay",
                employee_share=round(awop, 2)
            ))

        # ================= FINAL =================
        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(gross_pay - total_deductions, 2)

    db.session.commit()
    flash("Regular payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.view_payrolls"))