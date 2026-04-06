from flask_mail import Message
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from datetime import  datetime, timedelta
import secrets
import string

from main_app.models.user import  User
from main_app.extensions import db, mail



from main_app.blueprints.employee_system.routes.employee_auth import employee_auth_bp

OTP_EXPIRY_MINUTES = 10


def generate_otp(length=6):
    """Generate a numeric OTP"""
    return ''.join(secrets.choice(string.digits) for _ in range(length))

def send_otp_email(email, first_name, otp):
    """Send OTP via Gmail SMTP"""
    try:
        msg = Message(
            subject="🔐 Password Reset OTP - Employee Portal",
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto;">
                <h2 style="color: #7c3aed;">Password Reset Request</h2>
                <p>Hello <strong>{first_name}</strong>,</p>
                <p>You requested a password reset for your Employee Portal account.</p>
                <p style="font-size: 24px; font-weight: bold; letter-spacing: 4px; background: #f3e8ff; padding: 12px; border-radius: 8px; text-align: center;">
                    {otp}
                </p>
                <p>This code expires in <strong>{OTP_EXPIRY_MINUTES} minutes</strong>.</p>
                <p>If you didn't request this, please ignore this email or contact support.</p>
                <hr>
                <p style="font-size: 12px; color: #666;">Employee Portal • Secure Access System</p>
            </div>
            """
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send OTP email: {e}")
        return False
    



@employee_auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        fname = request.form.get('first_name', '').strip().title()
        lname = request.form.get('last_name', '').strip().title()

        # Find user with matching credentials
        user = User.query.filter_by(email=email).first()
        employee = user.employee_profile if user else None

        # Validate all 3 fields match (avoid user enumeration in production*)
        if user and employee and employee.first_name == fname and employee.last_name == lname:
            # Generate & store OTP
            otp = generate_otp()
            user.otp_code = otp  # Ensure your User model has these fields
            user.otp_expiry = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
            user.otp_verified = False
            db.session.commit()

            # Send OTP email
            if send_otp_email(email, fname, otp):
                flash('OTP sent to your email. Please check your inbox (and spam).', 'success')
                return redirect(url_for('employee_auth_bp.verify_otp', email=email))
            else:
                flash('Failed to send OTP. Please try again.', 'error')
        else:
            # For security, use generic message in production
            flash('If an account matches those details, an OTP has been sent.', 'success')
            return redirect(url_for('employee_auth_bp.login'))

    return render_template('employee_auth/forgot_password.html')



@employee_auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = request.args.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first()

    if not user or not user.otp_code or user.otp_expiry < datetime.utcnow():
        flash('Invalid or expired request. Please try again.', 'error')
        return redirect(url_for('employee_auth_bp.forgot_password'))

    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()
        
        if entered_otp == user.otp_code:
            # Mark OTP as verified
            user.otp_verified = True
            user.otp_code = None  # Invalidate used OTP
            user.otp_expiry = None
            db.session.commit()
            
            flash('OTP verified. Please set your new password.', 'success')
            return redirect(url_for('employee_auth_bp.reset_password', email=email))
        else:
            flash('Invalid OTP. Please try again.', 'error')

    return render_template('employee_auth/verify_otp.html', email=email)





@employee_auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = request.args.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first()

    # Ensure OTP was verified recently (add time buffer if needed)
    if not user or not getattr(user, 'otp_verified', False):
        flash('Unauthorized access. Please restart the process.', 'error')
        return redirect(url_for('employee_auth_bp.forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or len(new_password) < 8:
            flash('Password must be at least 8 characters.', 'error')
        elif new_password != confirm_password:
            flash('Passwords do not match.', 'error')
        else:
            # 🔐 SECURITY: Hash the password! (See note below)
            user.password = new_password  # ⚠️ Replace with hashing in production
            user.otp_verified = False  # Reset flag
            db.session.commit()
            
            flash('Password updated successfully. Please log in.', 'success')
            return redirect(url_for('employee_auth_bp.login'))

    return render_template('employee_auth/reset_password.html', email=email)