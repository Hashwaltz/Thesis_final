from flask import render_template, request, redirect, url_for, flash
from flask_login import  logout_user, login_required, current_user, login_user

from main_app.extensions import db
from main_app.models.user import User


from main_app.blueprints.employee_system.routes.employee_auth import employee_auth_bp


roles = ['hr_admin', 'officer', 'leave_officer', 'dept_head', 'employee', 'payroll_staff', 'payroll_admin']

@employee_auth_bp.route('/employee-about')
def about_employee():   
    return render_template('employee_auth/about.html')  



@employee_auth_bp.route('/employee-features')
def features_employee():
    return render_template('employee_auth/features.html')


@employee_auth_bp.route('/employee-login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:

        role = current_user.role.lower()
        if role not in roles:
            return redirect(url_for('employee_auth_bp.login'))
        else:
            return redirect(url_for('employee_bp.dashboard'))
    

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(email=email).first()
        
        if not user or user.password.strip() != password:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('employee_auth_bp.login'))

        if not user.active:
            flash('Account deactivated.', 'error')
            return redirect(url_for('employee_auth_bp.login'))

        login_user(user, remember=True)
        db.session.commit()
        db.session.flush()

        return redirect(url_for('employee_bp.dashboard'))

    return render_template('employee_auth/login.html')


@employee_auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('employee_auth_bp.login'))