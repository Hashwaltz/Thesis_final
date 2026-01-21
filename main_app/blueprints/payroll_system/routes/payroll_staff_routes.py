from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from main_app.models.users import PayrollUser
from main_app.models.payroll_models import Employee, Payroll, Payslip, PayrollPeriod, EmployeeDeduction, EmployeeAllowance
from main_app.forms import PayslipForm, PayrollSummaryForm
from main_app.utils import staff_required, calculate_payroll_summary, get_current_payroll_period
from main_app.extensions import db
from datetime import datetime, date, timedelta
import os
import pandas as pd
import io
from sqlalchemy.orm import joinedload
from calendar import monthrange
from sqlalchemy import case, func, asc
import random
from main_app.models.user import User
from main_app.models.hr_models import Attendance, Department, Position, EmploymentType


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "payroll_static")

payroll_staff_bp = Blueprint(
    "payroll_staff",
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR,
    static_url_path="/payroll/static"
)


# Helper function: get current payroll period
def get_current_payroll_period():
    today = date.today()
    return PayrollPeriod.query.filter(
        PayrollPeriod.start_date <= today,
        PayrollPeriod.end_date >= today
    ).first()

@payroll_staff_bp.route('/dashboard')
@login_required
@staff_required
def dashboard():
    # ----------------- EMPLOYEE STATS -----------------
    total_employees = Employee.query.filter_by(active=True).count()
    total_departments = Department.query.count()
    total_users = Employee.query.filter_by(active=True).count()
    total_inactive = Employee.query.filter_by(active=False).count()

    # ----------------- PAYROLL STATS -----------------
    total_payrolls = Payroll.query.count()
    total_payslips = Payslip.query.count()

    total_disbursed = db.session.query(func.sum(Payslip.net_pay)).scalar() or 0
    total_deductions = db.session.query(func.sum(Payslip.total_deductions)).scalar() or 0
    total_allowances = db.session.query(func.sum(Payslip.allowances)).scalar() or 0

    # ----------------- CURRENT PERIOD -----------------
    current_period = get_current_payroll_period()

    # ----------------- RECENT -----------------
    recent_payrolls = Payroll.query.order_by(Payroll.created_at.desc()).limit(5).all()
    recent_payslips = Payslip.query.order_by(Payslip.generated_at.desc()).limit(5).all()

    # ----------------- UNCLAIMED PAYSLIPS -----------------
    unclaimed_payslips = Payslip.query.filter_by(claimed=False).order_by(Payslip.generated_at.desc()).limit(10).all()
    unclaimed_count = Payslip.query.filter_by(claimed=False).count()

    # ----------------- MONTHLY ATTENDANCE -----------------
    today = date.today()
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])

    attendances = db.session.query(
        Attendance.date,
        func.sum(case((Attendance.status == "Present", 1), else_=0)).label("present_count"),
        func.sum(case((Attendance.status == "Absent", 1), else_=0)).label("absent_count"),
        func.sum(case((Attendance.status == "Late", 1), else_=0)).label("late_count")
    ).filter(
        Attendance.date >= month_start,
        Attendance.date <= month_end
    ).group_by(Attendance.date).order_by(Attendance.date).all()

    monthly_dates = [a.date.strftime("%Y-%m-%d") for a in attendances]
    monthly_present_counts = [a.present_count for a in attendances]
    monthly_absent_counts = [a.absent_count for a in attendances]
    monthly_late_counts = [a.late_count for a in attendances]

    return render_template(
        'payroll/staff/staff_dashboard.html',
        total_employees=total_employees,
        total_departments=total_departments,
        total_users=total_users,
        total_inactive=total_inactive,
        total_payrolls=total_payrolls,
        total_payslips=total_payslips,
        total_disbursed=total_disbursed,
        total_deductions=total_deductions,
        total_allowances=total_allowances,
        current_period=current_period,
        recent_payrolls=recent_payrolls,
        recent_payslips=recent_payslips,
        unclaimed_payslips=unclaimed_payslips,
        unclaimed_count=unclaimed_count,
        monthly_dates=monthly_dates,
        monthly_present_counts=monthly_present_counts,
        monthly_absent_counts=monthly_absent_counts,
        monthly_late_counts=monthly_late_counts
    )




@payroll_staff_bp.route('/employees')
@login_required
@staff_required
def employees():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    department = request.args.get('department', '')
    
    query = Employee.query.filter_by(active=True)
    
    if search:
        query = query.filter(
            (Employee.first_name.contains(search)) |
            (Employee.last_name.contains(search)) |
            (Employee.employee_id.contains(search))
        )
    
    if department:
        query = query.filter_by(department=department)
    
    employees = query.paginate(page=page, per_page=10, error_out=False)
    
    departments = db.session.query(Employee.department).distinct().all()
    departments = [dept[0] for dept in departments if dept[0]]
    
    return render_template('payroll/employees.html', 
                         employees=employees, 
                         departments=departments,
                         search=search,
                         selected_department=department)



@payroll_staff_bp.route('/payrolls')
@staff_required
@login_required
def view_payrolls():
    search = request.args.get('search', '', type=str).strip()
    department_id = request.args.get('department_id', type=int)
    pay_period_id = request.args.get('pay_period_id', type=int)
    page = request.args.get('page', 1, type=int)

    # Base query
    query = Payroll.query.join(Employee)

    # Apply department filter
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    # Apply search filter
    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%")) |
            (Employee.last_name.ilike(f"%{search}%")) |
            (Employee.employee_id.ilike(f"%{search}%"))
        )

    # Apply payroll period filter
    if pay_period_id:
        query = query.filter(Payroll.pay_period_id == pay_period_id)

    # Paginate results
    payrolls = query.order_by(Payroll.created_at.desc()).paginate(page=page, per_page=10)

    # Get department list for dropdown
    from main_app.models.hr_models import Department
    departments = Department.query.all()

    # Get payroll periods for dropdown
    from main_app.models.payroll_models import PayrollPeriod
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    # Get selected payroll period object
    selected_pay_period = PayrollPeriod.query.get(pay_period_id) if pay_period_id else None

    return render_template(
        'payroll/staff/view_payroll_details.html',
        payrolls=payrolls,
        search=search,
        departments=departments,
        selected_department=department_id,
        payroll_periods=payroll_periods,
        selected_pay_period=selected_pay_period
    )

@payroll_staff_bp.route('/payroll/export_excel', methods=['GET'])
@login_required
@staff_required
def export_payroll_excel():
    # Get filters from query parameters
    search = request.args.get('search', '')
    department_id = request.args.get('department_id')
    pay_period_id = request.args.get('pay_period_id')

    # Base query with eager loading for related data
    query = Payroll.query.options(
        joinedload(Payroll.employee)
            .joinedload(Employee.employee_deductions)
            .joinedload(EmployeeDeduction.deduction),
        joinedload(Payroll.employee)
            .joinedload(Employee.employee_allowances)
            .joinedload(EmployeeAllowance.allowance),
        joinedload(Payroll.employee)
            .joinedload(Employee.department)
    ).join(Payroll.employee)

    # Apply filters
    if search:
        query = query.filter(
            (Payroll.employee.first_name.ilike(f"%{search}%")) |
            (Payroll.employee.last_name.ilike(f"%{search}%"))
        )
    if department_id:
        query = query.filter(Payroll.employee.department_id == department_id)
    if pay_period_id:
        query = query.filter(Payroll.pay_period_id == pay_period_id)

    payrolls = query.all()

    # Build DataFrame
    data = []
    for p in payrolls:
        # Safely compute linked deductions and allowances
        total_linked_deductions = sum(
            (ed.deduction.amount or 0)
            for ed in getattr(p.employee, 'employee_deductions', [])
            if ed.deduction and ed.deduction.active
        )
        total_allowances = sum(
            (ea.allowance.amount or 0)
            for ea in getattr(p.employee, 'employee_allowances', [])
            if ea.allowance and ea.allowance.active
        )

        # Compute totals
        total_deductions = (p.total_deductions or 0) + total_linked_deductions
        gross_pay_with_allowances = (p.gross_pay or 0) + total_allowances

        data.append({
            "Employee ID": p.employee.employee_id,
            "Name": f"{p.employee.first_name} {p.employee.last_name}",
            "Department": p.employee.department.name if p.employee.department else "-",
            "Basic Salary": p.basic_salary or 0,
            "Overtime Hours": p.overtime_hours or 0,
            "Overtime Pay": p.overtime_pay or 0,
            "Holiday Pay": p.holiday_pay or 0,
            "Night Differential": p.night_differential or 0,
            "Allowances": total_allowances,
            "Gross Pay": gross_pay_with_allowances,
            "SSS": p.sss_contribution or 0,
            "PhilHealth": p.philhealth_contribution or 0,
            "Pag-IBIG": p.pagibig_contribution or 0,
            "Tax Withheld": p.tax_withheld or 0,
            "Other Deductions": p.other_deductions or 0,
            "Linked Deductions": total_linked_deductions,
            "Total Deductions": total_deductions,
            "Net Pay": p.net_pay or 0,
            "Status": p.status,
            "Pay Period": f"{p.pay_period_start} - {p.pay_period_end}"
        })

    df = pd.DataFrame(data)

    # Save to Excel in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Payroll')
    output.seek(0)

    # Send file to user
    filename = f"Payroll_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@payroll_staff_bp.route('/process', methods=['GET'])
@login_required
def process_payroll():
    # Get all active employees
    employees = Employee.query.filter_by(active=True).all()

    # Get unique departments
    departments = Department.query.all()

    # Count employees per department
    dept_data = []
    for dept in departments:
        count = Employee.query.filter_by(active=True, department_id=dept.id).count()
        dept_data.append({
            "id": dept.id,
            "name": dept.name,
            "employee_count": count
        })

    return render_template(
        'payroll/staff/process_payroll.html',
        departments=dept_data
    )



@payroll_staff_bp.route('/department/<int:department_id>/employees')
@login_required
def department_employees(department_id):
    department = Department.query.get_or_404(department_id)
    
    # Correct query
    employees = Employee.query.filter_by(
        active=True,
        department_id=department_id
    ).order_by(
        asc(Employee.last_name), asc(Employee.first_name)
    ).all()

    return render_template(
        'payroll/staff/employee_list.html',
        employees=employees,
        department=department
    )



# ---------------------------
# PART-TIME PAYROLL
# ---------------------------
@payroll_staff_bp.route('/parttime', methods=['GET', 'POST'])
@login_required
def parttime_payroll():
    department_id = request.args.get('department_id', type=int)
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    # Filter employees by department AND employment type "Part-Time"
    query = Employee.query.filter_by(active=True)
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
        'payroll/staff/parttime_payroll.html',  
        employees=employee_data,
        payroll_periods=payroll_periods,
        selected_department=selected_department
    )
# ---------------------------
# GET WORKING HOURS (UPDATED)
# ---------------------------
@payroll_staff_bp.route('/get_working_hours', methods=['GET'])
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

# ---------------------------
# REGULAR PAYROLL
# ---------------------------
@payroll_staff_bp.route('/regular', methods=['GET', 'POST'])
@login_required
def regular_payroll():
    department_id = request.args.get('department_id', type=int)

    # Filter payroll periods to only monthly periods (28–31 days)
    payroll_periods = [
        period for period in PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()
        if 28 <= (period.end_date - period.start_date).days + 1 <= 31
    ]

    # Filter employees by department AND employment type "Regular"
    query = Employee.query.filter_by(active=True)
    if department_id:
        query = query.filter_by(department_id=department_id)

    employees = query.join(Employee.employment_type).filter(EmploymentType.name.ilike("regular")).all()

    selected_department = None
    if department_id:
        department = Department.query.get(department_id)
        selected_department = department.name if department else None

    # Process payroll submission
    if request.method == 'POST':
        employee_id = int(request.form.get('employee_id'))
        pay_period_id = int(request.form.get('pay_period_id'))
        payroll_period = PayrollPeriod.query.get(pay_period_id)
        employee = Employee.query.get(employee_id)

        allowance = float(request.form.get('allowance', 0))
        sss = float(request.form.get('sss', 0))
        philhealth = float(request.form.get('philhealth', 0))
        pagibig = float(request.form.get('pagibig', 0))
        tax = float(request.form.get('tax', 0))
        other = float(request.form.get('other', 0))
        basic_salary = float(request.form.get('basic_salary', 0))
        worked_days = float(request.form.get('worked_days', 0))
        total_days = float(request.form.get('total_days', 1))

        prorated_salary = (basic_salary / total_days) * worked_days
        total_deductions = sss + philhealth + pagibig + tax + other
        net_pay = round(prorated_salary - total_deductions, 2)

        payroll = Payroll(
            employee_id=employee_id,
            pay_period_id=pay_period_id,
            pay_period_start=payroll_period.start_date,
            pay_period_end=payroll_period.end_date,
            basic_salary=basic_salary,
            working_hours=worked_days,
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
            "gross_pay": round(prorated_salary, 2),
            "total_deductions": round(total_deductions, 2),
            "net_pay": net_pay,
            "pay_period": f"{payroll_period.start_date} - {payroll_period.end_date}"
        })

    # Pre-fill allowances, deductions, and existing payrolls
    employee_data = []
    for emp in employees:
        allowance_total = sum([ea.allowance.amount for ea in emp.employee_allowances])
        sss_total = sum([ed.deduction.amount for ed in emp.employee_deductions if ed.deduction.name.lower() == "sss"])
        philhealth_total = sum([ed.deduction.amount for ed in emp.employee_deductions if ed.deduction.name.lower() == "philhealth"])
        pagibig_total = sum([ed.deduction.amount for ed in emp.employee_deductions if ed.deduction.name.lower() in ["pag-ibig", "pagibig"]])
        
        payrolls_dict = {p.pay_period_id: p for p in emp.payrolls}

        employee_data.append({
            "id": emp.id,
            "full_name": emp.get_full_name(),
            "basic_salary": emp.salary or 0,
            "employment_type": emp.employment_type.name if emp.employment_type else "N/A",
            "allowance": allowance_total,
            "sss": sss_total,
            "philhealth": philhealth_total,
            "pagibig": pagibig_total,
            "existing_payrolls": list(payrolls_dict.keys()),
            "payrolls_dict": payrolls_dict
        })

    return render_template(
        'payroll/staff/regular_payroll.html',
        employees=employee_data,
        payroll_periods=payroll_periods,
        selected_department=selected_department
    )



@payroll_staff_bp.route('/get_the_working_days_for_a_month', methods=['GET'])
@login_required
def get_the_working_days_for_a_month():
    employee_id = request.args.get('employee_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not employee_id or not start_date_str or not end_date_str:
        return jsonify({"error": "Missing parameters"}), 400

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    # Count all working days in the period (Mon-Fri)
    total_working_days = sum(
        1 for d in (start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1))
        if d.weekday() < 5
    )

    # Count absences from Attendance table
    attendances = Attendance.query.filter(
        Attendance.employee_id == employee_id,
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).all()

    days_absent = sum(1 for a in attendances if not a.time_in or not a.time_out)
    worked_days = total_working_days - days_absent

    return jsonify({
        "employee_id": employee_id,
        "worked_days": worked_days,
        "total_working_days": total_working_days
    })

# ---------------------------
# CASUAL PAYROLL
# ---------------------------
@payroll_staff_bp.route('/casual', methods=['GET', 'POST'])
@login_required
def casual_payroll():
    department_id = request.args.get('department_id', type=int)
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    # Filter employees by department AND employment type "Casual"
    query = Employee.query.filter_by(active=True)
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
        'payroll/staff/casual_payroll.html',
        employees=employee_data,
        payroll_periods=payroll_periods,
        selected_department=selected_department
    )


# ---------------------------
# GET WORKED DAYS FOR CASUAL EMPLOYEES
# ---------------------------
@payroll_staff_bp.route('/get_worked_days', methods=['GET'])
@login_required
def get_worked_days():
    employee_id = request.args.get('employee_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not employee_id or not start_date_str or not end_date_str:
        return jsonify({"error": "Missing parameters"}), 400

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    attendances = Attendance.query.filter(
        Attendance.employee_id == employee_id,
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).all()

    total_hours = sum(a.working_hours or 0 for a in attendances)
    worked_days = round(total_hours / 8, 2)  # 8 hours = 1 day

    return jsonify({
        "employee_id": employee_id,
        "worked_days": worked_days
    })


@payroll_staff_bp.route('/payslips')
@login_required
@staff_required
def view_payslips():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    department_id = request.args.get('department_id', '', type=str)
    status = request.args.get('status', '', type=str)
    period_id = request.args.get('period_id', '', type=str)

    # Base query with joins
    query = Payslip.query.join(Employee).join(Department, isouter=True)

    # 🔍 Search filter
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                Payslip.payslip_number.ilike(search_pattern),
                Employee.first_name.ilike(search_pattern),
                Employee.last_name.ilike(search_pattern)
            )
        )

    # 🏢 Department filter
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    # 🧾 Status filter (map UI → DB)
    if status:
        if status == "Not Claimed":
            query = query.filter(Payslip.status == "Generated")
        elif status == "Claimed":
            query = query.filter(Payslip.status == "Distributed")
        # else: if empty, show all

    # 📅 Payroll Period filter
    if period_id:
        query = query.filter(Payslip.payroll_id == period_id)

    # Sort newest first
    payslips = query.order_by(Payslip.generated_at.desc()).paginate(page=page, per_page=20, error_out=False)

    # Dropdown data
    departments = Department.query.order_by(Department.name.asc()).all()
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    return render_template(
        'payroll/staff/payslips.html',
        payslips=payslips,
        search=search,
        departments=departments,
        selected_department=department_id,
        selected_status=status,
        payroll_periods=payroll_periods,
        selected_period=period_id
    )


# =========================================================
# MARK AS DISTRIBUTED / CLAIMED
# =========================================================
@payroll_staff_bp.route('/payslips/distribute/<int:payslip_id>', methods=['POST'])
@login_required
@staff_required
def distribute_payslip(payslip_id):
    
    payslip = Payslip.query.get_or_404(payslip_id)

    if payslip.status == "Distributed":
        flash("Payslip already marked as distributed (claimed).", "info")
        return redirect(url_for('payroll_staff.view_payslips'))

    payslip.status = "Distributed"
    payslip.claimed = True  # ✅ Mark as claimed when distributed
    payslip.distributed_at = datetime.utcnow()
    db.session.commit()

    flash(f"Payslip {payslip.payslip_number} marked as distributed and claimed.", "success")
    return redirect(url_for('payroll_staff.view_payslips'))

# =========================================================
# HELPER FUNCTION
# =========================================================
def generate_payslip(payroll, generated_by_id=None):
    payslip = Payslip(
        employee_id=payroll.employee_id,
        payroll_id=payroll.id,
        payslip_number=f"PS-{payroll.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        pay_period_start=payroll.pay_period_start,
        pay_period_end=payroll.pay_period_end,
        basic_salary=payroll.basic_salary,
        overtime_pay=payroll.overtime_pay,
        holiday_pay=payroll.holiday_pay,
        night_differential=payroll.night_differential,
        gross_pay=payroll.gross_pay,
        sss_contribution=payroll.sss_contribution,
        philhealth_contribution=payroll.philhealth_contribution,
        pagibig_contribution=payroll.pagibig_contribution,
        tax_withheld=payroll.tax_withheld,
        total_deductions=payroll.total_deductions,
        net_pay=payroll.net_pay,
        generated_by=generated_by_id
    )
    db.session.add(payslip)
    return payslip


# =========================================================
# GENERATE PAYSLIPS BY PAYROLL PERIOD (SELECT PERIOD)
# =========================================================
@payroll_staff_bp.route('/payslips/generate', methods=['GET', 'POST'])
@login_required
@staff_required
def generate_payslips_by_period():
    # Get all payroll periods
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    if request.method == 'POST':
        pay_period_id = request.form.get('pay_period_id')
        if not pay_period_id:
            flash("Please select a payroll period.", "warning")
            return redirect(url_for('payroll_staff.generate_payslips_by_period'))

        # Fetch payrolls for selected period
        payrolls = Payroll.query.filter_by(pay_period_id=pay_period_id).all()
        if not payrolls:
            flash("No payrolls found for this pay period.", "warning")
            return redirect(url_for('payroll_staff.generate_payslips_by_period'))

        generated_by_id = current_user.id
        generated_count = 0

        for payroll in payrolls:
            existing = Payslip.query.filter_by(payroll_id=payroll.id).first()
            if existing:
                continue  # Skip if payslip already exists
            payslip = generate_payslip(payroll, generated_by_id)
            db.session.add(payslip)
            generated_count += 1

        db.session.commit()
        flash(f"{generated_count} payslips successfully generated for the selected period.", "success")
        return redirect(url_for('payroll_staff.view_payslips'))

    # GET: Render selection form
    return render_template('payroll/staff/generate_payslips.html', payroll_periods=payroll_periods)

@payroll_staff_bp.route('/reports')
@login_required
@staff_required
def reports():
    form = PayrollSummaryForm()
    form.period_id.choices = [(p.id, f"{p.period_name} ({p.start_date} to {p.end_date})") for p in PayrollPeriod.query.all()]
    
    summary = None
    if request.method == 'POST' and form.validate_on_submit():
        summary = calculate_payroll_summary(form.period_id.data, form.department.data)
    
    return render_template('payroll/reports.html', form=form, summary=summary)


