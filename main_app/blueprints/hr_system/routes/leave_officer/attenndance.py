from flask import request, render_template
from flask_login import login_required
from datetime import datetime



from main_app.extensions import db
from main_app.models.hr_models import Department, Leave, LeaveType, Employee
from main_app.helpers.decorators import leave_officer_required


from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp



@leave_officer_bp.route("/attendance")
@login_required
@leave_officer_required
def attendance():

    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    department_id = request.args.get("department_id", type=int)
    selected_date = request.args.get(
        "date",
        datetime.today().strftime("%Y-%m-%d")
    )

    selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()

    employees = Employee.query.filter_by(status="Active")

    if department_id:
        employees = employees.filter(Employee.department_id == department_id)

    records = []

    for emp in employees.all():

        # --- CHECK LEAVE ---
        leave = Leave.query.filter(
            Leave.employee_id == emp.id,
            Leave.status == "Approved",
            Leave.start_date <= selected_date_obj,
            Leave.end_date >= selected_date_obj
        ).first()

        if leave:
            record_status = "On Leave"

        else:
            # ⚠️ Replace this with real attendance logic
            attendance = getattr(emp, "attendance", None)

            if attendance and attendance.late_minutes > 0:
                record_status = "Late"
            else:
                record_status = "Absent"

        # FILTER STATUS
        if status and record_status.lower().replace(" ", "_") != status:
            continue

        records.append({
            "employee": emp,
            "department": emp.department.name if emp.department else "N/A",
            "status": record_status,
            "date": selected_date_obj
        })

    # --- MANUAL PAGINATION ---
    total = len(records)
    start = (page - 1) * 10
    end = start + 10
    paginated = records[start:end]

    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "hr/leave_officer/attendance.html",
        records=paginated,
        total=total,
        page=page,
        departments=departments,
        status=status,
        department_id=department_id,
        selected_date=selected_date
    )
