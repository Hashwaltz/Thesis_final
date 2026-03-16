from flask import render_template, request, jsonify, current_app
from flask_login import login_required
from datetime import datetime, date

from main_app.extensions import db
from main_app.models.hr_models import Employee, Department, Position
from main_app.helpers.decorators import hr_officer_required
from main_app.helpers.docs import export_employees_by_year_of_service 

from main_app.blueprints.hr_system.routes.officer import hr_officer_bp





@hr_officer_bp.route("/employees")
@login_required
@hr_officer_required
def employees():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")
    department = request.args.get("department", "")
    years_service = request.args.get("years_service", "")
    barangay = request.args.get("barangay", "")
    # Sort by name ascending (Explicit)
    query = Employee.query.filter_by(status="Active").order_by(Employee.last_name.asc())

    # Search by name or employee_id
    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%"))
            | (Employee.last_name.ilike(f"%{search}%"))
            | (Employee.employee_id.ilike(f"%{search}%"))
        )

    # Filter by department
    if department:
        query = query.filter_by(department_id=department)

    # Filter by years of service
    if years_service:
        today = date.today()
        min_date = date(today.year - (int(years_service) + 4), today.month, today.day)
        max_date = date(today.year - int(years_service), today.month, today.day)
        query = query.filter(Employee.date_hired.between(min_date, max_date))

    # Filter by barangay
    if barangay:
        query = query.filter(Employee.barangay.ilike(f"%{barangay}%"))

    # Sort
    query = query.order_by(Employee.last_name.asc(), Employee.first_name.asc())

    # Pagination
    employees = query.paginate(page=page, per_page=10, error_out=False)

    # Fetch all departments for dropdown
    departments = Department.query.all()

    return render_template(
        "hr/officer/employee/view_emp.html",
        employees=employees,
        search=search,
        selected_department=department,
        years_service=years_service,
        barangay=barangay,
        departments=departments
    )




# ---------------- EXPORT EMPLOYEES BY YEARS OF SERVICE ----------------
@hr_officer_bp.route("/employees/export-years-of-service")
@login_required
@hr_officer_required
def export_employees_years_of_service():
    # Get filters from query params
    search = request.args.get("search", "")
    department = request.args.get("department", "")
    years_service = request.args.get("years_service", type=int)
    barangay = request.args.get("barangay", "")

    # Base query
    query = Employee.query.filter_by(status="Active")

    # Apply search filter
    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%")) |
            (Employee.last_name.ilike(f"%{search}%")) |
            (Employee.employee_id.ilike(f"%{search}%"))
        )

    # Apply department filter
    if department:
        query = query.filter_by(department_id=department)

    # Apply barangay filter
    if barangay:
        query = query.filter(Employee.barangay.ilike(f"%{barangay}%"))

    # Apply years of service filter
    if years_service:
        today = date.today()
        # min_date: hired more than (years_service + 4) years ago
        min_date = date(today.year - (years_service + 4), today.month, today.day)
        # max_date: hired exactly years_service years ago
        max_date = date(today.year - years_service, today.month, today.day)
        query = query.filter(Employee.date_hired.between(min_date, max_date))

    return export_employees_by_year_of_service(query.all())

