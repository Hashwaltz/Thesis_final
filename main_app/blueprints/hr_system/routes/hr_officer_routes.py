from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    jsonify,
    session,
)
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta, time
from main_app.models.user import User
from main_app.models.hr_models import Employee, Attendance, Leave, Department, Position, LateComputation
from main_app.forms import EmployeeForm, AttendanceForm, LeaveForm
from main_app.utils import hr_officer_required, get_attendance_summary, get_current_month_range
from main_app.extensions import db
from sqlalchemy.orm import joinedload
import os
from sqlalchemy import func
from werkzeug.utils import secure_filename
import pandas as pd
import uuid
import calendar
from calendar import monthrange


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

hr_officer_bp = Blueprint(
    "officer",
    __name__,
    template_folder=TEMPLATE_DIR,
    static_url_path="/hr/static",
)


# --- OFFICER DASHBOARD ---
@hr_officer_bp.route("/dashboard")
@login_required
@hr_officer_required
def hr_dashboard():
    today = datetime.now().date()
    current_month_year = datetime.now().strftime("%B %Y")
    # --- Info Box Data (Today's Data) ---
    today_attendance_records = Attendance.query.filter_by(date=today).all()
    present_count_today = len(
        [r for r in today_attendance_records if r.status == "Present"]
    )
    absent_count_today = len(
        [r for r in today_attendance_records if r.status == "Absent"]
    )

    total_active_employees = Employee.query.filter_by(status="Active").count() or 0

    # --- Graph Data (Current Month Data) ---
    start_date, end_date = get_current_month_range()

    monthly_dates = []
    monthly_present_counts = []
    monthly_absent_counts = []
    monthly_late_counts = []

    current_date = start_date
    while current_date <= end_date:
        records_on_date = Attendance.query.filter_by(date=current_date).all()
        monthly_dates.append(current_date.strftime("%b %d"))  # e.g. Sep 01
        monthly_present_counts.append(
            len([r for r in records_on_date if r.status == "Present"])
        )
        monthly_absent_counts.append(
            len([r for r in records_on_date if r.status == "Absent"])
        )
        monthly_late_counts.append(
            len([r for r in records_on_date if r.status == "Late"])
        )
        current_date += timedelta(days=1)

    # --- Daily Reminders (Example) ---
    reminders = []
    # Example reminder: check for pending leave requests
    pending_leaves_count = Leave.query.filter_by(status="Pending").count()
    if pending_leaves_count > 0:
        reminders.append(
            f"You have {pending_leaves_count} pending leave requests to review."
        )

    return render_template(
        "hr/officer/officer_dashboard.html",
        present_count=present_count_today,
        absent_count=absent_count_today,
        total_users=total_active_employees,
        # Data for the graph
        monthly_dates=monthly_dates,
        monthly_present_counts=monthly_present_counts,
        monthly_absent_counts=monthly_absent_counts,
        monthly_late_counts=monthly_late_counts,
        reminders=reminders,
        current_month_year=current_month_year,
    )


@hr_officer_bp.route("/employees")
@login_required
@hr_officer_required
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

    # ✅ Sort employees in ascending order by last name, then first name
    query = query.order_by(Employee.last_name.asc(), Employee.first_name.asc())

    # Pagination
    employees = query.paginate(page=page, per_page=10, error_out=False)

    # Fetch all departments for dropdown
    departments = Department.query.all()

    return render_template(
        "hr/officer/officer_view_emp.html",
        employees=employees,
        search=search,
        selected_department=department,
        departments=departments,
    )



@hr_officer_bp.route("/employee/<int:employee_id>/view")
@login_required
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
        "hr/officer/officer_employee.html",
        employee=employee,
        leave_table=leave_table,
        start_date=start_date,
        end_date=end_date,
        today=today,
        datetime=datetime
    )


# ==========================
# HR Officer - Edit Employee (Limited Permissions)
# ==========================
@hr_officer_bp.route("/employees/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
@hr_officer_required
def edit_employee(employee_id):
    """HR Officer can edit limited employee info"""
    employee = Employee.query.get_or_404(employee_id)
    departments = Department.query.all()
    positions = Position.query.all()

    if request.method == "POST":
        try:
            # ✅ Update editable fields
            employee.phone = request.form.get("phone")
            employee.address = request.form.get("address")
            employee.marital_status = request.form.get("marital_status")
            employee.emergency_contact = request.form.get("emergency_contact")
            employee.emergency_phone = request.form.get("emergency_phone")

            employee.updated_at = datetime.utcnow()
            db.session.commit()

            # ✅ Return SweetAlert-friendly JSON response
            return jsonify(
                {
                    "status": "success",
                    "message": "Employee contact details updated successfully!",
                }
            )

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating employee {employee_id}: {e}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Error updating employee. Please try again.",
                    }
                ),
                500,
            )

    return render_template(
        "hr/officer/officer_edit.html",
        employee=employee,
        departments=departments,
        positions=positions,
    )


@hr_officer_bp.route("/attendance")
@login_required
@hr_officer_required
def attendance():
    page = request.args.get("page", 1, type=int)
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    employee_filter = request.args.get("employee", "")
    department_filter = request.args.get("department", "")

    query = Attendance.query.options(
        joinedload(Attendance.employee).joinedload(Employee.department)
    )

    # --- Apply Filters ---
    # Filter by Date Range
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(Attendance.date.between(start, end))
        except ValueError:
            flash("Invalid date format.", "danger")

    # Filter by Employee
    if employee_filter:
        query = query.filter(Attendance.employee_id == employee_filter)

    # Filter by Department
    if department_filter:
        query = query.join(Employee).filter(Employee.department_id == department_filter)

    attendances = query.order_by(
        Attendance.date.desc(), Attendance.time_in.desc()
    ).paginate(page=page, per_page=10, error_out=False)

    employees = (
        Employee.query.filter_by(status='Active').order_by(Employee.first_name).all()
    )
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "hr/officer/officer_view_attend.html",
        attendances=attendances,
        employees=employees,
        departments=departments,
        start_date=start_date,
        end_date=end_date,
        employee_filter=employee_filter,
        department_filter=department_filter,
    )


# ----------------- CONFIG -----------------
ALLOWED_EXTENSIONS = {"xls", "xlsx"}
UPLOAD_FOLDER = "uploads/attendance"


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ----------------- UPLOAD & PREVIEW -----------------
@hr_officer_bp.route("/add_attendance", methods=["GET", "POST"])
@login_required
@hr_officer_required
def add_attendance():
    preview_data = []

    if request.method == "POST" and "file" in request.files:
        file = request.files.get("file")
        if not file or not allowed_file(file.filename):
            flash("Please upload a valid Excel file (.xls or .xlsx).", "danger")
            return redirect(request.url)

        # Save uploaded file
        filename = secure_filename(file.filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filepath = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}_{filename}")
        file.save(filepath)

        try:
            df = pd.read_excel(filepath, header=None)
            records = []
            current_id, current_name, current_dept = None, None, None
            attendance_date = None

            for _, row in df.iterrows():
                line = " ".join(str(x) for x in row if str(x) != "nan").strip()
                if not line or "tabling date" in line.lower():
                    continue

                # Extract attendance date
                if "Attendance date:" in line:
                    attendance_date = line.split(":")[-1].strip()
                    continue

                # Extract employee info
                if "User ID" in line and "Name" in line:
                    uid_part = line.split("User ID:")[-1]
                    name_part = uid_part.split("Name:")
                    id_value = name_part[0].strip() if len(name_part) > 0 else None

                    if len(name_part) > 1:
                        name_dept_part = name_part[1].split("Department:")
                        name = name_dept_part[0].strip()
                        dept = (
                            name_dept_part[1].strip()
                            if len(name_dept_part) > 1
                            else "Unknown"
                        )
                    else:
                        name, dept = "Unknown", "Unknown"

                    current_id, current_name, current_dept = id_value, name, dept
                    continue

                # Extract times
                if ":" in line:
                    times = line.split()
                    time_in = times[0] if len(times) > 0 else None
                    time_out = times[1] if len(times) > 1 else None
                    day_value = attendance_date or datetime.now().date().isoformat()

                    # Check DB for employee
                    emp_match = None
                    try:
                        emp_id_int = int(float(current_id))
                        emp_match = Employee.query.get(emp_id_int)
                    except:
                        emp_match = None

                    # If matched, use DB name, else leave as Excel
                    record_name = (
                        emp_match.get_full_name()
                        if emp_match
                        else current_name or "Unknown"
                    )
                    matched = True if emp_match else False

                    records.append(
                        {
                            "Employee ID": current_id,
                            "Name": record_name,
                            "Department": (
                                getattr(emp_match.department, "name", "N/A")
                                if emp_match
                                else "Unknown"
                            ),
                            "Day": day_value,
                            "Time In": time_in if matched else None,
                            "Time Out": time_out if matched else None,
                            "Matched": matched,
                        }
                    )

            # Include unmatched active employees from DB not in Excel
            db_employees = Employee.query.filter_by(active=True).all()
            excel_ids = {int(float(r["Employee ID"])) for r in records if r["Matched"]}

            for emp in db_employees:
                if emp.id not in excel_ids:
                    # Mark absent
                    records.append(
                        {
                            "Employee ID": emp.id,
                            "Name": emp.get_full_name(),
                            "Department": (
                                getattr(emp.department, "name", "N/A")
                                if emp.department
                                else "N/A"
                            ),
                            "Day": attendance_date or datetime.now().date().isoformat(),
                            "Time In": None,
                            "Time Out": None,
                            "Matched": False,
                        }
                    )

            if not records:
                flash(
                    "No valid attendance records found. Please check the Excel format.",
                    "danger",
                )
                return redirect(request.url)

            session["import_attendance_preview"] = records
            preview_data = records
            flash("Preview loaded. Please confirm import.", "info")

        except Exception as e:
            flash(f"Error reading Excel file: {e}", "danger")
            return redirect(request.url)

    return render_template(
        "hr/officer/officer_import_attendance.html", preview=preview_data
    )


# ----------------- CONFIRM IMPORT -----------------
@hr_officer_bp.route("/add_attendance/confirm", methods=["POST"])
@login_required
def confirm_import_attendance():
    import os

    records = session.get("import_attendance_preview", [])
    if not records:
        flash("No attendance records to import.", "danger")
        return redirect(url_for("officer.add_attendance"))

    imported_count = 0

    for row in records:
        emp_id = row.get("Employee ID")
        try:
            emp_id_int = int(float(emp_id))
        except:
            continue

        emp = Employee.query.get(emp_id_int)
        if not emp:
            continue

        day = row.get("Day")
        if not day or "Tabling" in str(day):
            continue

        # Convert day string to date
        try:
            date_list = []
            if "~" in day:
                start_str, end_str = day.split("~")
                start_date = pd.to_datetime(start_str.strip(), errors="coerce").date()
                end_date = pd.to_datetime(end_str.strip(), errors="coerce").date()
                if start_date and end_date:
                    date_list = [
                        start_date + timedelta(days=i)
                        for i in range((end_date - start_date).days + 1)
                    ]
            else:
                single_date = pd.to_datetime(day.strip(), errors="coerce").date()
                if single_date:
                    date_list = [single_date]
        except:
            continue

        time_in = row.get("Time In")
        time_out = row.get("Time Out")

        for att_date in date_list:
            # ✅ Skip if already exists
            existing = Attendance.query.filter_by(
                employee_id=emp.id, date=att_date
            ).first()
            if existing:
                continue

            time_in_obj = (
                pd.to_datetime(time_in, errors="coerce").time() if time_in else None
            )
            time_out_obj = (
                pd.to_datetime(time_out, errors="coerce").time() if time_out else None
            )

            new_att = Attendance(
                employee_id=emp.id,
                date=att_date,
                time_in=time_in_obj,
                time_out=time_out_obj,
                status="Present" if time_in_obj else "Absent",
                remarks="",
            )
            db.session.add(new_att)
            imported_count += 1

    db.session.commit()
    session.pop("import_attendance_preview", None)

    # ✅ Cleanup uploaded files
    try:
        if os.path.exists(UPLOAD_FOLDER):
            for f in os.listdir(UPLOAD_FOLDER):
                os.remove(os.path.join(UPLOAD_FOLDER, f))
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

    flash(f"✅ Successfully imported {imported_count} attendance record(s).", "success")
    return redirect(url_for("officer.add_attendance"))


# ------------------------- Leaves -------------------------
@hr_officer_bp.route("/leaves")
@login_required
@hr_officer_required
def view_leaves():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")

    query = Leave.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    leaves = query.order_by(Leave.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template(
        "hr/officer/officer_view_leaves.html",
        leaves=leaves,
        status_filter=status_filter,
    )




@hr_officer_bp.route('/late_computation')
@login_required
def late_computation():
    # ✅ DEFAULT = CURRENT MONTH
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    months = list(enumerate(calendar.month_name))[1:]

    days_in_month = monthrange(year, month)[1]

    employees = Employee.query.order_by(Employee.last_name).all()
    data = []

    for emp in employees:
        row = {
            "employee": emp,
            "days": {},
            "total_late_minutes": 0,
            "total_undertime_minutes": 0,
        }

        for d in range(1, days_in_month + 1):
            current_date = date(year, month, d)

            att = Attendance.query.filter_by(
                employee_id=emp.id,
                date=current_date
            ).first()

            if not att:
                continue

            # LATE
            late_minutes = 0
            if att.time_in and att.time_in > time(8, 0):
                late_minutes = int(
                    (datetime.combine(current_date, att.time_in) -
                     datetime.combine(current_date, time(8, 0))
                    ).total_seconds() / 60
                )

            # UNDERTIME
            undertime_minutes = 0
            if att.time_out and att.time_out < time(17, 0):
                undertime_minutes = int(
                    (datetime.combine(current_date, time(17, 0)) -
                     datetime.combine(current_date, att.time_out)
                    ).total_seconds() / 60
                )

            row["days"][d] = {
                "time_in": att.time_in.strftime("%I:%M %p") if att.time_in else "",
                "late": late_minutes,
                "time_out": att.time_out.strftime("%I:%M %p") if att.time_out else "",
                "undertime": undertime_minutes
            }

            row["total_late_minutes"] += late_minutes
            row["total_undertime_minutes"] += undertime_minutes

        data.append(row)

    return render_template(
        "hr/officer/late_computation.html",
        data=data,
        year=year,
        month=month,
        days_in_month=days_in_month,
        months=months,
        datetime=datetime
    )   



# ----------------- OFFICER EDIT PASSWORD ROUTE -----------------
@hr_officer_bp.route("/edit_password", methods=["GET", "POST"])
@login_required
@hr_officer_required
def edit_password():
    if request.method == "POST":
        new_password = request.form.get("password", "").strip()
        if not new_password:
            flash("⚠️ Password cannot be empty.", "warning")
            return redirect(url_for("officer.edit_password"))

        # Update password directly (or hash it if your User model supports it)
        current_user.password = new_password
        try:
            db.session.commit()
            flash("✅ Password successfully updated.", "success")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating officer password: {e}")
            flash("❌ Error updating password. Please try again.", "danger")

        return redirect(url_for("officer.edit_password"))

    # GET request → show the form
    return render_template("hr/officer/officer_edit_profile.html", user=current_user)





    """
    Compute earned leave credits for an employee based on annual entitlement.
    Using 15 vacation + 15 sick per year entitlement (government rules).

    Returns a dict: {
        'vacation': { 'earned': x, 'used': y, 'remaining': z },
        'sick':     { 'earned': x, 'used': y, 'remaining': z }
    }
    """

    # Annual entitlement
    ANNUAL_VACATION = 15.0
    ANNUAL_SICK = 15.0

    # Days since hire
    if not employee.date_hired:
        return None

    today = date.today()
    hire_date = employee.date_hired
    
    # Total days worked (approx)
    total_days = (today - hire_date).days
    if total_days < 0:
        total_days = 0

    # Compute year fraction worked
    years_worked = total_days / 365.0

    # Earned credits
    earned_vacation = round(ANNUAL_VACATION * years_worked, 2)
    earned_sick     = round(ANNUAL_SICK * years_worked, 2)

    # Find current leave credit records in DB
    vacation_record = None
    sick_record     = None
    for credit in employee.leave_credits:
        if credit.leave_type.name.lower().startswith("vacat"):
            vacation_record = credit
        if credit.leave_type.name.lower().startswith("sick"):
            sick_record = credit

    used_vacation = vacation_record.used_credits if vacation_record else 0.0
    used_sick     = sick_record.used_credits if sick_record else 0.0

    remaining_vacation = round(earned_vacation - used_vacation, 2)
    remaining_sick     = round(earned_sick - used_sick,     2)

    return {
        "vacation": {
            "earned": earned_vacation,
            "used": used_vacation,
            "remaining": remaining_vacation
        },
        "sick": {
            "earned": earned_sick,
            "used": used_sick,
            "remaining": remaining_sick
        }
    }