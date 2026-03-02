from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required, current_user

from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Position, Employee, Department
from main_app.extensions import db

from main_app.blueprints.hr_system.routes.admin import hr_admin_bp

@hr_admin_bp.route('/hr/admin/positions')
@admin_required
@login_required
def view_positions():
    """Display paginated list of positions with employee count."""
    page = request.args.get('page', 1, type=int)
    per_page = 10

    positions = Position.query.order_by(Position.name.asc()).paginate(page=page, per_page=per_page)

    # Count employees in each position
    employee_counts = (
        db.session.query(Employee.position_id, db.func.count(Employee.id))
        .group_by(Employee.position_id)
        .all()
    )
    employee_counts = {pos_id: count for pos_id, count in employee_counts}

    return render_template(
        'hr/admin/position/view_positions.html',
        positions=positions,
        employee_counts=employee_counts
    )

@hr_admin_bp.route("/hr/admin/add_position", methods=["GET", "POST"])
@login_required
@admin_required
def add_position():
    from main_app.models.hr_models import Position

    if request.method == "POST":
        name = request.form.get("name").strip()
        description = request.form.get("description").strip()

        if not name:
            flash("Position name is required.", "error")
            return redirect(url_for("hr_admin_bp.add_position"))

        # Check for duplicate name
        existing_position = Position.query.filter_by(name=name).first()
        if existing_position:
            flash("A position with this name already exists.", "error")
            return redirect(url_for("hr_admin_bp.add_position"))

        # Create and save new position
        new_position = Position(name=name, description=description)
        db.session.add(new_position)
        db.session.commit()

        flash(f"Position '{name}' added successfully!", "success")
        return redirect(url_for("hr_admin_bp.view_positions"))  # You can adjust this target route

    return render_template("hr/admin/position/add_positions.html")





@hr_admin_bp.route("/position/<int:position_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_position(position_id):
    position = Position.query.get_or_404(position_id)
    departments = Department.query.all()

    if request.method == "POST":
        try:
            position.name = request.form.get("name") or position.name
            position.description = request.form.get("description") or position.description
            dept_id = request.form.get("department_id")
            position.department_id = int(dept_id) if dept_id else position.department_id

            db.session.commit()

            # For AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"status": "success", "message": "Position updated successfully!"})

            flash("Position updated successfully!", "success")
            return redirect(url_for("hr_admin_bp.view_positions"))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating position {position_id}: {e}")

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"status": "error", "message": "Error updating position. Please try again."})

            flash("Error updating position. Please try again.", "error")

    # Render form
    return render_template(
        "hr/admin/position/edit_position.html",
        position=position,
        departments=departments
    )
