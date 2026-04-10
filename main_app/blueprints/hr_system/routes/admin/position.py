from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required

from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Position, Employee, Department
from main_app.extensions import db

from main_app.blueprints.hr_system.routes.admin import hr_admin_bp


# ---------- VIEW ALL POSITIONS ----------
@hr_admin_bp.route('/hr/admin/positions')
@login_required
@admin_required
def view_positions():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    per_page = 10

    query = Position.query
    if search:
        query = query.filter(Position.name.ilike(f'%{search}%') | Position.description.ilike(f'%{search}%'))
    
    positions = query.order_by(Position.name.asc()).paginate(page=page, per_page=per_page, error_out=False)

    employee_counts = {
        pos_id: count for pos_id, count in 
        db.session.query(Employee.position_id, db.func.count(Employee.id))
        .group_by(Employee.position_id).all()
    }

    return render_template(
        'hr/admin/position/view_positions.html',
        positions=positions,
        employee_counts=employee_counts
    )


# ---------- GET POSITION DATA FOR EDIT MODAL (AJAX) ----------
@hr_admin_bp.route('/hr/admin/position/<int:position_id>/data')
@login_required
@admin_required
def get_position_data(position_id):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return jsonify({'error': 'Unauthorized access'}), 403
    
    position = Position.query.get_or_404(position_id)
    return jsonify({
        'id': position.id,
        'name': position.name,
        'description': position.description or ''
        # ✅ Removed is_active - not in model
    })


# ---------- CREATE POSITION ----------
@hr_admin_bp.route("/hr/admin/positions/create", methods=["POST"])
@login_required
@admin_required
def add_position():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    # ✅ Removed is_active handling

    if not name:
        flash("Position name is required.", "error")
        return redirect(url_for("hr_admin_bp.view_positions"))

    if Position.query.filter_by(name=name).first():
        flash("A position with this name already exists.", "error")
        return redirect(url_for("hr_admin_bp.view_positions"))

    try:
        new_position = Position(
            name=name, 
            description=description if description else None
            # ✅ Removed is_active
        )
        db.session.add(new_position)
        db.session.commit()
        flash(f"Position '{name}' added successfully!", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating position: {e}")
        flash(f"Error creating position: {str(e)}", "error")
    
    return redirect(url_for("hr_admin_bp.view_positions"))


# ---------- UPDATE POSITION ----------
@hr_admin_bp.route("/hr/admin/position/<int:position_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_position(position_id):
    position = Position.query.get_or_404(position_id)
    
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    # ✅ Removed is_active handling

    if not name:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "error", "message": "Position name is required"}), 400
        flash("Position name is required.", "error")
        return redirect(url_for("hr_admin_bp.view_positions"))

    try:
        position.name = name
        position.description = description if description else None
        # ✅ Removed is_active assignment
        
        db.session.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "success", "message": "Position updated successfully!"})

        flash("Position updated successfully!", "success")
        return redirect(url_for("hr_admin_bp.view_positions"))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating position {position_id}: {e}")
        
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "error", "message": "Error updating position. Please try again."}), 400

        flash("Error updating position. Please try again.", "error")
        return redirect(url_for("hr_admin_bp.view_positions"))


# ---------- DELETE POSITION ----------
@hr_admin_bp.route("/hr/admin/position/<int:position_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_position(position_id):
    position = Position.query.get_or_404(position_id)
    name = position.name
    
    try:
        if position.employees.count() > 0:
            flash(f"Cannot delete '{name}': {position.employees.count()} employee(s) assigned.", "error")
            return redirect(url_for("hr_admin_bp.view_positions"))
        
        db.session.delete(position)
        db.session.commit()
        flash(f"Position '{name}' deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting position {position_id}: {e}")
        flash(f"Error deleting position: {str(e)}", "error")
    
    return redirect(url_for("hr_admin_bp.view_positions"))