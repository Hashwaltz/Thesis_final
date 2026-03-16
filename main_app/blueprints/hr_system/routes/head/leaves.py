from flask import send_file, render_template, request, url_for, flash, redirect
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from main_app.extensions import db
from main_app.models.hr_models import Department, Employee, Leave, Attendance, LeaveCredit, LeaveType, LeaveCreditHistory
from main_app.helpers.decorators import dept_head_required

from main_app.blueprints.hr_system.routes.head import hr_head_bp

def consume_leave_from_history(employee_id, leave_type_id, leave_date, days_needed=1):
    """
    Consume leave credits starting from the leave month,
    then move to previous months if insufficient.
    Automatically creates missing history rows.
    """

    employee = Employee.query.get(employee_id)

    remaining = days_needed
    current_month = leave_date.replace(day=1)

    while remaining > 0:

        month_label = current_month.strftime("%b %Y")

        history = LeaveCreditHistory.query.filter_by(
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            month=month_label
        ).first()

        # 🔹 If history does not exist, create it with 0 earned
        if not history:
            history = LeaveCreditHistory(
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                earned=0,
                used=0,
                month=month_label
            )
            db.session.add(history)
            db.session.flush()

        available = history.earned - history.used

        if available > 0:
            deduct = min(available, remaining)
            history.used += deduct
            remaining -= deduct

        # move to previous month
        if current_month.month == 1:
            current_month = current_month.replace(year=current_month.year - 1, month=12)
        else:
            current_month = current_month.replace(month=current_month.month - 1)

        # stop before hire date
        if current_month < employee.date_hired.replace(day=1):
            break

    return remaining

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

        leave_type_name = leave.leave_type.name.lower()
        credit_types = ["sick leave", "vacation leave", "terminal leave", "adoption leave"]

        total_days = (leave.end_date - leave.start_date).days + 1
        skipped_dates = []

        sick_type = LeaveType.query.filter_by(name="Sick Leave").first()
        vacation_type = LeaveType.query.filter_by(name="Vacation Leave").first()

        for i in range(total_days):

            leave_date = leave.start_date + timedelta(days=i)

            existing = Attendance.query.filter_by(
                employee_id=employee.id,
                date=leave_date
            ).first()

            if existing and existing.status == "Leave":
                skipped_dates.append(leave_date.strftime("%Y-%m-%d"))
                continue

            working_hours = 0
            remarks = "Unpaid Leave"

            if leave_type_name in credit_types:

                credit_type_id = leave.leave_type_id

                # Vacation special rule
                if leave_type_name == "vacation leave":

                    vacation_remaining = consume_leave_from_history(
                        employee.id,
                        vacation_type.id,
                        leave_date,
                        1
                    )

                    if vacation_remaining == 0:
                        working_hours = 8
                        remarks = "Paid Vacation Leave"

                    else:
                        sick_remaining = consume_leave_from_history(
                            employee.id,
                            sick_type.id,
                            leave_date,
                            1
                        )

                        if sick_remaining == 0:
                            working_hours = 8
                            remarks = "Paid Sick Leave (Vacation ≤5)"

                else:

                    remaining = consume_leave_from_history(
                        employee.id,
                        credit_type_id,
                        leave_date,
                        1
                    )

                    if remaining == 0:
                        working_hours = 8
                        remarks = f"Paid {leave.leave_type.name}"

            attendance = Attendance(
                employee_id=employee.id,
                date=leave_date,
                status="Leave",
                working_hours=working_hours,
                remarks=remarks
            )

            db.session.add(attendance)

        if skipped_dates:
            flash(
                f"Some dates already had leave records: {', '.join(skipped_dates)}",
                "warning"
            )

    try:
        db.session.commit()
        flash(f"Leave request {status.lower()} successfully!", "success")

    except Exception as e:
        db.session.rollback()
        flash("Error updating leave request.", "error")
        print(e)

    return redirect(url_for('hr_head_bp.leaves'))