from flask import Blueprint, render_template, request,flash, redirect, url_for, jsonify, current_app
from flask_login import login_required, current_user

from main_app.helpers.decorators import admin_required
from main_app.models.user import User
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
        status_filter=status_filter  
    )





@hr_admin_bp.route("/user/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        try:
            user.email = request.form.get("email")
            user.first_name = request.form.get("first_name")
            user.last_name = request.form.get("last_name")
            user.role = request.form.get("role")
            user.active = request.form.get("status") == "1"

            db.session.commit()

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"status": "success", "message": "User updated successfully!"})

            flash("User updated successfully!", "success")
            return redirect(url_for("hr_admin_bp.view_users"))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating user {user_id}: {e}")
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"status": "error", "message": "Error updating user."}), 500
            flash("Error updating user.", "error")

    # GET → JSON for modal
    if request.headers.get("Accept") == "application/json":
        return jsonify({
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "active": user.active
        })

    return redirect(url_for("hr_admin_bp.view_users"))
