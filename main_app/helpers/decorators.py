from functools import wraps
from flask import jsonify, abort
from flask_login import current_user

# ------------------------
# Role-based decorators
# ------------------------

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'hr_admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def hr_officer_required(f):
    """Decorator to require HR officer role or higher"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['hr_admin', 'officer']:
            return jsonify({'error': 'HR Officer access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def leave_officer_required(f):
    """Decorator to require HR officer role or higher"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['hr_admin', 'officer', 'leave_officer']:
            return jsonify({'error': 'Leave Officer access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def dept_head_required(f):
    """Decorator to require department head role or higher"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['hr_admin', 'officer', 'leave_officer', 'dept_head']:
            return jsonify({'error': 'Department Head access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def employee_required(f):
    """Decorator to require employee or staff role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['employee', 'staff']:
            return jsonify({'error': 'Employee access required'}), 403
        return f(*args, **kwargs)
    return decorated_function



def payroll_admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'payroll_admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role.lower() not in ["staff", "officer", "dept_head", "admin"]:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


