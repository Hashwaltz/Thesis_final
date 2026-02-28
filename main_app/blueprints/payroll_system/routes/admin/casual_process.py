from main_app.extensions import db
from main_app.utils import payroll_admin_required
from main_app.models.hr_models import Employee, Department, Attendance, EmploymentType
from main_app.models.payroll_models import Payroll, PayrollPeriod
from main_app.extensions import db
from main_app.deductions import compute_regular_withholding_tax

from flask_login import login_required
from flask import render_template, redirect, request, flash, url_for, jsonify
from datetime import datetime, timedelta

from . import payroll_admin_bp


# ---------------------------
# CASUAL PAYROLL
# ---------------------------
@payroll_admin_bp.route('/casual', methods=['GET', 'POST'])
@login_required
@payroll_admin_required
def casual_payroll():
    department_id = request.args.get('department_id', type=int)
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    # Filter employees by department AND employment type "Casual"
    query = Employee.query.filter_by(status="Active")
    if department_id:
        query = query.filter_by(department_id=department_id)

    employees = query.join(Employee.employment_type).filter(EmploymentType.name.ilike("casual")).all()

    selected_department = None
    if department_id:
        department = Department.query.get(department_id)
        selected_department = department.name if department else None

    # ------------------------------------------
    # POST — Process Payroll for Casual Employee
    # ------------------------------------------
    if request.method == 'POST':
        employee_id = int(request.form.get('employee_id'))
        pay_period_id = int(request.form.get('pay_period_id'))
        payroll_period = PayrollPeriod.query.get(pay_period_id)
        employee = Employee.query.get(employee_id)

        # ✅ Get form values
        allowance = float(request.form.get('allowance', 0))
        sss = float(request.form.get('sss', 0))
        philhealth = float(request.form.get('philhealth', 0))
        pagibig = float(request.form.get('pagibig', 0))
        tax = float(request.form.get('tax', 0))
        other = float(request.form.get('other', 0))
        daily_rate = float(request.form.get('basic_salary', 0))
        worked_days = float(request.form.get('worked_days', 0))  # ✅ changed

        # ✅ Compute gross and net pay
        gross_pay = round(daily_rate * worked_days, 2)
        total_deductions = round(sss + philhealth + pagibig + tax + other, 2)
        net_pay = round((gross_pay + allowance) - total_deductions, 2)

        # ✅ Create Payroll Record
        payroll = Payroll(
            employee_id=employee_id,
            pay_period_id=pay_period_id,
            pay_period_start=payroll_period.start_date,
            pay_period_end=payroll_period.end_date,
            basic_salary=daily_rate,
            working_hours=worked_days * 8,  # store equivalent hours if needed
            overtime_hours=0,
            holiday_pay=0,
            night_differential=0,
            sss_contribution=sss,
            philhealth_contribution=philhealth,
            pagibig_contribution=pagibig,
            tax_withheld=tax,
            other_deductions=other,
            net_pay=net_pay
        )

        db.session.add(payroll)
        db.session.commit()

        return jsonify({
            "status": "success",
            "gross_pay": gross_pay,
            "deductions": total_deductions,
            "net_pay": net_pay
        })

    # ------------------------------------------
    # GET — Render Casual Payroll Page
    # ------------------------------------------
    employee_data = []
    for emp in employees:
        allowance_total = sum([ea.allowance.amount for ea in emp.employee_allowances])
        sss_total = sum([ed.deduction.amount for ed in emp.employee_deductions if ed.deduction.name.lower() == "sss"])
        philhealth_total = sum([ed.deduction.amount for ed in emp.employee_deductions if ed.deduction.name.lower() == "philhealth"])
        pagibig_total = sum([ed.deduction.amount for ed in emp.employee_deductions if ed.deduction.name.lower() in ["pag-ibig", "pagibig"]])
        existing_payrolls = [p.pay_period_id for p in emp.payrolls]

        employee_data.append({
            "id": emp.id,
            "full_name": emp.get_full_name(),
            "basic_salary": emp.salary or 0,
            "employment_type": emp.employment_type.name if emp.employment_type else "N/A",
            "allowance": allowance_total,
            "sss": sss_total,
            "philhealth": philhealth_total,
            "pagibig": pagibig_total,
            "existing_payrolls": existing_payrolls
        })

    return render_template(
        'payroll/admin/payroll_process/casual_payroll.html',
        employees=employee_data,
        payroll_periods=payroll_periods,
        selected_department=selected_department
    )


