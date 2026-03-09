
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime, timedelta

from main_app.extensions import db
from main_app.models.hr_models import Employee,  Attendance, LateComputation, LeaveCredit
from main_app.models.payroll_models import Payroll, PayrollPeriod, Deduction, PayrollDeduction, DeductionBracket

from main_app.helpers.decorators import staff_required

from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp


@payroll_staff_bp.route("/preview-parttimer/<int:period_id>")
@login_required
@staff_required
def preview_parttimer_payroll(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll already processed for this period.", "warning")
        return redirect(url_for("payroll_staff_bp.parttimer_select_period"))

    # Part-timers (employment_type_id = 2)
    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == 2
    ).all()

    payroll_rows = []

    for emp in employees:
        payroll = Payroll(
            employee=emp,
            employee_id=emp.id,
            payroll_period_id=period.id,
            period=period  # attach period to avoid AttributeError
        )

        # -----------------------------
        # Hours worked from attendance
        # -----------------------------
        hours_worked = payroll.compute_attendance_hours() if hasattr(payroll, "compute_attendance_hours") else 0
        payroll.hours_worked = hours_worked

        # -----------------------------
        # Gross pay
        # -----------------------------
        hourly_rate = emp.salary or 0
        payroll.basic_salary = hourly_rate
        payroll.gross_pay = round(hourly_rate * hours_worked, 2)

        # -----------------------------
        # Deductions (SSS, PhilHealth, Pag-IBIG, etc.)
        # -----------------------------
        total_deductions = 0
        deductions_list = []

        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = employer_share = 0
            salary = payroll.gross_pay

            # ----- Bracket type deductions (SSS / GSIS) -----
            if emp_ded.deduction.calculation_type == "bracket":
                for b in emp_ded.deduction.brackets:
                    if b.salary_from <= salary <= b.salary_to:
                        employee_share = b.employee_share or 0
                        employer_share = b.employer_share or 0
                        break

            # ----- Percentage type deductions (PhilHealth / Pag-IBIG) -----
            elif emp_ded.deduction.calculation_type == "percentage":
                rate = emp_ded.deduction.rate or 0
                floor = emp_ded.deduction.floor or 0
                ceiling = emp_ded.deduction.ceiling or float("inf")
                base = min(max(salary, floor), ceiling)
                employee_share = round(base * rate, 2)
                employer_share = employee_share  # if applicable

            # ----- Fixed / override / progressive deductions -----
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

        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(payroll.gross_pay - total_deductions, 2)
        payroll._deduction_breakdown = deductions_list
        payroll.hourly_rate_value = hourly_rate

        payroll_rows.append(payroll)

    return render_template(
        "payroll/staff/parttimer/payroll_preview.html",
        payroll_rows=payroll_rows,
        period=period
    )

# ------------------------------------------------------------
# 3️⃣ Confirm Part-Timer Payroll
# ------------------------------------------------------------
@payroll_staff_bp.route("/confirm-parttimer", methods=["POST"])
@login_required
@staff_required
def confirm_parttimer_payroll():
    period_id = request.form.get("period_id")
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll for this period is already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.parttimer_select_period"))

    # Fetch active Part-Timers
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

        # -----------------------------
        # Compute worked hours and gross pay
        # -----------------------------
        hours_worked = payroll.compute_attendance_hours() if hasattr(payroll, "compute_attendance_hours") else 0
        payroll.hours_worked = hours_worked
        payroll.basic_salary = emp.salary or 0
        payroll.gross_pay = round(payroll.basic_salary * hours_worked, 2)

        # -----------------------------
        # Deductions
        # -----------------------------
        total_deductions = 0
        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = employer_share = 0
            salary = payroll.gross_pay

            # ----- Bracket type deductions -----
            if emp_ded.deduction.calculation_type == "bracket":
                for b in emp_ded.deduction.brackets:
                    if b.salary_from <= salary <= b.salary_to:
                        employee_share = b.employee_share or 0
                        employer_share = b.employer_share or 0
                        break

            # ----- Percentage type deductions -----
            elif emp_ded.deduction.calculation_type == "percentage":
                rate = emp_ded.deduction.rate or 0
                floor = emp_ded.deduction.floor or 0
                ceiling = emp_ded.deduction.ceiling or float("inf")
                base = min(max(salary, floor), ceiling)
                employee_share = round(base * rate, 2)
                employer_share = employee_share

            # ----- Fixed / override deductions -----
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

        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(payroll.gross_pay - payroll.total_deductions, 2)

    db.session.commit()

    flash("Part-Timer Payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.parttimer_select_period"))