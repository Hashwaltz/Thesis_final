from flask import redirect, url_for, render_template


from main_app.blueprints.hr_system.routes.hr_auth   import hr_auth_bp


@hr_auth_bp.route('/')
def index():
    return redirect(url_for('hr_auth_bp.login'))



@hr_auth_bp.route('/about-hr')
def about_hr():
    return render_template('hr_auth/about.html')


@hr_auth_bp.route('/hr-features')
def hr_features():
    return render_template('hr_auth/features.html')
