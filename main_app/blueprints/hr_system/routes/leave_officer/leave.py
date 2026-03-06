from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required


from main_app.extensions import db
from main_app.models.hr_models import LeaveType
from main_app.helpers.decorators import leave_officer_required

from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp


# ======================================================
# VIEW ALL LEAVE TYPES
# ======================================================
@leave_officer_bp.route("/leave-types")
@leave_officer_required
@login_required
def leave_type_list():
    leave_types = LeaveType.query.order_by(LeaveType.name).all()
    return render_template(
        "hr/leave_officer/leave_type/leave_type_list.html",
        leave_types=leave_types
    )


# ======================================================
# CREATE LEAVE TYPE
# ======================================================
@leave_officer_bp.route("/leave-types/create", methods=["GET", "POST"])
@leave_officer_required
@login_required
def create_leave_type():

    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")

        existing = LeaveType.query.filter_by(name=name).first()
        if existing:
            flash("Leave type already exists.", "danger")
            return redirect(url_for("leave_officer_bp.leave_type_list"))

        leave_type = LeaveType(
            name=name,
            description=description
        )

        db.session.add(leave_type)
        db.session.commit()

        flash("Leave type created successfully.", "success")
        return redirect(url_for("leave_officer_bp.leave_type_list"))

    return render_template(
        "hr/leave_officer/leave_types/add_type.html"
    )


# ======================================================
# EDIT LEAVE TYPE
# ======================================================
@leave_officer_bp.route("/leave-types/edit/<int:id>", methods=["GET", "POST"])
@leave_officer_required
@login_required
def edit_leave_type(id):

    leave_type = LeaveType.query.get_or_404(id)

    if request.method == "POST":
        leave_type.name = request.form.get("name")
        leave_type.description = request.form.get("description")

        db.session.commit()

        flash("Leave type updated successfully.", "success")
        return redirect(url_for("leave_officer_bp.leave_type_list"))

    return render_template(
        "hr/leave_officer/leave_types/edit_type.html",
        leave_type=leave_type
    )


# ======================================================
# DELETE LEAVE TYPE
# ======================================================
@leave_officer_bp.route("/leave-types/delete/<int:id>", methods=["POST"])
@leave_officer_required
@login_required
def delete_leave_type(id):

    leave_type = LeaveType.query.get_or_404(id)

    db.session.delete(leave_type)
    db.session.commit()

    flash("Leave type deleted successfully.", "success")

    return redirect(url_for("leave_officer_bp.leave_type_list")) 