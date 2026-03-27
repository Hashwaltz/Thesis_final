from flask import render_template, send_file, abort
from flask_login import login_required, current_user

from main_app.helpers.decorators import employee_required
from main_app.models.payroll_models import Payroll, Payslip
from main_app.helpers.docs import generate_payslip_excel

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
@login_required
@employee_required
def view_payslip(id):
    payroll = Payroll.query.get_or_404(id)

    if payroll.employee_id != current_user.employee_profile.id:
        abort(403)

    return render_template("employee/payslip.html", payroll=payroll)

@employee_bp.route("/my-payslip/download/<int:id>")
@login_required
@employee_required
def download_my_payslip(id):

    payroll = Payroll.query.get_or_404(id)

    if payroll.employee_id != current_user.employee_profile.id:
        abort(403)
    payslip = payroll.payslip

    if not payslip:
        # Temporary object (not saved)
        class TempPayslip:
            employee = Payroll.employee
            payroll = Payroll

        payslip = TempPayslip()

    file_stream = generate_payslip_excel(payslip)

    filename = f"Payslip_{payroll.employee.last_name}_{payroll.id}.xlsx"

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )