from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, date
from main_app.models.user import User
from main_app.models.hr_models import Employee, Attendance
from main_app.forms import EmployeeForm
from main_app.utils import admin_required

api_bp = Blueprint('api', __name__)


@api_bp.route("/test", methods=["GET"])
def test_api():
    return jsonify({"success": True})



@api_bp.route("/auth/login", methods=["POST"])
def api_login():
    """API login for Payroll system (no password hashing)"""
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    try:
        user = User.query.filter_by(email=email, active=True).first()

        if user and user.password == password:  # ✅ direct comparison
            return jsonify({
                "success": True,
                "user_id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role
            })
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    """Fetch a single user's details"""
    try:
        user = User.query.get_or_404(user_id)
        return jsonify({
            "success": True,
            "data": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "department_id": user.department_id,
                "position": user.position,
                "active": user.active,
                "created_at": user.created_at.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route('/employees')
@login_required
def get_employees():
    """Get all employees for API consumption"""
    try:
        employees = Employee.query.filter_by(active=True).all()
        employee_data = []

        for emp in employees:
            employee_data.append({
                'id': emp.id,
                'employee_id': emp.employee_id,
                'first_name': emp.first_name,
                'last_name': emp.last_name,
                'middle_name': emp.middle_name,
                'email': emp.email,
                'phone': emp.phone,
                'department': emp.department,
                'position': emp.position,
                'salary': emp.salary,
                'date_hired': emp.date_hired.isoformat() if emp.date_hired else None,
                'date_of_birth': emp.date_of_birth.isoformat() if emp.date_of_birth else None,
                'gender': emp.gender,
                'marital_status': emp.marital_status,
                'active': emp.active,
                'created_at': emp.created_at.isoformat(),
                'updated_at': emp.updated_at.isoformat()
            })

        return jsonify({
            'success': True,
            'data': employee_data,
            'count': len(employee_data)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# --- Keep the rest of your API routes unchanged ---
# Just ensure that all imports use relative paths:
# from ..models.user, from ..models.hr_models, from ..utils, from .. import db
