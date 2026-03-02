from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user


hr_officer_bp = Blueprint(
    'hr_officer_bp',
    __name__,
    template_folder='templates'
)


from . import dashboard
from . import employees
from . import services