from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from main_app.extensions import db
from main_app.models.hr_models import Employee, LeaveCredit
from main_app.models.payroll_models import Payroll, PayrollPeriod, PayrollDeduction
from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

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
# PREVIEW PART-TIMER PAYROLL
# ==========================================
@payroll_staff_bp.route("/preview-parttimer/<int:period_id>")
@login_required
@staff_required
def preview_parttimer_payroll(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll already processed for this period.", "warning")
        return redirect(url_for("payroll_staff_bp.parttimer_select_period"))

    # Fetch active Part-Timers
    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == 2
    ).all()

    payroll_rows = []

    for emp in employees:
        # Hours worked
        hours_worked = emp.compute_attendance_hours() if hasattr(emp, "compute_attendance_hours") else 0

        # Salary + allowance
        salary_based_gross = emp.salary * hours_worked if emp.salary else 0
        allowance_total = sum(
            ea.allowance.amount for ea in emp.employee_allowances
            if ea.allowance and ea.allowance.active
        )

        # -----------------------------
        # Deductions
        # -----------------------------
        total_deductions = 0
        deductions_list = []

        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = employer_share = 0

            if "sss" in name:
                for b in emp_ded.deduction.brackets:
                    salary_from = b.salary_from or 0
                    salary_to = b.salary_to if b.salary_to is not None else float("inf")
                    if salary_from <= salary_based_gross <= salary_to:
                        employee_share = b.employee_share or 0
                        employer_share = b.employer_share or 0
                        break
            elif "philhealth" in name:
                rate = emp_ded.deduction.rate or 0.025
                floor = emp_ded.deduction.floor or 10000
                ceiling = emp_ded.deduction.ceiling or 100000
                base = min(max(salary_based_gross, floor), ceiling)
                employee_share = round(base * rate / 2, 2)
                employer_share = round(base * rate / 2, 2)
            elif "gsis" in name:
                employee_share = round(salary_based_gross * 0.09, 2)
                employer_share = round(salary_based_gross * 0.12, 2)
            elif "pag-ibig" in name or "hdmf" in name:
                base = min(salary_based_gross, 5000)
                employee_share = round(base * 0.02, 2)
                employer_share = employee_share
            elif "tax" in name:
                employee_share = round(compute_income_tax(salary_based_gross), 2)
            else:
                result = emp_ded.calculate() or {}
                employee_share = result.get("employee_share", 0) or 0
                employer_share = result.get("employer_share", 0) or 0

            total_deductions += employee_share
            deductions_list.append({
                "name": emp_ded.deduction.name,
                "employee_share": employee_share,
                "employer_share": employer_share
            })

        # -----------------------------
        # Net Pay & Payroll object
        # -----------------------------
        net_pay = round(salary_based_gross + allowance_total - total_deductions, 2)
        display_gross = salary_based_gross + allowance_total

        payroll = Payroll(
            employee=emp,
            period=period,
            hours_worked=hours_worked,
            gross_pay=display_gross,
            total_deductions=total_deductions,
            net_pay=net_pay
        )
        payroll.allowance_total = allowance_total
        payroll._deduction_breakdown = deductions_list

        payroll_rows.append(payroll)

    return render_template(
        "payroll/staff/parttimer/payroll_preview.html",
        payroll_rows=payroll_rows,
        period=period
    )


# ==========================================
# CONFIRM PART-TIMER PAYROLL
# ==========================================
@payroll_staff_bp.route("/confirm-parttimer", methods=["POST"])
@login_required
@staff_required
def confirm_parttimer_payroll():
    period_id = request.form.get("period_id")
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll for this period is already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.parttimer_select_period"))

    # Remove previous payrolls
    Payroll.query.filter_by(payroll_period_id=period.id).delete()
    db.session.flush()

    # Active part-timers
    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == 2
    ).all()

    for emp in employees:
        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            period=period,
            status="Confirmed"
        )
        db.session.add(payroll)
        db.session.flush()

        hours_worked = emp.compute_attendance_hours() if hasattr(emp, "compute_attendance_hours") else 0
        salary_based_gross = emp.salary * hours_worked if emp.salary else 0

        allowance = float(request.form.get(f"allowance_{emp.id}", 0))
        loan = float(request.form.get(f"loan_{emp.id}", 0))
        display_gross = salary_based_gross + allowance
        payroll.allowance_total = allowance

        # -----------------------------
        # Deductions
        # -----------------------------
        total_deductions = 0

        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = employer_share = 0

            if "sss" in name:
                for b in emp_ded.deduction.brackets:
                    salary_from = b.salary_from or 0
                    salary_to = b.salary_to if b.salary_to is not None else float("inf")
                    if salary_from <= salary_based_gross <= salary_to:
                        employee_share = b.employee_share or 0
                        employer_share = b.employer_share or 0
                        break
            elif "philhealth" in name:
                rate = emp_ded.deduction.rate or 0.025
                floor = emp_ded.deduction.floor or 10000
                ceiling = emp_ded.deduction.ceiling or 100000
                base = min(max(salary_based_gross, floor), ceiling)
                employee_share = round(base * rate / 2, 2)
                employer_share = round(base * rate / 2, 2)
            elif "gsis" in name:
                employee_share = round(salary_based_gross * 0.09, 2)
                employer_share = round(salary_based_gross * 0.12, 2)
            elif "pag-ibig" in name or "hdmf" in name:
                base = min(salary_based_gross, 5000)
                employee_share = round(base * 0.02, 2)
                employer_share = employee_share
            elif "tax" in name:
                employee_share = round(compute_income_tax(salary_based_gross), 2)
            else:
                result = emp_ded.calculate() or {}
                employee_share = result.get("employee_share", 0) or 0
                employer_share = result.get("employer_share", 0) or 0

            total_deductions += employee_share

            db.session.add(PayrollDeduction(
                payroll=payroll,
                deduction_name=emp_ded.deduction.name,
                employee_share=employee_share,
                employer_share=employer_share,
                ec=0
            ))

        # -----------------------------
        # Manual Loan / Other deductions
        # -----------------------------
        if loan > 0:
            total_deductions += loan
            db.session.add(PayrollDeduction(
                payroll=payroll,
                deduction_name="Loan / Other",
                employee_share=loan,
                employer_share=0,
                ec=0
            ))

        payroll.gross_pay = display_gross
        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(display_gross - total_deductions, 2)

    db.session.commit()
    flash("Part-Timer Payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.view_payrolls"))