from datetime import date, timedelta, datetime, time
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_
import os
import pandas as pd
from werkzeug.utils import secure_filename
import uuid


from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Employee, Department, Leave, Attendance, EmploymentType, Position
from main_app.models.user import User
from main_app.extensions import db
from main_app.helpers.functions import parse_date, allowed_file, ALLOWED_EXTENSIONS, UPLOAD_FOLDER

from main_app.blueprints.hr_system.routes.admin import hr_admin_bp



@hr_admin_bp.route('/attendance')
@admin_required
@login_required
def view_attendance():
    page = request.args.get('page', 1, type=int)
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    employee_filter = request.args.get('employee', '').strip()
    department_filter = request.args.get('department', '').strip()
    status_filter = request.args.get('status', '').strip()  

    # Base query
    query = Attendance.query.join(Employee).join(Employee.department)

    # Date filters
    try:
        if start_date and not end_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Attendance.date == start_date_obj)

        elif end_date and not start_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Attendance.date == end_date_obj)

        elif start_date and end_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()

            # Swap if user entered in reverse
            if end_date_obj < start_date_obj:
                start_date_obj, end_date_obj = end_date_obj, start_date_obj

            query = query.filter(
                and_(
                    Attendance.date >= start_date_obj,
                    Attendance.date <= end_date_obj
                )
            )
    except ValueError:
        pass

    # Employee and Department filters
    if employee_filter:
        query = query.filter(Attendance.employee_id == int(employee_filter))
    if department_filter:
        query = query.filter(Employee.department_id == int(department_filter))

    # ✅ Status filter
    if status_filter:
        query = query.filter(Attendance.status == status_filter)

    # Pagination
    attendances = query.order_by(Attendance.date.desc()).paginate(page=page, per_page=20, error_out=False)

    # Lists for dropdowns
    employees = Employee.query.filter_by(archived=False).all()
    departments = Department.query.order_by(Department.name.asc()).all()

    return render_template(
        'hr/admin/attendance/view_attendance.html',
        attendances=attendances,
        employees=employees,
        departments=departments,
        start_date=start_date,
        end_date=end_date,
        employee_filter=employee_filter,
        department_filter=department_filter,
        status_filter=status_filter  
    )





@hr_admin_bp.route('/add_attendance', methods=['GET', 'POST'])
@admin_required
@login_required
def add_attendance():
    preview_data = []
     
    employees = Employee.query.filter_by(status='Active').all()
    if request.method == 'POST' and 'file' in request.files:
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

                if "Attendance date:" in line:
                    attendance_date = line.split(":")[-1].strip()
                    continue

                if "User ID" in line and "Name" in line:
                    uid_part = line.split("User ID:")[-1]
                    name_part = uid_part.split("Name:")
                    id_value = name_part[0].strip() if len(name_part) > 0 else None

                    if len(name_part) > 1:
                        name_dept_part = name_part[1].split("Department:")
                        name = name_dept_part[0].strip()
                        dept = name_dept_part[1].strip() if len(name_dept_part) > 1 else "Unknown"
                    else:
                        name, dept = "Unknown", "Unknown"

                    current_id, current_name, current_dept = id_value, name, dept
                    continue

                if ":" in line:
                    times = line.split()
                    time_in = times[0] if len(times) > 0 else None
                    time_out = times[1] if len(times) > 1 else None
                    day_value = attendance_date or datetime.now().date().isoformat()

                    emp_match = None
                    try:
                        emp_id_int = int(float(current_id))
                        emp_match = Employee.query.get(emp_id_int)
                    except:
                        emp_match = None

                    record_name = emp_match.get_full_name() if emp_match else current_name or "Unknown"
                    matched = True if emp_match else False

                    records.append({
                        "Employee ID": current_id,
                        "Name": record_name,
                        "Department": getattr(emp_match.department, 'name', 'N/A') if emp_match else "Unknown",
                        "Day": day_value,
                        "Time In": time_in if matched else None,
                        "Time Out": time_out if matched else None,
                        "Matched": matched
                    })

            db_employees = Employee.query.filter_by(active=True).all()
            excel_ids = {int(float(r["Employee ID"])) for r in records if r["Matched"]}

            for emp in db_employees:
                if emp.id not in excel_ids:
                    records.append({
                        "Employee ID": emp.id,
                        "Name": emp.get_full_name(),
                        "Department": getattr(emp.department, 'name', 'N/A') if emp.department else 'N/A',
                        "Day": attendance_date or datetime.now().date().isoformat(),
                        "Time In": None,
                        "Time Out": None,
                        "Matched": False
                    })

            if not records:
                flash("No valid attendance records found. Please check the Excel format.", "danger")
                return redirect(request.url)

            # Store in session
            session['import_attendance_preview'] = records
            preview_data = records
            flash("Preview loaded. Please confirm import.", "info")

        except Exception as e:
            flash(f"Error reading Excel file: {e}", "danger")
            return redirect(request.url)

    # Load preview from session if exists
    if 'import_attendance_preview' in session and not preview_data:
        preview_data = session['import_attendance_preview']

    return render_template('hr/admin/attendance/import_attendance.html', preview=preview_data, employees=employees)





# ----------------- CONFIRM IMPORT -----------------
@hr_admin_bp.route('/add_attendance/confirm', methods=['POST'])
@admin_required
@login_required
def confirm_import_attendance():    
    import os
    records = session.get('import_attendance_preview', [])
    if not records:
        flash("No attendance records to import.", "danger")
        return redirect(url_for('hr_admin_bp.add_attendance'))

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
                start_date = pd.to_datetime(start_str.strip(), errors='coerce').date()
                end_date = pd.to_datetime(end_str.strip(), errors='coerce').date()
                if start_date and end_date:
                    date_list = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
            else:
                single_date = pd.to_datetime(day.strip(), errors='coerce').date()
                if single_date:
                    date_list = [single_date]
        except:
            continue

        time_in = row.get("Time In")
        time_out = row.get("Time Out")

        for att_date in date_list:
            # ✅ Skip if already exists
            existing = Attendance.query.filter_by(employee_id=emp.id, date=att_date).first()
            if existing:
                continue

            time_in_obj = pd.to_datetime(time_in, errors='coerce').time() if time_in else None
            time_out_obj = pd.to_datetime(time_out, errors='coerce').time() if time_out else None

            new_att = Attendance(
                employee_id=emp.id,
                date=att_date,
                time_in=time_in_obj,
                time_out=time_out_obj,
                status="Present" if time_in_obj else "Absent",
                remarks=""
            )
            db.session.add(new_att)
            imported_count += 1

    db.session.commit()
    session.pop('import_attendance_preview', None)

    # ✅ Cleanup uploaded files
    try:
        if os.path.exists(UPLOAD_FOLDER):
            for f in os.listdir(UPLOAD_FOLDER):
                os.remove(os.path.join(UPLOAD_FOLDER, f))
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

    flash(f"✅ Successfully imported {imported_count} attendance record(s).", "success")
    return redirect(url_for('hr_admin_bp.add_attendance'))




@hr_admin_bp.route('/attendance/<int:attendance_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_attendance(attendance_id):
    attendance = Attendance.query.get_or_404(attendance_id)
    
    if request.method == 'POST':
        # Get form data
        time_in_str = request.form.get('time_in')  # e.g., "08:54"
        time_out_str = request.form.get('time_out')  # e.g., "17:00"
        status = request.form.get('modal_status')
        remarks = request.form.get('remarks', '')

        # Convert strings to datetime.time objects if not empty
        if time_in_str:
            h, m = map(int, time_in_str.split(":"))
            attendance.time_in = time(hour=h, minute=m)
        else:
            attendance.time_in = None

        if time_out_str:
            h, m = map(int, time_out_str.split(":"))
            attendance.time_out = time(hour=h, minute=m)
        else:
            attendance.time_out = None

        # Update other fields
        attendance.status = status
        attendance.remarks = remarks

        # Recalculate working hours
        attendance.calculate_working_hours()

        # Commit changes
        db.session.commit()
        flash('Attendance updated!', 'success')
        return redirect(url_for('hr_admin_bp.attendance'))

    # GET request for modal JSON
    if request.headers.get('Accept') == 'application/json':
        return {
            "attendance_id": attendance.id,
            "date": attendance.date.strftime('%Y-%m-%d'),
            "time_in": attendance.time_in.strftime('%H:%M') if attendance.time_in else '',
            "time_out": attendance.time_out.strftime('%H:%M') if attendance.time_out else '',
            "modal_status": attendance.status,
            "remarks": attendance.remarks or ''
        }

    # fallback to page (optional)
    return render_template('hr/admin/atttendance/edit_attendance.html', attendance=attendance)





@hr_admin_bp.route('/add_manual_attendance', methods=['POST'])
@admin_required
@login_required  
def add_manual_attendance():
    employee_id = request.form.get('employee_id')
    date_str = request.form.get('date')
    time_in_str = request.form.get('time_in')
    time_out_str = request.form.get('time_out')
    status = request.form.get('status')
    remarks = request.form.get('remarks')

    # Validate employee
    emp = Employee.query.get(employee_id)
    if not emp:
        flash("Employee not found.", "danger")
        return redirect(url_for('hr_admin_bp.view_attendance'))

    # Convert date and times
    try:
        attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        flash("Invalid date format.", "danger")
        return redirect(url_for('hr_admin_bp.view_attendance'))

    time_in_obj = None
    time_out_obj = None
    try:
        if time_in_str:
            time_in_obj = datetime.strptime(time_in_str, '%H:%M').time()
        if time_out_str:
            time_out_obj = datetime.strptime(time_out_str, '%H:%M').time()
    except:
        flash("Invalid time format.", "danger")
        return redirect(url_for('hr_admin_bp.view_attendance'))

    # Check if attendance already exists
    existing_att = Attendance.query.filter_by(employee_id=emp.id, date=attendance_date).first()
    if existing_att:
        flash(f"Attendance already exists for {emp.get_full_name()} on {attendance_date}.", "danger")
        return redirect(url_for('hr_admin_bp.view_attendance'))

    # Create new attendance
    new_attendance = Attendance(
        employee_id=emp.id,
        date=attendance_date,
        time_in=time_in_obj,
        time_out=time_out_obj,
        status=status,
        remarks=remarks
    )

    db.session.add(new_attendance)
    db.session.commit()

    flash(f"Attendance for {emp.get_full_name()} on {attendance_date} added successfully.", "success")
    return redirect(url_for('hr_admin_bp.view_attendance'))


