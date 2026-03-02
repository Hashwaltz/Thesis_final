

"""
@hr_admin_bp.route('/review-leaves')
@login_required
@admin_required
def review_leaves():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    query = Leave.query

    # Apply filter if selected
    if status_filter:
        query = query.filter_by(status=status_filter)

    # ✅ Sort: Pending → Approved → Rejected → (None if any)
    query = query.order_by(
        db.case(
            (Leave.status == 'Pending', 0),
            (Leave.status == 'Approved', 1),
            (Leave.status == 'Rejected', 2),
            else_=3
        ),
        Leave.created_at.desc()
    )

    # Pagination
    leaves_paginated = query.paginate(page=page, per_page=20, error_out=False)
    
    return render_template(
        'hr/admin/review_leaves.html',
        leaves=leaves_paginated,
        status_filter=status_filter
    )
"""

"""
@hr_admin_bp.route('/leaves/<int:leave_id>/action', methods=['POST'])
@login_required
@admin_required
def leave_action(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    action = request.form.get('action')  # 'Approved' or 'Rejected'
    comments = request.form.get('comments', '').strip()  # strip extra spaces

    leave.status = action
    leave.comments = comments if comments else None  # set None if empty
    leave.approved_by = current_user.id
    leave.approved_at = datetime.utcnow()

    try:
        db.session.commit()
        flash(f'Leave request {action.lower()} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Leave action error: {e}")
        flash('Error updating leave request.', 'error')

    return redirect(url_for('hr_admin.view_leaves'))
"""






