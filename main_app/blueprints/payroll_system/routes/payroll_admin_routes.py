from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from  main_app.models.users import PayrollUser
from g4f.client import Client
from main_app.models.payroll_models import (
     Payroll, Payslip, PayrollPeriod, Deduction, Allowance, Tax, EmployeeDeduction, EmployeeAllowance
)
from main_app.deductions import (
    compute_philhealth_deduction,
    compute_pagibig_deduction,
    compute_sss_deduction,
    compute_gsis_deduction,
    compute_withholding_tax,
    compute_menpc_deduction,
    compute_pagibig_loan,
    compute_jo_withholding_tax,
    compute_regular_withholding_tax

)
from main_app.functions import generate_payslip

from main_app.forms import (
    PayrollPeriodForm, PayrollForm, PayslipForm,
    DeductionForm, AllowanceForm, TaxForm, PayrollSummaryForm
)
from main_app.utils import (
    admin_required, calculate_payroll_summary, get_current_payroll_period,
    get_payroll_summary,generate_ai_report, generate_department_chart,
    create_payroll_period, generate_payroll_insights, sync_all_employees_from_hr
)
from main_app.extensions import db
from main_app.models.user import User
from main_app.models.hr_models import Department, Employee, Attendance, EmploymentType, Leave, LateComputation
from datetime import datetime, date, timedelta, time
import os
from reportlab.lib.pagesizes import A4
from sqlalchemy import func, case, extract, asc
from sqlalchemy.orm import joinedload
from io import BytesIO
import io
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from main_app.utils import payroll_admin_required
from reportlab.lib.styles import getSampleStyleSheet
from math import ceil


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

payroll_admin_bp = Blueprint(
    "payroll_admin",
    __name__,
    template_folder=TEMPLATE_DIR,
    static_url_path="/payroll/static"
)





@payroll_admin_bp.route('/departments')
@payroll_admin_required
def payroll_departments():
    # Get all departments
    departments = Department.query.all()

    # Count active employees in each department
    dept_list = []
    for dept in departments:
        employee_count = Employee.query.filter_by(status="Active", department_id=dept.id).count()
        dept_list.append({
            "id": dept.id,
            "name": dept.name,
            "employee_count": employee_count
        })

    return render_template(
        'payroll/admin/payroll_departments.html',
        departments=dept_list
    )






@payroll_admin_bp.route('/get_the_working_days_for_a_month', methods=['GET'])
@payroll_admin_required
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


@payroll_admin_bp.route('/payrolls/edit/<int:payroll_id>', methods=['GET', 'POST'])
@payroll_admin_required
def edit_payroll(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)

    if request.method == 'POST':
        payroll.basic_salary = request.form.get('basic_salary', type=float)
        payroll.gross_pay = request.form.get('gross_pay', type=float)
        payroll.total_deductions = request.form.get('total_deductions', type=float)
        payroll.net_pay = request.form.get('net_pay', type=float)
        payroll.status = request.form.get('status')
        db.session.commit()
        flash('Payroll updated successfully.', 'success')
        return redirect(url_for('payroll_admin.view_payrolls'))

    return render_template('payroll/admin/edit_payroll_details.html', payroll=payroll)






# ==========================
# SYNC EMPLOYEES
# ==========================
@payroll_admin_bp.route('/employees/sync', methods=['POST'])
@payroll_admin_required
@payroll_admin_required
def sync_employees():
    try:
        hr_employees = sync_all_employees_from_hr()
        if not hr_employees:
            flash('No employees found in HR system or sync failed.', 'error')
            return redirect(url_for('payroll_admin.employees'))

        synced_count = 0
        for emp_data in hr_employees:
            existing_employee = Employee.query.filter_by(employee_id=emp_data['employee_id']).first()

            if not existing_employee:
                employee = Employee(
                    employee_id=emp_data['employee_id'],
                    first_name=emp_data['first_name'],
                    last_name=emp_data['last_name'],
                    middle_name=emp_data.get('middle_name'),
                    email=emp_data['email'],
                    phone=emp_data.get('phone'),
                    department=emp_data['department'],
                    position=emp_data['position'],
                    basic_salary=emp_data.get('salary', 0),
                    date_hired=datetime.strptime(emp_data['date_hired'], '%Y-%m-%d').date()
                    if emp_data.get('date_hired') else date.today(),
                    active=emp_data.get('active', True)
                )
                db.session.add(employee)
                synced_count += 1
            else:
                # Update existing employee
                existing_employee.first_name = emp_data['first_name']
                existing_employee.last_name = emp_data['last_name']
                existing_employee.middle_name = emp_data.get('middle_name')
                existing_employee.email = emp_data['email']
                existing_employee.phone = emp_data.get('phone')
                existing_employee.department = emp_data['department']
                existing_employee.position = emp_data['position']
                existing_employee.basic_salary = emp_data.get('salary', 0)
                existing_employee.updated_at = datetime.utcnow()

        db.session.commit()
        flash(f'Successfully synced {synced_count} employees from HR system.', 'success')

    except Exception:
        db.session.rollback()
        flash('Error syncing employees. Please try again.', 'error')

    return redirect(url_for('payroll_admin.employees'))


# ==========================
# PAYROLL PERIODS
# ==========================

from flask import request







# ==========================
# PAYROLL
# ==========================

@payroll_admin_bp.route('/payroll/details/<int:period_id>')
@payroll_admin_required
@payroll_admin_required
def payroll_details(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    
    payrolls = (
        Payroll.query
        .join(Employee)
        .filter(Payroll.pay_period_id == period_id)
        .order_by(Employee.last_name.asc())
        .all()
    )

    # Ensure calculations are correct
    for p in payrolls:
        p.calculate_earnings()  # updates gross_pay, total_deductions, net_pay

    total_gross = sum(p.gross_pay for p in payrolls)
    total_deductions = sum(p.total_deductions for p in payrolls)
    total_net = sum(p.net_pay for p in payrolls)

    return render_template(
        'payroll/admin/payroll_details.html',
        period=period,
        payrolls=payrolls,
        total_gross=total_gross,
        total_deductions=total_deductions,
        total_net=total_net
    )


# -----------------------------
# Helper: Apply allowances/deductions
# -----------------------------
def apply_allowances_and_deductions(employee, gross_pay):
    total_allowances = 0
    total_deductions = 0

    for ea in getattr(employee, 'employee_allowances', []):
        allowance = ea.allowance
        if not allowance.active:
            continue
        if allowance.type.lower() == 'fixed':
            total_allowances += allowance.amount
        else:
            total_allowances += gross_pay * allowance.percentage / 100

    for ed in getattr(employee, 'employee_deductions', []):
        deduction = ed.deduction
        if not deduction.active:
            continue
        if deduction.type.lower() == 'fixed':
            total_deductions += deduction.amount
        else:
            total_deductions += gross_pay * deduction.percentage / 100

    return total_allowances, total_deductions





# Helper functions
# -----------------------------
def get_working_hours(attendance):
    """Return working hours as float from time_in and time_out."""
    total_hours = 0
    for a in attendance:
        if a.time_in and a.time_out and a.status == "Present":
            delta = datetime.combine(datetime.min, a.time_out) - datetime.combine(datetime.min, a.time_in)
            hours = delta.total_seconds() / 3600
            total_hours += hours
    return total_hours

def get_employee_allowances(employee):
    """Sum of all employee allowances (amount or % of salary)."""
    total = 0
    for ea in employee.employee_allowances:
        allowance = ea.allowance
        if allowance.amount:
            total += allowance.amount
        elif allowance.percentage:
            total += (allowance.percentage / 100) * (employee.salary or 0)
    return total

def get_employee_deductions(employee):
    """Sum of all employee deductions (amount or % of salary)."""
    total = 0
    for ed in employee.employee_deductions:
        deduction = ed.deduction
        if deduction.amount:
            total += deduction.amount
        elif deduction.percentage:
            total += (deduction.percentage / 100) * (employee.salary or 0)
    return total






# =========================================================
# MARK AS DISTRIBUTED / CLAIMED
# =========================================================
@payroll_admin_bp.route('/payslips/distribute/<int:payslip_id>', methods=['POST'])
@payroll_admin_required
@payroll_admin_required
def distribute_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)

    if payslip.status == "Distributed":
        flash("Payslip already marked as distributed (claimed).", "info")
        return redirect(url_for('payroll_admin.view_payslips'))

    payslip.status = "Distributed"
    payslip.claimed = True  # ✅ Mark as claimed when distributed
    payslip.distributed_at = datetime.utcnow()
    db.session.commit()

    flash(f"Payslip {payslip.payslip_number} marked as distributed and claimed.", "success")
    return redirect(url_for('payroll_admin.view_payslips'))

# =========================================================
# GENERATE PAYSLIPS BY PAYROLL PERIOD (SELECT PERIOD)
# =========================================================
@payroll_admin_bp.route('/payslips/generate', methods=['GET', 'POST'])
@payroll_admin_required
@payroll_admin_required
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



# =========================================================
# GENERATE SINGLE PAYSLIP
# =========================================================
@payroll_admin_bp.route('/payslips/generate/<int:payroll_id>', methods=['POST'])
@payroll_admin_required
@payroll_admin_required
def generate_single_payslip(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)

    existing = Payslip.query.filter_by(payroll_id=payroll.id).first()
    if existing:
        flash("Payslip already exists for this employee.", "info")
        return redirect(url_for('payroll_admin.view_payslips'))

    payslip = generate_payslip(payroll, current_user.id)
    db.session.add(payslip)
    db.session.commit()

    flash(f"Payslip generated for employee ID {payroll.employee_id}.", "success")
    return redirect(url_for('payroll_admin.view_payslips'))



# =========================================================
# REVIEW & APPROVE PAYSLIPS (TABLE VIEW)
# =========================================================
@payroll_admin_bp.route('/payslips/review', methods=['GET', 'POST'])
@payroll_admin_required
@payroll_admin_required
def review_payslips():
    if request.method == 'POST':
        action = request.form.get('action')

        # Bulk approve all
        if action == 'approve_all':
            payslips = Payslip.query.filter(Payslip.status == "Generated").all()
            for p in payslips:
                p.status = "Approved"
                p.approved_by = current_user.id
                p.approved_at = datetime.utcnow()
            db.session.commit()
            flash(f"All generated payslips approved successfully.", "success")
            return redirect(url_for('payroll_admin.review_payslips'))

        # Individual approve/reject
        payslip_id = request.form.get('payslip_id')
        decision = request.form.get('decision')
        reason = request.form.get('reason', '').strip()
        payslip = Payslip.query.get_or_404(payslip_id)

        if payslip.status in ["Approved", "Rejected", "Distributed"]:
            flash(f"Payslip {payslip.payslip_number} already {payslip.status.lower()}.", "info")
            return redirect(url_for('payroll_admin.review_payslips'))

        if decision == 'approve':
            payslip.status = "Approved"
            payslip.approved_by = current_user.id
            payslip.approved_at = datetime.utcnow()
            payslip.rejection_reason = None
            flash(f"Payslip {payslip.payslip_number} approved.", "success")
        elif decision == 'reject':
            payslip.status = "Rejected"
            payslip.approved_by = current_user.id
            payslip.approved_at = datetime.utcnow()
            payslip.rejection_reason = reason or "No reason provided."
            flash(f"Payslip {payslip.payslip_number} rejected.", "danger")

        db.session.commit()
        return redirect(url_for('payroll_admin.review_payslips'))

    # GET: Load table
    payslips = Payslip.query.order_by(Payslip.generated_at.desc()).all()
    return render_template('payroll/admin/review_payslips.html', payslips=payslips)

# =========================================================
# APPROVE PAYSLIP
# =========================================================
@payroll_admin_bp.route('/payslips/approve/<int:payslip_id>', methods=['POST'])
@payroll_admin_required
@payroll_admin_required
def approve_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)

    if payslip.status in ["Approved", "Rejected", "Distributed"]:
        flash(f"Payslip {payslip.payslip_number} has already been {payslip.status.lower()}.", "info")
        return redirect(url_for('payroll_admin.view_payslips'))

    payslip.status = "Approved"
    payslip.approved_by = current_user.id
    payslip.approved_at = datetime.utcnow()
    db.session.commit()

    flash(f"Payslip {payslip.payslip_number} approved successfully.", "success")
    return redirect(url_for('payroll_admin.view_payslips'))


# =========================================================
# REJECT PAYSLIP
# =========================================================
@payroll_admin_bp.route('/payslips/reject/<int:payslip_id>', methods=['POST'])
@payroll_admin_required
@payroll_admin_required
def reject_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    reason = request.form.get('reason', '').strip()

    if payslip.status in ["Approved", "Rejected", "Distributed"]:
        flash(f"Payslip {payslip.payslip_number} has already been {payslip.status.lower()}.", "info")
        return redirect(url_for('payroll_admin.view_payslips'))

    payslip.status = "Rejected"
    payslip.rejection_reason = reason or "No reason provided"
    db.session.commit()

    flash(f"Payslip {payslip.payslip_number} rejected. Reason: {payslip.rejection_reason}", "warning")
    return redirect(url_for('payroll_admin.view_payslips'))





# ==========================
# CREATE DEDUCTION
# ==========================
@payroll_admin_bp.route('/deductions/create', methods=['GET', 'POST'])
@payroll_admin_required
def create_deduction():
    if request.method == 'POST':
        name = request.form.get('name').strip()
        if not name:
            flash('Deduction name is required.', 'danger')
            return redirect(url_for('payroll_admin.create_deduction'))

        deduction = Deduction(name=name)
        db.session.add(deduction)
        db.session.commit()
        flash('Deduction created successfully!', 'success')
        return redirect(url_for('payroll_admin.deductions'))

    return render_template('payroll/admin/deduction_form.html', action="Create", deduction=None)


# ==========================
# EDIT DEDUCTION
# ==========================
@payroll_admin_bp.route('/deductions/edit/<int:deduction_id>', methods=['GET', 'POST'])
@payroll_admin_required
def edit_deduction(deduction_id):
    deduction = Deduction.query.get_or_404(deduction_id)

    if request.method == 'POST':
        name = request.form.get('name').strip()
        if not name:
            flash('Deduction name is required.', 'danger')
            return redirect(url_for('payroll_admin.edit_deduction', deduction_id=deduction_id))

        deduction.name = name
        db.session.commit()
        flash('Deduction updated successfully!', 'success')
        return redirect(url_for('payroll_admin.deductions'))

    return render_template('payroll/admin/deduction_form.html', action="Edit", deduction=deduction)


# ==========================
# DELETE DEDUCTION
# ==========================
@payroll_admin_bp.route('/deductions/delete/<int:deduction_id>', methods=['POST'])
@payroll_admin_required
def delete_deduction(deduction_id):
    deduction = Deduction.query.get_or_404(deduction_id)
    db.session.delete(deduction)
    db.session.commit()
    flash('Deduction deleted successfully!', 'success')
    return redirect(url_for('payroll_admin.deductions'))


@payroll_admin_bp.route("/deductions/manage/<int:deduction_id>", methods=["GET", "POST"])
@payroll_admin_required
def manage_deduction_employees(deduction_id):
    deduction = Deduction.query.get_or_404(deduction_id)

    # === SEARCH ===
    search_query = request.args.get("search", "").strip()

    # Base query for active employees
    employees_query = Employee.query.filter_by(status="Active")

    # Apply search filter if provided
    if search_query:
        employees_query = employees_query.filter(
            db.or_(
                Employee.first_name.ilike(f"%{search_query}%"),
                Employee.last_name.ilike(f"%{search_query}%"),
                Employee.employee_id.ilike(f"%{search_query}%")
            )
        )

    # === PAGINATION ===
    page = request.args.get("page", 1, type=int)
    per_page = 10  # Change this to adjust items per page
    pagination = employees_query.order_by(Employee.last_name, Employee.first_name).paginate(page=page, per_page=per_page, error_out=False)
    employees = pagination.items

    if request.method == "POST":
        selected_ids = request.form.getlist("employees")  # list of employee IDs as strings

        # Remove existing links not in selected_ids
        for ed in deduction.employees:
            if str(ed.employee_id) not in selected_ids:
                db.session.delete(ed)

        # Add new links
        for emp_id in selected_ids:
            emp_id = int(emp_id)
            exists = EmployeeDeduction.query.filter_by(employee_id=emp_id, deduction_id=deduction.id).first()
            if not exists:
                new_link = EmployeeDeduction(employee_id=emp_id, deduction_id=deduction.id)
                db.session.add(new_link)

        db.session.commit()
        flash("Employees updated for deduction.", "success")
        return redirect(url_for("payroll_admin.manage_deduction_employees", deduction_id=deduction.id))

    # Pre-select employees already linked
    linked_employee_ids = [ed.employee_id for ed in deduction.employees]

    return render_template(
        "payroll/admin/manage_deduction_employees.html",
        deduction=deduction,
        employees=employees,
        linked_employee_ids=linked_employee_ids,
        pagination=pagination,
        search=search_query
    )

# ==========================
# ALLOWANCES
# ==========================
@payroll_admin_bp.route('/allowances')
@payroll_admin_required
@payroll_admin_required
def allowances():
    search = request.args.get('search', '', type=str).strip()
    page = request.args.get('page', 1, type=int)

    query = Allowance.query

    if search:
        query = query.filter(Allowance.name.ilike(f"%{search}%"))

    pagination = query.paginate(page=page, per_page=10)
    allowances = pagination.items

    return render_template(
        'payroll/admin/allowances.html',
        allowances=allowances,
        pagination=pagination,
        search=search,
    )



@payroll_admin_bp.route('/allowances/add', methods=['GET', 'POST'])
@payroll_admin_required
@payroll_admin_required
def add_allowance():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        type_ = request.form.get('type')
        amount = request.form.get('amount') or 0
        percentage = request.form.get('percentage') or 0
        active = True if request.form.get('active') == '1' else False

        new_allowance = Allowance(
            name=name,
            description=description,
            type=type_,
            amount=float(amount),
            percentage=float(percentage),
            active=active
        )

        try:
            db.session.add(new_allowance)
            db.session.commit()
            return jsonify({
                'success': True,
                'redirect': url_for('payroll_admin.allowance')  # <-- redirect URL
            })
        except Exception:
            db.session.rollback()
            return jsonify({'success': False})


    return render_template('payroll/admin/allowance_add.html')

# ==========================
# TAX BRACKETS
# ==========================
@payroll_admin_bp.route('/tax-brackets')
@payroll_admin_required
@payroll_admin_required
def tax_brackets():
    tax_brackets = Tax.query.order_by(Tax.min_income).all()
    return render_template('payroll/tax_brackets.html', tax_brackets=tax_brackets)


@payroll_admin_bp.route('/tax-brackets/add', methods=['GET', 'POST'])
@payroll_admin_required
@payroll_admin_required
def add_tax_bracket():
    form = TaxForm()
    if form.validate_on_submit():
        tax_bracket = Tax(
            min_income=form.min_income.data,
            max_income=form.max_income.data,
            tax_rate=form.tax_rate.data,
            fixed_amount=form.fixed_amount.data,
            active=form.active.data
        )
        try:
            db.session.add(tax_bracket)
            db.session.commit()
            flash('Tax bracket added successfully!', 'success')
            return redirect(url_for('payroll_admin.tax_brackets'))
        except Exception:
            db.session.rollback()
            flash('Error adding tax bracket. Please try again.', 'error')

    return render_template('payroll/add_tax_bracket.html', form=form)


# ==========================
# REPORTS
# ==========================
@payroll_admin_bp.route('/reports', methods=['GET', 'POST'])
@payroll_admin_required
def reports():
    form = PayrollSummaryForm()
    form.period_id.choices = [(p.id, f"{p.period_name} ({p.start_date} to {p.end_date})") for p in PayrollPeriod.query.all()]

    summary = None
    if form.validate_on_submit():
        summary = calculate_payroll_summary(form.period_id.data, form.department.data)

    return render_template('payroll/reports.html', form=form, summary=summary)


@payroll_admin_bp.route('/payroll/admin/summary', methods=['GET'])
@payroll_admin_required

def payroll_summary():
    department_id = request.args.get('department_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    page = request.args.get('page', 1, type=int)
    per_page = 10  # adjust as you prefer

    query = db.session.query(
        Department.name.label('department_name'),
        func.sum(Payroll.gross_pay).label('total_gross'),
        func.sum(Payroll.total_deductions).label('total_deductions'),
        func.sum(Payroll.net_pay).label('total_net')
    ).join(Employee, Payroll.employee_id == Employee.id
    ).join(Department, Employee.department_id == Department.id
    ).group_by(Department.name)

    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if start_date and end_date:
        query = query.filter(Payroll.pay_period_start >= start_date,
                             Payroll.pay_period_end <= end_date)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    departments = Department.query.all()

    return render_template(
        'payroll/admin/summary_reports.html',
        results=pagination.items,
        departments=departments,
        pagination=pagination,
        selected_department=department_id,
        start_date=start_date,
        end_date=end_date
    )



@payroll_admin_bp.route('/payroll/admin/export_excel')
@payroll_admin_required
def export_excel():
    department_id = request.args.get('department_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = db.session.query(
        Department.name.label('Department'),
        func.sum(Payroll.gross_pay).label('Total Gross'),
        func.sum(Payroll.total_deductions).label('Total Deductions'),
        func.sum(Payroll.net_pay).label('Total Net')
    ).join(Employee, Payroll.employee_id == Employee.id
    ).join(Department, Employee.department_id == Department.id
    ).group_by(Department.name)

    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if start_date and end_date:
        query = query.filter(
            Payroll.pay_period_start >= start_date,
            Payroll.pay_period_end <= end_date
        )

    # ✅ FIX HERE — use db.engine.connect()
    with db.engine.connect() as connection:
        df = pd.read_sql(query.statement, connection)

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        download_name="payroll_summary.xlsx",
        as_attachment=True
    )

@payroll_admin_bp.route('/payroll/admin/export_pdf')
@payroll_admin_required
def export_pdf():
    department_id = request.args.get('department_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # 🧮 Query payroll summary
    query = db.session.query(
        Department.name.label('department_name'),
        func.sum(Payroll.gross_pay).label('total_gross'),
        func.sum(Payroll.total_deductions).label('total_deductions'),
        func.sum(Payroll.net_pay).label('total_net')
    ).join(Employee, Payroll.employee_id == Employee.id
    ).join(Department, Employee.department_id == Department.id
    ).group_by(Department.name)

    # 🔍 Apply filters if provided
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if start_date and end_date:
        query = query.filter(
            Payroll.pay_period_start >= start_date,
            Payroll.pay_period_end <= end_date
        )

    results = query.all()

    # 🧾 Create PDF document
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # 🏷️ Title
    title_text = "Payroll Summary Report"
    elements.append(Paragraph(title_text, styles['Title']))
    elements.append(Spacer(1, 12))

    # 📅 Filters Info (Optional)
    filter_info = []
    if department_id:
        dept = Department.query.get(department_id)
        if dept:
            filter_info.append(f"Department: {dept.name}")
    if start_date and end_date:
        filter_info.append(f"Period: {start_date} to {end_date}")

    if filter_info:
        elements.append(Paragraph(", ".join(filter_info), styles['Normal']))
        elements.append(Spacer(1, 12))

    # 🧮 Table Data
    data = [["Department", "Total Gross", "Total Deductions", "Total Net"]]

    if results:
        for r in results:
            total_gross = r.total_gross or 0.00
            total_deductions = r.total_deductions or 0.00
            total_net = r.total_net or 0.00

            data.append([
                r.department_name,
                f"₱ {total_gross:,.2f}",
                f"₱ {total_deductions:,.2f}",
                f"₱ {total_net:,.2f}"
            ])
    else:
        data.append(["No records found", "", "", ""])

    # 🎨 Table Styling
    table = Table(data, hAlign='CENTER')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f2f2f2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
    ]))

    elements.append(table)

    # 📄 Build and return PDF
    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, download_name="payroll_summary.pdf", as_attachment=True)

@payroll_admin_bp.route('/payroll/admin/generate_payroll', methods=['POST'])
@payroll_admin_required
def generate_payrolls():
    from datetime import date, datetime, timedelta

    year = int(request.form.get('year'))
    month = int(request.form.get('month'))

    # ✅ Step 1: Get start and end date for the selected month
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)

    # ✅ Step 2: Automatically get or create PayrollPeriod
    payroll_period = PayrollPeriod.query.filter_by(
        start_date=start_date,
        end_date=end_date
    ).first()

    if not payroll_period:
        payroll_period = PayrollPeriod(
            start_date=start_date,
            end_date=end_date,
            description=f"{start_date.strftime('%B %Y')} Payroll"
        )
        db.session.add(payroll_period)
        db.session.commit()

    # ✅ Step 3: Generate payrolls for each employee
    employees = Employee.query.all()
    generated_count = 0

    for emp in employees:
        logs = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).all()

        total_hours = 0
        for log in logs:
            if log.time_in and log.time_out:
                delta = log.time_out - log.time_in
                total_hours += delta.total_seconds() / 3600

        if total_hours <= 0:
            continue

        existing_payroll = Payroll.query.filter_by(
            employee_id=emp.id,
            pay_period_id=payroll_period.id
        ).first()

        if existing_payroll:
            continue  # skip if already generated

        payroll = Payroll(
            employee_id=emp.id,
            pay_period_id=payroll_period.id,
            pay_period_start=start_date,
            pay_period_end=end_date,
            basic_salary=emp.basic_salary or 0,
            working_hours=total_hours
        )
        payroll.calculate_earnings()
        db.session.add(payroll)
        generated_count += 1

    db.session.commit()
    flash(f"Payroll generated for {generated_count} employees for {start_date.strftime('%B %Y')}.", "success")
    return redirect(url_for('payroll_admin.earnings_report'))


@payroll_admin_bp.route('/payroll/admin/earnings_report')
@payroll_admin_required
def earnings_report():
    report_type = request.args.get('type', 'monthly')
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)

    # 🧮 Compute total hours worked per employee (SQLite-compatible)
    subquery = db.session.query(
        Attendance.employee_id,
        func.sum(
            (
                func.strftime('%s', func.concat(Attendance.date, ' ', Attendance.time_out)) -
                func.strftime('%s', func.concat(Attendance.date, ' ', Attendance.time_in))
            ) / 3600.0  # convert seconds to hours
        ).label('total_hours')
    )

    if report_type == 'monthly':
        subquery = subquery.filter(
            extract('year', Attendance.date) == year,
            extract('month', Attendance.date) == month
        )
    elif report_type == 'annual':
        subquery = subquery.filter(extract('year', Attendance.date) == year)

    subquery = subquery.group_by(Attendance.employee_id).subquery()

    # 🧾 Join employee + computed total hours
    query = db.session.query(
        Employee.id,
        Employee.first_name,
        Employee.last_name,
        Employee.salary,
        func.coalesce(subquery.c.total_hours, 0).label('total_hours'),
        (func.coalesce(subquery.c.total_hours, 0) * (Employee.salary / 160)).label('total_earnings')
    ).outerjoin(subquery, Employee.id == subquery.c.employee_id)

    reports = query.all()

    return render_template(
        'payroll/admin/earnings_report.html',
        reports=reports,
        report_type=report_type,
        year=year,
        month=month
    )


# =========================================================
# 🧾 EXPORT EARNINGS REPORT AS PDF
# =========================================================
@payroll_admin_bp.route('/export_earnings_pdf')
@payroll_admin_required
def export_earnings_pdf():
    """Export the employee earnings report to a PDF file."""
    report_type = request.args.get('type', 'monthly')
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)

    query = db.session.query(
        Employee.first_name,
        Employee.last_name,
        func.sum(Payroll.working_hours).label('total_hours'),
        func.sum(Payroll.gross_pay).label('total_gross'),
        func.sum(Payroll.total_deductions).label('total_deductions'),
        func.sum(Payroll.net_pay).label('total_net')
    ).join(Payroll, Payroll.employee_id == Employee.id)

    if report_type == 'monthly':
        query = query.filter(
            extract('year', Payroll.pay_period_start) == year,
            extract('month', Payroll.pay_period_start) == month
        )
    else:
        query = query.filter(extract('year', Payroll.pay_period_start) == year)

    results = query.group_by(Employee.id).all()

    # --- Generate PDF
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 80

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, "Employee Earnings Report")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y - 20, f"Report Type: {report_type.capitalize()} | Year: {year}")
    if report_type == 'monthly':
        pdf.drawString(400, y - 20, f"Month: {month}")

    # Header
    y -= 50
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Employee")
    pdf.drawString(220, y, "Hours")
    pdf.drawString(300, y, "Gross Pay")
    pdf.drawString(400, y, "Deductions")
    pdf.drawString(500, y, "Net Pay")
    pdf.line(50, y - 2, 550, y - 2)
    y -= 20

    pdf.setFont("Helvetica", 10)
    for emp in results:
        if y < 100:
            pdf.showPage()
            y = height - 100
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(50, y, "Employee")
            pdf.drawString(220, y, "Hours")
            pdf.drawString(300, y, "Gross Pay")
            pdf.drawString(400, y, "Deductions")
            pdf.drawString(500, y, "Net Pay")
            pdf.line(50, y - 2, 550, y - 2)
            pdf.setFont("Helvetica", 10)
            y -= 20

        hours = emp.total_hours or 0
        gross = emp.total_gross or 0
        deductions = emp.total_deductions or 0
        net = emp.total_net or 0

        pdf.drawString(50, y, f"{emp.first_name} {emp.last_name}")
        pdf.drawRightString(270, y, f"{hours:.2f}")
        pdf.drawRightString(370, y, f"₱{gross:,.2f}")
        pdf.drawRightString(470, y, f"₱{deductions:,.2f}")
        pdf.drawRightString(560, y, f"₱{net:,.2f}")
        y -= 18

    pdf.save()
    buffer.seek(0)

    filename = f"earnings_report_{report_type}_{year}"
    if report_type == 'monthly':
        filename += f"_{month:02d}"
    filename += ".pdf"

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )


@payroll_admin_bp.route("/deductions")
@payroll_admin_required
@login_required
def deduction_list():

    deductions = Deduction.query.order_by(Deduction.created_at.desc()).all()
    return render_template(
        "deduction/list.html",
        deductions=deductions
    )



# =====================================================
# CREATE / UPDATE DEDUCTION
# =====================================================

@payroll_admin_bp.route("/save", methods=["POST"])
@payroll_admin_required
@login_required
def save_deduction():

    ded_id = request.form.get("deduction_id")

    if ded_id:
        deduction = Deduction.query.get_or_404(ded_id)
    else:
        deduction = Deduction()

    deduction.name = request.form.get("name")
    deduction.description = request.form.get("description")
    deduction.calculation_type = request.form.get("calculation_type")
    deduction.rate = float(request.form.get("rate") or 0)
    deduction.ceiling = request.form.get("ceiling") or None
    deduction.floor = request.form.get("floor") or None

    db.session.add(deduction)
    db.session.commit()

    flash("Deduction saved", "success")

    return redirect(url_for("deduction_bp.deduction_list"))


# =====================================================
# DELETE
# =====================================================

@payroll_admin_bp.route("/delete/<int:id>")
@payroll_admin_required
@login_required
def delete_deduction(id):

    deduction = Deduction.query.get_or_404(id)

    db.session.delete(deduction)
    db.session.commit()

    flash("Deleted", "warning")

    return redirect(url_for("deduction_bp.deduction_list"))


# =====================================================
# MANAGE EMPLOYEE DEDUCTION
# =====================================================

@payroll_admin_bp.route("/manage/<int:deduction_id>")
@payroll_admin_required
@login_required
def manage_employee_deduction(deduction_id):

    deduction = Deduction.query.get_or_404(deduction_id)

    employees = Employee.query.all()

    return render_template(
        "deduction/employee_manage.html",
        deduction=deduction,
        employees=employees
    )


@payroll_admin_bp.route("/assign-employee", methods=["POST"])
@login_required
def assign_employee():

    employee_id = request.form.get("employee_id")
    deduction_id = request.form.get("deduction_id")

    link = EmployeeDeduction(
        employee_id=employee_id,
        deduction_id=deduction_id,
        override_amount=request.form.get("override_amount") or None,
        active=True
    )

    db.session.add(link)
    db.session.commit()

    flash("Employee deduction linked", "success")

    return redirect(
        url_for(
            "deduction_bp.manage_employee_deduction",
            deduction_id=deduction_id
        )
    )


# =====================================================
# VIEW BRACKETS
# =====================================================

@payroll_admin_bp.route("/bracket/<int:deduction_id>")
@login_required
def view_bracket(deduction_id):

    deduction = Deduction.query.get_or_404(deduction_id)

    return render_template(
        "deduction/bracket_modal.html",
        deduction=deduction
    )


# =====================================================
# COMPUTATION PREVIEW
# =====================================================

@payroll_admin_bp.route("/preview/<int:employee_deduction_id>")
@login_required
def preview_computation(employee_deduction_id):

    link = EmployeeDeduction.query.get_or_404(employee_deduction_id)

    result = link.calculate()

    return result