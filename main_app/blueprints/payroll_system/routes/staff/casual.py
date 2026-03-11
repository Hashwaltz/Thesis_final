from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime, timedelta

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance, LateComputation, LeaveCredit
from main_app.models.payroll_models import Payroll, PayrollPeriod, Deduction, PayrollDeduction, DeductionBracket

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp


# ==========================================
# PREVIEW CASUAL PAYROLL
# ==========================================
@payroll_staff_bp.route("/preview-casual/<int:period_id>")
@login_required
@staff_required
def preview_casual_payroll(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll already processed for this period.", "warning")
        return redirect(url_for("payroll_staff_bp.casual_select_period"))

    # Casual employees
    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == 3
    ).all()

    payroll_rows = []

    for emp in employees:
        payroll = Payroll(
            employee=emp,
            employee_id=emp.id,
            period=period,
            payroll_period_id=period.id
        )

        # Attendance computation
        worked_days = payroll.compute_attendance_days()

        # Deduct leave credits
        worked_days = payroll.apply_leave_credit_deductions(worked_days)
        payroll.days_worked = worked_days
        payroll.hours_worked = worked_days * 8

        # Salary × Days + Allowances
        daily_rate = emp.salary or 0
        salary_by_days = daily_rate * worked_days
        allowance_total = payroll.allowance_total or 0
        gross_pay = salary_by_days + allowance_total
        payroll.gross_pay = gross_pay

        # Compute deductions
        total_deductions = 0
        deductions_list = []

        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = employer_share = 0

            # SSS brackets
            if "sss" in name:
                for b in emp_ded.deduction.brackets:
                    if b.salary_from <= gross_pay <= b.salary_to:
                        employee_share = b.employee_share or 0
                        employer_share = b.employer_share or 0
                        break

            # PhilHealth
            elif "philhealth" in name:
                rate = emp_ded.deduction.rate or 0.025
                floor = emp_ded.deduction.floor or 10000
                ceiling = emp_ded.deduction.ceiling or 100000
                base = min(max(gross_pay, floor), ceiling)
                employee_share = round(base * rate / 2, 2)
                employer_share = round(base * rate / 2, 2)

            # GSIS
            elif "gsis" in name:
                if emp_ded.deduction.brackets:
                    for b in emp_ded.deduction.brackets:
                        if b.salary_from <= gross_pay <= b.salary_to:
                            employee_share = b.employee_share or 0
                            employer_share = b.employer_share or 0
                            break
                else:
                    rate_emp = emp_ded.deduction.rate or 0.09
                    rate_employer = 0.12
                    employee_share = round(gross_pay * rate_emp, 2)
                    employer_share = round(gross_pay * rate_employer, 2)

            # Pag-IBIG / HDMF
            elif "pag-ibig" in name or "hdmf" in name:
                rate = emp_ded.deduction.rate or 0.02
                ceiling = emp_ded.deduction.ceiling or 5000
                base = min(gross_pay, ceiling)
                employee_share = round(base * rate, 2)
                employer_share = employee_share

            # Other deductions
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
        payroll.net_pay = gross_pay - total_deductions
        payroll._deduction_breakdown = deductions_list
        payroll.daily_rate_value = daily_rate

        payroll_rows.append(payroll)

    return render_template(
        "payroll/staff/casual/payroll_preview.html",
        payroll_rows=payroll_rows,
        period=period
    )



# ==========================================
# CONFIRM CASUAL PAYROLL
# ==========================================
@payroll_staff_bp.route("/confirm-casual", methods=["POST"])
@login_required
@staff_required
def confirm_casual_payroll():
    period_id = request.form.get("period_id")
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll for this period is already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.casual_select_period"))

    
    # Delete existing payrolls to prevent duplicates
    Payroll.query.filter_by(payroll_period_id=period.id).delete()
    db.session.flush()
    
    # Get all active casual employees
    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == 3
    ).all()

    for emp in employees:
        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            status="Confirmed"
        )
        db.session.add(payroll)
        db.session.flush()  # To get payroll.id if needed for PayrollDeduction

        # ------------------------------
        # Attendance and leave credits
        # ------------------------------
        worked_days = payroll.compute_attendance_days()
        worked_days = payroll.apply_leave_credit_deductions(worked_days)
        payroll.days_worked = worked_days
        payroll.hours_worked = worked_days * 8

        # ------------------------------
        # Allowances and loans
        # ------------------------------
        allowance = float(request.form.get(f"allowance_{emp.id}", 0))
        loan = float(request.form.get(f"loan_{emp.id}", 0))
        basic_salary = emp.salary or 0

        payroll.basic_salary = basic_salary
        payroll.allowance_total = allowance  # ✅ store allowance
        payroll.gross_pay = round(basic_salary * worked_days + allowance, 2)

        # ------------------------------
        # Deductions
        # ------------------------------
        total_deductions = 0
        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = employer_share = 0

            # SSS brackets
            if "sss" in name and emp_ded.deduction.brackets:
                for b in emp_ded.deduction.brackets:
                    if b.salary_from <= payroll.gross_pay <= b.salary_to:
                        employee_share = b.employee_share or 0
                        employer_share = b.employer_share or 0
                        break

            # PhilHealth
            elif "philhealth" in name:
                rate = emp_ded.deduction.rate or 0.025
                floor = emp_ded.deduction.floor or 10000
                ceiling = emp_ded.deduction.ceiling or 100000
                base = min(max(payroll.gross_pay, floor), ceiling)
                employee_share = round(base * rate / 2, 2)
                employer_share = round(base * rate / 2, 2)

            # GSIS
            elif "gsis" in name:
                if emp_ded.deduction.brackets:
                    for b in emp_ded.deduction.brackets:
                        if b.salary_from <= payroll.gross_pay <= b.salary_to:
                            employee_share = b.employee_share or 0
                            employer_share = b.employer_share or 0
                            break
                else:
                    rate_emp = emp_ded.deduction.rate or 0.09
                    rate_employer = 0.12
                    employee_share = round(payroll.gross_pay * rate_emp, 2)
                    employer_share = round(payroll.gross_pay * rate_employer, 2)

            # Pag-IBIG / HDMF
            elif "pag-ibig" in name or "hdmf" in name:
                rate = emp_ded.deduction.rate or 0.02
                ceiling = emp_ded.deduction.ceiling or 5000
                base = min(payroll.gross_pay, ceiling)
                employee_share = round(base * rate, 2)
                employer_share = employee_share

            # Other deductions
            else:
                result = emp_ded.calculate()
                employee_share = result.get("employee_share", 0)
                employer_share = result.get("employer_share", 0)

            total_deductions += employee_share

            # Save deduction
            db.session.add(PayrollDeduction(
                payroll=payroll,
                deduction_name=emp_ded.deduction.name,
                employee_share=employee_share,
                employer_share=employer_share,
                ec=0
            ))

        # ------------------------------
        # Manual deductions (Loans / Other)
        # ------------------------------
        if loan > 0:
            total_deductions += loan
            db.session.add(PayrollDeduction(
                payroll=payroll,
                deduction_name="Loan / Other",
                employee_share=loan,
                employer_share=0,
                ec=0
            ))

        # ------------------------------
        # Final totals
        # ------------------------------
        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(payroll.gross_pay - payroll.total_deductions, 2)

    db.session.commit()
    flash("Casual Payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.view_payrolls"))