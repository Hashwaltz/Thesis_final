from flask import render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import date, datetime
import threading
from flask_mail import Message


from main_app.helpers.decorators import employee_required
from main_app.models.user import  User
from main_app.extensions import db, mail

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

    # 🔐 Verify current password (plain-text comparison)
    if current_password != user.password:
        return jsonify({'status': 'error', 'message': 'Current password is incorrect.'}), 400

    # 📧 Update email if provided
    if new_email and new_email != user.email:
        existing_user = User.query.filter_by(email=new_email).first()
        if existing_user:
            return jsonify({'status': 'error', 'message': 'Email already in use.'}), 400
        user.email = new_email
        if employee:
            employee.email = new_email

    # 🔑 Update password if provided
    password_changed = False
    if new_password:
        if new_password != confirm_password:
            return jsonify({'status': 'error', 'message': 'Passwords do not match.'}), 400
        user.password = new_password  # ✅ Plain text per your request
        password_changed = True

    try:
        db.session.commit()

        # 📬 Send email notification asynchronously if password was changed
        if password_changed and user.email:
            # ✅ Pass the actual app instance to the thread
            _send_employee_password_notification(current_app._get_current_object(), user)

        return jsonify({'status': 'success', 'message': 'Profile updated successfully.'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating employee profile: {e}")
        return jsonify({'status': 'error', 'message': 'An error occurred. Please try again.'}), 500


# =====================================================
# 📧 EMAIL HELPER FUNCTIONS FOR EMPLOYEE PORTAL
# =====================================================
def _send_employee_password_notification(app, user):
    """Send password change notification to employee - receives actual app instance"""
    
    def _send_async_email(app_instance, msg):
        """Inner function that runs within app context for Flask-Mail"""
        with app_instance.app_context():
            mail.send(msg)
    
    msg = Message(
        subject="🔐 Your Employee Portal Password Has Been Updated",
        sender=app.config.get("MAIL_DEFAULT_SENDER", "noreply@yourdomain.com"),
        recipients=[user.email]
    )
    
    # Build email body with employee-specific branding
    app_name = app.config.get('APP_NAME', 'GovHRPay Employee Portal')
    support_email = app.config.get('SUPPORT_EMAIL', 'support@yourdomain.com')
    
    msg.body = f"""Hello {user.first_name or 'Employee'},

Your Employee Portal account password has been successfully updated.

🔑 New Password: {user.password}

📅 Updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

⚠️ SECURITY NOTICE:
• Keep this password confidential and do not share it with anyone
• GovHRPay staff will NEVER ask for your password via email or phone
• If you did not request this change, contact your system administrator immediately:
  📧 {support_email}
  📞 Your agency's IT Helpdesk

🔒 For your protection:
• Always log out when using shared or public computers
• Use a unique password for your Employee Portal account
• Enable multi-factor authentication if available

Regards,
{app_name} Security Team
---
This is an automated security notification. Please do not reply to this email.
"""
    
    # Optional: HTML version for richer email clients
    msg.html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
          <div style="background: linear-gradient(135deg, #7e22ce 0%, #9333ea 100%); padding: 20px; border-radius: 12px 12px 0 0;">
            <h2 style="color: white; margin: 0;">🔐 Password Updated</h2>
            <p style="color: #e9d5ff; margin: 5px 0 0 0;">Employee Portal Security Notification</p>
          </div>
          
          <div style="background: #f8fafc; padding: 20px; border: 1px solid #e2e8f0; border-radius: 0 0 12px 12px;">
            <p>Hello <strong>{user.first_name or 'Employee'}</strong>,</p>
            
            <p>Your Employee Portal account password has been successfully updated.</p>
            
            <div style="background: #fff; border-left: 4px solid #9333ea; padding: 12px 16px; margin: 20px 0;">
              <p style="margin: 0;"><strong>🔑 New Password:</strong> <code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">{user.password}</code></p>
              <p style="margin: 8px 0 0 0; font-size: 0.9em; color: #64748b;">Updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>
            
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin: 20px 0;">
              <p style="margin: 0 0 10px 0; color: #991b1b;"><strong>⚠️ Security Notice</strong></p>
              <ul style="margin: 0; padding-left: 20px; color: #7f1d1d;">
                <li>Keep this password confidential</li>
                <li>GovHRPay staff will NEVER ask for your password</li>
                <li>Contact IT immediately if you didn't request this change</li>
              </ul>
            </div>
            
            <p style="margin-top: 20px;">Regards,<br><strong>{app_name} Security Team</strong></p>
            
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
            <p style="font-size: 0.85em; color: #64748b; margin: 0;">
              This is an automated security notification. Please do not reply to this email.<br>
              For support, contact: <a href="mailto:{support_email}" style="color: #7e22ce;">{support_email}</a>
            </p>
          </div>
        </div>
      </body>
    </html>
    """
    
    # ✅ Start thread with app instance passed as argument
    thread = threading.Thread(target=_send_async_email, args=(app, msg))
    thread.daemon = True  # Allows main app to exit even if thread is running
    thread.start()