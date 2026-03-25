from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from main_app.models.hr_models import Employee, Attendance, LeaveCredit
from main_app.models.payroll_models import Payslip
from main_app.helpers.decorators import employee_required
from datetime import date


from main_app.blueprints.employee_system.routes.employee import employee_bp 



# =======================
# Dashboard
# =======================
@employee_bp.route("/dashboard")
@login_required
@employee_required
def dashboard():
    employee = Employee.query.filter_by(user_id=current_user.id).first()
    if not employee:
        flash("Employee not found")
        return redirect(url_for("employee_auth_bp.logout"))
    # Attendance summary for current month
    today = date.today()
    attendances = Attendance.query.filter(
        Attendance.employee_id == employee.id,
        Attendance.date.between(date(today.year, today.month, 1), date(today.year, today.month, 31))
    ).all()
    
    present_days = sum(1 for a in attendances if a.status == "Present")
    late_days = sum(1 for a in attendances if a.status == "Late")
    total_days = len(attendances)

    # Leave balances
    leave_credits = LeaveCredit.query.filter_by(employee_id=employee.id).all()
    leave_summary = {lc.leave_type.name: lc.remaining_credits() for lc in leave_credits}

    # Latest payslip
    latest_payslip = Payslip.query.filter_by(employee_id=employee.id).order_by(Payslip.generated_at.desc()).first()

    return render_template(
        "employee/dashboard.html",
        employee=employee,
        present_days=present_days,
        late_days=late_days,
        total_days=total_days,
        leave_summary=leave_summary,
        latest_payslip=latest_payslip, 
        today=date.today()
    )