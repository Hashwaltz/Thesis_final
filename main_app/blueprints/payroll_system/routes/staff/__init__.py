from flask import Blueprint


payroll_staff_bp = Blueprint(
    'payroll_staff_bp',
     __name__,
     template_folder='templates')


from . import views
from . import department
from . import jo
from . import regular
from . import casual
from . import parttime