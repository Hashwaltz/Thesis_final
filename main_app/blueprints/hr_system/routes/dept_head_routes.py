from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from datetime import datetime
from main_app.models.user import User
from main_app.models.hr_models import Employee, Attendance, Leave, Department, Position
from main_app.forms import AttendanceForm, LeaveForm
from main_app.utils import dept_head_required, get_attendance_summary, get_current_month_range,get_department_attendance_summary
from main_app.extensions import db
import csv
from io import BytesIO
from flask import send_file
import os
from openpyxl import Workbook
from types import SimpleNamespace


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

dept_head_bp = Blueprint(
    'dept_head',
    __name__,
    template_folder=TEMPLATE_DIR,
    static_url_path='/hr/static'
    )



@dept_head_bp.route('/dashboard')
@login_required
@dept_head_required
def dashboard():
    """Department Head Dashboard"""

    # Determine department
    department = None
    if current_user.department_id:
        department = Department.query.get(current_user.department_id)
    else:
        department = Department.query.filter_by(head_id=current_user.id).first()

    # Not assigned yet
    if not department:
        return render_template(
            'hr/head/head_dashboard.html',
            not_assigned=True,
            department=None,
            total_employees=0,
            recent_leaves=[],
            attendance_summary=SimpleNamespace(
                total_present=0,
                total_absent=0,
                total_late=0,
                dates=[],
                present_counts=[],
                absent_counts=[],
                late_counts=[]
            ),
            reminders=[],
            notes=[]
        )

    # Update user's department_id if missing
    if not current_user.department_id:
        current_user.department_id = department.id
        db.session.commit()

    # Employees
    department_employees = Employee.query.filter_by(department_id=department.id, status="Active").all()
    total_employees = len(department_employees)

    # Recent leaves (with employee relationship loaded)
    recent_leaves = (
        Leave.query
        .join(Employee)
        .options(db.joinedload(Leave.employee))
        .filter(Employee.department_id == department.id)
        .order_by(Leave.created_at.desc())
        .limit(5)
        .all()
    )

    # Attendance summary
    start_date, end_date = get_current_month_range()
    summary_raw = get_department_attendance_summary(department.id, start_date, end_date)

    attendance_summary = SimpleNamespace(
        total_present=summary_raw.get('total_present', 0),
        total_absent=summary_raw.get('total_absent', 0),
        total_late=summary_raw.get('total_late', 0),
        dates=[d.strftime("%Y-%m-%d") for d in summary_raw.get('dates', [])],
        present_counts=list(summary_raw.get('present_counts', [])),
        absent_counts=list(summary_raw.get('absent_counts', [])),
        late_counts=list(summary_raw.get('late_counts', []))
    )

    # Dummy reminders and notes
    reminders = ["Submit monthly report", "Approve leave requests"]
    notes = ["Team meeting on Friday", "Prepare onboarding documents"]

    return render_template(
        'hr/head/head_dashboard.html',
        not_assigned=False,
        department=department,
        total_employees=total_employees,
        recent_leaves=recent_leaves,
        attendance_summary=attendance_summary,
        reminders=reminders,
        notes=notes
    )


@dept_head_bp.route('/employee/<int:employee_id>/edit')
@login_required
@dept_head_required
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    positions = Position.query.all()
    departments = Department.query.all()


    # Ensure dept head can only access employees in their department
    if employee.department_id != current_user.department_id:
        flash("Unauthorized access", "danger")
        return redirect(url_for('dept_head.employees'))

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        # Return partial template for modal
        return render_template("head/head_edit.html", employee=employee)

    return render_template("hr/head/head_edit.html", employee=employee, positions=positions, departments=departments)

@dept_head_bp.route('/employees')
@login_required
@dept_head_required
def employees():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    # Get the department of the current department head
    department = current_user.department

    # Only employees in the same department
    query = Employee.query.filter_by(
        department=department,
        status="Active"
    )

    # Apply search if given
    if search:
        query = query.filter(
            (Employee.first_name.contains(search)) |
            (Employee.last_name.contains(search)) |
            (Employee.employee_id.contains(search))
        )

    query = query.order_by(Employee.last_name.asc(), Employee.first_name.asc())

    # Paginate results
    employees = query.paginate(page=page, per_page=10, error_out=False)

    return render_template(
        'hr/head/head_employee.html',
        employees=employees,
        search=search,
        department=department  
    )



@dept_head_bp.route('/employees/export')
@login_required
@dept_head_required
def export_employees():
    dept_id = current_user.department_id
    employees = Employee.query.filter_by(department_id=dept_id, active=True).all()

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"

    # Header row
    headers = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Department', 'Status']
    ws.append(headers)

    # Data rows
    for emp in employees:
        ws.append([
            emp.employee_id,
            emp.first_name,
            emp.last_name,
            emp.email or '',
            emp.department.name if emp.department else '',
            'Active' if emp.active else 'Inactive'
        ])

    # Adjust column widths
    for column_cells in ws.columns:
        length = max(len(str(cell.value)) if cell.value else 0 for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = length + 2

    # Save workbook to memory (not disk)
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="employees_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@dept_head_bp.route('/attendance')
@login_required
@dept_head_required
def attendance():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str).strip()
    date_filter = request.args.get('date', type=str)
    employee_filter = request.args.get('employee', type=int)

    dept_id = current_user.department_id

    # --- EMPLOYEES: same department ---
    emp_query = Employee.query.filter(
        Employee.department_id == dept_id,
        Employee.status == "Active"
    ).filter(Employee.id != current_user.id)

    if search:
        emp_query = emp_query.filter(
            (Employee.first_name.ilike(f"%{search}%")) |
            (Employee.last_name.ilike(f"%{search}%")) |
            (Employee.email.ilike(f"%{search}%"))
        )

    employees = emp_query.order_by(Employee.last_name.asc()).paginate(page=page, per_page=10, error_out=False)

    # --- ATTENDANCE RECORDS ---
    att_query = Attendance.query.join(Employee).filter(Employee.department_id == dept_id)
    if date_filter:
        att_query = att_query.filter(Attendance.date == date_filter)
    if employee_filter:
        att_query = att_query.filter(Attendance.employee_id == employee_filter)

    attendances = att_query.order_by(Attendance.date.desc()).paginate(page=page, per_page=10, error_out=False)

    # --- ABSENTEES ---
    absentees = []
    if date_filter:
        attended_ids = [att.employee_id for att in att_query.all()]
        absentees = Employee.query.filter(
            Employee.department_id == dept_id,
            Employee.status == "Active",
            ~Employee.id.in_(attended_ids)
        ).all()

    # --- LATE ARRIVALS ---
    shift_start = datetime.strptime("09:00", "%H:%M").time()
    late_arrivals = []
    if date_filter:
        late_arrivals = Attendance.query.join(Employee).filter(
            Employee.department_id == dept_id,
            Attendance.date == date_filter,
            Attendance.time_in > shift_start
        ).all()

    # --- DEPARTMENT NAME (for header) ---
    department = Department.query.get(dept_id)

    return render_template(
        'hr/head/head_attendance.html',
        employees=employees,
        attendances=attendances,
        absentees=absentees,
        late_arrivals=late_arrivals,
        search=search,
        date_filter=date_filter,
        employee_filter=employee_filter,
        department=department
    )



# --- Export Route ---
import csv
from flask import Response

@dept_head_bp.route('/attendance/export')
@login_required
@dept_head_required
def export_attendance():
    dept_id = current_user.department_id
    date_filter = request.args.get('date')

    query = Attendance.query.join(Employee).filter(Employee.department_id == dept_id)
    if date_filter:
        query = query.filter(Attendance.date == date_filter)

    records = query.all()

    def generate():
        data = [['Date', 'Employee', 'Time In', 'Time Out', 'Status']]
        for att in records:
            data.append([
                att.date.strftime('%Y-%m-%d'),
                att.employee.get_full_name(),
                att.time_in.strftime('%H:%M') if att.time_in else '',
                att.time_out.strftime('%H:%M') if att.time_out else '',
                att.status
            ])
        output = []
        for row in data:
            output.append(','.join(row))
        return '\n'.join(output)

    return Response(generate(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=attendance_report.csv"})




@dept_head_bp.route('/attendance/add', methods=['GET', 'POST'])
@login_required
@dept_head_required
def add_attendance():
    form = AttendanceForm()
    form.employee_id.choices = [
        (e.id, f"{e.employee_id} - {e.get_full_name()}")
        for e in Employee.query.filter_by(
            department=current_user.department,
            active=True
        ).all()
    ]

    if form.validate_on_submit():
        attendance = Attendance(
            employee_id=form.employee_id.data,
            date=form.date.data,
            time_in=form.time_in.data,
            time_out=form.time_out.data,
            status=form.status.data,
            remarks=form.remarks.data
        )
        try:
            db.session.add(attendance)
            db.session.commit()
            flash('Attendance recorded successfully!', 'success')
            return redirect(url_for('dept_head.attendance'))
        except Exception:
            db.session.rollback()
            flash('Error recording attendance. Please try again.', 'error')

    return render_template('add_attendance.html', form=form)


@dept_head_bp.route('/leaves')
@login_required
@dept_head_required
def leaves():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    department_employee_ids = [
        e.id for e in Employee.query.filter_by(
            department=current_user.department,
            status="Active"
        ).all()
    ]

    query = Leave.query.filter(Leave.employee_id.in_(department_employee_ids))

    if status_filter:
        query = query.filter_by(status=status_filter)

    leaves = query.order_by(Leave.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('hr/head/leaves.html', leaves=leaves, status_filter=status_filter)

@dept_head_bp.route('/leaves/<int:leave_id>/approve', methods=['POST'])
@login_required
@dept_head_required
def approve_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    employee = Employee.query.get(leave.employee_id)

    if employee.department != current_user.department:
        flash('You are not authorized to approve this leave request.', 'error')
        return redirect(url_for('dept_head.leaves'))

    status = request.form.get('status')
    comments = request.form.get('comments', '')

    leave.status = status
    leave.approved_by = current_user.id
    leave.approved_at = datetime.utcnow()
    leave.comments = comments

    try:
        db.session.commit()
        flash(f'Leave request {status.lower()} successfully!', 'success')
    except Exception:
        db.session.rollback()
        flash('Error updating leave request.', 'error')

    return redirect(url_for('dept_head.leaves'))@dept_head_bp.route('/profile', methods=['GET', 'POST'])

# ----------------- EDIT PASSWORD ROUTE FOR DEPT HEAD -----------------
@dept_head_bp.route('/edit_password', methods=['GET', 'POST'])
@login_required
@dept_head_required
def edit_password():
    if request.method == 'POST':
        new_password = request.form.get('password', '').strip()
        if not new_password:
            flash("⚠️ Password cannot be empty.", "warning")
            return redirect(url_for('dept_head.edit_password'))

        # Update password directly (no hashing)
        current_user.password = new_password
        db.session.commit()

        flash("✅ Password successfully updated.", "success")
        return redirect(url_for('dept_head.edit_password'))

    # GET request → show the form
    return render_template('hr/head/edit_profile.html')  # create this template
