from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, send_file
from io import BytesIO 
from collections import Counter
from docx import Document
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta


from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Position, Employee, Department, Attendance, Leave


from main_app.blueprints.hr_system.routes.admin import hr_admin_bp



# ------------------------- Reports -------------------------
@hr_admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    # Get filters from query parameters
    report_type = request.args.get('report_type', 'attendance')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    page = request.args.get('page', 1, type=int)

    # Convert dates to datetime objects if provided
    try:
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
    except ValueError:
        flash("Invalid date format", "error")
        start_date_obj = end_date_obj = None

    # Fetch data based on report type
    if report_type == 'attendance':
        query = Attendance.query
        if start_date_obj:
            query = query.filter(Attendance.date >= start_date_obj)
        if end_date_obj:
            query = query.filter(Attendance.date <= end_date_obj)
        data = query.order_by(Attendance.date.desc()).paginate(page=page, per_page=20)

        employees = Employee.query.filter_by(active=True).all()  # for filter dropdown

    elif report_type == 'leaves':
        query = Leave.query
        if start_date_obj:
            query = query.filter(Leave.start_date >= start_date_obj)
        if end_date_obj:
            query = query.filter(Leave.end_date <= end_date_obj)
        data = query.order_by(Leave.start_date.desc()).paginate(page=page, per_page=20)
        employees = Employee.query.filter_by(active=True).all()

    elif report_type == 'payroll':
        # Example payroll: just employees with salary (you can expand later)
        query = Employee.query.filter(Employee.salary != None)
        data = query.paginate(page=page, per_page=20)
        employees = None

    else:
        flash("Invalid report type", "error")
        return redirect(url_for('hr_admin.reports'))

    return render_template(
        'hr/admin/reports/reports.html',
        data=data,
        report_type=report_type,
        start_date=start_date or '',
        end_date=end_date or '',
        employees=employees if report_type in ['attendance', 'leaves'] else []
    )




@hr_admin_bp.route('/attendance-report', methods=['GET'])
@login_required
@admin_required
def attendance_report():
    # ------------------------------
    # Get filter params
    # ------------------------------
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department_id = request.args.get('department_id')

    # Default to current month
    if not start_date:
        start_date = date.today().replace(day=1)
    else:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    
    if not end_date:
        end_date = date.today()
    else:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    # ------------------------------
    # Base employee query
    # ------------------------------
    employees_query = Employee.query.filter(Employee.status == "Active")
    if department_id:
        employees_query = employees_query.filter(Employee.department_id == department_id)
    employees = employees_query.all()
    total_employees = len(employees)

    # ------------------------------
    # Collect attendance data per employee
    # ------------------------------
    report_data = []
    total_hours_worked = 0
    total_present_days = 0

    for emp in employees:
        emp_attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).all()

        days_present = sum(1 for a in emp_attendances if a.status in ["Present", "Late"])
        days_absent = sum(1 for a in emp_attendances if a.status == "Absent")
        late_count = sum(1 for a in emp_attendances if a.status == "Late")
        hours_worked = sum(a.working_hours for a in emp_attendances)

        total_hours_worked += hours_worked
        total_present_days += days_present

        report_data.append({
            "employee_name": emp.get_full_name(),
            "department_name": emp.department.name if emp.department else "",
            "days_present": days_present,
            "days_absent": days_absent,
            "late_count": late_count,
            "total_hours": round(hours_worked, 2)
        })

    # ------------------------------
    # Average attendance rate
    # ------------------------------
    avg_attendance_rate = (
        round((total_present_days / (total_employees * ((end_date - start_date).days + 1))) * 100, 2)
        if total_employees > 0 else 0
    )

    # ------------------------------
    # Department summary
    # ------------------------------
    department_summary = []
    departments = Department.query.all()
    for dept in departments:
        dept_emps = [e for e in employees if e.department_id == dept.id]
        if not dept_emps:
            continue

        dept_attendance_days = 0
        dept_total_hours = 0
        for emp in dept_emps:
            emp_att = [a for a in report_data if a["employee_name"] == emp.get_full_name()]
            if emp_att:
                dept_attendance_days += emp_att[0]["days_present"]
                dept_total_hours += emp_att[0]["total_hours"]
        
        num_days = ((end_date - start_date).days + 1) * len(dept_emps)
        avg_att = round((dept_attendance_days / num_days) * 100, 2) if num_days > 0 else 0
        avg_hours = round(dept_total_hours / len(dept_emps), 2) if dept_emps else 0

        department_summary.append({
            "name": dept.name,
            "avg_attendance": avg_att,
            "avg_hours": avg_hours
        })

    # ------------------------------
    # Render template
    # ------------------------------
    return render_template(
        "hr/admin/reports/attendance_reports.html",
        report_data=report_data,
        department_summary=department_summary,
        total_employees=total_employees,
        total_hours_worked=round(total_hours_worked, 2),
        avg_attendance_rate=avg_attendance_rate,
        start_date=start_date,
        end_date=end_date,
        department_id=int(department_id) if department_id else "",
        departments=departments,
        current_date=date.today().strftime("%B %d, %Y"),
        current_user=current_user
    )




@hr_admin_bp.route('/attendance/reports/word')
@login_required
@admin_required
def attendance_report_word():
    # -----------------------------
    # Filters from GET
    # -----------------------------
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    department_id = request.args.get('department_id')

    # Default date range: last 30 days
    if start_date_str:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    else:
        start_date = date.today() - timedelta(days=30)

    if end_date_str:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    else:
        end_date = date.today()

    total_days = (end_date - start_date).days + 1

    # -----------------------------
    # Fetch employees (optional filter by department)
    # -----------------------------
    employees = Employee.query.filter(Employee.archived == False)
    if department_id:
        employees = employees.filter(Employee.department_id == department_id)
    employees = employees.all()

    # -----------------------------
    # Create Word Document
    # -----------------------------
    doc = Document()

    # Header
    header = doc.add_paragraph()
    header.alignment = 1  # center
    header.add_run("MUNICIPALITY OF NORZAGARAY\n").bold = True
    header.add_run("Attendance Report\n").bold = True
    header.add_run(f"From {start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}\n").italic = True

    # Table header
    table = doc.add_table(rows=1, cols=5)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Employee Name"
    hdr_cells[1].text = "Department"
    hdr_cells[2].text = "Days Present"
    hdr_cells[3].text = "Days Absent"
    hdr_cells[4].text = "Total Hours Worked"

    # Attendance data
    for emp in employees:
        emp_att = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).all()

        days_present = sum(1 for a in emp_att if a.status in ["Present", "Late"])
        days_absent = sum(1 for a in emp_att if a.status == "Absent")
        total_hours = sum(a.working_hours for a in emp_att)

        row_cells = table.add_row().cells
        row_cells[0].text = emp.get_full_name()
        row_cells[1].text = emp.department.name if emp.department else "N/A"
        row_cells[2].text = str(days_present)
        row_cells[3].text = str(days_absent)
        row_cells[4].text = f"{total_hours:.2f}"

    # -----------------------------
    # Insights Section
    # -----------------------------
    doc.add_paragraph('\nOverall Insights', style='Heading 2')

    if employees:
        total_attendance_days = sum(
            sum(1 for a in Attendance.query.filter(
                Attendance.employee_id == emp.id,
                Attendance.date >= start_date,
                Attendance.date <= end_date
            ).all() if a.status in ["Present", "Late"]) for emp in employees
        )
        total_possible_days = total_days * len(employees)
        avg_attendance = round((total_attendance_days / total_possible_days) * 100, 2) if total_possible_days > 0 else 0

        total_working_hours = sum(
            sum(a.working_hours for a in Attendance.query.filter(
                Attendance.employee_id == emp.id,
                Attendance.date >= start_date,
                Attendance.date <= end_date
            ).all()) for emp in employees
        )
        avg_hours_per_employee = round(total_working_hours / len(employees), 2)

        doc.add_paragraph(f"Total Employees: {len(employees)}")
        doc.add_paragraph(f"Average Attendance: {avg_attendance}%")
        doc.add_paragraph(f"Average Hours Worked per Employee: {avg_hours_per_employee} hrs")

    # Department-wise insights
    doc.add_paragraph('\nDepartment-wise Insights', style='Heading 2')
    departments = Department.query.all()
    for dept in departments:
        dept_emps = [e for e in employees if e.department_id == dept.id]
        if not dept_emps:
            continue

        dept_attendance_days = 0
        dept_total_hours = 0

        for emp in dept_emps:
            emp_att = Attendance.query.filter(
                Attendance.employee_id == emp.id,
                Attendance.date >= start_date,
                Attendance.date <= end_date
            ).all()
            dept_attendance_days += sum(1 for a in emp_att if a.status in ["Present", "Late"])
            dept_total_hours += sum(a.working_hours for a in emp_att)

        num_days = total_days * len(dept_emps)
        avg_att = round((dept_attendance_days / num_days) * 100, 2) if num_days > 0 else 0
        avg_hours = round(dept_total_hours / len(dept_emps), 2) if dept_emps else 0

        doc.add_paragraph(f"{dept.name}: Avg Attendance: {avg_att}%, Avg Hours: {avg_hours}")

    # -----------------------------
    # Return as Word file
    # -----------------------------
    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=f"Attendance_Report_{start_date}_{end_date}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )





@hr_admin_bp.route("/hr_admin/leave_report")
@admin_required
@login_required
def leave_report():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    department_id = request.args.get('department_id')
    status_filter = request.args.get('status')

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else date.today() - timedelta(days=30)
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else date.today()

    employees = Employee.query.filter(Employee.archived == False)
    if department_id:
        employees = employees.filter(Employee.department_id == department_id)
    employees = employees.all()

    leave_data = []
    for emp in employees:
        emp_leaves = Leave.query.filter(
            Leave.employee_id == emp.id,
            Leave.start_date >= start_date,
            Leave.end_date <= end_date
        )
        if status_filter:
            emp_leaves = emp_leaves.filter(Leave.status == status_filter)
        leave_data.extend(emp_leaves.all())

    # Insights
    total_leaves = len(leave_data)
    avg_days_per_leave = round(sum(lv.days_requested for lv in leave_data)/total_leaves,2) if total_leaves else 0
    leave_types = [lv.leave_type.name for lv in leave_data if lv.leave_type]
    most_common_leave_type = Counter(leave_types).most_common(1)[0][0] if leave_types else "N/A"

    # Department-wise summary
    dept_summary = {}
    for dept in Department.query.all():
        dept_leaves = [lv for lv in leave_data if lv.employee.department_id == dept.id]
        if dept_leaves:
            dept_summary[dept.name] = {
                "total": len(dept_leaves),
                "avg_days": round(sum(lv.days_requested for lv in dept_leaves)/len(dept_leaves), 2)
            }

    return render_template(
        "hr/admin/reports/leave_reports.html",
        leave_data=leave_data,
        start_date=start_date,
        end_date=end_date,
        departments=Department.query.all(),
        department_id=int(department_id) if department_id else None,
        total_leaves=total_leaves,
        avg_days_per_leave=avg_days_per_leave,
        most_common_leave_type=most_common_leave_type,
        dept_summary=dept_summary
    )




# ------------------------------
# Leave Report Word Export
# ------------------------------
@hr_admin_bp.route("/leave-report/word")
@login_required
@admin_required
def leave_report_word():
    # --- Filter params ---
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")
    department_id = request.args.get("department_id", type=int)

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else None
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else None

    # --- Fetch leaves ---
    query = Leave.query.join(Employee).join(Department)
    if start_date:
        query = query.filter(Leave.start_date >= start_date)
    if end_date:
        query = query.filter(Leave.end_date <= end_date)
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    all_leaves = query.order_by(Leave.start_date.asc()).all()

    # --- Create Word doc ---
    doc = Document()
    doc.add_heading("Municipality of Norzagaray", 0).alignment = 1
    doc.add_paragraph(f"Leave Report ({start_date_str or 'N/A'} - {end_date_str or 'N/A'})", style="Heading 1")
    doc.add_paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}\n")

    # --- Table ---
    table = doc.add_table(rows=1, cols=7)
    hdr_cells = table.rows[0].cells
    headers = ["Employee Name", "Department", "Leave Type", "Start Date", "End Date", "Days Requested", "Status"]
    for i, h in enumerate(headers):
        hdr_cells[i].text = h

    for leave in all_leaves:
        row_cells = table.add_row().cells
        row_cells[0].text = leave.employee.get_full_name()
        row_cells[1].text = leave.employee.department.name if leave.employee.department else ""
        row_cells[2].text = leave.leave_type.name if leave.leave_type else ""
        row_cells[3].text = leave.start_date.strftime("%Y-%m-%d")
        row_cells[4].text = leave.end_date.strftime("%Y-%m-%d")
        row_cells[5].text = str(leave.days_requested)
        row_cells[6].text = leave.status

    # --- Insights ---
    doc.add_paragraph("\nInsights", style="Heading 2")
    total_leaves = len(all_leaves)
    avg_days = round(sum(lv.days_requested for lv in all_leaves)/total_leaves, 2) if total_leaves else 0
    doc.add_paragraph(f"Total leaves: {total_leaves}")
    doc.add_paragraph(f"Average leave days per record: {avg_days}")

    # --- Department-wise summary ---
    dept_summary = {}
    for dept in Department.query.all():
        dept_leaves = [lv for lv in all_leaves if lv.employee.department_id == dept.id]
        if dept_leaves:
            dept_summary[dept.name] = {
                "total": len(dept_leaves),
                "avg_days": round(sum(lv.days_requested for lv in dept_leaves) / len(dept_leaves), 2)
            }

    if dept_summary:
        doc.add_paragraph("\nDepartment-wise Summary", style="Heading 2")
        for dept, stats in dept_summary.items():
            doc.add_paragraph(f"{dept}: Total Leaves = {stats['total']}, Average Days = {stats['avg_days']}")

    # --- Send as file ---
    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    filename = f"Leave_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
