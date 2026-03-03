from flask import Blueprint, render_template, request,flash, redirect, url_for, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime

from main_app.helpers.decorators import admin_required
from main_app.models.user import User
from main_app.models.hr_models import Employee, Department
from main_app.extensions import db


from main_app.blueprints.hr_system.routes.admin import hr_admin_bp



@hr_admin_bp.route('/users', methods=['GET'])
@admin_required
@login_required
def view_users():
    # Get query params
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role', '').strip()
    status_filter = request.args.get('status', '').strip()  

    # Base query
    query = User.query
    departments = Department.query.all()
    # Apply search filter
    if search:
        query = query.filter(
            (User.first_name.ilike(f"%{search}%")) |
            (User.last_name.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%"))
        )

    # Apply role filter
    if role_filter:
        query = query.filter(User.role == role_filter)

    # ✅ Apply status filter
    if status_filter == "active":
        query = query.filter(User.active.is_(True))
    elif status_filter == "inactive":
        query = query.filter(User.active.is_(False))

    # Paginate results
    users = query.order_by(User.id.asc()).paginate(page=page, per_page=10)

    # Roles for dropdown
    roles = ['admin', 'employee', 'dept_head', 'officer']

    return render_template(
        'hr/admin/users/view_users.html',
        users=users,
        roles=roles,
        search=search,
        role_filter=role_filter,
        status_filter=status_filter,
        departments = departments
    )





# EDIT USER (AJAX)
# ===============================
@hr_admin_bp.route("/user/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def edit_user(user_id):

    user = User.query.get_or_404(user_id)

    # ===============================
    # GET → Return JSON
    # ===============================
    if request.method == "GET":
        employee = user.employee_profile

        return jsonify({
            "status": "success",
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "active": user.active,
            "department_id": employee.department_id if employee else None
        })

    # ===============================
    # POST → Update
    # ===============================
    try:
        role = request.form.get("role")
        status = request.form.get("status")
        department_id = request.form.get("department_id") or None

        user.role = role
        user.active = (status == "1")

        employee = user.employee_profile

        if role == "dept_head":

            if not department_id:
                return jsonify({
                    "status": "error",
                    "message": "Department must be assigned for Department Head role."
                }), 400

            if not employee:
                employee = Employee(
                    user_id=user.id,
                    employee_id=f"EMP-{user.id}",
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email
                )
                db.session.add(employee)

            employee.department_id = int(department_id)

        else:
            if employee:
                employee.department_id = None

        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "User updated successfully."
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(str(e))

        return jsonify({
            "status": "error",
            "message": "Update failed."
        }), 500