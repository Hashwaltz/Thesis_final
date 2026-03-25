from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required


from main_app.models.hr_models import Employee, Department, Attendance
from main_app.models.payroll_models import Payroll, PayrollPeriod, Deduction, EmployeeDeduction
from main_app.extensions import db
from main_app.helpers.decorators import payroll_admin_required

from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp



@payroll_admin_bp.route('/deductions/create', methods=['GET', 'POST'])
@login_required
@payroll_admin_required
def create_deduction():

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            calculation_type = request.form.get('calculation_type')

            if not name:
                flash("Deduction name is required", "error")
                return redirect(url_for('payroll_admin_bp.create_deduction'))

            if not calculation_type:
                flash("Calculation type is required", "error")
                return redirect(url_for('payroll_admin_bp.create_deduction'))

            def safe_float(v):
                try:
                    return float(v) if v not in ("", None) else None
                except:
                    return None

            deduction = Deduction(
                name=name,  
                description=request.form.get('description', '').strip(),
                calculation_type=calculation_type,
                rate=safe_float(request.form.get('rate')),
                ceiling=safe_float(request.form.get('ceiling')),
                floor=safe_float(request.form.get('floor')),
                active=bool(request.form.get('active'))
            )

            db.session.add(deduction)
            db.session.commit()

            flash("Deduction created successfully", "success")

            return redirect(url_for('payroll_admin_bp.deductions'))

        except Exception as e:
            db.session.rollback()

            print("🔥 Deduction Create Error:", repr(e))

            flash(f"Database Error: {str(e)}", "error")


            return redirect(url_for('payroll_admin_bp.create_deduction'))

    return render_template(
        "payroll/admin/deductions/deduction_form.html",
        action="Create",
        deduction=None
    )

# ==========================
# EDIT DEDUCTION
# ==========================
@payroll_admin_bp.route('/deductions/edit/<int:deduction_id>', methods=['GET', 'POST'])
@login_required
@payroll_admin_required
def edit_deduction(deduction_id):
    deduction = Deduction.query.get_or_404(deduction_id)

    if request.method == 'POST':
        try:
            # Basic fields
            name = request.form.get('name', '').strip()
            calculation_type = request.form.get('calculation_type')
            description = request.form.get('description', '').strip()

            if not name:
                flash('Deduction name is required.', 'danger')
                return redirect(url_for('payroll_admin_bp.edit_deduction', deduction_id=deduction_id))

            if not calculation_type:
                flash('Calculation type is required.', 'danger')
                return redirect(url_for('payroll_admin_bp.edit_deduction', deduction_id=deduction_id))
            
            if not description:
                flash('Description is required.', 'danger')
                return redirect(url_for('payroll_admin_bp.edit_deduction', deduction_id=deduction_id))

            # Optional numeric fields
            def safe_float(value):
                try:
                    return float(value) if value not in (None, '', ' ') else None
                except ValueError:
                    return None

            rate = safe_float(request.form.get('rate'))
            ceiling = safe_float(request.form.get('ceiling'))
            floor = safe_float(request.form.get('floor'))

            active = True if request.form.get('active') else False

            # Update deduction
            deduction.name = name
            deduction.description = description
            deduction.calculation_type = calculation_type
            deduction.rate = rate
            deduction.ceiling = ceiling
            deduction.floor = floor
            deduction.active = active

            db.session.commit()
            flash('Deduction updated successfully!', 'success')
            return redirect(url_for('payroll_admin_bp.deductions'))

        except Exception as e:
            db.session.rollback()
            print(f"Deduction Edit Error: {e}")
            flash('Error updating deduction.', 'danger')
            return redirect(url_for('payroll_admin_bp.edit_deduction', deduction_id=deduction_id))

    return render_template(
        'payroll/admin/deductions/deduction_form.html',
        action="Edit",
        deduction=deduction
    )




# ==========================
# DELETE DEDUCTION
# ==========================
@payroll_admin_bp.route('/deductions/delete/<int:deduction_id>', methods=['POST'])
@login_required
@payroll_admin_required
def delete_deduction(deduction_id):
    deduction = Deduction.query.get_or_404(deduction_id)
    db.session.delete(deduction)
    db.session.commit()
    flash('Deduction deleted successfully!', 'success')
    return redirect(url_for('payroll_admin_bp.deductions'))


@payroll_admin_bp.route("/deductions/manage/<int:deduction_id>", methods=["GET", "POST"])
@login_required
@payroll_admin_required
def manage_deduction_employees(deduction_id):
    deduction = Deduction.query.get_or_404(deduction_id)

    # === SEARCH ===
    search_query = request.args.get("search", "").strip()

    # Base query for active employees
    employees_query = Employee.query.filter_by(status="Active")

    # Apply search filter if provided
    if search_query:
        employees_query = employees_query.filter(
            db.or_(
                Employee.first_name.ilike(f"%{search_query}%"),
                Employee.last_name.ilike(f"%{search_query}%"),
                Employee.employee_id.ilike(f"%{search_query}%")
            )
        )

    # === PAGINATION ===
    page = request.args.get("page", 1, type=int)
    per_page = 10  # Change this to adjust items per page
    pagination = employees_query.order_by(Employee.last_name, Employee.first_name).paginate(page=page, per_page=per_page, error_out=False)
    employees = pagination.items

    if request.method == "POST":
        selected_ids = request.form.getlist("employees")  # list of employee IDs as strings

        # Remove existing links not in selected_ids
        for ed in deduction.employees:
            if str(ed.employee_id) not in selected_ids:
                db.session.delete(ed)

        # Add new links
        for emp_id in selected_ids:
            emp_id = int(emp_id)
            exists = EmployeeDeduction.query.filter_by(employee_id=emp_id, deduction_id=deduction.id).first()
            if not exists:
                new_link = EmployeeDeduction(employee_id=emp_id, deduction_id=deduction.id)
                db.session.add(new_link)

        db.session.commit()
        flash("Employees updated for deduction.", "success")
        return redirect(url_for("payroll_admin_bp.manage_deduction_employees", deduction_id=deduction.id))

    # Pre-select employees already linked
    linked_employee_ids = [ed.employee_id for ed in deduction.employees]

    return render_template(
        "payroll/admin/deductions/manage_deduction_employees.html",
        deduction=deduction,
        employees=employees,
        linked_employee_ids=linked_employee_ids,
        pagination=pagination,
        search=search_query
    )
