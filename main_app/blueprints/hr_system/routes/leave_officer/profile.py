from flask import request, jsonify, render_template, abort, current_app
from flask_login import login_required, current_user
from datetime import date
from flask_mail import Message
import threading

from main_app.extensions import db, mail
from main_app.models.hr_models import Department, Leave, LeaveType, Employee
from main_app.models.user import User
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
        return jsonify({"status": "error", "message": "Current password is incorrect"}), 400

    # --- Check new password confirmation ---
    if new_password and new_password != confirm_password:
        return jsonify({"status": "error", "message": "New password and confirm password do not match"}), 400

    # --- Track if password changed for email notification ---
    password_changed = False

    # --- Update email ---
    if new_email and new_email != current_user.email:
        # Optional: check if email is already taken by another user
        existing = User.query.filter_by(email=new_email).first()
        if existing and existing.id != current_user.id:
            return jsonify({"status": "error", "message": "Email already in use"}), 400
        current_user.email = new_email

    # --- Update password if provided ---
    if new_password and new_password.strip():
        current_user.password = new_password.strip()  # ✅ Plain text per your request
        password_changed = True

    try:
        db.session.commit()

        # 📬 Send email notification asynchronously if password was changed
        if password_changed and current_user.email:
            _send_leave_officer_password_notification(
                current_app._get_current_object(), 
                current_user
            )

        return jsonify({"status": "success", "message": "Profile updated successfully"})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating leave officer profile: {str(e)}")
        return jsonify({"status": "error", "message": "An error occurred. Please try again."}), 500


# =====================================================
# 📧 EMAIL HELPER FUNCTIONS (Thread-Safe)
# =====================================================
def _send_leave_officer_password_notification(app, user):
    """Send password change notification - receives actual Flask app instance"""
    
    def _send_async_email(app_instance, msg):
        """Inner function that runs within proper app context"""
        with app_instance.app_context():
            try:
                mail.send(msg)
                app_instance.logger.info(f"Password notification sent to {user.email}")
            except Exception as e:
                app_instance.logger.error(f"Failed to send email to {user.email}: {str(e)}")
    
    msg = Message(
        subject="🔐 Your Password Has Been Successfully Updated",
        sender=app.config.get("MAIL_DEFAULT_SENDER", "noreply@yourdomain.com"),
        recipients=[user.email]
    )
    msg.body = f"""Hello {getattr(user, 'first_name', 'User')},

Your account password has been successfully updated.

🔑 New Password: {user.password}

⚠️ For your security, please keep this password confidential. If you did not request this change, contact your system administrator immediately.

Regards,
{app.config.get('APP_NAME', 'HR System')} Admin Team
"""
    # ✅ Start background thread with daemon mode
    thread = threading.Thread(target=_send_async_email, args=(app, msg))
    thread.daemon = True
    thread.start()