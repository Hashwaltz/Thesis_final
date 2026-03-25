from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required

from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance, LateComputation, LeaveCredit
from main_app.models.payroll_models import Payroll, PayrollPeriod, PayrollDeduction

from main_app.helpers.decorators import staff_required
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp

JOB_ORDER_ID = 5

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
# PREVIEW PAYROLL
# ==========================================
@payroll_staff_bp.route("/preview/<int:period_id>")
@login_required
@staff_required
def preview_payroll(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)

    if period.status == "Locked":
        flash("Payroll already processed.", "warning")
        return redirect(url_for("payroll_staff_bp.select_period"))

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == JOB_ORDER_ID
    ).all()

    payroll_rows = []

    for emp in employees:
        # -----------------------------
        # WORKED DAYS
        # -----------------------------
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

        # Deduct leaves
        leave_credits = LeaveCredit.query.filter_by(employee_id=emp.id).all()
        leave_days = sum(l.used_credits for l in leave_credits)
        worked_days -= leave_days
        worked_days = max(worked_days, 0)

        # -----------------------------
        # ALLOWANCE
        # -----------------------------
        allowance_total = sum(
            ea.allowance.amount
            for ea in emp.employee_allowances
            if ea.allowance and ea.allowance.active
        )

        # -----------------------------
        # SALARY-BASED GROSS PAY
        # (for deduction computation)
        # -----------------------------
        salary_based_gross = emp.salary * worked_days

        # -----------------------------
        # DEDUCTIONS
        # -----------------------------
        total_deductions = 0
        deductions_list = []

        for emp_ded in emp.employee_deductions:
            if not emp_ded.active or not emp_ded.deduction:
                continue

            name = emp_ded.deduction.name.lower()
            employee_share = 0
            employer_share = 0

            if "sss" in name:
                for b in emp_ded.deduction.brackets:
                    if b.salary_from <= salary_based_gross <= b.salary_to:
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
                result = emp_ded.calculate()
                employee_share = result.get("employee_share", 0)
                employer_share = result.get("employer_share", 0)

            total_deductions += employee_share
            deductions_list.append({
                "name": emp_ded.deduction.name,
                "employee_share": employee_share,
                "employer_share": employer_share
            })

        # -----------------------------
        # NET PAY
        # -----------------------------
        net_pay = round(salary_based_gross + allowance_total - total_deductions, 2)
        display_gross = salary_based_gross + allowance_total

        payroll = Payroll(
            employee=emp,
            period=period,
            days_worked=worked_days,
            gross_pay=display_gross,   # for showing in template
            total_deductions=total_deductions,
            net_pay=net_pay
        )
        payroll.allowance_total = allowance_total
        payroll._deduction_breakdown = deductions_list

        payroll_rows.append(payroll)

    return render_template(
        "payroll/staff/jo/payroll_preview.html",
        payroll_rows=payroll_rows,
        period=period
    )

# ==========================================
# CONFIRM PAYROLL - INSERT EXACTLY AS PREVIEWED
# ==========================================
@payroll_staff_bp.route("/confirm", methods=["POST"])
@login_required
@staff_required
def confirm_payroll():
    period_id = request.form.get("period_id")
    period = PayrollPeriod.query.get_or_404(period_id)

    # Delete existing payrolls to prevent duplicates
    Payroll.query.filter_by(payroll_period_id=period.id).delete()
    db.session.flush()

    employees = Employee.query.filter(
        Employee.status == "Active",
        Employee.employment_type_id == JOB_ORDER_ID
    ).all()

    for emp in employees:
        days_worked = float(request.form.get(f"days_{emp.id}", 0))
        allowance = float(request.form.get(f"allowance_{emp.id}", 0))
        loan = float(request.form.get(f"loan_{emp.id}", 0))
        gross_pay = float(request.form.get(f"gross_{emp.id}", emp.salary * days_worked + allowance))

        payroll = Payroll(
            employee_id=emp.id,
            payroll_period_id=period.id,
            status="Confirmed",
            days_worked=days_worked,
            hours_worked=days_worked * 8,
            basic_salary=emp.salary,
            allowance_total=allowance,
            gross_pay=gross_pay
        )
        db.session.add(payroll)
        db.session.flush()

        total_deductions = 0

        # Loop over deductions sent from form
        for key, value in request.form.items():
            if key.startswith(f"deduction_{emp.id}_"):
                name = key.split(f"deduction_{emp.id}_")[1]
                employee_share = float(value)
                employer_share = float(request.form.get(f"employer_{emp.id}_{name}", 0))
                total_deductions += employee_share

                db.session.add(PayrollDeduction(
                    payroll_id=payroll.id,
                    deduction_name=name,
                    employee_share=employee_share,
                    employer_share=employer_share
                ))

        # Include loan if any
        if loan > 0:
            total_deductions += loan
            db.session.add(PayrollDeduction(
                payroll_id=payroll.id,
                deduction_name="Loan / Other",
                employee_share=loan,
                employer_share=0
            ))

        payroll.total_deductions = round(total_deductions, 2)
        payroll.net_pay = round(gross_pay - total_deductions, 2)

    db.session.commit()
    flash("JO Payroll processed successfully!", "success")
    return redirect(url_for("payroll_staff_bp.view_payrolls"))