from flask import render_template, request
from flask_login import login_required, current_user

from main_app.models.hr_models import Employee, Department
from main_app.helpers.decorators import employee_required

from main_app.blueprints.employee_system.routes.employee import employee_bp

@employee_bp.route("/my-department")
@login_required
@employee_required
def my_department():
    # Get the logged-in user's employee record
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

    # Pagination
    page = request.args.get("page", 1, type=int)

    # ✅ FIXED: Removed `Employee.id != employee.id` so the current user appears in the grid
    coworkers = Employee.query.filter(
        Employee.department_id == employee.department_id,
        Employee.status == "Active"
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