from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import datetime

from main_app.extensions import db
from main_app.models.hr_models import Shift
from main_app.helpers.decorators import admin_required
from main_app.blueprints.hr_system.routes.admin import hr_admin_bp


# Helper: Calculate shift stats
def get_shift_stats():
    shifts = Shift.query.all()
    morning = sum(1 for s in shifts if s.start_time and 5 <= s.start_time.hour < 12)
    evening = sum(1 for s in shifts if s.start_time and 12 <= s.start_time.hour < 18)
    
    total_duration = 0
    count = 0
    for s in shifts:
        if s.start_time and s.end_time:
            start_mins = s.start_time.hour * 60 + s.start_time.minute
            end_mins = s.end_time.hour * 60 + s.end_time.minute
            duration = (end_mins - start_mins) % (24 * 60)
            total_duration += duration
            count += 1
    avg_duration = round(total_duration / count / 60, 1) if count > 0 else 0
    
    return morning, evening, avg_duration


# ---------- VIEW ALL SHIFTS WITH PAGINATION ----------
@hr_admin_bp.route("/shifts")
@login_required
@admin_required
def list_shifts():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    per_page = 10

    query = Shift.query
    if search:
        query = query.filter(Shift.name.ilike(f'%{search}%'))
    
    shifts = query.order_by(Shift.start_time).paginate(page=page, per_page=per_page, error_out=False)
    
    # Calculate stats for display
    morning_count, evening_count, avg_duration = get_shift_stats()

    return render_template(
        "hr/admin/shifts/list_shifts.html",
        shifts=shifts,
        morning_count=morning_count,
        evening_count=evening_count,
        avg_duration=avg_duration
    )


# ---------- CREATE SHIFT (POST only - modal submission) ----------
@hr_admin_bp.route("/shifts/create", methods=["POST"])
@login_required
@admin_required
def create_shift():
    """Handle shift creation from modal form"""
    name = request.form.get("name", "").strip()
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")

    if not name or not start_time or not end_time:
        flash("All fields are required.", "warning")
        return redirect(url_for("hr_admin_bp.list_shifts"))

    try:
        shift = Shift(
            name=name,
            start_time=datetime.strptime(start_time, "%H:%M").time(),
            end_time=datetime.strptime(end_time, "%H:%M").time()
        )
        db.session.add(shift)
        db.session.commit()
        flash(f"Shift '{name}' created successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error creating shift: {str(e)}", "error")
    
    return redirect(url_for("hr_admin_bp.list_shifts"))


# ---------- UPDATE SHIFT (POST only - modal submission) ----------
@hr_admin_bp.route("/shifts/edit/<int:shift_id>", methods=["POST"])
@login_required
@admin_required
def edit_shift(shift_id):
    """Handle shift update from modal form"""
    shift = Shift.query.get_or_404(shift_id)
    
    name = request.form.get("name", "").strip()
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")

    if not name or not start_time or not end_time:
        flash("All fields are required.", "warning")
        return redirect(url_for("hr_admin_bp.list_shifts"))

    try:
        shift.name = name
        shift.start_time = datetime.strptime(start_time, "%H:%M").time()
        shift.end_time = datetime.strptime(end_time, "%H:%M").time()
        db.session.commit()
        flash(f"Shift '{shift.name}' updated successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating shift: {str(e)}", "error")
    
    return redirect(url_for("hr_admin_bp.list_shifts"))


# ---------- DELETE SHIFT ----------
@hr_admin_bp.route("/shifts/delete/<int:shift_id>", methods=["POST"])
@login_required
@admin_required
def delete_shift(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    name = shift.name
    try:
        db.session.delete(shift)
        db.session.commit()
        flash(f"Shift '{name}' deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting shift: {str(e)}", "error")
    
    return redirect(url_for("hr_admin_bp.list_shifts"))