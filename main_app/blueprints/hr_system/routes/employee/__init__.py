from flask import Blueprint


hr_employee_bp = Blueprint(
    'hr_employee_bp',
    __name__,
    template_folder="templates"
    )



from . import dashboard
from . import attendance
from . import leaves    