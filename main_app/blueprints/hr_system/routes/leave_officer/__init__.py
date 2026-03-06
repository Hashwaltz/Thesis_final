from flask import Blueprint


leave_officer_bp = Blueprint(
    'leave_officer_bp',
    __name__,
    template_folder='templates')



from . import attenndance
from . import dashboard
from . import employee
from . import late
from . import leave
from . import profile
from . import report