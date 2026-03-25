
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from datetime import date, datetime
from flask import render_template, request, redirect, flash, url_for
from flask_login import login_required, current_user


from main_app.models.hr_models import Employee, Leave, Department, EmploymentType
from main_app.models.payroll_models import PayrollPeriod, Payroll, Deduction, Payslip, LoanPayment, PayrollDeduction, DeductionBracket
from main_app.helpers.decorators import payroll_admin_required
from main_app.extensions import db
from main_app.helpers.utils import generate_payslip


from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp


@payroll_admin_bp.route('/payroll-dashboard')
@payroll_admin_required
@login_required
def payroll_dashboard():

    today = date.today()
    start_month = today.replace(day=1)

    # ================= BASIC METRICS =================

    total_employees = Employee.query.count()

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

    # ================= PAYROLL TOTALS =================

    total_payroll_amount = (
        db.session.query(func.sum(Payroll.net_pay))
        .join(PayrollPeriod)
        .filter(PayrollPeriod.start_date >= start_month)
        .scalar() or 0
    )

    total_gross = (
        db.session.query(func.sum(Payroll.gross_pay))
        .join(PayrollPeriod)
        .filter(PayrollPeriod.start_date >= start_month)
        .scalar() or 0
    )

    total_deductions = (
        db.session.query(func.sum(Payroll.total_deductions))
        .join(PayrollPeriod)
        .filter(PayrollPeriod.start_date >= start_month)
        .scalar() or 0
    )

    highest_salary = (
        db.session.query(func.max(Payroll.net_pay))
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

    # ================= LEAVE IMPACT =================

    leave_impact = (
        db.session.query(func.count(Leave.id))
        .filter(
            Leave.status == 'Approved',
            Leave.start_date >= start_month
        )
        .scalar() or 0
    )

    # ================= PAYROLL STATUS =================

    approved_payrolls = Payroll.query.filter_by(status="Approved").count()

    draft_payrolls = Payroll.query.filter_by(status="Draft").count()

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

    # ================= DEDUCTION BREAKDOWN =================

    deduction_summary = (
        db.session.query(
            PayrollDeduction.deduction_name,
            func.sum(PayrollDeduction.employee_share)
        )
        .group_by(PayrollDeduction.deduction_name)
        .all()
    )

    ded_labels = [d for d, _ in deduction_summary]
    ded_values = [float(v or 0) for _, v in deduction_summary]

    # ================= TABLE DATA =================

    recent_payrolls = (
        Payroll.query
        .order_by(Payroll.created_at.desc())
        .limit(8)
        .all()
    )

    pending_list = (
        Payroll.query
        .filter(Payroll.status != "Approved")
        .limit(8)
        .all()
    )

    upcoming_period = PayrollPeriod.query.filter_by(status="Open").first()

    # ================= RENDER =================

    return render_template(
        'payroll/admin/views/admin_dashboard.html',

        total_employees=total_employees,
        employees_paid=employees_paid,
        pending_payrolls=pending_payrolls,

        total_payroll_amount=total_payroll_amount,
        total_gross=total_gross,
        total_deductions=total_deductions,
        highest_salary=highest_salary,
        avg_salary=avg_salary,

        leave_impact=leave_impact,

        approved_payrolls=approved_payrolls,
        draft_payrolls=draft_payrolls,

        chart_labels=chart_labels,
        chart_values=chart_values,

        salary_labels=salary_labels,
        salary_values=salary_values,

        ded_labels=ded_labels,
        ded_values=ded_values,

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

    query = Payroll.query.options(

        # Employee + relations
        joinedload(Payroll.employee)
        .joinedload(Employee.department),

        joinedload(Payroll.employee)
        .joinedload(Employee.employment_type),

        joinedload(Payroll.employee)
        .joinedload(Employee.attendances),

        # Period
        joinedload(Payroll.period),

        # Deductions
        joinedload(Payroll.deduction_breakdown),

        # ✅ Loans (ADDED)
        joinedload(Payroll.loan_payments)
        .joinedload(LoanPayment.loan)
    )

    # -------------------------
    # FILTERS
    # -------------------------

    if department_id:
        query = query.join(Employee).filter(
            Employee.department_id == department_id
        )

    if search:
        query = query.join(Employee).filter(
            or_(
                Employee.first_name.ilike(f"%{search}%"),
                Employee.last_name.ilike(f"%{search}%"),
                Employee.employee_id.ilike(f"%{search}%")
            )
        )

    if pay_period_id:
        query = query.filter(
            Payroll.payroll_period_id == pay_period_id
        )

    payrolls = query.order_by(
        Payroll.id.desc()
    ).paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    # -------------------------
    # PROCESSING
    # -------------------------

    for payroll in payrolls.items:

        employee = payroll.employee

        # -------------------------
        # EMPLOYEE TYPE
        # -------------------------

        payroll.employee_type = (
            employee.employment_type.name
            if employee and employee.employment_type
            else "Regular"
        )

        # -------------------------
        # ATTENDANCE
        # -------------------------

        if employee and payroll.period:

            attendances = [
                a for a in employee.attendances
                if payroll.period.start_date <= a.date <= payroll.period.end_date
            ]

            emp_type = payroll.employee_type

            if emp_type == "Regular":
                payroll.days_worked = sum(
                    1 for a in attendances if a.status != "Absent"
                )

            elif emp_type == "Part-Time":
                payroll.working_hours = round(
                    sum(a.working_hours for a in attendances),
                    2
                )

            elif emp_type in ["Casual", "Job Order (JO)", "Job Orders"]:
                payroll.days_worked = sum(
                    1 for a in attendances if a.status != "Absent"
                )

            else:
                payroll.days_worked = 0
                payroll.working_hours = 0

        else:
            payroll.days_worked = 0
            payroll.working_hours = 0

        # -------------------------
        # RATES
        # -------------------------

        payroll.hourly_rate_value = (
            employee.salary if payroll.employee_type == "Part-Time" else 0
        )

        payroll.daily_rate_value = (
            employee.salary
            if payroll.employee_type in ["Casual", "Job Order (JO)", "Job Orders"]
            else 0
        )

        payroll.allowance_total = payroll.allowance_total or 0
        payroll.gross_pay = payroll.gross_pay or 0

        # -------------------------
        # DEDUCTIONS
        # -------------------------

        total_deductions = sum(
            d.employee_share for d in payroll.deduction_breakdown
        )

        payroll.total_deductions = round(total_deductions, 2)

        # -------------------------
        # LOAN DEDUCTIONS
        # -------------------------

        loan_breakdown = []
        loan_total = 0

        for lp in payroll.loan_payments:

            amount = lp.amount_paid or 0
            loan_total += amount

            loan_breakdown.append({
                "name": f"{lp.loan.provider} ({lp.loan.loan_type})",
                "amount": amount
            })

        payroll.loan_total = round(loan_total, 2)
        payroll.loan_breakdown = loan_breakdown

        # -------------------------
        # NET PAY
        # -------------------------

        payroll.net_pay = round(
            payroll.gross_pay - payroll.total_deductions - payroll.loan_total,
            2
        )

    # -------------------------
    # DROPDOWNS
    # -------------------------

    departments = Department.query.all()

    payroll_periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    selected_pay_period = (
        PayrollPeriod.query.get(pay_period_id)
        if pay_period_id else None
    )

    return render_template(
        "payroll/admin/views/view_payrolls.html",
        payrolls=payrolls,
        search=search,
        departments=departments,
        selected_department=department_id,
        payroll_periods=payroll_periods,
        selected_pay_period=selected_pay_period
    )


# =========================================================
# VIEW BRACKETS
# =========================================================

@payroll_admin_bp.route("/deduction/brackets")
@login_required
@payroll_admin_required
def deduction_brackets():

    brackets = DeductionBracket.query.order_by(
        DeductionBracket.salary_from.asc()
    ).all()

    return render_template(
        "payroll/admin/views/brackets.html",
        brackets=brackets
    )




@payroll_admin_bp.route("/payroll-departments")
@login_required
@payroll_admin_required
def payroll_departments():

    today = date.today()

    period_id = request.args.get("period_id", type=int)
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    # Default period = latest or closest to today
    if period_id:
        period = PayrollPeriod.query.get(period_id)
    else:
        period = PayrollPeriod.query.filter(PayrollPeriod.start_date <= today)\
                                     .order_by(PayrollPeriod.start_date.desc()).first()

    if not period and payroll_periods:
        period = payroll_periods[0]

    # Get departments and compute total payroll
    departments = Department.query.all()
    department_rows = []
    municipality_total = 0

    for dept in departments:
        employees = Employee.query.filter_by(department_id=dept.id).all()
        dept_total = 0
        for emp in employees:
            payroll = Payroll.query.filter_by(
                employee_id=emp.id,
                payroll_period_id=period.id
            ).first()
            if payroll:
                dept_total += payroll.net_pay or 0

        department_rows.append({
            "id": dept.id,
            "name": dept.name,
            "employee_count": len(employees),
            "total": round(dept_total, 2)
        })
        municipality_total += dept_total

    return render_template(
        "payroll/admin/views/department_payrolls.html",
        payroll_periods=payroll_periods,
        selected_period=period,
        department_rows=department_rows,
        municipality_total=round(municipality_total, 2)
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
        'payroll/admin/views/view_employees.html',
        employees=employees,
        search=search,
        departments=departments,
        selected_department=department_id
    )




@payroll_admin_bp.route('/payroll-periods')
@payroll_admin_required
@login_required
def view_payroll_periods():
    """
    View Payroll Periods with optional filters:
      - status (Open, Processing, Closed)
      - start_date (YYYY-MM-DD)
      - end_date (YYYY-MM-DD)
    Pagination included.
    """

    # ===== Get filters from query parameters =====
    status_filter = request.args.get('status', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    # ===== Base query =====
    query = PayrollPeriod.query

    # ===== Apply filters =====

    # Status filter
    if status_filter:
        query = query.filter(PayrollPeriod.status == status_filter)

    # Start date filter
    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
            query = query.filter(PayrollPeriod.start_date >= start_date_obj)
        except ValueError:
            pass

    # End date filter
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(PayrollPeriod.end_date <= end_date_obj)
        except ValueError:
            pass

    # ===== Pagination =====
    page = request.args.get('page', 1, type=int)
    per_page = 10  # You can adjust this

    periods_paginated = query.order_by(
        PayrollPeriod.id.desc()
    ).paginate(
        page=page,
        per_page=per_page
    )

    # ===== Render Template =====
    return render_template(
        'payroll/admin/views/view_periods.html',
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
        "payroll/admin/views/history_dashboard.html",
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
        'payroll/admin/views/view_deductions.html',
        deductions=deductions_paginated.items,
        pagination=deductions_paginated,
        search=search
    )


# =========================================================
# GENERATE PAYSLIPS BY PAYROLL PERIOD (IMPROVED)
# =========================================================
@payroll_admin_bp.route('/payslips/generate', methods=['GET', 'POST'])
@payroll_admin_required
@login_required
def generate_payslips_by_period():

    payroll_periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    if request.method == 'POST':

        pay_period_id = request.form.get('pay_period_id')

        if not pay_period_id:
            flash("Please select a payroll period.", "warning")
            return redirect(url_for('payroll_admin_bp.generate_payslips_by_period'))

        pay_period_id = int(pay_period_id)

        payrolls = Payroll.query.options(
            joinedload(Payroll.employee)
                .joinedload(Employee.department),

            joinedload(Payroll.employee)
                .joinedload(Employee.position),

            joinedload(Payroll.employee)
                .joinedload(Employee.employment_type),

            joinedload(Payroll.period),

            joinedload(Payroll.deduction_breakdown),

            joinedload(Payroll.loan_payments)
                .joinedload(LoanPayment.loan)
        ).filter_by(
            payroll_period_id=pay_period_id
        ).all()

        if not payrolls:
            flash("No payrolls found for this pay period.", "warning")
            return redirect(url_for('payroll_admin_bp.generate_payslips_by_period'))

        generated_by_id = current_user.id
        generated_count = 0

        for payroll in payrolls:

            # جلوگیری duplicate
            existing = Payslip.query.filter_by(
                payroll_id=payroll.id
            ).first()

            if existing:
                continue

            employee = payroll.employee
            period = payroll.period

            # =========================
            # BASIC INFO
            # =========================
            monthly_rate = employee.salary or 0
            semi_monthly = monthly_rate / 2

            allowance = payroll.allowance_total or 0
            overtime = payroll.overtime_pay or 0

            gross_pay = payroll.gross_pay or 0

            # =========================
            # DEDUCTIONS
            # =========================
            deduction_dict = {}
            total_deductions = 0

            for d in payroll.deduction_breakdown:
                name = (d.deduction_name or "").upper()
                amount = d.employee_share or 0

                deduction_dict[name] = amount
                total_deductions += amount

            # =========================
            # LOANS
            # =========================
            loan_dict = {}

            for lp in payroll.loan_payments:
                loan_name = f"{lp.loan.provider} ({lp.loan.loan_type})".upper()
                amount = lp.amount_paid or 0

                loan_dict[loan_name] = amount
                total_deductions += amount

            # =========================
            # NET PAY
            # =========================
            net_pay = round(gross_pay - total_deductions, 2)

            # =========================
            # PAYSLIP NUMBER
            # =========================
            import uuid
            payslip_number = f"PS-{uuid.uuid4().hex[:8].upper()}"

            # =========================
            # CREATE PAYSLIP
            # =========================
            payslip = Payslip(
                employee_id=employee.id,
                payroll_id=payroll.id,
                payslip_number=payslip_number,
                gross_pay=gross_pay,
                total_deductions=round(total_deductions, 2),
                net_pay=net_pay,
                status="Generated"
            )

            # =========================
            # OPTIONAL: SAVE BREAKDOWN (RECOMMENDED)
            # =========================
            if hasattr(Payslip, "breakdown"):
                payslip.breakdown = {
                    "employee_name": employee.get_full_name(),
                    "position": employee.position.name if employee.position else "-",
                    "department": employee.department.name if employee.department else "-",
                    "employment_type": employee.employment_type.name if employee.employment_type else "Regular",

                    "pay_date": period.pay_date.strftime("%m/%d/%y"),
                    "period_start": period.start_date.strftime("%m/%d/%y"),
                    "period_end": period.end_date.strftime("%m/%d/%y"),
                    "period_name": period.period_name,

                    "monthly_rate": monthly_rate,
                    "semi_monthly": semi_monthly,

                    "allowance": allowance,
                    "overtime": overtime,

                    "gross_pay": gross_pay,
                    "deductions": deduction_dict,
                    "loans": loan_dict,
                    "total_deductions": total_deductions,
                    "net_pay": net_pay
                }

            db.session.add(payslip)
            generated_count += 1

        db.session.commit()

        flash(
            f"{generated_count} payslips successfully generated for the selected period.",
            "success"
        )

        return redirect(url_for('payroll_admin_bp.view_payslips'))

    return render_template(
        'payroll/admin/payslips/generate_payslips.html',
        payroll_periods=payroll_periods
    )




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
        'payroll/admin/views/view_payslips.html',
        payslips=payslips,
        search=search,
        departments=departments,
        selected_department=department_id,
        selected_status=status,
        payroll_periods=payroll_periods,
        selected_period=period_id
    )

