from flask import render_template, request
from flask_login import login_required, current_user

from main_app.models.hr_models import Employee, Department
from main_app.blueprints.employee_system.routes.employee import employee_bp

from main_app.helpers.decorators import employee_required

# ===========================
# Employee: My Department / Coworkers
# ===========================
@employee_bp.route("/my-department")
@login_required
@employee_required
def my_department():
    employee = Employee.query.filter_by(user_id=current_user.id).first_or_404()
    department = employee.department

    # Leadership
    mayors = Employee.query.filter(
        Employee.position.has(name="Mayor"),
        Employee.status == "Active"
    ).all()

    vice_mayors = Employee.query.filter(
        Employee.position.has(name="Vice Mayor"),
        Employee.status == "Active"
    ).all()

    municipal_admins = Employee.query.filter(
        Employee.position.has(name="Municipal Administrator"),
        Employee.status == "Active"
    ).all()

    councilors = Employee.query.filter(
        Employee.position.has(name="Councilor"),
        Employee.status == "Active"
    ).all()

    # Coworkers in same department
    page = request.args.get("page", 1, type=int)

    coworkers = Employee.query.filter(
        Employee.department_id == employee.department_id,
        Employee.status == "Active",
        Employee.id != employee.id
    ).order_by(Employee.last_name.asc()).paginate(
        page=page,
        per_page=8,
        error_out=False
    )

    return render_template(
        "employee/org_chart.html",
        employee=employee,
        department=department,
        coworkers=coworkers,
        mayors=mayors,
        vice_mayors=vice_mayors,
        municipal_admins=municipal_admins,
        councilors=councilors
    )