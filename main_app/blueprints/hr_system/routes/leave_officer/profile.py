from flask import request, jsonify, render_template, abort
from flask_login import login_required, current_user
from datetime import date



from main_app.extensions import db
from main_app.models.hr_models import Department, Leave, LeaveType, Employee
from main_app.helpers.decorators import leave_officer_required


from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp




@leave_officer_bp.route("/profile", methods=["GET"])
@login_required
@leave_officer_required
def profile():
    employee = Employee.query.filter_by(user_id=current_user.id).first()

    if not employee:
        abort(404)

    # Compute age
    age = None
    if employee.date_of_birth:
        today = date.today()
        age = today.year - employee.date_of_birth.year - (
            (today.month, today.day) < (employee.date_of_birth.month, employee.date_of_birth.day)
        )

    # Working duration
    working_duration = None
    if employee.date_hired:
        working_duration = (date.today() - employee.date_hired).days // 365

    return render_template(
        "hr/leave_officer/profile.html",
        employee=employee,
        user=current_user,
        age=age,
        working_duration=working_duration
    )






@leave_officer_bp.route("/profile/edit", methods=["POST"])
@login_required
@leave_officer_required
def edit_profile():
    data = request.get_json()
    current_password = data.get("current_password")
    new_email = data.get("email")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    # --- Check current password ---
    if current_password != current_user.password:
        return jsonify({"status": "error", "message": "Current password is incorrect"})

    # --- Check new password confirmation ---
    if new_password and new_password != confirm_password:
        return jsonify({"status": "error", "message": "New password and confirm password do not match"})

    # --- Update email ---
    if new_email:
        current_user.email = new_email

    # --- Update password if provided ---
    if new_password:
        current_user.password = new_password

    # --- Commit changes ---
    db.session.commit()

    return jsonify({"status": "success", "message": "Profile updated successfully"})