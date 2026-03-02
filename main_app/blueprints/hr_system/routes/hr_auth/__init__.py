import os
from flask import Blueprint


hr_auth_bp = Blueprint(
    "hr_auth_bp",
    __name__,
    template_folder="templates"
)



from . import navs
from . import login