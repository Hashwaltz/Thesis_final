from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from flask import render_template, request, redirect, flash, url_for, current_app
from flask_login import login_required, current_user

from main_app.models.hr_models import Employee, Leave, Department, EmploymentType
from main_app.models.payroll_models import PayrollPeriod, Payroll, Deduction, Payslip, PayrollDeduction, DeductionBracket, LoanPayment
from main_app.helpers.decorators import payroll_admin_required
from main_app.extensions import db
from main_app.helpers.utils import generate_payslip

from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp


@payroll_admin_bp.route('/payroll-dashboard')
@payroll_admin_required
@login_required
def payroll_dashboard():
    today = date.today()
    
    # Default: Last 6 months of data
    default_from = today - relativedelta(months=5)
    default_to = today
    
    # Parse query params safely
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    
    try:
        date_from = date.fromisoformat(date_from_str) if date_from_str else default_from
    except (ValueError, TypeError):
        date_from = default_from
        
    try:
        date_to = date.fromisoformat(date_to_str) if date_to_str else default_to
    except (ValueError, TypeError):
        date_to = default_to

    # ✅ OVERLAP CONDITION: Catches any payroll period that touches the date range
    period_overlap = (PayrollPeriod.start_date <= date_to) & (PayrollPeriod.end_date >= date_from)
    
    # ✅ Accept both "Approved" AND "Processed" as completed payroll statuses
    COMPLETED_STATUSES = ["Approved", "Processed"]

    # ================= BASIC METRICS =================
    total_employees = Employee.query.filter_by(status="Active").count()
    
    # Paid query - includes completed statuses only
    paid_query = db.session.query(Payroll)\
        .join(PayrollPeriod, Payroll.payroll_period_id == PayrollPeriod.id)\
        .filter(
            Payroll.status.in_(COMPLETED_STATUSES),
            period_overlap
        )
    
    employees_paid = paid_query.count()
    payroll_completion_rate = round((employees_paid / total_employees * 100) if total_employees > 0 else 0, 1)
    
    # Pending query - excludes completed statuses
    pending_payrolls = db.session.query(Payroll)\
        .join(PayrollPeriod, Payroll.payroll_period_id == PayrollPeriod.id)\
        .filter(
            ~Payroll.status.in_(COMPLETED_STATUSES),
            period_overlap
        ).count()
    
    # ================= FINANCIAL METRICS =================
    financial_data = paid_query.with_entities(
        func.sum(Payroll.net_pay).label('total_net'),
        func.sum(Payroll.gross_pay).label('total_gross'),
        func.sum(Payroll.total_deductions).label('total_deductions'),
        func.avg(Payroll.net_pay).label('avg_net'),
        func.max(Payroll.net_pay).label('max_net'),
        func.min(Payroll.net_pay).label('min_net')
    ).first()
    
    # ✅ Safe attribute access (SQLAlchemy Row, NOT dict)
    total_payroll_amount = financial_data.total_net or 0 if financial_data else 0
    total_gross = financial_data.total_gross or 0 if financial_data else 0
    total_deductions = financial_data.total_deductions or 0 if financial_data else 0
    avg_salary = financial_data.avg_net or 0 if financial_data else 0
    highest_salary = financial_data.max_net or 0 if financial_data else 0
    lowest_salary = financial_data.min_net or 0 if financial_data else 0
    
    # ================= DEPARTMENT BREAKDOWN =================
    dept_breakdown = db.session.query(
        Department.name,
        func.count(Payroll.id).label('paid_count'),
        func.sum(Payroll.net_pay).label('dept_total')
    ).select_from(Payroll)\
     .join(Employee, Payroll.employee_id == Employee.id)\
     .join(Department, Employee.department_id == Department.id)\
     .join(PayrollPeriod, Payroll.payroll_period_id == PayrollPeriod.id)\
     .filter(
         Payroll.status.in_(COMPLETED_STATUSES),
         period_overlap
     ).group_by(Department.id).all()
    
    # ================= PAYROLL TREND (Last 6 months) =================
    from_date_trend = today - relativedelta(months=5)
    monthly_trend = db.session.query(
        func.strftime('%Y-%m', PayrollPeriod.start_date).label('month'),
        func.sum(Payroll.net_pay).label('total'),
        func.count(Payroll.id).label('count')
    ).join(PayrollPeriod, Payroll.payroll_period_id == PayrollPeriod.id)\
     .filter(PayrollPeriod.start_date >= from_date_trend)\
     .group_by(func.strftime('%Y-%m', PayrollPeriod.start_date))\
     .order_by(func.strftime('%Y-%m', PayrollPeriod.start_date)).all()
    
    ALLOWED_DEDUCTIONS = [
        "PhilHealth",
        "GSIS", 
        "Withholding Tax (1–15)",
        "Pag-IBIG",
        "SSS",
        "Withholding Tax (16–End)",
        "CTW Tax",
        "GMP-PT"
    ]
    # ================= DEDUCTION BREAKDOWN =================
    deduction_summary = db.session.query(
        PayrollDeduction.deduction_name,
        func.sum(PayrollDeduction.employee_share).label('total')
    ).join(Payroll, PayrollDeduction.payroll_id == Payroll.id)\
    .join(PayrollPeriod, Payroll.payroll_period_id == PayrollPeriod.id)\
    .filter(
        period_overlap,
        PayrollDeduction.deduction_name.in_(ALLOWED_DEDUCTIONS)  # ✅ Filter to statutory deductions only
    )\
    .group_by(PayrollDeduction.deduction_name)\
    .order_by(func.sum(PayrollDeduction.employee_share).desc()).all()
    
    # ================= LEAVE & OVERTIME IMPACT =================
    leave_impact = db.session.query(func.count(Leave.id))\
        .filter(
            Leave.status == 'Approved',
            Leave.start_date.between(date_from, date_to)
        ).scalar() or 0
    
    overtime_total = db.session.query(func.sum(Payroll.overtime_hours))\
        .join(PayrollPeriod, Payroll.payroll_period_id == PayrollPeriod.id)\
        .filter(period_overlap)\
        .scalar() or 0
    
    # ================= STATUS DISTRIBUTION (All statuses for chart) =================
    status_counts = db.session.query(
        Payroll.status,
        func.count(Payroll.id)
    ).join(PayrollPeriod, Payroll.payroll_period_id == PayrollPeriod.id)\
     .filter(period_overlap)\
     .group_by(Payroll.status).all()
    
    # ================= RECENT ACTIVITY (No date filter - always show latest) =================
    recent_payrolls = Payroll.query\
        .options(joinedload(Payroll.employee), joinedload(Payroll.period))\
        .order_by(Payroll.created_at.desc())\
        .limit(10).all()
    
    pending_list = Payroll.query\
        .filter(~Payroll.status.in_(COMPLETED_STATUSES))\
        .options(joinedload(Payroll.employee))\
        .order_by(Payroll.created_at.desc())\
        .limit(8).all()
    
    # ================= UPCOMING DEADLINES =================
    upcoming_period = PayrollPeriod.query\
        .filter(PayrollPeriod.status == "Open", PayrollPeriod.end_date >= today)\
        .order_by(PayrollPeriod.end_date.asc()).first()
    
    days_until_payday = (upcoming_period.pay_date - today).days if upcoming_period else None
    
    # ================= ALERTS =================
    alerts = []
    if total_employees > 0 and pending_payrolls > total_employees * 0.3:
        alerts.append({'type': 'warning', 'message': f'{pending_payrolls} payrolls pending approval'})
    if overtime_total and overtime_total > 500:
        alerts.append({'type': 'info', 'message': f'High overtime: {overtime_total:.1f} hours this period'})
    if employees_paid == 0 and total_employees > 0:
        alerts.append({
            'type': 'info', 
            'message': f'No completed payrolls found for {date_from.strftime("%b %d")} to {date_to.strftime("%b %d, %Y")}. Try adjusting the date range.'
        })
    
    # ================= PREPARE CHART DATA =================
    chart_labels = [row.month for row in monthly_trend]
    chart_values = [float(row.total or 0) for row in monthly_trend]
    chart_counts = [int(row.count or 0) for row in monthly_trend]
    
    ded_labels = [row.deduction_name for row in deduction_summary]
    ded_values = [float(row.total or 0) for row in deduction_summary]
    
    status_labels = [row[0] for row in status_counts]
    status_values = [int(row[1]) for row in status_counts]
    
    dept_labels = [row.name for row in dept_breakdown]
    dept_values = [float(row.dept_total or 0) for row in dept_breakdown]
    
    # 🔍 DEBUG LOGGING (Remove in production)
    current_app.logger.info(f"Dashboard: date_from={date_from}, date_to={date_to}, paid={employees_paid}, total_emp={total_employees}")
    
    return render_template(
        'payroll/admin/views/admin_dashboard.html',
        # Metrics
        total_employees=total_employees,
        employees_paid=employees_paid,
        pending_payrolls=pending_payrolls,
        payroll_completion_rate=payroll_completion_rate,
        
        # Financials
        total_payroll_amount=total_payroll_amount,
        total_gross=total_gross,
        total_deductions=total_deductions,
        highest_salary=highest_salary,
        lowest_salary=lowest_salary,
        avg_salary=avg_salary,
        
        # Impact metrics
        leave_impact=leave_impact,
        overtime_total=round(overtime_total, 1) if overtime_total else 0,
        
        # Status & Trends
        status_labels=status_labels,
        status_values=status_values,
        chart_labels=chart_labels,
        chart_values=chart_values,
        chart_counts=chart_counts,
        
        # Breakdowns
        ded_labels=ded_labels,
        ded_values=ded_values,
        dept_labels=dept_labels,
        dept_values=dept_values,
        
        # Tables & Lists
        recent_payrolls=recent_payrolls,
        pending_list=pending_list,
        
        # Context
        upcoming_period=upcoming_period,
        days_until_payday=days_until_payday,
        alerts=alerts,
        
        # Filters (ISO format for form persistence)
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        
        # For display in template
        filter_start=date_from,
        filter_end=date_to,
    )



@payroll_admin_bp.route('/payrolls')
@payroll_admin_required
@login_required
def view_payrolls():
    search = request.args.get('search', '', type=str).strip()
    department_id = request.args.get('department_id', type=int)
    pay_period_id = request.args.get('pay_period_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # ONLY filter pay_period in SQL
    base_query = Payroll.query
    if pay_period_id is not None:
        base_query = base_query.filter(Payroll.payroll_period_id == pay_period_id)
    
    # Fetch ALL with eager loading - NO employee filters in SQL
    all_payrolls = base_query.options(
        joinedload(Payroll.employee).joinedload(Employee.department),
        joinedload(Payroll.employee).joinedload(Employee.employment_type),
        joinedload(Payroll.employee).joinedload(Employee.attendances),
        joinedload(Payroll.period),
        joinedload(Payroll.deduction_breakdown),
        joinedload(Payroll.loan_payments).joinedload(LoanPayment.loan)
    ).order_by(Payroll.id.desc()).all()

    # FILTER IN PYTHON - zero SQL joins for filtering
    filtered = []
    for p in all_payrolls:
        emp = p.employee
        if not emp:
            continue
        if department_id is not None and emp.department_id != department_id:
            continue
        if search:
            s = search.lower()
            if not (s in emp.first_name.lower() or s in emp.last_name.lower() or s in emp.employee_id.lower()):
                continue
        filtered.append(p)

    # Manual pagination
    total = len(filtered)
    pages = (total + per_page - 1) // per_page if total else 0
    start = (page - 1) * per_page
    items = filtered[start:start + per_page]

    # Pagination object for template
    class Pag:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page if total else 0
            self.has_next = page * per_page < total
            self.has_prev = page > 1
            self.next_num = page + 1 if self.has_next else None
            self.prev_num = page - 1 if self.has_prev else None
    payrolls = Pag(items, page, per_page, total)

    # Processing logic
    for payroll in payrolls.items:
        employee = payroll.employee
        payroll.employee_type = employee.employment_type.name if employee and employee.employment_type else "Regular"
        if employee and payroll.period:
            attendances = [a for a in employee.attendances if payroll.period.start_date <= a.date <= payroll.period.end_date]
            emp_type = payroll.employee_type
            if emp_type == "Regular":
                payroll.days_worked = sum(1 for a in attendances if a.status != "Absent")
            elif emp_type == "Part-Time":
                payroll.working_hours = round(sum(a.working_hours for a in attendances), 2)
            elif emp_type in ["Casual", "Job Order (JO)", "Job Orders"]:
                payroll.days_worked = sum(1 for a in attendances if a.status != "Absent")
            else:
                payroll.days_worked = 0
                payroll.working_hours = 0
        else:
            payroll.days_worked = 0
            payroll.working_hours = 0
        payroll.hourly_rate_value = employee.salary if payroll.employee_type == "Part-Time" else 0
        payroll.daily_rate_value = employee.salary if payroll.employee_type in ["Casual", "Job Order (JO)", "Job Orders"] else 0
        payroll.allowance_total = payroll.allowance_total or 0
        payroll.gross_pay = payroll.gross_pay or 0
        payroll.total_deductions = round(sum(d.employee_share for d in payroll.deduction_breakdown), 2)
        loan_breakdown, loan_total = [], 0
        for lp in payroll.loan_payments:
            amount = lp.amount_paid or 0
            loan_total += amount
            loan_breakdown.append({"name": f"{lp.loan.provider} ({lp.loan.loan_type})", "amount": amount})
        payroll.loan_total = round(loan_total, 2)
        payroll.loan_breakdown = loan_breakdown
        payroll.net_pay = round(payroll.gross_pay - payroll.total_deductions - payroll.loan_total, 2)

    departments = Department.query.all()
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()
    selected_pay_period = PayrollPeriod.query.get(pay_period_id) if pay_period_id else None

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




from flask import flash, render_template, request
from datetime import date
# ... your other imports ...

@payroll_admin_bp.route("/payroll-departments")
@login_required
@payroll_admin_required
def payroll_departments():
    today = date.today()
    period_id = request.args.get("period_id", type=int)
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    period = None

    # 1. Try explicit period_id
    if period_id:
        period = PayrollPeriod.query.get(period_id)

    # 2. Fallback to latest period starting on or before today
    if not period:
        period = PayrollPeriod.query.filter(PayrollPeriod.start_date <= today)\
                                    .order_by(PayrollPeriod.start_date.desc()).first()

    # 3. Fallback to absolute latest period regardless of date
    if not period and payroll_periods:
        period = payroll_periods[0]

    # 4. CRITICAL: Handle case where NO periods exist in the DB
    if not period:
        flash("No payroll periods have been created yet.", "warning")
        return render_template(
            "payroll/admin/views/department_payrolls.html",
            payroll_periods=[],
            selected_period=None,
            department_rows=[],
            municipality_total=0
        )

    # Proceed only when a valid period is guaranteed
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

import logging

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
logger = logging.getLogger(__name__)


@payroll_admin_bp.route('/payslips/generate', methods=['GET', 'POST'])
@payroll_admin_required
@login_required
def generate_payslips_by_period():
    
    # GET: Show period selection form
    if request.method == 'GET':
        payroll_periods = PayrollPeriod.query.order_by(
            PayrollPeriod.start_date.desc()
        ).all()
        
        return render_template(
            'payroll/admin/payslips/generate_payslips.html',
            payroll_periods=payroll_periods
        )
    
    # POST: Generate payslips
    try:
        pay_period_id = request.form.get('pay_period_id')
        
        if not pay_period_id:
            flash("Please select a payroll period.", "warning")
            return redirect(url_for('payroll_admin_bp.generate_payslips_by_period'))
        
        pay_period_id = int(pay_period_id)
        payroll_period = PayrollPeriod.query.get_or_404(pay_period_id)
        
        # Fetch payrolls for this period
        payrolls = Payroll.query.filter_by(
            payroll_period_id=pay_period_id
        ).join(Employee).all()
        
        if not payrolls:
            flash(f"No payrolls found for period {payroll_period.start_date.strftime('%B %Y')}.", "warning")
            return redirect(url_for('payroll_admin_bp.generate_payslips_by_period'))
        
        generated_count = 0
        skipped_count = 0
        errors = []
        
        for payroll in payrolls:
            try:
                # 🔍 Check for existing payslip (employee + payroll combo)
                existing = Payslip.query.filter_by(
                    employee_id=payroll.employee_id,
                    payroll_id=payroll.id
                ).first()
                
                if existing:
                    skipped_count += 1
                    continue
                
                # 🔢 Generate unique payslip number
                payslip_number = generate_unique_payslip_number(payroll_period)
                
                # 📊 Calculate totals (adjust to your business logic)
                gross_pay = payroll.gross_pay or 0.0
                # Example: 6.5% total deductions - customize as needed
                total_deductions = round(gross_pay * 0.065, 2)
                net_pay = round(gross_pay - total_deductions, 2)
                
                # 📝 Create payslip - ONLY fields your model actually has
                new_payslip = Payslip(
                    employee_id=payroll.employee_id,
                    payroll_id=payroll.id,
                    payslip_number=payslip_number,
                    gross_pay=gross_pay,
                    total_deductions=total_deductions,
                    net_pay=net_pay,
                    generated_at=datetime.utcnow(),
                    status='Generated'
                    # ❌ Removed: generated_by (not in your model)
                    # ❌ Removed: any other fields not defined in your Payslip class
                )
                
                db.session.add(new_payslip)
                generated_count += 1
                logger.info(f"✓ Generated {payslip_number} for employee {payroll.employee_id}")
                
            except IntegrityError as ie:
                db.session.rollback()
                error_msg = f"Integrity error payroll {payroll.id}: {str(ie)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
                
            except Exception as e:
                db.session.rollback()
                error_msg = f"Error payroll {payroll.id}: {str(e)}"
                logger.exception(error_msg)
                errors.append(error_msg)
                continue
        
        # 🎯 Final commit
        if errors and generated_count == 0:
            db.session.rollback()
            flash("Failed to generate payslips. Check logs.", "danger")
        else:
            db.session.commit()
            
            # 📢 Build feedback message
            messages = []
            if generated_count > 0:
                messages.append(f"✅ {generated_count} payslip(s) generated")
            if skipped_count > 0:
                messages.append(f"⏭️ {skipped_count} duplicate(s) skipped")
            if errors:
                messages.append(f"⚠️ {len(errors)} error(s) - see logs")
            
            flash(" | ".join(messages), "success" if not errors else "warning")
        
        return redirect(url_for('payroll_admin_bp.view_payslips'))
        
    except SQLAlchemyError as db_err:
        db.session.rollback()
        logger.exception(f"DB error: {db_err}")
        flash("Database error. Please try again.", "danger")
        return redirect(url_for('payroll_admin_bp.generate_payslips_by_period'))
        
    except Exception as e:
        db.session.rollback()
        logger.exception(f"Unexpected error: {e}")
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('payroll_admin_bp.view_payslips_by_period'))
    

@payroll_admin_bp.route('/payslips')
@payroll_admin_required
@login_required
def view_payslips():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    department_id = request.args.get('department_id', '', type=str)
    status = request.args.get('status', '', type=str)
    period_id = request.args.get('period_id', '', type=str)

    # Cast IDs to int if numeric
    if department_id and department_id.isdigit():
        department_id = int(department_id)
    else:
        department_id = None
        
    if period_id and period_id.isdigit():
        period_id = int(period_id)
    else:
        period_id = None

    # Base query
    query = Payslip.query.join(Employee).join(Department, isouter=True)

    # SEARCH FILTER
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                Payslip.payslip_number.ilike(search_pattern),
                Employee.first_name.ilike(search_pattern),
                Employee.last_name.ilike(search_pattern)
            )
        )

    # DEPARTMENT FILTER
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    # STATUS FILTER — MATCH YOUR ACTUAL DB VALUES!
    if status:
        if status == "Generated":  # Frontend sends this
            query = query.filter(Payslip.status == "Generated")  # ← Verify this matches your DB!
        elif status == "Distributed":
            query = query.filter(Payslip.status == "CLAIMED")  # ← Verify this matches your DB!

    # PERIOD FILTER
    if period_id:
        query = query.filter(Payslip.payroll_period_id == period_id)

    # ORDER + PAGINATION
    payslips = query.order_by(Payslip.generated_at.desc())\
        .paginate(page=page, per_page=20, error_out=False)

    # DROPDOWN DATA
    departments = Department.query.order_by(Department.name.asc()).all()
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()

    return render_template(
        'payroll/admin/views/view_payslips.html',
        payslips=payslips,
        search=search,
        departments=departments,
        selected_department=department_id,
        selected_status=status,  # Keep as string for template comparison
        payroll_periods=payroll_periods,
        selected_period=period_id,
    )




def generate_unique_payslip_number(payroll_period) -> str:
    """
    Generate unique payslip number: PS{YYYYMM}{SEQ:04d}
    Queries DB to find next available sequence.
    """
    base = f"PS{payroll_period.start_date.strftime('%Y%m')}"
    
    # Find highest existing sequence for this base
    last = db.session.query(Payslip).filter(
        Payslip.payslip_number.like(f"{base}%")
    ).order_by(Payslip.payslip_number.desc()).first()
    
    if last:
        try:
            last_seq = int(last.payslip_number[-4:])
            next_seq = last_seq + 1
        except (ValueError, TypeError, IndexError):
            next_seq = 1
    else:
        next_seq = 1
    
    return f"{base}{next_seq:04d}"

def calculate_payslip_totals(payroll) -> dict:
    """
    Calculate gross_pay, deductions, and net_pay from payroll data.
    Adjust logic to match your business rules.
    """
    gross_pay = payroll.gross_pay or 0.0
    
    # Example deduction calculations - customize as needed
    sss_contribution = gross_pay * 0.045  # 4.5%
    philhealth = gross_pay * 0.0275       # 2.75%
    pagibig = min(gross_pay * 0.02, 100)  # 2% capped at 100
    tax_withholding = max(0, (gross_pay - 20833) * 0.15) if gross_pay > 20833 else 0
    
    total_deductions = round(sss_contribution + philhealth + pagibig + tax_withholding, 2)
    net_pay = round(gross_pay - total_deductions, 2)
    
    return {
        'gross_pay': round(gross_pay, 2),
        'total_deductions': total_deductions,
        'net_pay': net_pay,
        'breakdown': {
            'sss': round(sss_contribution, 2),
            'philhealth': round(philhealth, 2),
            'pagibig': round(pagibig, 2),
            'tax': round(tax_withholding, 2)
        }
    }