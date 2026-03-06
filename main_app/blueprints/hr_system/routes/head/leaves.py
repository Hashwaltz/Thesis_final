from flask import send_file,render_template, request, url_for, flash, redirect
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from main_app.extensions import db
from main_app.models.hr_models import Department, Employee, Leave, Attendance, LeaveCredit
from main_app.helpers.decorators import dept_head_required


from main_app.blueprints.hr_system.routes.head import hr_head_bp




@hr_head_bp.route('/leaves')
@login_required
@dept_head_required
def leaves():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    department_employee_ids = [
        e.id for e in Employee.query.filter_by(
            department=current_user.department,
            status="Active"
        ).all()
    ]

    query = Leave.query.filter(Leave.employee_id.in_(department_employee_ids))

    if status_filter:
        query = query.filter_by(status=status_filter)

    leaves = query.order_by(Leave.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('hr/head/leaves.html', leaves=leaves, status_filter=status_filter)



@hr_head_bp.route('/leaves/<int:leave_id>/approve', methods=['POST'])
@login_required
@dept_head_required
def approve_leave(leave_id):

    leave = Leave.query.get_or_404(leave_id)
    employee = Employee.query.get(leave.employee_id)

    # Authorization check
    if employee.department != current_user.department:
        flash('You are not authorized to approve this leave request.', 'error')
        return redirect(url_for('hr_head_bp.leaves'))

    status = request.form.get('status')
    comments = request.form.get('comments', '')

    leave.status = status
    leave.approved_by = current_user.id
    leave.approved_at = datetime.utcnow()
    leave.comments = comments

    if status == "Approved":

        leave_credit = LeaveCredit.query.filter_by(
            employee_id=leave.employee_id,
            leave_type_id=leave.leave_type_id
        ).first()

        # total leave days (inclusive)
        total_days = (leave.end_date - leave.start_date).days + 1

        for day_offset in range(total_days):

            leave_date = leave.start_date + timedelta(days=day_offset)

            # -------------------------
            # Prevent overwriting attendance
            # -------------------------
            existing = Attendance.query.filter_by(
                employee_id=leave.employee_id,
                date=leave_date
            ).first()

            if existing:
                continue

            # -------------------------
            # Determine if paid leave
            # -------------------------
            if leave_credit and leave_credit.remaining_credits() > 0:

                leave_credit.use_credits(1)

                working_hours = 8
                remarks = "Paid Leave"

            else:

                working_hours = 0
                remarks = "Unpaid Leave"

            attendance = Attendance(
                employee_id=leave.employee_id,
                date=leave_date,
                status="Leave",
                working_hours=working_hours,
                remarks=remarks
            )

            db.session.add(attendance)

    try:
        db.session.commit()
        flash(f'Leave request {status.lower()} successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash('Error updating leave request.', 'error')
        print(e)

    return redirect(url_for('hr_head_bp.leaves'))