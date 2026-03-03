from flask import Blueprint


payroll_auth_bp = Blueprint(
    "payroll_auth_bp",
    __name__,
    template_folder="teamplates"
)