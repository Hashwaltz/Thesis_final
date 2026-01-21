from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from main_app.forms import LoginForm, RegistrationForm
from main_app.extensions import db
from main_app.models.user import User  # shared model
from datetime import datetime
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))  # Thesis/
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates", "payroll_auth")


payroll_auth_bp = Blueprint(
    "payroll_auth",
    __name__,
    template_folder=TEMPLATE_DIR,
    static_url_path="/payroll/static"
)
#======================================
# INDEX → redirect to login
# =========================================================
@payroll_auth_bp.route("/")
def index():
    return redirect(url_for("payroll_auth.login"))


# =========================================================
# LOGIN
# =========================================================
@payroll_auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect_by_role(current_user.role)

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip()).first()

        if not user:
            flash('Invalid email or password.', 'error')
            return render_template('payroll_login.html', form=form)

        if check_password_hash(user.password, form.password.data) or user.password.strip() == form.password.data.strip():
            if not user.active:
                flash('Your account has been deactivated. Please contact administrator.', 'error')
                return render_template('payroll_login.html', form=form)

            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()

            return redirect_by_role(user.role)
        else:
            flash('Invalid email or password.', 'error')

    return render_template("payroll_auth/payroll_login.html", form=form)


# =========================================================
# ROLE REDIRECT HELPER
# =========================================================
def redirect_by_role(role: str):
    role = role.lower() if role else ""
    if role in ["payroll_admin"]:
        return redirect(url_for("payroll_admin.payroll_dashboard"))
    elif role in ["payroll_staff"]:
        return redirect(url_for("payroll_staff.dashboard"))
    elif role in ["employee", "officer", "dept_head"]:
        return redirect(url_for("payroll_employee.dashboard"))
    flash("Role not recognized.", "danger")
    return redirect(url_for("payroll_auth.login"))


# =========================================================
# LOGOUT
# =========================================================
@payroll_auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("payroll_auth.login"))
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
            return redirect(url_for("payroll_auth.login"))
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
        return redirect(url_for("payroll_auth.profile"))

    return render_template("change_password.html")



@payroll_auth_bp.route("/about")
def about_payroll():
    return render_template("payroll_auth/about.html")

@payroll_auth_bp.route("/features")
def payroll_features():
    return render_template("payroll_auth/features.html")