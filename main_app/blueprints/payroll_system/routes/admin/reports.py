from flask import Blueprint, request, render_template
from datetime import datetime
from flask_login import login_required

from main_app.models.payroll_models import Payroll, PayrollPeriod
from main_app.helpers.decorators import payroll_admin_required
from main_app.models.hr_models import Employee, Department

from main_app.helpers.docs import (
    payroll_summary_report,
    deduction_summary_report,
    employee_payroll_history
)


from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp


# ======================================================
# PAYROLL SUMMARY REPORT
# ======================================================

@payroll_admin_bp.route("/payroll-summary")
@login_required
@payroll_admin_required
def payroll_summary():

    period_id = request.args.get("period", type=int)
    department_id = request.args.get("department_id", type=int)

    # Get payrolls filtered by period and/or department
    query = Payroll.query.join(Payroll.employee)

    if period_id:
        query = query.filter(Payroll.payroll_period_id == period_id)

    if department_id:
        query = query.filter(Payroll.employee.department_id == department_id)

    payrolls = query.all()

    # Get period info for header
    period = PayrollPeriod.query.get(period_id) if period_id else None

    # Departments for filter dropdown
    departments = Department.query.all()

    # Compute payroll totals for insights
    total_employees = len(payrolls)
    total_gross = sum(p.gross_pay for p in payrolls)
    total_deductions = sum(p.total_deductions for p in payrolls)
    total_net = sum(p.net_pay for p in payrolls)

    # Optional department summary
    department_summary = []
    if department_id is None:
        for dept in departments:
            dept_payrolls = [p for p in payrolls if p.employee.department_id == dept.id]
            if dept_payrolls:
                department_summary.append({
                    "name": dept.name,
                    "total_gross": sum(p.gross_pay for p in dept_payrolls),
                    "total_net": sum(p.net_pay for p in dept_payrolls)
                })

    return render_template(
        "payroll/admin/reports/reports_base.html",
        payrolls=payrolls,
        period=period,
        periods=PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all(),
        departments=departments,
        department_id=department_id,
        period_id=period_id,
        total_employees=total_employees,
        total_gross=total_gross,
        total_deductions=total_deductions,
        total_net=total_net,
        department_summary=department_summary,
        current_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

# ======================================================
# DEDUCTION SUMMARY REPORT
# ======================================================

@payroll_admin_bp.route("/deduction-summary")
@login_required
@payroll_admin_required
def deduction_summary():

    period_id = request.args.get("period")

    query = Payroll.query

    if period_id:
        query = query.filter_by(payroll_period_id=period_id)

    payrolls = query.all()

    return deduction_summary_report(payrolls)


# ======================================================
# EMPLOYEE PAYROLL HISTORY
# ======================================================

@payroll_admin_bp.route("/employee/<int:employee_id>/payroll-history")
@login_required
def employee_history(employee_id):

    employee = Employee.query.get_or_404(employee_id)

    return employee_payroll_history(employee)