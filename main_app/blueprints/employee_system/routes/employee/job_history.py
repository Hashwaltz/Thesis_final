from flask import render_template, request
from flask_login import login_required, current_user

from main_app.models.hr_models import JobHistory, Employee

from main_app.helpers.decorators import employee_required


from main_app.blueprints.employee_system.routes.employee import employee_bp


@employee_bp.route("/job-history")
@login_required
@employee_required
def employee_job_history():

    page = request.args.get("page", 1, type=int)

    # Get logged-in employee
    employee = Employee.query.filter_by(user_id=current_user.id).first_or_404()

    job_history = JobHistory.query.filter_by(
        employee_id=employee.id
    ).order_by(
        JobHistory.effective_date.desc()
    ).paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    return render_template(
        "employee/job_history.html",
        job_history=job_history,
        employee=employee
    )