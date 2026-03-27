from main_app.extensions import db
from main_app.helpers.decorators import payroll_admin_required
from main_app.models.hr_models import Employee, Department, Attendance, EmploymentType
from main_app.models.payroll_models import Payroll, PayrollPeriod
from main_app.deductions import compute_regular_withholding_tax

from flask_login import login_required
from flask import render_template, redirect, request, flash, url_for, jsonify
from datetime import datetime, timedelta

from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp


@payroll_admin_bp.route('/payroll-periods/add', methods=['GET', 'POST'])
@payroll_admin_required
@login_required
def add_payroll_period():

    if request.method == 'POST':
        try:
            period_name = request.form.get('period_name').strip()

            # Convert string to Python date objects
            start_date = datetime.strptime(request.form.get('start_date'), "%Y-%m-%d").date()
            end_date = datetime.strptime(request.form.get('end_date'), "%Y-%m-%d").date()
            pay_date = datetime.strptime(request.form.get('pay_date'), "%Y-%m-%d").date()
            
            
            if not period_name or not start_date or not end_date or not pay_date:
                flash("All fields are required.", "danger")
                return redirect(request.url)

            if start_date > end_date:
                flash("Start date cannot be later than end date.", "danger")
                return redirect(request.url)

            new_period = PayrollPeriod(
                period_name=period_name,
                start_date=start_date,
                end_date=end_date,
                pay_date=pay_date,
                status="Open"
            )

            db.session.add(new_period)
            db.session.commit()

            flash(f'Payroll period "{period_name}" created successfully!', 'success')
            return redirect(url_for('payroll_admin_bp.view_payroll_periods'))

        except Exception as e:
            db.session.rollback()
            print(f"Error creating payroll period: {e}")
            flash('An error occurred while creating the payroll period. Please try again.', 'danger')

    return render_template('payroll/admin/payroll_periods/add_period.html')




@payroll_admin_bp.route('/payroll-periods/edit/<int:period_id>', methods=['GET', 'POST'])
@payroll_admin_required
@login_required
def edit_payroll_period(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)

    if request.method == 'POST':
        period.period_name = request.form.get('period_name')
        # Convert string to date objects
        period.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        period.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        period.pay_date = datetime.strptime(request.form.get('pay_date'), '%Y-%m-%d').date()
        period.status = request.form.get('status')
        
        db.session.commit()
        flash('Payroll period updated successfully.', 'success')
        return redirect(url_for('payroll_admin_bp.view_payroll_periods'))

    return render_template('payroll/admin/payroll_periods/edit_period.html', payroll_period=period)



@payroll_admin_bp.route('/payroll-periods/delete/<int:period_id>', methods=['POST'])
@payroll_admin_required
@login_required
def delete_payroll_period(period_id):
    period = PayrollPeriod.query.get_or_404(period_id)
    db.session.delete(period)
    db.session.commit()
    flash('Payroll period deleted successfully.', 'success')
    return redirect(url_for('payroll_admin_bp.view_payroll_periods'))