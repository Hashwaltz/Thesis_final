from datetime import date, datetime, timedelta
from flask import render_template, request
from flask_login import login_required


from main_app.models.hr_models import Employee, Leave, Department
from main_app.helpers.decorators import leave_officer_required

from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp





# ===============================
# VIEW EMPLOYEES (LEAVE OFFICER)
# ===============================
@leave_officer_bp.route("/employees")
@login_required
@leave_officer_required
def employees():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")
    department = request.args.get("department", "")

    # Base query (only active employees)
    query = Employee.query.filter_by(status="Active")

    # Search by name or employee_id
    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%"))
            | (Employee.last_name.ilike(f"%{search}%"))
            | (Employee.employee_id.ilike(f"%{search}%"))
        )

    # Filter by department if selected
    if department:
        query = query.filter_by(department_id=department)

    # Sort by last name then first name
    query = query.order_by(Employee.last_name.asc(), Employee.first_name.asc())

    # Pagination
    employees = query.paginate(page=page, per_page=10, error_out=False)

    # Fetch all departments for dropdown
    departments = Department.query.all()

    return render_template(
        "hr/leave_officer/employees.html",
        employees=employees,
        search=search,
        selected_department=department,
        departments=departments,
    )



# ===============================
# VIEW SINGLE EMPLOYEE LEAVE DETAILS
# ===============================
@leave_officer_bp.route("/employee/<int:employee_id>/view")
@login_required
@leave_officer_required
def view_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)

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

    # Leave policy constants
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

    # Used leaves
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

    # Totals
    total_vac = BASE_VACATION + earned_vac
    total_sick = BASE_SICK + earned_sick

    balance_vac = max(total_vac - used_vac, 0)
    balance_sick = max(total_sick - used_sick, 0)

    # Leave table for display
    leave_table = [
        {"particulars": "Balance Forwarded", "vacation": BASE_VACATION, "sick": BASE_SICK, "total": BASE_VACATION + BASE_SICK},
        {"particulars": "Leave Credits Earned for the Period", "vacation": earned_vac, "sick": earned_sick, "total": earned_vac + earned_sick, "type": "earned"},
        {"particulars": "Total", "vacation": total_vac, "sick": total_sick, "total": total_vac + total_sick},
        {"particulars": "Less: Leaves Enjoyed", "vacation": used_vac, "sick": used_sick, "total": used_vac + used_sick},
        {"particulars": "Balance Leave Credits", "vacation": balance_vac, "sick": balance_sick, "total": balance_vac + balance_sick, "type": "balance"},
    ]

    return render_template(
        "hr/leave_officer/employee.html",
        employee=employee,
        leave_table=leave_table,
        start_date=start_date,
        end_date=end_date,
        today=today,
        datetime=datetime
    )




# =========================
# View Leave Requests
# =========================
@leave_officer_bp.route("/leave-requests")
@login_required
@leave_officer_required
def view_leaves():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    department_filter = request.args.get("department", "")
    search = request.args.get("search", "")

    query = Leave.query.join(Employee)

    # Filter by employee name or ID
    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%")) |
            (Employee.last_name.ilike(f"%{search}%")) |
            (Employee.employee_id.ilike(f"%{search}%"))
        )

    # Filter by leave status
    if status_filter:
        query = query.filter(Leave.status == status_filter)

    # Filter by department
    if department_filter:
        query = query.filter(Employee.department_id == department_filter)

    # Sort by most recent
    query = query.order_by(Leave.created_at.desc())

    leaves = query.paginate(page=page, per_page=10, error_out=False)
    departments = Department.query.all()

    return render_template(
        "hr/leave_officer/leave_requests.html",
        leaves=leaves,
        status_filter=status_filter,
        selected_department=department_filter,
        search=search,
        departments=departments
    )


