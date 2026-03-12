from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime

from main_app.extensions import db
from main_app.models.hr_models import Shift
from main_app.helpers.decorators import admin_required

from main_app.blueprints.hr_system.routes.admin import hr_admin_bp



# ---------- VIEW ALL SHIFTS WITH PAGINATION ----------
@hr_admin_bp.route("/shifts")
@login_required
@admin_required
def list_shifts():
    page = request.args.get('page', 1, type=int)
    per_page = 10  # number of shifts per page

    shifts = Shift.query.order_by(Shift.start_time).paginate(page=page, per_page=per_page)

    return render_template(
        "hr/admin/shifts/list_shifts.html",
        shifts=shifts
    )

# ---------- CREATE SHIFT ----------
@hr_admin_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_shift():
    if request.method == "POST":
        name = request.form.get("name")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")

        if not name or not start_time or not end_time:
            flash("All fields are required.", "warning")
            return redirect(url_for("hr_admin_bp.create_shift"))

        shift = Shift(
            name=name,
            start_time=datetime.strptime(start_time, "%H:%M").time(),
            end_time=datetime.strptime(end_time, "%H:%M").time()
        )
        db.session.add(shift)
        db.session.commit()
        flash(f"Shift '{name}' created successfully!", "success")
        return redirect(url_for("hr_admin_bp.list_shifts"))

    return render_template("hr/admin/shifts/add_shift.html")





# ---------- UPDATE SHIFT ----------
@hr_admin_bp.route("/edit/<int:shift_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_shift(shift_id):
    shift = Shift.query.get_or_404(shift_id)

    if request.method == "POST":
        shift.name = request.form.get("name")
        shift.start_time = datetime.strptime(request.form.get("start_time"), "%H:%M").time()
        shift.end_time = datetime.strptime(request.form.get("end_time"), "%H:%M").time()

        db.session.commit()
        flash(f"Shift '{shift.name}' updated successfully!", "success")
        return redirect(url_for("hr_admin_bp.list_shifts"))

    return render_template("admin/shifts/edit_shift.html", shift=shift)





# ---------- DELETE SHIFT ----------
@hr_admin_bp.route("/delete/<int:shift_id>", methods=["POST"])
@login_required
@admin_required
def delete_shift(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    db.session.delete(shift)
    db.session.commit()
    flash(f"Shift '{shift.name}' deleted successfully!", "success")
    return redirect(url_for("hr_admin_bp.list_shifts"))