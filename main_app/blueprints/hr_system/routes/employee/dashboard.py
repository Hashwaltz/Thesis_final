from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import date

from main_app.helpers.decorators import employee_required
from main_app.models.hr_models import LeaveType
from main_app.helpers.utils import get_leave_balance, get_attendance_chart_data, get_attendance_summary
from main_app.extensions import db

from main_app.blueprints.hr_system.routes.employee import hr_employee_bp


@hr_employee_bp.route('/dashboard')
@login_required
@employee_required
def dashboard():
    employee = current_user.employee_profile

    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('hr_auth.logout'))

    today = date.today()
    start_date = today.replace(day=1)
    end_date = today

    attendance_summary = get_attendance_summary(employee.id, start_date, end_date)
    attendance_chart = get_attendance_chart_data(employee.id, start_date, end_date) or {}
    attendance_chart.setdefault("dates", [])
    attendance_chart.setdefault("present_counts", [])
    attendance_chart.setdefault("absent_counts", [])
    attendance_chart.setdefault("late_counts", [])

    leave_types = LeaveType.query.all()
    leave_balances = {lt.name: get_leave_balance(employee.id, lt.name) for lt in leave_types}

    working_duration = employee.get_working_duration()

    return render_template(
        'hr/employee/employee_dashboard.html',
        employee=employee,
        attendance_summary=attendance_summary,
        attendance_chart=attendance_chart,
        leave_balances=leave_balances or [],
        working_duration=working_duration,
        not_assigned=False
    )




@hr_employee_bp.route("/profile")
@login_required
@employee_required
def employee_profile():

    employee = current_user.employee_profile

    if not employee:
        return render_template(
            "hr/employee/employee_profile.html",
            employee=None
        )

    # ------------------------------------------------
    # Leave Credit Table Builder
    # ------------------------------------------------
    leave_table = []

    today = date.today()

    for credit in employee.leave_credits:

        leave_table.append({
            "particulars": credit.leave_type.name,
            "vacation": credit.total_credits if credit.leave_type.name.lower().startswith("vacation") else "-",
            "sick": credit.total_credits if credit.leave_type.name.lower().startswith("sick") else "-",
            "total": round(credit.remaining_credits(), 2),
            "type": "balance"
        })

    return render_template(
        "hr/employee//employee_profile.html",
        employee=employee,
        leave_table=leave_table,
        today=today
    )




@hr_employee_bp.route('/edit_password', methods=['GET', 'POST'])
@login_required
@employee_required
def edit_password():
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        current_password = data.get('current_password', '').strip()
        new_password = data.get('new_password', '').strip()
        confirm_password = data.get('confirm_password', '').strip()

        # Validate empty
        if not current_password or not new_password or not confirm_password:
            return jsonify({'status': 'error', 'message': 'All fields are required.'}), 400

        # Verify current password
        if current_password != current_user.password:
            return jsonify({'status': 'error', 'message': 'Current password is incorrect.'}), 400

        # Check new vs confirm
        if new_password != confirm_password:
            return jsonify({'status': 'error', 'message': 'Passwords do not match.'}), 400

        # Update password
        try:
            current_user.password = new_password  # plain text (for now)
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Password successfully updated.'})
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating employee password: {e}")
            return jsonify({'status': 'error', 'message': 'Failed to update password.'}), 500

    # GET → show the form
    return render_template('hr/employee/employee_user.html', employee=current_user.employee_profile)