from datetime import date, timedelta, datetime
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_
from werkzeug.utils import secure_filename
import os
import uuid
import pandas as pd



from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Employee, Department, Leave, Attendance, EmploymentType, Position
from main_app.models.user import User 
from main_app.extensions import db
from main_app.helpers.functions import parse_date, allowed_file, ALLOWED_EXTENSIONS, UPLOAD_FOLDER

from main_app.blueprints.hr_system.routes.admin import hr_admin_bp



@hr_admin_bp.route('/dashboard')
@admin_required
@login_required
def hr_dashboard():
    today = date.today()

    # --- Basic Stats ---
    total_employees = Employee.query.count()
    # Count only Active employees using status string
    active_employees = Employee.query.filter_by(status="Active").count()
    total_departments = Department.query.count()

    # --- Recent records ---
    recent_employees = Employee.query.order_by(Employee.created_at.desc()).limit(5).all()
    recent_leaves = Leave.query.order_by(Leave.created_at.desc()).limit(5).all()

    # --- Employee Growth (Monthly Count) ---
    growth_labels = []
    growth_counts = []
    for i in range(6, 0, -1):
        month = today.replace(day=1) - timedelta(days=30*(i-1))
        month_start = month.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        count = Employee.query.filter(Employee.date_hired.between(month_start, month_end)).count()
        growth_labels.append(month_start.strftime("%b"))
        growth_counts.append(count)

    # --- Department Distribution ---
    dept_data = db.session.query(
        Department.name, db.func.count(Employee.id)
    ).join(Employee, Employee.department_id == Department.id)\
     .group_by(Department.name).all()
    dept_labels = [d[0] for d in dept_data]
    dept_counts = [d[1] for d in dept_data]

    # --- Employees per Barangay ---
    barangay_data = db.session.query(
        Employee.barangay, db.func.count(Employee.id)
    ).group_by(Employee.barangay).all()
    barangay_labels = [b[0] or "N/A" for b in barangay_data]
    barangay_counts = [b[1] for b in barangay_data]

    # --- Attendance Overview (Past 7 days) ---
    attendance_labels = []
    attendance_counts = []
    for i in range(7):
        day = today - timedelta(days=6-i)
        records = Attendance.query.filter_by(date=day).all()
        total = len(records)
        present = len([r for r in records if r.status == "Present"])
        attendance_percentage = round((present / total * 100) if total else 0, 2)
        attendance_labels.append(day.strftime("%a"))
        attendance_counts.append(attendance_percentage)

    # --- Leave Requests ---
    leave_data = db.session.query(
        Leave.status, db.func.count(Leave.id)
    ).group_by(Leave.status).all()
    leave_labels = [l[0] for l in leave_data]
    leave_counts = [l[1] for l in leave_data]

    return render_template(
        'hr/admin/navigations/dashboard.html',
        total_employees=total_employees,
        active_employees=active_employees,
        total_departments=total_departments,
        recent_employees=recent_employees,
        recent_leaves=recent_leaves,
        growth_labels=growth_labels,
        growth_counts=growth_counts,
        dept_labels=dept_labels,
        dept_counts=dept_counts,
        barangay_labels=barangay_labels,
        barangay_counts=barangay_counts,
        attendance_labels=attendance_labels,
        attendance_counts=attendance_counts,
        leave_labels=leave_labels,
        leave_counts=leave_counts,
        user=current_user
    )



@hr_admin_bp.route('/profile', methods=['GET'])
@login_required
@admin_required
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
    "hr/admin/navigations/profile.html",
    user=user,
    employee=employee,
    age=age,
    working_duration=working_duration
    )



@hr_admin_bp.route('/profile/edit', methods=['POST'])
@login_required
@admin_required
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