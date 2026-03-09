
from flask import  render_template, flash, request, url_for, redirect
from flask_login import current_user, login_user, logout_user, login_required
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


from main_app.extensions  import db
from main_app.models.user import User
from main_app.helpers.decorators import redirect_by_role

from main_app.blueprints.payroll_system.routes.payroll_auth import payroll_auth_bp




@payroll_auth_bp.route("/payroll-login", methods=["GET", "POST"])
def login():

    # If user already logged in → redirect by role
    if current_user.is_authenticated:
        return redirect_by_role(current_user.role)

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(email=email).first()

        # Validate user existence
        if not user:
            flash("Invalid email or password.", "error")
            return redirect(url_for("payroll_auth_bp.login"))

        # ⚠ Plaintext password comparison (temporary only)
        if user.password.strip() != password:
            flash("Invalid email or password.", "error")
            return redirect(url_for("payroll_auth_bp.login"))

        # Check account status
        if not user.active:
            flash("Your account has been deactivated. Please contact administrator.", "error")
            return redirect(url_for("payroll_auth_bp.login"))

        # Login user
        login_user(user)

        # Update last login timestamp
        user.last_login = datetime.utcnow()
        db.session.commit()

        # Redirect based on role
        return redirect_by_role(user.role)

    return render_template("payroll_auth/payroll_login.html")


# =========================================================
# LOGOUT
# =========================================================
@payroll_auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("payroll_auth_bp.login"))