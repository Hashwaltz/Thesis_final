from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime, timedelta

from main_app.extensions import db
from main_app.models.hr_models import Employee,  Attendance, LateComputation, LeaveCredit
from main_app.models.payroll_models import Payroll, PayrollPeriod, Deduction, PayrollDeduction, DeductionBracket

from main_app.helpers.decorators import staff_required

from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

JOB_ORDER_ID = 5

@payroll_staff_bp.route("/preview/<int:period_id>")
@login_required
@staff_required
def preview_payroll(period_id):
    # Get payroll period
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll already processed for this period.", "warning")
        return redirect(url_for("payroll_staff_bp.select_period"))

    # Fetch active Job Order employees
    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == 5
    ).all()

    payroll_rows = []

    for emp in employees:
        # ---------------------------
        # 1️⃣ Compute worked days (attendance & late)
        # ---------------------------
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date.between(period.start_date, period.end_date)
        ).all()

        worked_days = 0
        for att in attendances:
            if att.status in ("Present", "Late"):
                late_record = LateComputation.query.filter_by(attendance_id=att.id).first()
                late_equiv = late_record.day_equivalent if late_record else 0
                worked_days += 1 - late_equiv

        # Deduct leave equivalents
        leave_credits = LeaveCredit.query.filter_by(employee_id=emp.id).all()
        total_leave_days = sum(lc.used_credits for lc in leave_credits)
        worked_days -= total_leave_days
        worked_days = max(worked_days, 0)

        # ---------------------------
        # 2️⃣ Compute gross pay
        # ---------------------------
        gross_pay = emp.salary * worked_days

        # Add allowances
        allowance_total = sum(
            ea.allowance.amount for ea in emp.employee_allowances
            if ea.allowance and ea.allowance.active
        )
        gross_pay += allowance_total

        # ---------------------------
        # 3️⃣ Compute deductions (SSS, PhilHealth, GSIS, etc.)
        # ---------------------------
        total_deductions = 0
        deductions_list = []

        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = employer_share = 0

            # ----- SSS using brackets -----
            if "sss" in name and gross_pay:
                for b in emp_ded.deduction.brackets:
                    if b.salary_from <= gross_pay <= b.salary_to:
                        employee_share = b.employee_share or 0
                        employer_share = b.employer_share or 0
                        break

            # ----- PhilHealth percentage -----
            elif "philhealth" in name:
                rate = emp_ded.deduction.rate or 0.025
                floor = emp_ded.deduction.floor or 10000
                ceiling = emp_ded.deduction.ceiling or 100000
                base = min(max(gross_pay, floor), ceiling)
                employee_share = round(base * rate / 2, 2)
                employer_share = round(base * rate / 2, 2)

            # ----- GSIS (percentage or brackets) -----
            elif "gsis" in name:
                if emp_ded.deduction.brackets:
                    # Use brackets if defined
                    for b in emp_ded.deduction.brackets:
                        if b.salary_from <= gross_pay <= b.salary_to:
                            employee_share = b.employee_share or 0
                            employer_share = b.employer_share or 0
                            break
                else:
                    # Percentage method (9% employee / 12% employer)
                    rate_emp = emp_ded.deduction.rate or 0.09
                    rate_employer = 0.12  # hardcoded employer contribution
                    base = gross_pay
                    employee_share = round(base * rate_emp, 2)
                    employer_share = round(base * rate_employer, 2)


             # ----- Pag-IBIG (percentage with ceiling) -----
            elif "pag-ibig" in name or "hdmf" in name:
                rate = emp_ded.deduction.rate or 0.02
                ceiling = emp_ded.deduction.ceiling or 5000
                base = min(gross_pay, ceiling)
                employee_share = round(base * rate, 2)
                employer_share = employee_share  # usually same as employee

            # ----- Other deductions -----
            else:
                result = emp_ded.calculate()
                employee_share = result.get("employee_share", 0)
                employer_share = result.get("employer_share", 0)

            total_deductions += employee_share

            deductions_list.append({
                "name": emp_ded.deduction.name if emp_ded.deduction else "Custom",
                "employee_share": employee_share,
                "employer_share": employer_share
            })

        # ---------------------------
        # 4️⃣ Create Payroll object for template
        # ---------------------------
        payroll = Payroll(
            employee=emp,
            period=period,
            days_worked=worked_days,
            gross_pay=gross_pay,
            total_deductions=total_deductions,
            net_pay=gross_pay - total_deductions
        )

        payroll._deduction_breakdown = deductions_list
        payroll.allowance_total = allowance_total

        payroll_rows.append(payroll)

    # ---------------------------
    # Render template
    # ---------------------------
    return render_template(
        "payroll/staff/jo/payroll_preview.html",
        payroll_rows=payroll_rows,
        period=period
    )


@payroll_staff_bp.route("/confirm", methods=["POST"])
@login_required
@staff_required
def confirm_payroll():
    """Save JO payroll for the selected period."""
    
    period_id = request.form.get("period_id")
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll for this period is already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.jo_select_period"))

    # Fetch active Job Order employees
    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == 5
    ).all()

    for emp in employees:
        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            status="Confirmed"
        )

        # -----------------------------
        # 1️⃣ Get form input values
        # -----------------------------
        days_worked = float(request.form.get(f"days_{emp.id}", 0))
        allowance = float(request.form.get(f"allowance_{emp.id}", 0))
        loan = float(request.form.get(f"loan_{emp.id}", 0))

        payroll.days_worked = days_worked
        payroll.hours_worked = days_worked * 8

        # -----------------------------
        # 2️⃣ Compute gross pay
        # -----------------------------
        payroll.basic_salary = emp.salary or 0
        payroll.gross_pay = round(payroll.basic_salary * days_worked + allowance, 2)

        # -----------------------------
        # 3️⃣ Compute deductions
        # -----------------------------
        total_deductions = 0

        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            # Use the calculation engine from the model
            result = emp_ded.calculate()
            total_deductions += result.get("employee_share", 0)

            # Save PayrollDeduction record
            pd = PayrollDeduction(
                payroll=payroll,
                deduction_name=emp_ded.deduction.name,
                employee_share=result.get("employee_share", 0),
                employer_share=result.get("employer_share", 0),
                ec=result.get("ec", 0)
            )
            db.session.add(pd)

        # Add any extra manual deductions from form (Loans/Other)
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

        # -----------------------------
        # 4️⃣ Compute net pay
        # -----------------------------
        payroll.net_pay = round(payroll.gross_pay - payroll.total_deductions, 2)

        db.session.add(payroll)
    db.session.commit()

    flash("JO Payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.jo_select_period"))
    