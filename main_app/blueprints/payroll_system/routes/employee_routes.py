from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from main_app.models.users import PayrollUser
from main_app.models.payroll_models import Employee, Payroll, Payslip
from main_app.forms import PayslipSearchForm
from main_app.extensions import db
from datetime import datetime, date
import os
from random import randint
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "payroll_static")



payroll_employee_bp = Blueprint(
    "payroll_employee",
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR,
    static_url_path="/payroll/static"
)
@payroll_employee_bp.route('/dashboard')
@login_required
def dashboard():
    employee = Employee.query.filter_by(user_id=current_user.id).first()
    # Payroll stats
    payrolls = Payroll.query.filter_by(employee_id=employee.id).order_by(Payroll.created_at.asc()).all()

    total_disbursed = sum((p.net_pay or 0) for p in payrolls)
    total_deductions = sum((p.total_deductions or 0) for p in payrolls)
    total_allowances = sum(
        (link.allowance.amount or 0)
        for link in employee.employee_allowances
        if link.allowance and link.allowance.active
    )

    # Chart Data (per payroll period)
    payroll_labels = [p.pay_period_start.strftime("%b %d") for p in payrolls]
    gross_earnings = [p.gross_pay or 0 for p in payrolls]
    deductions = [p.total_deductions or 0 for p in payrolls]
    net_earnings = [p.net_pay or 0 for p in payrolls]

    # Recent payslips
    recent_payslips = Payslip.query.filter_by(employee_id=employee.id) \
                                   .order_by(Payslip.generated_at.desc()) \
                                   .limit(5).all()

    current_payroll = Payroll.query.filter_by(employee_id=employee.id) \
                                   .order_by(Payroll.created_at.desc()).first()

    return render_template(
        'payroll/employee/employee_dashboard.html',
        employee=employee,
        total_disbursed=total_disbursed,
        total_deductions=total_deductions,
        total_allowances=total_allowances,
        recent_payslips=recent_payslips,
        current_payroll=current_payroll,
        payroll_labels=payroll_labels,
        gross_earnings=gross_earnings,
        deductions=deductions,
        net_earnings=net_earnings
    )

@payroll_employee_bp.route('/profile')
@login_required
def profile():
    employee = Employee.query.filter_by(email=current_user.email).first()
    
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('payroll_auth.logout'))
    
    return render_template('payroll/employee_profile.html', employee=employee)





@payroll_employee_bp.route('/payslips')
@login_required
def payslips():
    # Fetch the employee record of the current user
    employee = Employee.query.filter_by(user_id=current_user.id).first()

    if not employee:
        flash("Employee record not found.", "warning")
        return redirect(url_for('main.index'))

    # Filtering
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # Base query
    query = Payslip.query.filter_by(employee_id=employee.id)

    # Apply status filter if not 'all'
    if status_filter != 'all':
        query = query.filter(Payslip.status == status_filter)

    # Pagination
    payslips_pagination = query.order_by(Payslip.generated_at.desc()) \
                               .paginate(page=page, per_page=per_page, error_out=False)

    payslips = payslips_pagination.items

    return render_template(
        'payroll/employee/employee_payslips.html',
        employee=employee,
        payslips=payslips,
        pagination=payslips_pagination,
        status_filter=status_filter
    )


@payroll_employee_bp.route('/payslips/<int:payslip_id>')
@login_required
def view_payslip(payslip_id):
    employee = Employee.query.filter_by(email=current_user.email).first()
    
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('payroll_auth.logout'))
    
    payslip = Payslip.query.filter_by(id=payslip_id, employee_id=employee.id).first_or_404()
    
    return render_template('payroll/view_payslip.html', payslip=payslip, employee=employee)

@payroll_employee_bp.route('/payslips/<int:payslip_id>/download')
@login_required
def download_payslip(payslip_id):
    employee = Employee.query.filter_by(email=current_user.email).first()
    
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('payroll_auth.logout'))
    
    payslip = Payslip.query.filter_by(id=payslip_id, employee_id=employee.id).first_or_404()
    
    # Update status to downloaded
    payslip.status = 'Downloaded'
    db.session.commit()
    
    # This would generate and return the PDF
    flash('Payslip downloaded successfully!', 'success')
    return redirect(url_for('payroll_employee.payslips'))


@payroll_employee_bp.route('/payroll-history')
@login_required
def payroll_history():
    employee = Employee.query.filter_by(email=current_user.email).first()
    
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('payroll_auth.logout'))

    page = request.args.get('page', 1, type=int)

    # Fetch all payroll records for this employee (no year filter)
    payrolls = (
        Payroll.query
        .filter_by(employee_id=employee.id)
        .order_by(Payroll.pay_period_start.desc())
        .paginate(page=page, per_page=12, error_out=False)
    )

    return render_template(
        'payroll/employee/employee_history.html',
        payrolls=payrolls,
        employee=employee
    )


@payroll_employee_bp.route('/payroll-summary')
@login_required
def payroll_summary():
    employee = Employee.query.filter_by(email=current_user.email).first()
    
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('payroll_auth.logout'))
    
    year = request.args.get('year', date.today().year, type=int)
    
    # Get payroll summary for the year
    payrolls = Payroll.query.filter(
        Payroll.employee_id == employee.id,
        Payroll.pay_period_start >= date(year, 1, 1),
        Payroll.pay_period_start <= date(year, 12, 31)
    ).all()
    
    summary = {
        'total_gross_pay': sum(p.gross_pay for p in payrolls),
        'total_deductions': sum(p.total_deductions for p in payrolls),
        'total_net_pay': sum(p.net_pay for p in payrolls),
        'total_sss': sum(p.sss_contribution for p in payrolls),
        'total_philhealth': sum(p.philhealth_contribution for p in payrolls),
        'total_pagibig': sum(p.pagibig_contribution for p in payrolls),
        'total_tax': sum(p.tax_withheld for p in payrolls),
        'payroll_count': len(payrolls)
    }
    
    # Get available years
    years = db.session.query(Payroll.pay_period_start).filter_by(employee_id=employee.id).all()
    years = list(set([p[0].year for p in years if p[0]]))
    years.sort(reverse=True)
    
    return render_template('payroll//employee/employee_summary.html', 
                         summary=summary, 
                         employee=employee,
                         selected_year=year,
                         years=years)


