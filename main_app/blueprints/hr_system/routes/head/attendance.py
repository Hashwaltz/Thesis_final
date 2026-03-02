
from flask import send_file,render_template, request, url_for, flash, redirect, Response
from flask_login import login_required, current_user
from types import SimpleNamespace
from io import BytesIO
from datetime import datetime

from main_app.extensions import db
from main_app.models.hr_models import Department, Employee, Attendance
from main_app.helpers.decorators import dept_head_required


from main_app.blueprints.hr_system.routes.head import hr_head_bp



@hr_head_bp.route('/attendance')
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



@hr_head_bp.route('/attendance/export')
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
