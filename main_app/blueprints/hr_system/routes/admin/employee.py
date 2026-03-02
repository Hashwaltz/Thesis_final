import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, send_file, jsonify
from flask_login import login_required, current_user
from flask_mail import Message
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from datetime import datetime, date

from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Employee, Department, LeaveCredit, EmploymentType, Position
from main_app.models.user import User
from main_app.extensions import db, mail
from main_app.helpers.functions import parse_date
from main_app.helpers.utils import generate_employee_id
from main_app.helpers.docs import generate_moa_excel, generate_excel_employees, generate_service_record_docx, generate_coe_pdf


from main_app.blueprints.hr_system.routes.admin import hr_admin_bp


@hr_admin_bp.route('/employees')
@admin_required
@login_required
def view_employees():
    search = request.args.get('search', '')
    department_id = request.args.get('department_id', '')
    employment_type_id = request.args.get('employment_type_id', '')
    page = request.args.get('page', 1, type=int)

    # Base query with joins, excluding archived (archived=True will be hidden)
    query = Employee.query.options(
        joinedload(Employee.department),
        joinedload(Employee.position),
        joinedload(Employee.employment_type)
    ).filter(Employee.archived.isnot(True))  # ✅ includes False and NULL

    # Apply search filter
    if search:
        query = query.filter(
            Employee.first_name.ilike(f"%{search}%") |
            Employee.last_name.ilike(f"%{search}%") |
            Employee.email.ilike(f"%{search}%")
        )

    # Apply department filter
    if department_id:
        query = query.filter(Employee.department_id == int(department_id))

    # Apply employment type filter
    if employment_type_id:
        query = query.filter(Employee.employment_type_id == int(employment_type_id))

    # Order employees alphabetically
    query = query.order_by(Employee.last_name.asc(), Employee.first_name.asc())

    # Paginate
    employees = query.paginate(page=page, per_page=10)

    # Fetch all filter dropdown data
    departments = Department.query.order_by(Department.name.asc()).all()
    employment_types = EmploymentType.query.order_by(EmploymentType.name.asc()).all()
    positions = Position.query.order_by(Position.name.asc()).all()

    return render_template(
        'hr/admin/employees/view_employees.html',
        employees=employees,
        search=search,
        positions=positions,
        departments=departments,
        employment_types=employment_types,
        selected_department=department_id,
        selected_employment_type=employment_type_id
    )





@hr_admin_bp.route('/employees/add', methods=['POST'])
@login_required
@admin_required
def add_employee():
    try:
        # --- 1. Get form data ---
        department_id = request.form['department_id']
        new_employee_id = generate_employee_id(department_id)

        # Parse dates safely
        date_hired = parse_date(request.form['date_hired'], "Date Hired")
        date_of_birth = parse_date(request.form['date_of_birth'], "Date of Birth")
        if not date_hired or not date_of_birth:
            flash("Invalid date format!", "danger")
            return redirect(url_for('hr_admin_bp.view_employees'))

        # Parse salary
        salary_str = request.form.get('salary', '').strip()
        try:
            salary = float(salary_str) if salary_str else 0.0
        except ValueError:
            flash("Invalid salary value!", "danger")
            return redirect(url_for('hr_admin_bp.view_employees'))

        # Address
        street = request.form.get('street_address', '').strip()
        barangay = request.form.get('barangay', '').strip()
        municipality = request.form.get('municipality', '').strip()
        province = request.form.get('province', '').strip()
        postal_code = request.form.get('postal_code', '').strip()

        # --- 2. Create User ---
        default_password = "password123"
        user = User(
            email=request.form['email'],
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            role="employee",
            password=default_password
        )
        db.session.add(user)
        db.session.flush()  # get user.id

        # --- 3. Create Employee ---
        employment_type_id = int(request.form['employment_type_id'])
        employee = Employee(
            employee_id=new_employee_id,
            user_id=user.id,
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            middle_name=request.form.get('middle_name'),
            email=request.form['email'],
            phone=request.form['phone'],
            street_address=street,
            barangay=barangay,
            municipality=municipality,
            province=province,
            postal_code=postal_code,
            department_id=department_id,
            position_id=request.form['position_id'],
            employment_type_id=employment_type_id,
            salary=salary,
            date_hired=date_hired,
            date_of_birth=date_of_birth,
            gender=request.form['gender'],
            marital_status=request.form['marital_status'],
            emergency_contact=request.form['emergency_contact'],
            status='Active'
        )
        db.session.add(employee)
        db.session.flush()  # get employee.id for leave credits

        # --- 4. Initialize Leave Credits ONLY for Regular (1) & Casual (3) ---
        if employment_type_id in [1, 3]:
            # Vacation Leave (leave_type_id = 1)
            vacation_credit = LeaveCredit(
                employee_id=employee.id,
                leave_type_id=1,
                total_credits=15.0,
                used_credits=0
            )
            db.session.add(vacation_credit)

            # Sick Leave (leave_type_id = 2)
            sick_credit = LeaveCredit(
                employee_id=employee.id,
                leave_type_id=2,
                total_credits=15.0,
                used_credits=0
            )
            db.session.add(sick_credit)

        # --- 5. Commit everything together ---
        db.session.commit()

        # --- 6. Send Gmail notification ---
        try:
            msg = Message(
                subject="Your govHRPay Account Details",
                sender=("GovHRPay Admin", "natanielashleyrodelas@gmail.com"),  # system email
                recipients=[user.email]
            )
            msg.body = f"""
Hello {user.first_name} {user.last_name},

Your govHRPay account has been created successfully!

Login credentials:
Email: {user.email}
Password: {default_password}

Please log in at: http://127.0.0.1:5000/hr/auth/login

For security, you should change your password after first login.

Thank you,
GovHRPay Admin
"""
            mail.send(msg)
        except Exception as mail_err:
            current_app.logger.error(f"Failed to send account email to {user.email}: {mail_err}")
            flash("Employee created, but failed to send email notification.", "warning")
        else:
            flash("Employee and user account created successfully! Email sent with login details.", "success")

        return redirect(url_for('hr_admin_bp.view_employees'))

    except IntegrityError as e:
        db.session.rollback()
        flash(f"Error: Employee or User already exists! ({str(e)})", "danger")
        return redirect(url_for('hr_admin_bp.view_employees'))

    except Exception as e:
        db.session.rollback()
        flash(f"Unexpected error: {str(e)}", "danger")
        return redirect(url_for('hr_admin_bp.view_employees'))




    
@hr_admin_bp.route("/generate_moa_all/<int:employment_type_id>")
@admin_required
@login_required
def generate_moa_all(employment_type_id):

    if employment_type_id == 0:
        etypes = EmploymentType.query.order_by(EmploymentType.name).all()
        employees_by_type = {
            etype: Employee.query.filter_by(employment_type_id=etype.id).all()
            for etype in etypes
        }
    else:
        etype = EmploymentType.query.get_or_404(employment_type_id)
        employees_by_type = {
            etype: Employee.query.filter_by(employment_type_id=etype.id).all()
        }

    if not any(employees_by_type.values()):
        flash("No employees found for the selected type(s).", "warning")
        return redirect(url_for("hr_admin.view_employees"))

    file_stream = generate_moa_excel(employees_by_type)

    filename = f"MOA_List_{date.today().strftime('%Y%m%d')}.xlsx"

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )





@hr_admin_bp.route('/employees/export')
@login_required
@admin_required
def export_employees_excel():
    employees = Employee.query.order_by(Employee.last_name).all()

    if not employees:
        flash("No employees found.", "warning")
        return redirect(url_for("hr_admin.view_employees"))

    # ===== BUILD DATA =====
    data = [
        [
            idx,
            emp.employee_id or "",
            emp.last_name or "",
            emp.first_name or "",
            emp.email or "",
            emp.department.name if emp.department else "",
            emp.status or "",
            emp.employment_type.name if emp.employment_type else ""
        ]
        for idx, emp in enumerate(employees, start=1)
    ]

    # ===== HEADERS =====
    headers = [
        "NO.",
        "EMPLOYEE ID",
        "LAST NAME",
        "FIRST NAME",
        "EMAIL",
        "DEPARTMENT",
        "STATUS",
        "EMPLOYMENT TYPE"
    ]

    # ===== CALL REUSABLE EXPORT ENGINE =====
    file_stream = generate_excel_employees(
        data=data,
        headers=headers,
        title="MASTERLIST OF EMPLOYEES",
        agency_name="LGU-NORZAGARAY, BULACAN",
        regional_office="3"
    )

    filename = f"Employees_Report_{date.today().strftime('%Y%m%d')}.xlsx"

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )





@hr_admin_bp.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@admin_required
@login_required
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)

    if request.method == 'GET':
        # Return JSON for modal population
        return jsonify({
            "first_name": employee.first_name,
            "middle_name": employee.middle_name,
            "last_name": employee.last_name,
            "email": employee.email,
            "phone": employee.phone,
            "gender": employee.gender,
            "marital_status": employee.marital_status,
            "emergency_contact": employee.emergency_contact,
            "emergency_phone": employee.emergency_phone,
            "department_id": employee.department_id,
            "position_id": employee.position_id,
            "employment_type_id": employee.employment_type_id,
            "salary": str(employee.salary) if employee.salary else "",
            "date_of_birth": employee.date_of_birth.isoformat() if employee.date_of_birth else "",
            "date_hired": employee.date_hired.isoformat() if employee.date_hired else "",
            "status": employee.status,  
            "street_address": employee.street_address,
            "barangay": employee.barangay,
            "municipality": employee.municipality,
            "province": employee.province,
            "postal_code": employee.postal_code
        })

    if request.method == 'POST':
        try:
            # Personal info
            new_email = request.form.get("email")
            employee.first_name = request.form.get("first_name")
            employee.middle_name = request.form.get("middle_name")
            employee.last_name = request.form.get("last_name")
            employee.email = new_email
            employee.phone = request.form.get("phone")
            employee.gender = request.form.get("gender")
            employee.marital_status = request.form.get("marital_status")
            employee.emergency_contact = request.form.get("emergency_contact")
            employee.emergency_phone = request.form.get("emergency_phone")

            # Address fields
            employee.street_address = request.form.get("street_address")
            employee.barangay = request.form.get("barangay")
            employee.municipality = request.form.get("municipality")
            employee.province = request.form.get("province")
            employee.postal_code = request.form.get("postal_code")

            # Employment info
            employee.department_id = int(request.form.get("department_id")) if request.form.get("department_id") else None
            employee.position_id = int(request.form.get("position_id")) if request.form.get("position_id") else None
            employee.employment_type_id = int(request.form.get("employment_type_id")) if request.form.get("employment_type_id") else None
            salary_val = request.form.get("salary")
            employee.salary = float(salary_val) if salary_val else None

            # Dates
            def parse_date(date_str):
                if not date_str:
                    return None
                try:
                    return datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    return None

            employee.date_of_birth = parse_date(request.form.get("date_of_birth"))
            employee.date_hired = parse_date(request.form.get("date_hired"))

            # Status (string)
            employee.status = request.form.get("status")  # ✅ Updated

            # --- Update linked user email if exists ---
            if hasattr(employee, 'user') and employee.user:
                employee.user.email = new_email

            # Commit changes
            db.session.commit()
            return redirect(url_for('hr_admin_bp.view_employees'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating employee {employee_id}: {e}")
            return redirect(url_for('hr_admin_bp.view_employees'))
        




@hr_admin_bp.route('/employees/<int:employee_id>/service_record')
@admin_required
@login_required
def export_service_record(employee_id):

    employee = Employee.query.get_or_404(employee_id)

    file_stream = generate_service_record_docx(employee)

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=f"service_record_{employee.employee_id}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )





@hr_admin_bp.route("/employee/<int:employee_id>/generate-coe")
@admin_required
@login_required
def generate_coe(employee_id):

    employee = Employee.query.get_or_404(employee_id)

    buffer = generate_coe_pdf(employee)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"COE_{employee.employee_id}.pdf",
        mimetype="application/pdf"
    )





@hr_admin_bp.route("/employees/<int:employee_id>/archive", methods=["POST"])
@admin_required
@login_required
def archive_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    employee.archived = True
    employee.archived_at = datetime.utcnow()

    db.session.commit()

    # Return JSON if AJAX, otherwise redirect to archived page
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True})
    
    return redirect(url_for("hr_admin_bp.view_archived_employees"))





@hr_admin_bp.route("/employees/archived")
@admin_required
@login_required
def view_archived_employees():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "", type=str)
    department_id = request.args.get("department_id", type=int)
    employment_type_id = request.args.get("employment_type_id", type=int)

    query = Employee.query.filter_by(archived=True)

    if search:
        query = query.filter(
            (Employee.first_name.ilike(f"%{search}%")) |
            (Employee.last_name.ilike(f"%{search}%"))
        )
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if employment_type_id:
        query = query.filter(Employee.employment_type_id == employment_type_id)

    employees = query.order_by(Employee.archived_at.desc()).paginate(page=page, per_page=10)

    # Assuming you have department and employment type lists for filter dropdowns
    departments = Department.query.all()
    employment_types = EmploymentType.query.all()

    return render_template(
        "hr/admin/employees/view_archives.html",
        employees=employees,
        departments=departments,
        employment_types=employment_types,
        search=search,
        selected_department=str(department_id) if department_id else "",
        selected_employment_type=str(employment_type_id) if employment_type_id else ""
    )





@hr_admin_bp.route('/employees/restore/<int:employee_id>', methods=['POST'])
@login_required
@admin_required
def restore_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)

    if not employee.archived:
        flash("Employee is not archived.", "warning")
        return redirect(url_for('hr_admin_bp.view_archived_employees'))

    employee.archived = False
    db.session.commit()

    flash(f"Employee {employee.get_full_name()} has been restored.", "success")
    return redirect(url_for('hr_admin_bp.view_archived_employees'))
