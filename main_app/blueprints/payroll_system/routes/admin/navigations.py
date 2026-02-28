from main_app.models.hr_models import Employee, Leave, Department
from main_app.models.payroll_models import PayrollPeriod, Payroll, Deduction, Payslip
from main_app.utils import payroll_admin_required
from main_app.extensions import db
from main_app.functions import generate_payslip

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from datetime import date
from flask import render_template, request, redirect, flash, url_for
from flask_login import login_required, current_user


from . import payroll_admin_bp


@payroll_admin_bp.route('/dashboard')
@payroll_admin_required
@login_required
def payroll_dashboard():

    today = date.today()
    start_month = today.replace(day=1)

    total_employees = Employee.query.count()

    # ================= METRICS =================

    employees_paid = (
        db.session.query(Payroll)
        .join(PayrollPeriod)
        .filter(
            Payroll.status == "Approved",
            PayrollPeriod.start_date >= start_month
        )
        .count()
    )

    pending_payrolls = (
        db.session.query(Payroll)
        .join(PayrollPeriod)
        .filter(
            Payroll.status != "Approved",
            PayrollPeriod.start_date >= start_month
        )
        .count()
    )

    total_payroll_amount = (
        db.session.query(func.sum(Payroll.net_pay))
        .join(PayrollPeriod)
        .filter(PayrollPeriod.start_date >= start_month)
        .scalar() or 0
    )

    avg_salary = (
        db.session.query(func.avg(Payroll.net_pay))
        .join(PayrollPeriod)
        .filter(PayrollPeriod.start_date >= start_month)
        .scalar() or 0
    )

    leave_impact = (
        db.session.query(func.count(Leave.id))
        .filter(
            Leave.status == 'Approved',
            Leave.start_date >= start_month
        )
        .scalar() or 0
    )

    # ================= PAYROLL TREND =================

    monthly_data = (
        db.session.query(
            func.strftime('%Y-%m', PayrollPeriod.start_date),
            func.sum(Payroll.net_pay)
        )
        .join(PayrollPeriod)
        .group_by(func.strftime('%Y-%m', PayrollPeriod.start_date))
        .order_by(func.strftime('%Y-%m', PayrollPeriod.start_date))
        .all()
    )

    chart_labels = [m for m, _ in monthly_data]
    chart_values = [float(v or 0) for _, v in monthly_data]

    # ================= SALARY TREND =================

    salary_data = (
        db.session.query(
            func.strftime('%Y-%m', PayrollPeriod.start_date),
            func.avg(Payroll.net_pay)
        )
        .join(PayrollPeriod)
        .group_by(func.strftime('%Y-%m', PayrollPeriod.start_date))
        .order_by(func.strftime('%Y-%m', PayrollPeriod.start_date))
        .all()
    )

    salary_labels = [m for m, _ in salary_data]
    salary_values = [float(v or 0) for _, v in salary_data]

    # ================= TABLES =================

    recent_payrolls = Payroll.query.order_by(Payroll.created_at.desc()).limit(8).all()

    pending_list = Payroll.query.filter(Payroll.status != 'Approved').limit(8).all()

    upcoming_period = PayrollPeriod.query.filter_by(status="Open").first()

    return render_template(
        'payroll/admin/navigations/admin_dashboard.html',

        total_employees=total_employees,
        employees_paid=employees_paid,
        pending_payrolls=pending_payrolls,
        total_payroll_amount=total_payroll_amount,
        avg_salary=avg_salary,
        leave_impact=leave_impact,

        chart_labels=chart_labels,
        chart_values=chart_values,
        salary_labels=salary_labels,
        salary_values=salary_values,

        recent_payrolls=recent_payrolls,
        pending_list=pending_list,
        upcoming_period=upcoming_period
    )




@payroll_admin_bp.route('/payrolls')
@payroll_admin_required
@login_required
def view_payrolls():
    search = request.args.get('search', '', type=str).strip()
    department_id = request.args.get('department_id', type=int)
    pay_period_id = request.args.get('pay_period_id', type=int)
    page = request.args.get('page', 1, type=int)

    # ================= BASE QUERY =================
    query = Payroll.query.join(Employee, Payroll.employee_id == Employee.id)

    # ---------------- Department Filter ----------------
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    # ---------------- Search ----------------
    if search:
        query = query.filter(
            or_(
                Employee.first_name.ilike(f"%{search}%"),
                Employee.last_name.ilike(f"%{search}%"),
                Employee.employee_id.ilike(f"%{search}%")
            )
        )

    # ---------------- Payroll Period ----------------
    if pay_period_id:
        query = query.filter(Payroll.payroll_period_id == pay_period_id)

    # ---------------- Pagination ----------------
    payrolls = query.order_by(Payroll.id.desc()).paginate(page=page, per_page=10, error_out=False)

    # Dropdown Data
    departments = Department.query.all()
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    selected_pay_period = PayrollPeriod.query.get(pay_period_id) if pay_period_id else None

    return render_template(
        "payroll/admin/navigations/view_payrolls.html",
        payrolls=payrolls,
        search=search,
        departments=departments,
        selected_department=department_id,
        payroll_periods=payroll_periods,
        selected_pay_period=selected_pay_period
    )





@payroll_admin_bp.route('/process', methods=['GET'])
@payroll_admin_required
@login_required
def process_payroll():
    # Get all active employees
    employees = Employee.query.filter_by(status="Active").all()

    # Get unique departments
    departments = Department.query.all()

    # Count employees per department
    dept_data = []
    for dept in departments:
        count = Employee.query.filter_by(status="Active", department_id=dept.id).count()
        dept_data.append({
            "id": dept.id,
            "name": dept.name,
            "employee_count": count
        })

    return render_template(
        'payroll/admin/navigations/process_payroll.html',
        departments=dept_data
    )





@payroll_admin_bp.route('/employees')
@payroll_admin_required
@login_required
def view_employees():
    search = request.args.get('search', '', type=str)
    department_id = request.args.get('department_id', '', type=str)
    page = request.args.get('page', 1, type=int)

    query = Employee.query.options(
        joinedload(Employee.department),
        joinedload(Employee.position)
    )

   
    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%")) |
            (Employee.last_name.ilike(f"%{search}%")) |
            (Employee.employee_id.ilike(f"%{search}%")) |
            (Employee.email.ilike(f"%{search}%"))
        )

    
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    employees = query.order_by(Employee.last_name).paginate(page=page, per_page=10, error_out=False)

    
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        'payroll/admin/navigations/view_employees.html',
        employees=employees,
        search=search,
        departments=departments,
        selected_department=department_id
    )



@payroll_admin_bp.route('/payroll-periods')
@payroll_admin_required
@login_required
def view_payroll_periods():
    # Get filters from query parameters
    status_filter = request.args.get('status', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    # Base query
    query = PayrollPeriod.query

    # Apply filters
    if status_filter:
        query = query.filter_by(status=status_filter)
    if start_date:
        query = query.filter(PayrollPeriod.start_date >= start_date)
    if end_date:
        query = query.filter(PayrollPeriod.end_date <= end_date)

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Change as needed
    periods_paginated = query.order_by(PayrollPeriod.id.desc()).paginate(page=page, per_page=per_page)

    return render_template(
        'payroll/admin/navigations/view_periods.html',
        periods=periods_paginated.items,
        pagination=periods_paginated
    )




@payroll_admin_bp.route('/payroll-history-dashboard')
@payroll_admin_required
@login_required
def payroll_history_dashboard():
    # Fetch all employees and all payroll periods
    employees = Employee.query.order_by(Employee.last_name).all()
    periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    return render_template(
        "payroll/admin/navigations/history_dashboard.html",
        employees=employees,
        periods=periods
    )




# ==========================
# LIST & SEARCH DEDUCTIONS
# ==========================
@payroll_admin_bp.route('/deductions')
@payroll_admin_required
@login_required
def deductions():
    search = request.args.get('search', '', type=str).strip()
    page = request.args.get('page', 1, type=int)
    per_page = 10  # adjust page size

    query = Deduction.query
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(Deduction.name.ilike(search_pattern))

    deductions_paginated = query.order_by(Deduction.id.desc()).paginate(page=page, per_page=per_page)

    return render_template(
        'payroll/admin/navigations/view_deductions.html',
        deductions=deductions_paginated.items,
        pagination=deductions_paginated,
        search=search
    )



# =========================================================
# GENERATE PAYSLIPS BY PAYROLL PERIOD (SELECT PERIOD)
# =========================================================
@payroll_admin_bp.route('/payslips/generate', methods=['GET', 'POST'])
@payroll_admin_required
@login_required
def generate_payslips_by_period():
    # Get all payroll periods
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    if request.method == 'POST':
        pay_period_id = request.form.get('pay_period_id')
        if not pay_period_id:
            flash("Please select a payroll period.", "warning")
            return redirect(url_for('payroll_admin.generate_payslips_by_period'))

        # Fetch payrolls for selected period
        payrolls = Payroll.query.filter_by(pay_period_id=pay_period_id).all()
        if not payrolls:
            flash("No payrolls found for this pay period.", "warning")
            return redirect(url_for('payroll_admin.generate_payslips_by_period'))

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
        return redirect(url_for('payroll_admin.view_payslips'))

    # GET: Render selection form
    return render_template('payroll/admin/generate_payslips.html', payroll_periods=payroll_periods)




@payroll_admin_bp.route('/payslips')
@payroll_admin_required
@login_required
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
        'payroll/admin/view_payslips.html',
        payslips=payslips,
        search=search,
        departments=departments,
        selected_department=department_id,
        selected_status=status,
        payroll_periods=payroll_periods,
        selected_period=period_id
    )

