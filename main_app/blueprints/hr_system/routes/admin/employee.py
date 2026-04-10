import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, send_file, jsonify
from flask_login import login_required, current_user
from flask_mail import Message
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from datetime import datetime, date

from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Employee, Department, LeaveCredit, EmploymentType, Position, JobHistory
from main_app.models.user import User
from main_app.extensions import db, mail
from main_app.helpers.functions import parse_date, generate_password
from main_app.helpers.utils import generate_employee_id
from main_app.helpers.docs import generate_moa_excel, generate_excel_employees, generate_service_record_docx, generate_coe_pdf


from main_app.blueprints.hr_system.routes.admin import hr_admin_bp
import re

def is_valid_email(email):
    """
    Validate email format per RFC 5321 basics.
    Returns True if valid, False otherwise.
    """
    if not email:
        return False
    
    email = email.strip().lower()
    
    # Basic RFC 5321 pattern: local@domain.tld
    # - Local part: letters, numbers, dots, underscores, %, +, -
    # - @ symbol required
    # - Domain: letters, numbers, dots, hyphens
    # - TLD: at least 2 letters
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(pattern, email):
        return False
    
    # Additional checks
    if email.count('@') != 1:
        return False
    
    local, domain = email.split('@')
    if not local or not domain:
        return False
    if domain.startswith(('.', '-')) or domain.endswith(('.', '-')):
        return False
    if '..' in email:
        return False
        
    return True

@hr_admin_bp.route('/employees')
@admin_required
@login_required
def view_employees():
    search = request.args.get('search', '')
    department_id = request.args.get('department_id', '')
    employment_type_id = request.args.get('employment_type_id', '')
    barangay = request.args.get('barangay', '') 
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
   
    # Apply barangay filter
    if barangay:
        query = query.filter(Employee.barangay.ilike(f"%{barangay}%"))

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
        selected_employment_type=employment_type_id,
        selected_barangay=barangay
    )



@hr_admin_bp.route('/employees/add', methods=['POST'])
@login_required
@admin_required
def add_employee():
    try:
        # --- 1. Get and validate form data ---
        
        # ✅ Validate email FIRST before any DB operations
        email = request.form.get('email', '').strip().lower()
        if not is_valid_email(email):
            flash('Invalid email address format. Please use: user@domain.com', 'error')
            return redirect(url_for('hr_admin_bp.view_employees'))
        
        # Validate other required fields
        if not request.form.get('first_name') or not request.form.get('last_name'):
            flash('First name and last name are required.', 'error')
            return redirect(url_for('hr_admin_bp.view_employees'))
        
        department_id = request.form.get('department_id')
        if not department_id:
            flash('Department is required.', 'error')
            return redirect(url_for('hr_admin_bp.view_employees'))
            
        new_employee_id = generate_employee_id(department_id)

        # Parse dates safely
        date_hired = parse_date(request.form['date_hired'], "Date Hired")
        date_of_birth = parse_date(request.form['date_of_birth'], "Date of Birth")
        if not date_hired or not date_of_birth:
            flash("Invalid date format! Please use YYYY-MM-DD", "error")
            return redirect(url_for('hr_admin_bp.view_employees'))

        # Validate date logic (can't be hired before birth, etc.)
        if date_of_birth >= date_hired:
            flash("Date of Birth must be before Date Hired.", "error")
            return redirect(url_for('hr_admin_bp.view_employees'))

        # Parse salary
        salary_str = request.form.get('salary', '').strip()
        try:
            salary = float(salary_str) if salary_str else 0.0
            if salary < 0:
                raise ValueError("Negative salary")
        except ValueError:
            flash("Invalid salary value! Please enter a valid number.", "error")
            return redirect(url_for('hr_admin_bp.view_employees'))

        # Address fields (optional but validated if provided)
        street = request.form.get('street_address', '').strip()
        barangay = request.form.get('barangay', '').strip()
        municipality = request.form.get('municipality', '').strip()
        province = request.form.get('province', '').strip()
        postal_code = request.form.get('postal_code', '').strip()

        # --- 2. Check for duplicate email BEFORE creating user ---
        existing_user = User.query.filter(func.lower(User.email) == email).first()
        if existing_user:
            flash(f"Email '{email}' is already registered to another account.", "error")
            return redirect(url_for('hr_admin_bp.view_employees'))
            
        existing_employee = Employee.query.filter(func.lower(Employee.email) == email).first()
        if existing_employee:
            flash(f"Email '{email}' is already assigned to another employee.", "error")
            return redirect(url_for('hr_admin_bp.view_employees'))

        # --- 3. Create User ---
        default_password = generate_password(12)
        user = User(
            email=email,  # ✅ Use validated, lowercased email
            first_name=request.form['first_name'].strip(),
            last_name=request.form['last_name'].strip(),
            role="employee",
            password=default_password
        )
        db.session.add(user)
        db.session.flush()  # get user.id

        # --- 4. Create Employee ---
        employment_type_id = int(request.form['employment_type_id'])
        employee = Employee(
            employee_id=new_employee_id,
            user_id=user.id,
            first_name=request.form['first_name'].strip(),
            last_name=request.form['last_name'].strip(),
            middle_name=request.form.get('middle_name', '').strip(),
            email=email,  # ✅ Use validated email
            phone=request.form.get('phone', '').strip(),
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
            emergency_contact=request.form.get('emergency_contact', '').strip(),
            status='Active'
        )
        db.session.add(employee)
        db.session.flush()

        # --- 5. Create initial JobHistory entry ---
        job_entry = JobHistory(
            employee_id=employee.id,
            effective_date=date_hired,
            position_id=employee.position_id,
            department_id=employee.department_id,
            employment_type_id=employee.employment_type_id,
            salary=employee.salary,
            status=employee.status,
            remarks="Initial appointment"
        )
        db.session.add(job_entry)

        # --- 6. Commit everything together ---
        db.session.commit()

        # --- 7. Send Gmail notification (with error handling) ---
        try:
            msg = Message(
                subject="Your govHRPay Account Details",
                sender=("GovHRPay Admin", "natanielashleyrodelas@gmail.com"),
                recipients=[email]  # ✅ Use validated email
            )
            msg.body = f"""
Hello {user.first_name} {user.last_name},

Your govHRPay account has been created successfully!

Login credentials:
Email: {user.email}
Temporary Password: {default_password}

Please log in at: https://web-production-e5e7e.up.railway.app/employee/auth/employee-login

⚠️ For security, please change your password after first login.

Thank you,
GovHRPay Admin Team
"""
            mail.send(msg)
            flash("Employee and user account created successfully! Email sent with login details.", "success")
            
        except Exception as mail_err:
            # Log error but don't fail the whole operation
            current_app.logger.error(f"Failed to send account email to {email}: {mail_err}")
            flash(
                f"Employee created successfully! ⚠️ Failed to send email to '{email}'. "
                f"Please manually provide credentials or check SMTP settings.", 
                "warning"
            )

        return redirect(url_for('hr_admin_bp.view_employees'))

    except IntegrityError as e:
        db.session.rollback()
        # Check if it's a unique constraint violation on email
        if 'email' in str(e).lower() or 'unique' in str(e).lower():
            flash("Error: An employee or user with this email already exists!", "error")
        else:
            flash(f"Database error: {str(e)}", "error")
        return redirect(url_for('hr_admin_bp.view_employees'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error in add_employee: {e}", exc_info=True)
        flash(f"Unexpected error: {str(e)}", "error")
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
            # --- Store old values for JobHistory comparison ---
            old_position_id = employee.position_id
            old_department_id = employee.department_id
            old_employment_type_id = employee.employment_type_id
            old_salary = employee.salary
            old_status = employee.status

            # --- Personal info ---
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

            # --- Address fields ---
            employee.street_address = request.form.get("street_address")
            employee.barangay = request.form.get("barangay")
            employee.municipality = request.form.get("municipality")
            employee.province = request.form.get("province")
            employee.postal_code = request.form.get("postal_code")

            # --- Employment info ---
            employee.department_id = int(request.form.get("department_id")) if request.form.get("department_id") else None
            employee.position_id = int(request.form.get("position_id")) if request.form.get("position_id") else None
            employee.employment_type_id = int(request.form.get("employment_type_id")) if request.form.get("employment_type_id") else None
            salary_val = request.form.get("salary")
            employee.salary = float(salary_val) if salary_val else None

            # --- Dates ---
            def parse_date(date_str):
                if not date_str:
                    return None
                try:
                    return datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    return None

            employee.date_of_birth = parse_date(request.form.get("date_of_birth"))
            employee.date_hired = parse_date(request.form.get("date_hired"))

            # --- Status ---
            employee.status = request.form.get("status")

            # --- Update linked user email if exists ---
            if hasattr(employee, 'user') and employee.user:
                employee.user.email = new_email

            # --- Create JobHistory if any employment field changed ---
            if (old_position_id != employee.position_id or
                old_department_id != employee.department_id or
                old_employment_type_id != employee.employment_type_id or
                old_salary != employee.salary or
                old_status != employee.status):

                remarks_list = []
              # Fetch names for remarks
                old_employment_type_name = EmploymentType.query.get(old_employment_type_id).name if old_employment_type_id else "N/A"
                new_employment_type_name = employee.employment_type.name if employee.employment_type else "N/A"

                old_department_name = Department.query.get(old_department_id).name if old_department_id else "N/A"
                new_department_name = employee.department.name if employee.department else "N/A"

                old_position_name = Position.query.get(old_position_id).name if old_position_id else "N/A"
                new_position_name = employee.position.name if employee.position else "N/A"

                # Build remarks
                if old_position_id != employee.position_id:
                    remarks_list.append(f"Position: {old_position_name} → {new_position_name}")
                if old_department_id != employee.department_id:
                    remarks_list.append(f"Department: {old_department_name} → {new_department_name}")
                if old_employment_type_id != employee.employment_type_id:
                    remarks_list.append(f"Employment Type: {old_employment_type_name} → {new_employment_type_name}")

                job_entry = JobHistory(
                    employee_id=employee.id,
                    effective_date=datetime.today().date(),
                    position_id=employee.position_id,
                    department_id=employee.department_id,
                    employment_type_id=employee.employment_type_id,
                    salary=employee.salary,
                    status=employee.status,
                    remarks="; ".join(remarks_list)
                )
                db.session.add(job_entry)

            # --- Commit all changes ---
            db.session.commit()
            flash("Employee updated successfully and service record logged.", "success")
            return redirect(url_for('hr_admin_bp.view_employees'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating employee {employee_id}: {e}")
            flash("Failed to update employee.", "danger")
            return redirect(url_for('hr_admin_bp.view_employees'))     


@hr_admin_bp.route("/employees/<int:employee_id>/archive", methods=["POST"])
@admin_required
@login_required
def archive_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    employee.archived = True
    employee.status = "Inactive"
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
    employee.status = "Active"
    db.session.commit()

    flash(f"Employee {employee.get_full_name()} has been restored.", "success")
    return redirect(url_for('hr_admin_bp.view_archived_employees'))