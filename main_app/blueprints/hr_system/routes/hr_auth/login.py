from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user



from main_app.extensions import db
from main_app.models.user import User

from main_app.blueprints.hr_system.routes.hr_auth  import hr_auth_bp



# ----------------- LOGIN -----------------
@hr_auth_bp.route('/hr-login', methods=['GET', 'POST'])
def login():

    if current_user.is_authenticated:
        role = current_user.role.lower()

        if role == 'hr_admin':
            return redirect(url_for('hr_admin_bp.hr_dashboard'))
        elif role == 'officer':
            return redirect(url_for('hr_officer_bp.hr_dashboard'))
        elif role == 'leave_officer':
            return redirect(url_for('leave_officer.leave_dashboard'))
        elif role == 'dept_head':
            return redirect(url_for('hr_head_bp.dashboard'))
        elif role in ['employee', 'staff']:
            return redirect(url_for('hr_employee_bp.dashboard'))

    if request.method == 'POST':

        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(email=email).first()

        if not user or user.password.strip() != password:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('hr_auth_bp.login'))

        if not user.active:
            flash('Account deactivated.', 'error')
            return redirect(url_for('hr_auth_bp.login'))

        # ⭐ FORCE SESSION SAVE
        login_user(user, remember=True)

        db.session.commit()
        db.session.flush()

        role = user.role.lower()

        if role in ['hr_admin', 'admin']:
            return redirect(url_for('hr_admin_bp.hr_dashboard'))
        elif role == 'officer':
            return redirect(url_for('hr_officer_bp.hr_dashboard'))
        elif role == 'dept_head':
            return redirect(url_for('hr_head_bp.dashboard'))
        elif role in ['employee', 'staff']:
            return redirect(url_for('hr_employee_bp.dashboard'))

        return redirect(url_for('hr_auth_bp.login'))

    return render_template('hr_auth/hr_login.html')



# ----------------- LOGOUT -----------------
@hr_auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('hr_auth_bp.login'))




# ----------------- EDIT PROFILE -----------------
@hr_auth_bp.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user = current_user

    if request.method == 'POST':
        user.email = request.form.get('email')
        user.first_name = request.form.get('first_name')
        user.last_name = request.form.get('last_name')

        password = request.form.get('password')
        if password and password.strip():
            user.password = password.strip()

        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')

        return redirect(url_for('hr_auth.edit_profile'))

    return render_template('hr_auth/profile.html', user=user)
