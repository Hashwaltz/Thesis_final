from flask import  render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from main_app.models.hr_models import Employee, Attendance
from main_app.models.payroll_models import Payslip, Payroll, PayrollPeriod
from main_app.helpers.decorators import payroll_employee_required
from main_app.blueprints.payroll_system.routes.employee import payroll_employee_bp



@payroll_employee_bp.route("/payroll-emp-dashboard")
@login_required
@payroll_employee_required
def payroll_emp_dashboard():
# Get current logged-in employee
    employee = Employee.query.filter_by(user_id=current_user.id).first()

    if not employee:
        return redirect(url_for("payroll_auth_bp.logout"))
        

    # Get latest payroll period
    latest_period = PayrollPeriod.query.order_by(PayrollPeriod.pay_date.desc()).first()

    # Payroll for this employee in the latest period
    payroll = Payroll.query.filter_by(employee_id=employee.id, payroll_period_id=latest_period.id if latest_period else None).first()

    total_gross = payroll.gross_pay if payroll else 0
    total_deductions = payroll.total_deductions if payroll else 0
    net_pay = payroll.net_pay if payroll else 0
    last_pay_period = f"{latest_period.start_date.strftime('%b %d, %Y')} - {latest_period.end_date.strftime('%b %d, %Y')}" if latest_period else "N/A"
    pay_date = latest_period.pay_date.strftime('%b %d, %Y') if latest_period else "N/A"

    return render_template(
        "payroll/employee/employee_dashboard.html",
        total_gross=total_gross,
        total_deductions=total_deductions,
        net_pay=net_pay,
        last_pay_period=last_pay_period,
        pay_date=pay_date,
        employee=employee
    )



@payroll_employee_bp.route("/payroll-history")
@login_required
@payroll_employee_required
def payroll_history():
    # Get employee profile
    employee = Employee.query.filter_by(user_id=current_user.id).first()
    if not employee:
        return "Employee profile not found.", 404

    # Get all payrolls for this employee (latest first)
    payrolls = Payroll.query.filter_by(employee_id=employee.id).order_by(Payroll.payroll_period_id.desc()).all()

    return render_template(
        "payroll/employee/employee_history.html",
        payrolls=payrolls
    )



# View payslip (HTML / PDF preview)
@payroll_employee_bp.route("/payroll/<int:payroll_id>/view")
@login_required
@payroll_employee_required
def view_payslip(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)
    if payroll.employee.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("payroll_employee_bp.payroll_emp_dashboard"))

    return render_template("payroll/employee/employee_payslips.html", payroll=payroll)


# Download payslip (PDF)
@payroll_employee_bp.route("/payroll/<int:payroll_id>/download")
@login_required
@payroll_employee_required
def download_payslip(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)
    if payroll.employee.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("payroll_employee_bp.payroll_emp_dashboard"))

    # TODO: Generate PDF file and return as attachment
    return f"Download payslip for Payroll ID: {payroll.id}"