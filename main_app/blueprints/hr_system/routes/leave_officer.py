from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    abort
)
from flask_login import login_required, current_user
from datetime import datetime, timedelta,   date
from main_app.models.hr_models import Employee, Leave, Department, LeaveType
from main_app.utils import leave_officer_required, get_current_month_range
import os
from main_app.extensions import db
import calendar
from sqlalchemy import func


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")



leave_officer_bp = Blueprint(
    "leave_officer",
    __name__,
    template_folder=TEMPLATE_DIR,
    static_url_path="/hr/static",
)

# =========================================================
# LEAVE OFFICER DASHBOARD
# =========================================================
@leave_officer_bp.route("/dashboard")
@login_required
@leave_officer_required
def leave_dashboard():
    today = datetime.now().date()
    current_month_year = datetime.now().strftime("%B %Y")

    # --- LEAVE COUNTS ---
    pending_leaves = Leave.query.filter_by(status="Pending").count()
    approved_leaves = Leave.query.filter_by(status="Approved").count()
    rejected_leaves = Leave.query.filter_by(status="Rejected").count()

    # --- ACTIVE EMPLOYEES ---
    total_active_employees = Employee.query.filter_by(status="Active").count() or 0

    # --- REMINDERS ---
    reminders = []
    if pending_leaves > 0:
        reminders.append(
            f"You have {pending_leaves} pending leave requests to review."
        )

    # --- GRAPH DATA (CURRENT MONTH) ---
    start_date, end_date = get_current_month_range()

    monthly_leave_labels = []
    pending_data = []
    approved_data = []
    rejected_data = []

    current_date = start_date
    while current_date <= end_date:
        monthly_leave_labels.append(current_date.strftime("%b %d"))

        pending_data.append(
            Leave.query.filter(
                Leave.created_at == current_date,
                Leave.status == "Pending"
            ).count()
        )

        approved_data.append(
            Leave.query.filter(
                Leave.created_at == current_date,
                Leave.status == "Approved"
            ).count()
        )

        rejected_data.append(
            Leave.query.filter(
                Leave.created_at == current_date,
                Leave.status == "Rejected"
            ).count()
        )

        current_date += timedelta(days=1)

    return render_template(
        "hr/leave_officer/dashboard.html",
        pending_leaves=pending_leaves,
        approved_leaves=approved_leaves,
        rejected_leaves=rejected_leaves,
        total_users=total_active_employees,
        reminders=reminders,
        current_month_year=current_month_year,

        # GRAPH DATA
        monthly_leave_labels=monthly_leave_labels,
        pending_data=pending_data,
        approved_data=approved_data,
        rejected_data=rejected_data,
    )



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



@leave_officer_bp.route('/leave_report', methods=['GET'])
def leave_report():
    # --- Get filters from request ---
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department_id = request.args.get('department_id', type=int)

    # --- Base query for leave records ---
    query = Leave.query.join(Employee).join(Employee.department).join(Leave.leave_type)

    # --- Apply filters ---
    if start_date:
        query = query.filter(Leave.start_date >= start_date)
    if end_date:
        query = query.filter(Leave.end_date <= end_date)
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    leave_data = query.order_by(Leave.start_date.desc()).all()

    # --- Compute insights ---
    total_leaves = len(leave_data)
    avg_days_per_leave = round(sum(lv.days_requested for lv in leave_data) / total_leaves, 2) if total_leaves else 0

    # Most common leave type
    most_common_leave_type = None
    if leave_data:
        leave_type_counts = db.session.query(
            Leave.leave_type_id, func.count(Leave.id)
        ).group_by(Leave.leave_type_id).all()
        if leave_type_counts:
            # Get leave_type_id with max count
            most_common_id = max(leave_type_counts, key=lambda x: x[1])[0]
            most_common_leave_type = LeaveType.query.get(most_common_id).name

    # Department-wise summary
    dept_summary = {}
    departments = Department.query.all()
    for dept in departments:
        dept_leaves = [lv for lv in leave_data if lv.employee.department_id == dept.id]
        total = len(dept_leaves)
        avg_days = round(sum(lv.days_requested for lv in dept_leaves)/total, 2) if total else 0
        dept_summary[dept.name] = {"total": total, "avg_days": avg_days}

    return render_template(
        'hr/leave_officer/leave_report.html',
        leave_data=leave_data,
        start_date=start_date,
        end_date=end_date,
        department_id=department_id,
        total_leaves=total_leaves,
        avg_days_per_leave=avg_days_per_leave,
        most_common_leave_type=most_common_leave_type,
        dept_summary=dept_summary,
        departments=departments
    )



@leave_officer_bp.route("/late-computation", methods=["GET"])
@login_required
def late_computation():
    # ----------------------------
    # FILTERS
    # ----------------------------
    month = request.args.get("month", type=int, default=datetime.now().month)
    year = request.args.get("year", type=int, default=datetime.now().year)

    days_in_month = calendar.monthrange(year, month)[1]

    # ----------------------------
    # DATA (replace with real logic)
    # ----------------------------
    employees = Employee.query.all()

    data = []
    for emp in employees:
        row = {
            "employee": emp,
            "total_late_minutes": 0,
            "total_undertime_minutes": 0,
            "days": {}
        }

        # SAMPLE empty day data (prevents template errors)
        for d in range(1, days_in_month + 1):
            row["days"][d] = {
                "time_in": "-",
                "late": "-",
                "time_out": "-",
                "undertime": "-"
            }

        data.append(row)

    # ----------------------------
    return render_template(
        "hr/leave_officer/late_computation.html",
        data=data,
        month=month,
        year=year,
        days_in_month=days_in_month,
        datetime=datetime
    )    



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


@leave_officer_bp.route("/profile", methods=["GET"])
@login_required
@leave_officer_required
def profile():
    employee = Employee.query.filter_by(user_id=current_user.id).first()

    if not employee:
        abort(404)

    # Compute age
    age = None
    if employee.date_of_birth:
        today = date.today()
        age = today.year - employee.date_of_birth.year - (
            (today.month, today.day) < (employee.date_of_birth.month, employee.date_of_birth.day)
        )

    # Working duration
    working_duration = None
    if employee.date_hired:
        working_duration = (date.today() - employee.date_hired).days // 365

    return render_template(
        "hr/leave_officer/profile.html",
        employee=employee,
        user=current_user,
        age=age,
        working_duration=working_duration
    )



@leave_officer_bp.route("/profile/edit", methods=["POST"])
@login_required
def edit_profile():
    data = request.get_json()
    current_password = data.get("current_password")
    new_email = data.get("email")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    # --- Check current password ---
    if current_password != current_user.password:
        return jsonify({"status": "error", "message": "Current password is incorrect"})

    # --- Check new password confirmation ---
    if new_password and new_password != confirm_password:
        return jsonify({"status": "error", "message": "New password and confirm password do not match"})

    # --- Update email ---
    if new_email:
        current_user.email = new_email

    # --- Update password if provided ---
    if new_password:
        current_user.password = new_password

    # --- Commit changes ---
    db.session.commit()

    return jsonify({"status": "success", "message": "Profile updated successfully"})