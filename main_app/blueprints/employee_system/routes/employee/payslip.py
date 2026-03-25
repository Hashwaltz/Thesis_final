from flask import render_template, request
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy.orm import joinedload

from main_app.helpers.decorators import employee_required
from main_app.models.payroll_models import Payroll, LoanPayment

from main_app.blueprints.employee_system.routes.employee import employee_bp


@employee_bp.route("/my-payslips")
@login_required
@employee_required
def my_payslips():
    payrolls = Payroll.query.filter_by(
        employee_id=current_user.employee_profile.id
    ).order_by(Payroll.id.desc()).all()

    return render_template("employee/my_payslips.html", payrolls=payrolls)



@employee_bp.route("/my-payslip/<int:id>")
def view_payslip(id):
    payroll = Payroll.query.get_or_404(id)

    return render_template("employee/payslip.html", payroll=payroll)