from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, send_file
from flask_login import login_required, current_user, login_user
from datetime import datetime, date
from main_app.models.user import User
from main_app.models.hr_models import Employee, Attendance, Leave, LeaveType
from main_app.forms import LeaveForm
from main_app.helpers.utils import get_attendance_summary, get_leave_balance, get_attendance_chart_data, generate_csform4_quadrants_pdf
from main_app.helpers.decorators import employee_required
from main_app.extensions import db
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
import os
import io
from sqlalchemy import func

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

employee_bp = Blueprint(
    'employee',
    __name__,
    template_folder=TEMPLATE_DIR,
    static_url_path='/hr/static'
    )










# ---------------- VIEW LEAVE ----------------
@employee_bp.route('/leaves/<int:leave_id>')
@login_required
@employee_required
def view_leave(leave_id):
    employee = current_user.employee_profile
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('hr_auth.logout'))

    leave = Leave.query.filter_by(id=leave_id, employee_id=employee.id).first_or_404()
    return render_template('hr/employee/view_leave.html', leave=leave, employee=employee)


# ---------------- PAYSLIPS ----------------
@employee_bp.route('/payslips')
@login_required
@employee_required
def payslips():
    employee = current_user.employee_profile
    if not employee:
        flash('Employee record not found. Please contact HR.', 'error')
        return redirect(url_for('hr_auth.logout'))

    return render_template('hr/employee_payslips.html', employee=employee)


