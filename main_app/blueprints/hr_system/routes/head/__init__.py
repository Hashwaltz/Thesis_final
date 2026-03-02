from flask import Blueprint



hr_head_bp = Blueprint(
    'hr_head_bp',
    __name__,
    template_folder='templates'
    )



from . import dashboard
from . import attendance
from . import employee
from . import leaves