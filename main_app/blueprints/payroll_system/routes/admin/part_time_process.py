


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
# PART-TIME PAYROLL
# ---------------------------
@payroll_admin_bp.route('/parttime', methods=['GET', 'POST'])
@payroll_admin_required
def parttime_payroll():
    department_id = request.args.get('department_id', type=int)
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    # Filter employees by department AND employment type "Part-Time"
    query = Employee.query.filter_by(status="Active")
    if department_id:
        query = query.filter_by(department_id=department_id)
    
    employees = query.join(Employee.employment_type).filter(EmploymentType.name.ilike("part-time")).all()

    # Get selected department name if any
    selected_department = None
    if department_id:
        department = Department.query.get(department_id)
        selected_department = department.name if department else None

    if request.method == 'POST':
        employee_id = int(request.form.get('employee_id'))
        pay_period_id = int(request.form.get('pay_period_id'))
        payroll_period = PayrollPeriod.query.get(pay_period_id)
        employee = Employee.query.get(employee_id)

        # Retrieve form values
        allowance = float(request.form.get('allowance', 0))
        sss = float(request.form.get('sss', 0))
        philhealth = float(request.form.get('philhealth', 0))
        pagibig = float(request.form.get('pagibig', 0))
        tax = float(request.form.get('tax', 0))
        other = float(request.form.get('other', 0))
        working_hours = float(request.form.get('working_hours', 0))
        basic_salary = float(request.form.get('basic_salary', 0))

        # ===========================
        # COMPUTE GROSS PAY FOR PART-TIME
        # ===========================
        gross_pay = basic_salary * working_hours

        # ===========================
        # COMPUTE NET PAY
        # ===========================
        net_pay = round(gross_pay + allowance - (sss + philhealth + pagibig + tax + other), 2)

        # Create payroll entry
        payroll = Payroll(
            employee_id=employee_id,
            pay_period_id=pay_period_id,
            pay_period_start=payroll_period.start_date,
            pay_period_end=payroll_period.end_date,
            basic_salary=basic_salary,
            working_hours=working_hours,
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

        return jsonify({"status": "success", "net_pay": net_pay, "gross_pay": gross_pay})

    # Pre-fill allowances and deductions
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
        'payroll/admin/payroll_process/part_time_payroll.html',  
        employees=employee_data,
        payroll_periods=payroll_periods,
        selected_department=selected_department
    )


# ---------------------------
# GET WORKING HOURS (UPDATED)
# ---------------------------
@payroll_admin_bp.route('/get_working_hours', methods=['GET'])
@payroll_admin_required
@login_required
def get_working_hours():
    employee_id = request.args.get('employee_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not employee_id or not start_date_str or not end_date_str:
        return jsonify({"error": "Missing parameters"}), 400

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    # ✅ Use stored working_hours instead of recalculating
    attendances = Attendance.query.filter(
        Attendance.employee_id == employee_id,
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).all()

    total_hours = sum(a.working_hours or 0 for a in attendances)

    return jsonify({
        "employee_id": employee_id,
        "working_hours": round(total_hours, 2)
    })

