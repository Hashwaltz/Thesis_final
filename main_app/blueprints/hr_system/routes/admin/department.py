from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func

from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Department, Employee
from main_app.models.user import User
from main_app.extensions import db

from main_app.blueprints.hr_system.routes.admin import hr_admin_bp

@hr_admin_bp.route('/departments')
@login_required
@admin_required
def view_departments():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '', type=str)

    query = Department.query

    if search_query:
        query = query.filter(Department.name.ilike(f'%{search_query}%'))

    departments = query.paginate(page=page, per_page=8)

    employee_counts = dict(
        db.session.query(
            Employee.department_id,
            func.count(Employee.id)
        ).group_by(Employee.department_id).all()
    )

    # If AJAX request, return only the cards HTML
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template(
            'hr/admin/_department_cards.html', 
            departments=departments, 
            employee_counts=employee_counts
        )

    return render_template(
        'hr/admin/department/view_departments.html',
        departments=departments,
        employee_counts=employee_counts
    )




@hr_admin_bp.route('/departments/<int:department_id>')
@login_required
@admin_required
def department_details(department_id):

    department = Department.query.get_or_404(department_id)

    # ✅ Use relationship (User, not Employee)
    head = department.head

    # ✅ Load department employees
    employees = Employee.query.filter(
        Employee.department_id == department_id,
        Employee.status == "Active"
    ).all()

    return render_template(
        'hr/admin/department/dept_details.html',
        department=department,
        employees=employees,
        head=head
    )


@hr_admin_bp.route('/departments/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_department():
    # Get employees who can be assigned as department head
    employees = Employee.query.join(User).filter(User.role.in_(['admin','officer','dept_head'])).all()

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        head_id = request.form.get('head_id') or None

        department = Department(
            name=name,
            description=description,
            head_id=head_id
        )
        try:
            db.session.add(department)
            db.session.commit()

            # If a head is assigned, update their User role to 'dept_head'
            if head_id:
                employee = Employee.query.get(int(head_id))
                if employee and employee.user:
                    employee.user.role = 'dept_head'
                    db.session.commit()

            flash('Department added successfully!', 'success')
            return redirect(url_for('hr_admin_bp.add_department'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding department: {str(e)}', 'error')

    return render_template('hr/admin/department/add_dept.html', employees=employees)

@hr_admin_bp.route("/department/<int:department_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_department(department_id):

    department = Department.query.get_or_404(department_id)

    try:
        department.name = request.form.get("name") or department.name
        department.description = request.form.get("description") or department.description

        head_emp_id = request.form.get("dept_head")

        # ⭐ Previous head (User model)
        previous_head = None

        if department.head_id:
            previous_head = User.query.get(department.head_id)

        # =====================================================
        # ⭐ Assign New Head
        # =====================================================
        if head_emp_id:

            employee = Employee.query.get(int(head_emp_id))

            if not employee:
                return jsonify(status="error", message="Employee not found.")

            # Must belong to department
            if employee.department_id != department.id:
                return jsonify(
                    status="error",
                    message="Employee must belong to this department."
                )

            user = employee.user

            if not user:
                return jsonify(
                    status="error",
                    message="Employee has no user account."
                )

            # ⭐ Downgrade previous head
            if previous_head and previous_head.id != user.id:
                previous_head.role = "employee"

            # ⭐ Upgrade new head
            user.role = "dept_head"

            # ⭐ Assign department head
            department.head_id = user.id

        else:

            if previous_head:
                previous_head.role = "employee"

            department.head_id = None

        db.session.commit()

        return jsonify(
            status="success",
            message="Department updated successfully!"
        )

    except Exception as e:

        db.session.rollback()

        current_app.logger.error(str(e))

        return jsonify(
            status="error",
            message="Update failed."
        )