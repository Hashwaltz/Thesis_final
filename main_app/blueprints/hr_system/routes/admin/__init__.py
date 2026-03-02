from flask import Blueprint, render_template, redirect, url_for, flash



hr_admin_bp = Blueprint(
    'hr_admin_bp',
    __name__,
    template_folder='templates'
)



from . import attendance
from . import dashboard
from . import department
from . import employee
from . import leaves
from . import position
from . import reports
from . import users