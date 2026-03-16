from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import date

from main_app.helpers.decorators import employee_required
from main_app.models.user import  User
from main_app.helpers.utils import get_leave_balance, get_attendance_chart_data, get_attendance_summary
from main_app.extensions import db

from main_app.blueprints.employee_system.routes.employee import employee_bp




@employee_bp.route('/profile', methods=['GET'])
@login_required
@employee_required
def profile():
    user = current_user
    employee = user.employee_profile


    age = None
    working_duration = None
    if employee:
        if employee.date_of_birth:
            today = date.today()
            age = today.year - employee.date_of_birth.year - ((today.month, today.day) < (employee.date_of_birth.month, employee.date_of_birth.day))
        working_duration = employee.get_working_duration()


    return render_template(
    "employee/profile.html",
    user=user,
    employee=employee,
    age=age,
    working_duration=working_duration
    )



@employee_bp.route('/profile/edit', methods=['POST'])
@login_required
@employee_required
def edit_profile():
    user = current_user
    employee = user.employee_profile


    data = request.get_json()
    current_password = data.get('current_password')
    new_email = data.get('email')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')


    # Verify current password
    if current_password != user.password:
        return jsonify({'status': 'error', 'message': 'Current password is incorrect.'}), 400


    # Update email
    if new_email and new_email != user.email:
        existing_user = User.query.filter_by(email=new_email).first()
        if existing_user:
            return jsonify({'status': 'error', 'message': 'Email already in use.'}), 400
        user.email = new_email
        if employee:
            employee.email = new_email


    # Update password
    if new_password:
        if new_password != confirm_password:
            return jsonify({'status': 'error', 'message': 'Passwords do not match.'}), 400
        user.password = new_password # plain text (for now)


    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Profile updated successfully.'})