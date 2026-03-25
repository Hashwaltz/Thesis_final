from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required
from datetime import datetime

from main_app.models.hr_models import Employee
from main_app.models.payroll_models import Loan, LoanPayment
from main_app.extensions import db
from main_app.helpers.decorators import payroll_admin_required

from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp



@payroll_admin_bp.route("/loans")
@login_required
@payroll_admin_required
def loans():

    page = request.args.get("page", 1, type=int)

    pagination = Loan.query.order_by(
        Loan.created_at.desc()
    ).paginate(page=page, per_page=10, error_out=False)

    return render_template(
        "payroll/admin/views/loan_list.html",
        loans=pagination.items,
        pagination=pagination
    )



@payroll_admin_bp.route('/loans/create', methods=['GET', 'POST'])
@login_required
@payroll_admin_required
def create_loan():

    employees = Employee.query.filter_by(status="Active").order_by(Employee.last_name, Employee.first_name).all()

    if request.method == 'POST':
        try:
            employee_id = request.form.get("employee_id")
            provider = request.form.get("provider")
            loan_type = request.form.get("loan_type")

            total_amount = float(request.form.get("total_amount") or 0)
            monthly_payment = float(request.form.get("monthly_payment") or 0)

            start_date_raw = request.form.get("start_date")

            # Convert date safely
            start_date = datetime.strptime(start_date_raw, "%Y-%m-%d").date() if start_date_raw else None

            # VALIDATION
            if not employee_id:
                flash("Employee is required", "error")
                return redirect(url_for('payroll_admin_bp.create_loan'))

            if not provider:
                flash("Loan provider is required", "error")
                return redirect(url_for('payroll_admin_bp.create_loan'))

            if not loan_type:
                flash("Loan type is required", "error")
                return redirect(url_for('payroll_admin_bp.create_loan'))

            loan = Loan(
                employee_id=employee_id,
                provider=provider,
                loan_type=loan_type,
                total_amount=total_amount,
                monthly_payment=monthly_payment,
                remaining_balance=total_amount,
                start_date=start_date,
                active=True
            )

            db.session.add(loan)
            db.session.commit()

            flash("Loan created successfully", "success")
            return redirect(url_for('payroll_admin_bp.loans'))

        except Exception as e:
            db.session.rollback()
            print("Loan Create Error:", e)
            flash("Error creating loan", "danger")

    return render_template(
        "payroll/admin/loans/loan_form.html",
        action="Create",
        loan=None,
        employees=employees
    )



@payroll_admin_bp.route("/loans/<int:loan_id>/edit", methods=["GET", "POST"])
@login_required
@payroll_admin_required
def edit_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)

    if request.method == "POST":
        loan.provider = request.form.get("provider")
        loan.loan_type = request.form.get("loan_type")
        loan.total_amount = float(request.form.get("total_amount"))
        loan.monthly_payment = float(request.form.get("monthly_payment"))

        db.session.commit()
        flash("Loan updated successfully!", "success")
        return redirect(url_for("payroll_admin_bp.loans"))

    return render_template(
        "payroll/admin/loans/edit_loan.html",
        loan=loan
    )



@payroll_admin_bp.route('/loans/delete/<int:loan_id>', methods=['POST'])
@login_required
@payroll_admin_required
def delete_loan(loan_id):

    loan = Loan.query.get_or_404(loan_id)

    db.session.delete(loan)

    db.session.commit()

    flash("Loan deleted successfully", "success")

    return redirect(url_for("payroll_admin_bp.loans"))




@payroll_admin_bp.route("/loans/<int:loan_id>/payments")
@login_required
@payroll_admin_required
def loan_payments(loan_id):

    loan = Loan.query.get_or_404(loan_id)

    payments = LoanPayment.query.filter_by(
        loan_id=loan.id
    ).order_by(LoanPayment.created_at.desc()).all()

    return render_template(
        "payroll/admin/loans/loan_payments.html",
        loan=loan,
        payments=payments
    )