from sqlalchemy.orm import  joinedload 
from flask import render_template, request
from flask_login import login_required
from datetime import date
from calendar import monthrange
from sqlalchemy import func, case, or_
import calendar

from main_app.helpers.decorators import staff_required
from main_app.extensions import db
from main_app.models.payroll_models import PayrollPeriod, Payroll, Payslip, LoanPayment
from main_app.models.hr_models import Employee, Department, Attendance
from main_app.models.user import User
from main_app.blueprints.payroll_system.routes.staff import payroll_staff_bp


# Helper function: get current payroll period
def get_current_payroll_period():
    today = date.today()
    return PayrollPeriod.query.filter(
        PayrollPeriod.start_date <= today,
        PayrollPeriod.end_date >= today
    ).first()


@payroll_staff_bp.route('/staff-dashboard')
@login_required
@staff_required
def staff_dashboard():

    today = date.today()

    # =====================================================
    # EMPLOYEE SUMMARY
    # =====================================================

    total_employees = Employee.query.filter_by(status="Active").count()
    total_departments = Department.query.count()

    # =====================================================
    # PAYROLL PIPELINE STATUS
    # =====================================================

    pending_payrolls = Payroll.query.filter_by(status="Draft").count()
    processing_payrolls = Payroll.query.filter_by(status="Processing").count()
    completed_payrolls = Payroll.query.filter_by(status="Completed").count()

    generated_payslips = Payslip.query.filter_by(status="Generated").count()
    claimed_payslips = Payslip.query.filter_by(status="Claimed").count()

    payroll_queue_size = pending_payrolls + processing_payrolls

    # =====================================================
    # PERIOD MONITORING
    # =====================================================

    current_period = PayrollPeriod.query.filter_by(
        status="Open"
    ).order_by(
        PayrollPeriod.start_date.desc()
    ).first()

    has_open_period = current_period is not None

    # =====================================================
    # FINANCIAL SUMMARY (SAFE AGGREGATION)
    # =====================================================

    total_disbursed = db.session.scalar(
        db.select(func.coalesce(func.sum(Payslip.net_pay), 0))
    ) or 0

    total_deductions = db.session.scalar(
        db.select(func.coalesce(func.sum(Payslip.total_deductions), 0))
    ) or 0

    # ✅ Compute allowance total safely in Python layer
    total_allowances = 0

    payroll_ids = db.session.scalars(
        db.select(Payroll.id)
    ).all()

    if payroll_ids:
        payroll_records = Payroll.query.filter(
            Payroll.id.in_(payroll_ids)
        ).all()

        total_allowances = sum(
            p.allowance_total for p in payroll_records
        )

    # =====================================================
    # MONTHLY PROCESSING PERFORMANCE
    # =====================================================

    month_start = today.replace(day=1)

    monthly_completed_payrolls = Payroll.query.filter(
        Payroll.created_at >= month_start,
        Payroll.status == "Completed"
    ).count()

    monthly_generated_payslips = Payslip.query.filter(
        Payslip.generated_at >= month_start
    ).count()

    # =====================================================
    # RECENT WORKFLOW ACTIVITY
    # =====================================================

    recent_payrolls = Payroll.query.order_by(
        Payroll.updated_at.desc() if hasattr(Payroll, 'updated_at')
        else Payroll.created_at.desc()
    ).limit(10).all()

    recent_payslips = Payslip.query.order_by(
        Payslip.generated_at.desc()
    ).limit(10).all()

    # =====================================================
    # PENDING TASK LIST
    # =====================================================

    unclaimed_payslips = Payslip.query.filter(
        Payslip.status == "Generated"
    ).order_by(
        Payslip.generated_at.asc()
    ).limit(10).all()

    unclaimed_count = Payslip.query.filter(
        Payslip.status == "Generated"
    ).count()

    # =====================================================
    # ATTENDANCE ANALYTICS
    # =====================================================

    month_end = today.replace(
        day=monthrange(today.year, today.month)[1]
    )

    attendance_query = db.session.query(
        Attendance.date.label("date"),

        func.sum(
            case((Attendance.status == "Present", 1), else_=0)
        ).label("present_count"),

        func.sum(
            case((Attendance.status == "Absent", 1), else_=0)
        ).label("absent_count"),

        func.sum(
            case((Attendance.status == "Late", 1), else_=0)
        ).label("late_count")

    ).filter(
        Attendance.date.between(month_start, month_end)
    ).group_by(
        Attendance.date
    ).order_by(
        Attendance.date
    )

    attendances = attendance_query.all()

    monthly_dates = [a.date.strftime("%Y-%m-%d") for a in attendances]
    monthly_present_counts = [a.present_count or 0 for a in attendances]
    monthly_absent_counts = [a.absent_count or 0 for a in attendances]
    monthly_late_counts = [a.late_count or 0 for a in attendances]

    # =====================================================
    # RENDER TEMPLATE
    # =====================================================

    return render_template(
        'payroll/staff/views/staff_dashboard.html',

        total_employees=total_employees,
        total_departments=total_departments,

        pending_payrolls=pending_payrolls,
        processing_payrolls=processing_payrolls,
        completed_payrolls=completed_payrolls,

        generated_payslips=generated_payslips,
        claimed_payslips=claimed_payslips,

        payroll_queue_size=payroll_queue_size,

        total_disbursed=total_disbursed,
        total_deductions=total_deductions,
        total_allowances=round(total_allowances, 2),

        has_open_period=has_open_period,
        current_period=current_period,

        monthly_completed_payrolls=monthly_completed_payrolls,
        monthly_generated_payslips=monthly_generated_payslips,

        recent_payrolls=recent_payrolls,
        recent_payslips=recent_payslips,

        unclaimed_payslips=unclaimed_payslips,
        unclaimed_count=unclaimed_count,

        monthly_dates=monthly_dates,
        monthly_present_counts=monthly_present_counts,
        monthly_absent_counts=monthly_absent_counts,
        monthly_late_counts=monthly_late_counts
    )



@payroll_staff_bp.route('/payrolls')
@staff_required
@login_required
def view_payrolls():

    search = request.args.get('search', '', type=str).strip()
    department_id = request.args.get('department_id', type=int)
    pay_period_id = request.args.get('pay_period_id', type=int)
    page = request.args.get('page', 1, type=int)

    query = Payroll.query.options(

        joinedload(Payroll.employee)
        .joinedload(Employee.department),

        joinedload(Payroll.employee)
        .joinedload(Employee.employment_type),

        joinedload(Payroll.employee)
        .joinedload(Employee.attendances),

        joinedload(Payroll.period),

        joinedload(Payroll.deduction_breakdown),

        # ✅ ADD LOANS
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
        # 💥 LOAN DEDUCTIONS (NEW)
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

    departments = Department.query.all()

    payroll_periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    selected_pay_period = (
        PayrollPeriod.query.get(pay_period_id)
        if pay_period_id else None
    )

    return render_template(
        "payroll/staff/views/payroll_details.html",
        payrolls=payrolls,
        search=search,
        departments=departments,
        selected_department=department_id,
        payroll_periods=payroll_periods,
        selected_pay_period=selected_pay_period
    )


@payroll_staff_bp.route("/payroll-departments")
@login_required
@staff_required
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
        "payroll/staff/views/department_payrolls.html",
        payroll_periods=payroll_periods,
        selected_period=period,
        department_rows=department_rows,
        municipality_total=round(municipality_total, 2),
        departments=departments
    )


  
@payroll_staff_bp.route("/regular-select-periods")
@login_required
@staff_required
def regular_select_period():
    # Get all payroll periods, most recent first
    all_periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    # Filter: only whole-month periods
    whole_month_periods = []
    for p in all_periods:
        start = p.start_date
        end = p.end_date

        # Check if start is the 1st of the month
        if start.day != 1:
            continue

        # Check if end is the last day of the month
        last_day = calendar.monthrange(end.year, end.month)[1]
        if end.day != last_day:
            continue

        whole_month_periods.append(p)

    return render_template(
        "payroll/staff/views/regular_select_period.html",
        periods=whole_month_periods
    )



@payroll_staff_bp.route("/casual-select-periods")
@login_required
@staff_required
def casual_select_period():
    periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    filtered_periods = []
    for p in periods:
        start_day = p.start_date.day
        end_day = p.end_date.day
        last_day = monthrange(p.start_date.year, p.start_date.month)[1]

        # Keep only bi-monthly periods
        if (start_day == 1 and end_day == 15) or (start_day == 16 and end_day in (30,31,last_day)):
            filtered_periods.append(p)

    return render_template(
        "payroll/staff/views/casual_select_period.html",
        filtered_periods=filtered_periods
    )


@payroll_staff_bp.route("/jo-select-periods")
@login_required
@staff_required
def jo_select_period():

    periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    filtered_periods = []

    for p in periods:
        start_day = p.start_date.day
        end_day = p.end_date.day
        last_day = monthrange(p.start_date.year, p.start_date.month)[1]

        # JO BI-MONTHLY FILTER (same structure as casual, but separated for clarity)
        if (start_day == 1 and end_day == 15) or (start_day == 16 and end_day in (30, 31, last_day)):
            filtered_periods.append(p)

    return render_template(
        "payroll/staff/views/jo_select_period.html",
        periods=filtered_periods
    )


@payroll_staff_bp.route("/parttimer-select-periods")
@login_required
@staff_required
def parttimer_select_period():
    periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()

    return render_template(
        "payroll/staff/views/parttimer_select_period.html",
        periods=periods
    )