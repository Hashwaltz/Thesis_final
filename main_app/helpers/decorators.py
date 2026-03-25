from functools import wraps
from flask import jsonify, abort, redirect, url_for, flash
from flask_login import current_user


# =========================================================
# ROLE REDIRECT HELPER
# =========================================================
def redirect_by_role(role: str):
    role = role.lower() if role else ""
    if role in ["payroll_admin"]:
        return redirect(url_for("payroll_admin_bp.payroll_dashboard"))
    elif role in ["payroll_staff"]:
        return redirect(url_for("payroll_staff_bp.staff_dashboard"))
    elif role in ["employee", "officer", "dept_head", "hr_admin", "leave_officer"]:
        return redirect(url_for("payroll_auth_bp.logout"))
    flash("Role not recognized.", "danger")
    return redirect(url_for("payroll_auth_bp.login"))


# ------------------------
# Role-based decorators
# ------------------------


def admin_required(f):
    """Decorator to require HR Admin/Admin role safely"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("hr_auth_bp.login"))

        # safe access: works even if role is None
        role = getattr(current_user, "role", "").lower()
        if role not in ["hr_admin", "admin"]:
            flash("Admin access required.", "error")
            return redirect(url_for("hr_auth_bp.login"))

        return f(*args, **kwargs)

    return decorated_function


def hr_officer_required(f):
    """Decorator to require HR officer role or higher"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("hr_auth_bp.login"))

        role = getattr(current_user, "role", "").lower()
        if role not in ['hr_admin', 'officer']:
            flash("HR Officer access required.", "error")
            return redirect(url_for("hr_auth_bp.login"))

        return f(*args, **kwargs)
    return decorated_function




def leave_officer_required(f):
    """Decorator to require HR officer or leave officer role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("hr_auth_bp.login"))

        role = getattr(current_user, "role", "").lower()
        if role not in ['hr_admin', 'officer', 'leave_officer']:
            flash("Leave Officer access required.", "error")
            return redirect(url_for("hr_auth_bp.login"))

        return f(*args, **kwargs)
    return decorated_function


def dept_head_required(f):
    """Decorator to require department head role or higher"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("hr_auth_bp.login"))

        role = getattr(current_user, "role", "").lower()
        if role not in ['hr_admin', 'officer', 'leave_officer', 'dept_head']:
            flash("Department Head access required.", "error")
            return redirect(url_for("hr_auth_bp.login"))

        return f(*args, **kwargs)
    return decorated_function


def employee_required(f):
    """Decorator to require employee or staff role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("employee_auth_bp.login"))

        role = getattr(current_user, "role", "").lower()
        if role not in ['hr_admin', 'officer', 'leave_officer', 'dept_head', 'employee', 'payroll_staff', 'payroll_admin']:
            flash("Employee access required.", "error")
            return redirect(url_for("employee_auth_bp.login"))

        return f(*args, **kwargs)
    return decorated_function


def payroll_admin_required(f):
    """Decorator to require payroll admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("payroll_auth_bp.login"))

        role = getattr(current_user, "role", "").lower()
        if role != 'payroll_admin':
            flash("Admin access required.", "error")
            return redirect(url_for("payroll_auth_bp.login"))

        return f(*args, **kwargs)
    return decorated_function



def staff_required(f):
    """Require payroll staff or admin role safely"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in.", "warning")
            return redirect(url_for("payroll_auth_bp.login"))

        role = getattr(current_user, "role", "").lower()
        if role not in ["payroll_staff", "payroll_admin"]:
            flash("Staff access required.", "danger")
            return redirect(url_for("payroll_auth_bp.login"))

        return f(*args, **kwargs)
    return decorated_function













