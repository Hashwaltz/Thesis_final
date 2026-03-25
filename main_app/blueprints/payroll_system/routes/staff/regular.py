from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime, timedelta

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance, LateComputation, LeaveCredit
from main_app.models.payroll_models import Payroll, PayrollPeriod, Deduction, PayrollDeduction, DeductionBracket

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

REGULAR_ID = 1  # employment_type_id for regular employees

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
# PREVIEW REGULAR PAYROLL
# ==========================================
@payroll_staff_bp.route("/preview-regular/<int:period_id>")
@login_required
@staff_required
def preview_regular_payroll(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll already processed for this period.", "warning")
        return redirect(url_for("payroll_staff_bp.regular_select_period"))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == REGULAR_ID
    ).all()

    payroll_rows = []

    for emp in employees:
        payroll = Payroll(
            employee=emp,
            employee_id=emp.id,
            period=period,
            payroll_period_id=period.id
        )

        # ----------------------
        # Attendance / Leave
        # ----------------------
        worked_days = 22  # assume 22 working days in month
        leave_credits = LeaveCredit.query.filter_by(employee_id=emp.id).all()
        total_leave_days = sum(lc.used_credits for lc in leave_credits)
        worked_days -= total_leave_days
        payroll.days_worked = worked_days

        # ----------------------
        # Allowances
        # ----------------------
        allowance_total = sum(
            ea.allowance.amount for ea in emp.employee_allowances
            if ea.allowance and ea.allowance.active
        )
        payroll.allowance_total = allowance_total

        # ----------------------
        # Gross Pay
        # ----------------------
        payroll.basic_salary = emp.salary or 0
        gross_pay = round(emp.salary - (emp.salary / 22) * total_leave_days + allowance_total, 2)
        payroll.gross_pay = gross_pay

        # ----------------------
        # Deductions including TAX
        # ----------------------
        total_deductions = 0
        deductions_list = []

        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = employer_share = 0
            gross = payroll.gross_pay

            # ----- SSS brackets -----
            if "sss" in name and emp_ded.deduction.brackets:
                for b in emp_ded.deduction.brackets:
                    if b.salary_from <= gross <= b.salary_to:
                        employee_share = b.employee_share or 0
                        employer_share = b.employer_share or 0
                        break
            # ----- PhilHealth -----
            elif "philhealth" in name:
                rate = emp_ded.deduction.rate or 0.025
                floor = emp_ded.deduction.floor or 10000
                ceiling = emp_ded.deduction.ceiling or 100000
                base = min(max(gross, floor), ceiling)
                employee_share = round(base * rate / 2, 2)
                employer_share = round(base * rate / 2, 2)
            # ----- GSIS -----
            elif "gsis" in name:
                if emp_ded.deduction.brackets:
                    for b in emp_ded.deduction.brackets:
                        if b.salary_from <= gross <= b.salary_to:
                            employee_share = b.employee_share or 0
                            employer_share = b.employer_share or 0
                            break
                else:
                    employee_share = round(gross * 0.09, 2)
                    employer_share = round(gross * 0.12, 2)
            # ----- Pag-IBIG / HDMF -----
            elif "pag-ibig" in name or "hdmf" in name:
                rate = emp_ded.deduction.rate or 0.02
                ceiling = emp_ded.deduction.ceiling or 5000
                base = min(gross, ceiling)
                employee_share = round(base * rate, 2)
                employer_share = employee_share
            # ----- TAX -----
            elif "tax" in name:
                employee_share = round(compute_income_tax(gross), 2)
            # ----- Other deductions -----
            else:
                result = emp_ded.calculate()
                employee_share = result.get("employee_share", 0)
                employer_share = result.get("employer_share", 0)

            total_deductions += employee_share
            deductions_list.append({
                "name": emp_ded.deduction.name,
                "employee_share": employee_share,
                "employer_share": employer_share
            })

        payroll.total_deductions = total_deductions
        payroll.net_pay = round(gross_pay - total_deductions, 2)
        payroll._deduction_breakdown = deductions_list

        payroll_rows.append(payroll)

    return render_template(
        "payroll/staff/regular/payroll_preview.html",
        payroll_rows=payroll_rows,
        period=period
    )

# ==========================================
# CONFIRM REGULAR PAYROLL
# ==========================================
@payroll_staff_bp.route("/confirm-regular", methods=["POST"])
@login_required
@staff_required
def confirm_regular_payroll():
    period_id = request.form.get("period_id")
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll for this period is already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.regular_select_period"))

    Payroll.query.filter_by(payroll_period_id=period.id).delete()
    db.session.flush()

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == REGULAR_ID
    ).all()

    for emp in employees:
        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            status="Confirmed"
        )
        db.session.add(payroll)
        db.session.flush()

        worked_days = 22
        leave_credits = LeaveCredit.query.filter_by(employee_id=emp.id).all()
        total_leave_days = sum(lc.used_credits for lc in leave_credits)
        worked_days -= total_leave_days
        payroll.days_worked = worked_days

        allowance = float(request.form.get(f"allowance_{emp.id}", 0))
        loan = float(request.form.get(f"loan_{emp.id}", 0))
        payroll.allowance_total = allowance
        payroll.basic_salary = emp.salary or 0
        gross_pay = round(payroll.basic_salary - (payroll.basic_salary / 22) * total_leave_days + allowance, 2)
        payroll.gross_pay = gross_pay

        total_deductions = 0

        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = employer_share = 0
            gross = payroll.gross_pay

            if "sss" in name and emp_ded.deduction.brackets:
                for b in emp_ded.deduction.brackets:
                    if b.salary_from <= gross <= b.salary_to:
                        employee_share = b.employee_share or 0
                        employer_share = b.employer_share or 0
                        break
            elif "philhealth" in name:
                rate = emp_ded.deduction.rate or 0.025
                floor = emp_ded.deduction.floor or 10000
                ceiling = emp_ded.deduction.ceiling or 100000
                base = min(max(gross, floor), ceiling)
                employee_share = round(base * rate / 2, 2)
                employer_share = round(base * rate / 2, 2)
            elif "gsis" in name:
                if emp_ded.deduction.brackets:
                    for b in emp_ded.deduction.brackets:
                        if b.salary_from <= gross <= b.salary_to:
                            employee_share = b.employee_share or 0
                            employer_share = b.employer_share or 0
                            break
                else:
                    employee_share = round(gross * 0.09, 2)
                    employer_share = round(gross * 0.12, 2)
            elif "pag-ibig" in name or "hdmf" in name:
                base = min(gross, 5000)
                employee_share = round(base * 0.02, 2)
                employer_share = employee_share
            elif "tax" in name:
                employee_share = round(compute_income_tax(gross), 2)
            else:
                result = emp_ded.calculate()
                employee_share = result.get("employee_share", 0)
                employer_share = result.get("employer_share", 0)

            total_deductions += employee_share
            db.session.add(PayrollDeduction(
                payroll=payroll,
                deduction_name=emp_ded.deduction.name,
                employee_share=employee_share,
                employer_share=employer_share,
                ec=0
            ))

        # Manual deductions (loan / other)
        if loan > 0:
            total_deductions += loan
            db.session.add(PayrollDeduction(
                payroll=payroll,
                deduction_name="Loan / Other",
                employee_share=loan,
                employer_share=0,
                ec=0
            ))

        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(gross_pay - total_deductions, 2)

    db.session.commit()
    flash("Regular Payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.view_payrolls"))