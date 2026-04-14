from flask import Blueprint, render_template, request,flash, redirect, url_for, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime
from flask_mail import Message
from threading import Thread
from main_app.helpers.decorators import admin_required
from main_app.models.user import User
from main_app.models.hr_models import Employee, Department
from main_app.extensions import db, mail


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



@hr_admin_bp.route("/user/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
@login_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    # =====================================================
    # GET → Modal Load JSON
    # =====================================================
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

    # =====================================================
    # POST → Update Role, Status & Optional Password
    # =====================================================
    if request.method == "POST":
        try:
            role = request.form.get("role")
            status = request.form.get("status")
            new_password = request.form.get("new_password")

            # Update role if provided
            if role:
                user.role = role

            # Update active/inactive status
            user.active = True if status == "1" else False

            # Handle password change (PLAINTEXT as requested)
            password_changed = False
            if new_password and new_password.strip():
                user.password = new_password.strip()  # ⚠️ No hashing per your request
                password_changed = True

            db.session.commit()

            # Send email notification asynchronously if password changed
            if password_changed and user.email:
                _send_password_reset_email(user, new_password.strip())

            return jsonify({
                "status": "success",
                "message": "User updated successfully." + (" New password sent to email." if password_changed else "")
            })

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"User update failed: {str(e)}")
            return jsonify({
                "status": "error",
                "message": "Update failed"
            }), 500


# =====================================================
# EMAIL HELPER FUNCTIONS
# =====================================================
def _send_password_reset_email(user, password):
    msg = Message(
        subject="🔐 Your Account Password Has Been Updated",
        sender=current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@yourdomain.com"),
        recipients=[user.email]
    )
    msg.body = f"""Hello {user.first_name} {user.last_name},

Your account password has been updated by an administrator.

🔑 New Password: {password}

⚠️ Please log in and change this password immediately for your security.
If you did not expect this change, contact your IT/Admin team right away.

Regards,
{current_app.config.get('APP_NAME', 'HR System')} Admin Team
"""
    # Run email in background thread to avoid blocking the HTTP response
    Thread(target=_send_async_email, args=(msg,)).start()


def _send_async_email(msg):
    with current_app.app_context():
        mail.send(msg)