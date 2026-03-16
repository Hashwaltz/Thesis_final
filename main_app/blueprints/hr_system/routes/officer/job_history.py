from flask import request, render_template
from flask_login import login_required

from main_app.models.hr_models import JobHistory, Employee, Department
from main_app.extensions import db
from main_app.helpers.decorators import hr_officer_required

from main_app.blueprints.hr_system.routes.officer import hr_officer_bp


@hr_officer_bp.route("/JOB-HISTORY-LIST")
@login_required
@hr_officer_required
def job_history_list():

    page = request.args.get("page", 1, type=int)

    employee = request.args.get("employee")
    department = request.args.get("department")
    status = request.args.get("status")

    query = JobHistory.query

    # FILTERS
    if employee:
        query = query.join(Employee).filter(Employee.first_name.ilike(f"%{employee}%"))

    if department:
        query = query.join(JobHistory.department).filter_by(id=department)

    if status:
        query = query.filter(JobHistory.status == status)

    # PAGINATION
    job_history = query.order_by(
        JobHistory.effective_date.desc()
    ).paginate(page=page, per_page=10)

    employees = Employee.query.all()
    departments = Department.query.all()

    return render_template(
        "hr/officer/job_history_list.html",
        job_history=job_history,
        employees=employees,
        departments=departments
    )