from flask import Blueprint


employee_bp = Blueprint(
    "employee_bp",
    __name__,
    template_folder="templates"
)

from . import views  
from . import attendance
from . import leaves
from . import leave_credit
from . import department
from . import job_history
from . import profile
from . import payslip