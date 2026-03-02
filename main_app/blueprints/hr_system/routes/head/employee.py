from flask import send_file,render_template, request, url_for, flash, redirect
from flask_login import login_required, current_user
from types import SimpleNamespace
from io import BytesIO
from openpyxl import Workbook

from main_app.extensions import db
from main_app.models.hr_models import Department, Employee, Position
from main_app.helpers.decorators import dept_head_required


from main_app.blueprints.hr_system.routes.head import hr_head_bp




@hr_head_bp.route('/employees')
@login_required
@dept_head_required
def employees():

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    department = current_user.department

    # ---------------- Leadership Positions ----------------

    mayors = Employee.query.filter(
        Employee.position.has(name="Mayor"),
        Employee.status == "Active"
    ).all()

    vice_mayors = Employee.query.filter(
        Employee.position.has(name="Vice Mayor"),
        Employee.status == "Active"
    ).all()

    municipal_admins = Employee.query.filter(
        Employee.position.has(name="Municipal Administrator"),
        Employee.status == "Active"
    ).all()

    councilors = Employee.query.filter(
        Employee.position.has(name="Councilor"),
        Employee.status == "Active"
    ).all()

    # ---------------- Department Employees ----------------

    query = Employee.query.filter(
        Employee.department == department,
        Employee.status == "Active",
        Employee.id != current_user.id  
    )

    if search:
        query = query.filter(
            (Employee.first_name.contains(search)) |
            (Employee.last_name.contains(search))
        )

    employees = query.order_by(
        Employee.last_name.asc()
    ).paginate(
        page=page,
        per_page=8,
        error_out=False
    )

    return render_template(
        "hr/head/head_employee.html",
        employees=employees,
        search=search,
        department=department,
        mayors=mayors,
        vice_mayors=vice_mayors,
        municipal_admins=municipal_admins,
        councilors=councilors
    )

@hr_head_bp.route('/employee/<int:employee_id>/edit')
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





@hr_head_bp.route('/employees/export')
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
