from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance, Department
from main_app.models.payroll_models import Payroll, PayrollPeriod, PayrollDeduction, EmployeeDeduction, Deduction, Loan
from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

# ==========================================
# CONSTANTS
# ==========================================
PARTTIMER_ID = 2
STANDARD_MONTHLY_HOURS = 176  # 22 days × 8 hours (adjust per your policy)

# ==========================================
# Philippine TRAIN Income Tax (Monthly)
# ==========================================
def compute_income_tax(monthly_salary):
    if monthly_salary <= 20833:
        return 0
    elif monthly_salary <= 33332:
        return (monthly_salary - 20833) * 0.20
    elif monthly_salary <= 66666:
        return 2500 + (monthly_salary - 33332) * 0.25
    elif monthly_salary <= 166666:
        return 10833.33 + (monthly_salary - 66666) * 0.30
    elif monthly_salary <= 666666:
        return 40833.33 + (monthly_salary - 166666) * 0.32
    else:
        return 200833.33 + (monthly_salary - 666666) * 0.35

# ==========================================
# Compute hours worked from Attendance
# ==========================================
def compute_hours_worked(emp, start_date, end_date, leave_hours=0):
    attendances = Attendance.query.filter(
        Attendance.employee_id == emp.id,
        Attendance.date.between(start_date, end_date)
    ).all()

    total_seconds = 0
    for att in attendances:
        if att.time_in and att.time_out:
            dt_in = datetime.combine(att.date, att.time_in)
            dt_out = datetime.combine(att.date, att.time_out)
            seconds = (dt_out - dt_in).total_seconds()
            if seconds > 0:
                total_seconds += seconds
        elif att.status and att.status.lower() == "on leave":
            total_seconds += leave_hours * 3600

    total_hours_decimal = total_seconds / 3600
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    display_hours = f"{hours}h {minutes}m"
    return total_hours_decimal, display_hours

# ==========================================
# Safe float helper
# ==========================================
def safe_float(value):
    try:
        return float(value) if value is not None and value != "" else 0.0
    except (ValueError, TypeError):
        return 0.0
    


@payroll_staff_bp.route("/parttimer/select-department/<int:period_id>")
@login_required
@staff_required
def parttimer_select_department(period_id):
    """Show departments for part-timer payroll selection"""
    period = PayrollPeriod.query.get_or_404(period_id)
    
    if period.status == "Locked":
        flash("Payroll already processed for this period.", "warning")
        return redirect(url_for("payroll_staff_bp.parttimer_select_period"))
    
    departments = Department.query.order_by(Department.name).all()
    department_status = {}
    
    for dept in departments:
        has_payroll = Payroll.query.join(Employee).filter(
            Payroll.payroll_period_id == period.id,
            Employee.department_id == dept.id,
            Employee.employment_type_id == PARTTIMER_ID,
            Employee.status == "Active"
        ).first()
        department_status[dept.id] = bool(has_payroll)

    return render_template(
        "payroll/staff/parttimer/select_department.html",
        period=period,
        departments=departments,
        department_status=department_status
    )



# ==========================================
# PREVIEW PART-TIMER PAYROLL (Step 3a - requires department)
# ==========================================
@payroll_staff_bp.route("/preview-parttimer/<int:period_id>/dept/<int:department_id>")
@login_required
@staff_required
def preview_parttimer_payroll(period_id, department_id):
    """Preview part-timer payroll for a specific department"""
    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    if period.status == "Locked":
        flash("Payroll already processed for this period.", "warning")
        return redirect(url_for("payroll_staff_bp.parttimer_select_department", period_id=period.id))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == PARTTIMER_ID,
        Employee.department_id == department_id
    ).all()

    payroll_rows = []

    for emp in employees:
        # === HOURLY PAY CALCULATION ===
        # ✅ FIX: emp.salary IS the hourly rate - NO division needed!
        total_hours_decimal, display_hours = compute_hours_worked(emp, period.start_date, period.end_date)
        hourly_rate = emp.salary or 0  # ← This is already the hourly rate!
        salary_based_gross = hourly_rate * total_hours_decimal

        allowance_total = sum(
            ea.allowance.amount for ea in emp.employee_allowances
            if ea.allowance and ea.allowance.active
        )
        gross_pay = salary_based_gross + allowance_total

        # === OPTIONAL DEDUCTIONS ===
        deductions = []

        def get_deduction_config(name):
            ded = Deduction.query.filter_by(name=name).first()
            if not ded:
                return None
            emp_ded = EmployeeDeduction.query.filter_by(
                employee_id=emp.id, deduction_id=ded.id, active=True
            ).first()
            return emp_ded, ded

        # SSS
        sss_cfg = get_deduction_config("SSS Contribution")
        if sss_cfg:
            emp_ded, ded_obj = sss_cfg
            auto_value = emp_ded.override_amount if emp_ded and emp_ded.override_amount is not None else 0
            if auto_value == 0 and ded_obj and ded_obj.brackets:
                for b in ded_obj.brackets:
                    if (b.salary_from or 0) <= gross_pay <= (b.salary_to or float("inf")):
                        auto_value = b.employee_share or 0
                        break
            deductions.append({"key": "sss", "name": "SSS", "employee_share": auto_value, "editable": True, "auto_value": auto_value, "type": "fixed", "optional": True})

        # PhilHealth
        ph_cfg = get_deduction_config("PhilHealth Contribution")
        if ph_cfg:
            emp_ded, ded_obj = ph_cfg
            auto_value = emp_ded.override_amount if emp_ded and emp_ded.override_amount is not None else None
            if auto_value is None:
                rate = ded_obj.rate if ded_obj and ded_obj.rate else 0.025
                floor = ded_obj.floor if ded_obj and ded_obj.floor else 10000
                ceiling = ded_obj.ceiling if ded_obj and ded_obj.ceiling else 100000
                base = min(max(gross_pay, floor), ceiling)
                auto_value = round(base * rate / 2, 2)
            deductions.append({"key": "philhealth", "name": "PhilHealth", "employee_share": auto_value, "editable": True, "auto_value": auto_value, "type": "percentage", "optional": True})

        # Pag-IBIG
        pag_cfg = get_deduction_config("Pag-IBIG Contribution")
        if pag_cfg:
            emp_ded, ded_obj = pag_cfg
            auto_value = emp_ded.override_amount if emp_ded and emp_ded.override_amount is not None else 100.00
            deductions.append({"key": "pagibig", "name": "Pag-IBIG", "employee_share": auto_value, "editable": True, "auto_value": auto_value, "type": "fixed", "optional": True})

        # GSIS
        gsis_cfg = get_deduction_config("GSIS Contribution")
        if gsis_cfg:
            emp_ded, ded_obj = gsis_cfg
            auto_value = emp_ded.override_amount if emp_ded and emp_ded.override_amount is not None else round(gross_pay * 0.09, 2)
            deductions.append({"key": "gsis", "name": "GSIS", "employee_share": auto_value, "editable": True, "auto_value": auto_value, "type": "percentage", "optional": True})

        # TRAIN Tax
        tax_cfg = get_deduction_config("Tax")
        if tax_cfg:
            emp_ded, ded_obj = tax_cfg
            auto_value = emp_ded.override_amount if emp_ded and emp_ded.override_amount is not None else round(compute_income_tax(gross_pay), 2)
            deductions.append({"key": "tax", "name": "TRAIN Income Tax", "employee_share": auto_value, "editable": True, "auto_value": auto_value, "type": "computed", "optional": True})

        # Loans
        for loan in Loan.query.filter_by(employee_id=emp.id, active=True).all():
            deductions.append({
                "key": f"loan_{loan.id}", "name": f"{loan.provider} - {loan.loan_type}",
                "employee_share": loan.monthly_payment or 0, "editable": True,
                "auto_value": loan.monthly_payment or 0, "type": "loan", "optional": True, "loan_id": loan.id
            })

        # Other deductions
        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue
            name = emp_ded.deduction.name.lower()
            if any(k in name for k in ["sss", "philhealth", "pag-ibig", "hdmf", "gsis", "tax"]):
                continue
            auto_value = emp_ded.override_amount if emp_ded.override_amount is not None else (emp_ded.calculate() or {}).get("employee_share", 0)
            deductions.append({"key": f"other_{emp_ded.id}", "name": emp_ded.deduction.name, "employee_share": auto_value, "editable": True, "auto_value": auto_value, "type": "other", "optional": True})

        payroll_rows.append({
            "employee": emp,
            "hours_worked": display_hours,
            "total_hours_decimal": total_hours_decimal,
            "hourly_rate": round(hourly_rate, 2),  # ← Already the hourly rate!
            "salary_based_gross": round(salary_based_gross, 2),
            "allowance_total": allowance_total,
            "gross_pay": round(gross_pay, 2),
            "deductions": deductions,
            "net_pay_preview": round(gross_pay - sum(d["employee_share"] for d in deductions), 2)
        })

    return render_template(
        "payroll/staff/parttimer/payroll_preview.html",
        payroll_rows=payroll_rows,
        period=period,
        department=department
    )

# ==========================================
# PROCESS PART-TIMER PAYROLL (Step 3b - requires department)
# ==========================================
@payroll_staff_bp.route("/process-parttimer/<int:period_id>/dept/<int:department_id>", methods=["POST"])
@login_required
@staff_required
def process_parttimer_payroll(period_id, department_id):
    """Process and save part-timer payroll for a specific department"""
    period = PayrollPeriod.query.get_or_404(period_id)
    department = Department.query.get_or_404(department_id)

    if period.status == "Locked":
        flash("Payroll for this period is already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.parttimer_select_department", period_id=period.id))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == PARTTIMER_ID,
        Employee.department_id == department_id
    ).all()

    for emp in employees:
        # === HOURLY PAY ===
        total_hours_decimal, _ = compute_hours_worked(emp, period.start_date, period.end_date)
        hourly_rate = emp.salary or 0  # ← Already the hourly rate!
        salary_based_gross = hourly_rate * total_hours_decimal
        allowance_total = safe_float(request.form.get(f"allowance_{emp.id}", 0))
        gross_pay = salary_based_gross + allowance_total

        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            hours_worked=total_hours_decimal,
            basic_salary=salary_based_gross,
            allowance_total=allowance_total,
            gross_pay=gross_pay,
            status="Processed"
        )
        db.session.add(payroll)
        db.session.flush()

        total_deductions = 0

        # Optional deductions: only save if form value is provided and > 0
        for ded_key in ["sss", "philhealth", "pagibig", "gsis", "tax"]:
            val = request.form.get(f"{ded_key}_{emp.id}", "").strip()
            if val:
                amt = safe_float(val)
                if amt > 0:
                    total_deductions += amt
                    employer_share = 0
                    if ded_key == "philhealth":
                        employer_share = round(amt, 2)
                    elif ded_key == "pagibig":
                        employer_share = round(amt, 2)
                    elif ded_key == "gsis":
                        employer_share = round(amt * 0.12/0.09, 2) if amt > 0 else 0
                    db.session.add(PayrollDeduction(
                        payroll=payroll, deduction_name=ded_key.upper() if ded_key != "tax" else "TRAIN Income Tax",
                        employee_share=round(amt, 2), employer_share=employer_share
                    ))

        # Loans
        for loan in Loan.query.filter_by(employee_id=emp.id, active=True).all():
            val = request.form.get(f"loan_{loan.id}", "").strip()
            if val:
                amt = safe_float(val)
                if amt > 0:
                    total_deductions += amt
                    db.session.add(PayrollDeduction(
                        payroll=payroll, deduction_name=f"{loan.provider} - {loan.loan_type}",
                        employee_share=round(amt, 2), employer_share=0
                    ))

        # Other deductions
        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue
            key = f"other_{emp_ded.id}"
            val = request.form.get(key, "").strip()
            if val:
                amt = safe_float(val)
                if amt > 0:
                    total_deductions += amt
                    db.session.add(PayrollDeduction(
                        payroll=payroll, deduction_name=emp_ded.deduction.name,
                        employee_share=round(amt, 2), employer_share=0
                    ))

        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(gross_pay - total_deductions, 2)

    db.session.commit()
    flash("Part-Timer payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.view_payrolls"))