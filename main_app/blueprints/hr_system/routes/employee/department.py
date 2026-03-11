from flask import render_template, request
from flask_login import login_required, current_user
from main_app.helpers.decorators import employee_required
from main_app.models.hr_models import Employee
from main_app.blueprints.hr_system.routes.employee import hr_employee_bp

@hr_employee_bp.route('/my-department')
@login_required
@employee_required
def my_department():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    # ---------------- Get the Employee instance ----------------
    employee_profile = Employee.query.filter_by(user_id=current_user.id).first()

    if not employee_profile or not employee_profile.department:
        return render_template(
            "hr/employee/org_chart.html",
            department=None,
            coworkers=None
        )

    department = employee_profile.department

    # ---------------- Department Employees ----------------
    query = Employee.query.filter(
        Employee.department_id == department.id,
        Employee.status == "Active"
    )

    if search:
        query = query.filter(
            Employee.first_name.contains(search) | Employee.last_name.contains(search)
        )

    coworkers = query.order_by(Employee.last_name.asc()).paginate(
        page=page,
        per_page=8,
        error_out=False
    )

    return render_template(
        "hr/employee/org_chart.html",
        department=department,
        coworkers=coworkers,
        current_user_employee=employee_profile
    )