from main_app.services.docs import export_payroll_excel
from main_app.models.payroll_models import Payroll
from main_app.utils import payroll_admin_required

from flask import request
from flask_login import login_required


from . import payroll_admin_bp


@payroll_admin_bp.route('/payroll/export_excel')
@payroll_admin_required
@login_required
def export_payroll_excel_route():

    search = request.args.get('search', '')
    department_id = request.args.get('department_id')
    pay_period_id = request.args.get('pay_period_id')

    query = Payroll.query.join(Payroll.employee)

    return export_payroll_excel(query)