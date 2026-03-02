from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user

from main_app.helpers.decorators import admin_required
from main_app.models.hr_models import Leave

from main_app.blueprints.hr_system.routes.admin import hr_admin_bp

# ------------------------- Leaves -------------------------
@hr_admin_bp.route('/leaves')
@admin_required
@login_required
def view_leaves():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    query = Leave.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    leaves = query.order_by(Leave.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('hr/admin/leaves/view_leaves.html', leaves=leaves, status_filter=status_filter)
