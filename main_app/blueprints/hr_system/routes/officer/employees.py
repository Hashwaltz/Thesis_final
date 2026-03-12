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





@hr_officer_bp.route("/employee/<int:employee_id>/view")
@login_required
@hr_officer_required
def view_employee(employee_id):
    
    employee = Employee.query.get_or_404(employee_id)

    # ===============================
    # DATE FILTERS
    # ===============================
    today = date.today()

    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    start_date = (
        datetime.strptime(start_date_str, "%Y-%m-%d").date()
        if start_date_str else date(today.year, 1, 1)
    )

    end_date = (
        datetime.strptime(end_date_str, "%Y-%m-%d").date()
        if end_date_str else today
    )

    # ===============================
    # LEAVE POLICY
    # ===============================
    BASE_VACATION = 15
    BASE_SICK = 15

    # Earned leave: 1 per month
    months = max(
        (end_date.year - start_date.year) * 12 +
        (end_date.month - start_date.month) + 1,
        0
    )

    earned_vac = months
    earned_sick = months

    # ===============================
    # USED LEAVES
    # ===============================
    used_vac = sum(
        l.days_requested for l in employee.leaves
        if l.status == "Approved"
        and l.leave_type.name.lower() == "vacation"
        and start_date <= l.start_date <= end_date
    )

    used_sick = sum(
        l.days_requested for l in employee.leaves
        if l.status == "Approved"
        and l.leave_type.name.lower() == "sick"
        and start_date <= l.start_date <= end_date
    )

    # ===============================
    # TOTALS
    # ===============================
    total_vac = BASE_VACATION + earned_vac
    total_sick = BASE_SICK + earned_sick

    balance_vac = max(total_vac - used_vac, 0)
    balance_sick = max(total_sick - used_sick, 0)

    # ===============================
    # TABLE DATA
    # ===============================
    leave_table = [
        {
            "particulars": "Balance Forwarded",
            "vacation": BASE_VACATION,
            "sick": BASE_SICK,
            "total": BASE_VACATION + BASE_SICK
        },
        {
            "particulars": "Leave Credits Earned for the Period",
            "vacation": earned_vac,
            "sick": earned_sick,
            "total": earned_vac + earned_sick,
            "type": "earned"
        },
        {
            "particulars": "Total",
            "vacation": total_vac,
            "sick": total_sick,
            "total": total_vac + total_sick
        },
        {
            "particulars": "Less: Leaves Enjoyed",
            "vacation": used_vac,
            "sick": used_sick,
            "total": used_vac + used_sick
        },
        {
            "particulars": "Balance Leave Credits",
            "vacation": balance_vac,
            "sick": balance_sick,
            "total": balance_vac + balance_sick,
            "type": "balance"
        },
    ]

    return render_template(
        "hr/officer/employee/employee.html",
        employee=employee,
        leave_table=leave_table,
        start_date=start_date,
        end_date=end_date,
        today=today,
        datetime=datetime
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

