
from flask import render_template, flash, request, url_for, redirect
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

from main_app.forms import LoginForm, RegistrationForm
from main_app.extensions import db
from main_app.models.user import User

from main_app.blueprints.payroll_system.routes.payroll_auth import payroll_auth_bp


# =========================================================
# REGISTER
# =========================================================
@payroll_auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("payroll_employee.dashboard"))

    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash("Email already registered.", "danger")
            return render_template("register.html", form=form)

        user = User(
            email=form.email.data,
            password=generate_password_hash(form.password.data),
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            role=form.role.data,
        )

        try:
            db.session.add(user)
            db.session.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("payroll_auth_bp.login"))
        except Exception as e:
            db.session.rollback()
            flash(f"Registration failed: {str(e)}", "danger")

    return render_template("register.html", form=form)


# =========================================================
# PROFILE
# =========================================================
@payroll_auth_bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=current_user)


# =========================================================
# CHANGE PASSWORD
# =========================================================
@payroll_auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not check_password_hash(current_user.password, current_password):
            flash("Current password is incorrect.", "danger")
            return render_template("change_password.html")

        if new_password != confirm_password:
            flash("New passwords do not match.", "danger")
            return render_template("change_password.html")

        if len(new_password) < 6:
            flash("New password must be at least 6 characters long.", "danger")
            return render_template("change_password.html")

        current_user.password = generate_password_hash(new_password)
        db.session.commit()
        flash("Password changed successfully.", "success")
        return redirect(url_for("payroll_auth_bp.profile"))

    return render_template("change_password.html")



@payroll_auth_bp.route("/about-payroll")
def about_payroll():
    return render_template("payroll_auth/about.html")

@payroll_auth_bp.route("/features-payroll")
def payroll_features():
    return render_template("payroll_auth/features.html")