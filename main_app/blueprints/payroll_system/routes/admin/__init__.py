from flask import Blueprint
import os

BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../")
)

TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

payroll_admin_bp = Blueprint(
    "payroll_admin_bp",
    __name__,
    template_folder=TEMPLATE_DIR
)

from . import casual_process
from . import history
from . import jo_process
from . import navigations
from . import part_time_process
from . import payroll_services
from . import periods_services
from . import process_payrolls
from . import regular_process