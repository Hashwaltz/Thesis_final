from flask import Blueprint


payroll_employee_bp = Blueprint(
    "payroll_employee_bp",
    __name__,
    template_folder="templates")



from . import views