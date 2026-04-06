from flask import Blueprint

employee_auth_bp = Blueprint(
    'employee_auth_bp',
    __name__,
    template_folder='templates')


from . import login
from . import forgot_password