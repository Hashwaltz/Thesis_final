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
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    # Safely parse date strings into date objects
    df = dt = None
    try:
        if date_from:
            df = datetime.strptime(date_from, '%Y-%m-%d').date()
        if date_to:
            dt = datetime.strptime(date_to, '%Y-%m-%d').date()
    except ValueError:
        pass  # Ignore invalid date formats

    department_employee_ids = [
        e.id for e in Employee.query.filter_by(
            department=current_user.department,
            status="Active"
        ).all()
    ]

    query = Leave.query

    if department_employee_ids:
        query = query.filter(Leave.employee_id.in_(department_employee_ids))
    else:
        query = query.filter(False)

    query = query.filter(Leave.status != 'Canceled')

    if status_filter:
        query = query.filter_by(status=status_filter)

    # 🔹 Date range filter using overlap logic
    if df and dt:
        query = query.filter(Leave.start_date <= dt, Leave.end_date >= df)
    elif df:
        query = query.filter(Leave.start_date >= df)
    elif dt:
        query = query.filter(Leave.end_date <= dt)

    leaves = query.order_by(Leave.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    return render_template('hr/head/leaves.html',
                           leaves=leaves,
                           status_filter=status_filter,
                           date_from=date_from,
                           date_to=date_to)


# =========================================================
# 🆕 ENHANCED: CONSUME WITH VL→SL FALLBACK (FOR LATE DEDUCTIONS)
# =========================================================
def consume_leave_with_fallback(employee_id, consumption_date, amount=1.0, preferred_type_name="Vacation Leave", fallback_type_name="Sick Leave"):
    """
    Deducts credits with fallback logic:
    1. Try to deduct from preferred type (e.g., Vacation Leave)
    2. If exhausted, deduct remaining from fallback type (e.g., Sick Leave)
    
    Returns:
        dict: {
            "remaining": float,  # Total remaining across both types
            "vl_deducted": float,
            "sl_deducted": float,
            "unapplied": float   # Amount that couldn't be deducted (no credits left)
        }
    """
    from main_app.models.hr_models import LeaveCredit, LeaveCreditHistory, LeaveType
    from main_app.extensions import db
    
    # Get leave types
    preferred_type = LeaveType.query.filter_by(name=preferred_type_name).first()
    fallback_type = LeaveType.query.filter_by(name=fallback_type_name).first()
    
    if not preferred_type and not fallback_type:
        return {"remaining": 0.0, "vl_deducted": 0, "sl_deducted": 0, "unapplied": amount}
    
    remaining_to_deduct = amount
    preferred_deducted = 0.0
    fallback_deducted = 0.0
    month_label = consumption_date.strftime("%b %Y")
    
    # 🔥 STEP 1: Deduct from preferred type first
    if remaining_to_deduct > 0 and preferred_type:
        credit = LeaveCredit.query.filter_by(
            employee_id=employee_id,
            leave_type_id=preferred_type.id
        ).first()
        
        if not credit:
            credit = LeaveCredit(
                employee_id=employee_id,
                leave_type_id=preferred_type.id,
                total_credits=0.0,
                used_credits=0.0
            )
            db.session.add(credit)
            db.session.flush()
        
        available = max(0.0, credit.total_credits - credit.used_credits)
        to_deduct = min(remaining_to_deduct, available)
        
        if to_deduct > 0:
            credit.used_credits += to_deduct
            preferred_deducted = to_deduct
            remaining_to_deduct -= to_deduct
            
            # Record history
            hist = LeaveCreditHistory.query.filter_by(
                employee_id=employee_id,
                leave_type_id=preferred_type.id,
                month=month_label
            ).first()
            
            if hist:
                hist.used += to_deduct
            else:
                db.session.add(LeaveCreditHistory(
                    employee_id=employee_id,
                    leave_type_id=preferred_type.id,
                    earned=0.0,
                    used=to_deduct,
                    month=month_label
                ))
    
    # 🔥 STEP 2: Deduct remaining from fallback type
    if remaining_to_deduct > 0 and fallback_type:
        credit = LeaveCredit.query.filter_by(
            employee_id=employee_id,
            leave_type_id=fallback_type.id
        ).first()
        
        if not credit:
            credit = LeaveCredit(
                employee_id=employee_id,
                leave_type_id=fallback_type.id,
                total_credits=0.0,
                used_credits=0.0
            )
            db.session.add(credit)
            db.session.flush()
        
        available = max(0.0, credit.total_credits - credit.used_credits)
        to_deduct = min(remaining_to_deduct, available)
        
        if to_deduct > 0:
            credit.used_credits += to_deduct
            fallback_deducted = to_deduct
            remaining_to_deduct -= to_deduct
            
            # Record history
            hist = LeaveCreditHistory.query.filter_by(
                employee_id=employee_id,
                leave_type_id=fallback_type.id,
                month=month_label
            ).first()
            
            if hist:
                hist.used += to_deduct
            else:
                db.session.add(LeaveCreditHistory(
                    employee_id=employee_id,
                    leave_type_id=fallback_type.id,
                    earned=0.0,
                    used=to_deduct,
                    month=month_label
                ))
    
    # Calculate final remaining balance across both types
    total_remaining = 0.0
    for lt in [preferred_type, fallback_type]:
        if lt:
            credit = LeaveCredit.query.filter_by(
                employee_id=employee_id,
                leave_type_id=lt.id
            ).first()
            if credit:
                total_remaining += max(0.0, credit.total_credits - credit.used_credits)
    
    return {
        "remaining": round(total_remaining, 3),
        "vl_deducted": round(preferred_deducted, 3),
        "sl_deducted": round(fallback_deducted, 3),
        "unapplied": round(remaining_to_deduct, 3)
    }




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
        deduction_log = []  # Track what was deducted for debugging

        sick_type = LeaveType.query.filter_by(name="Sick Leave").first()
        vacation_type = LeaveType.query.filter_by(name="Vacation Leave").first()

        for i in range(total_days):
            leave_date = leave.start_date + timedelta(days=i)

            # Skip if attendance already exists for this date
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

                # 🔥 VACATION LEAVE: Apply VL-first fallback policy
                if leave_type_name == "vacation leave" and vacation_type and sick_type:
                    result = consume_leave_with_fallback(
                        employee_id=employee.id,
                        consumption_date=leave_date,
                        amount=1.0,
                        preferred_type_name="Vacation Leave",
                        fallback_type_name="Sick Leave"
                    )
                    
                    if result["vl_deducted"] > 0 or result["sl_deducted"] > 0:
                        working_hours = 8
                        if result["vl_deducted"] > 0:
                            remarks = "Paid Vacation Leave"
                        else:
                            remarks = "Paid Sick Leave (VL exhausted)"
                        
                        deduction_log.append({
                            "date": leave_date,
                            "vl": result["vl_deducted"],
                            "sl": result["sl_deducted"]
                        })

                # 🔥 OTHER CREDIT TYPES: Direct deduction
                else:
                    remaining = consume_leave_from_history(
                        employee.id,
                        credit_type_id,
                        leave_date,
                        1.0
                    )
                    
                    if remaining < 1.0:  # Successfully deducted at least partial
                        working_hours = 8
                        remarks = f"Paid {leave.leave_type.name}"
                        deduction_log.append({
                            "date": leave_date,
                            "type": leave.leave_type.name,
                            "deducted": 1.0 - remaining
                        })

            # Create attendance record
            attendance = Attendance(
                employee_id=employee.id,
                date=leave_date,
                status="Leave",
                working_hours=working_hours,
                remarks=remarks
            )
            db.session.add(attendance)

        if skipped_dates:
            flash(f"⚠️ Skipped existing leave records: {', '.join(skipped_dates)}", "warning")
        
        # Optional: Log deduction summary for debugging
        # print(f"Leave {leave_id} deductions: {deduction_log}")

    try:
        db.session.commit()
        flash(f"✅ Leave request {status.lower()} successfully! Credits deducted.", "success")

    except Exception as e:
        db.session.rollback()
        flash("❌ Error updating leave request.", "error")
        print(f"Approval error: {e}")
        # Optional: Log to error tracking system

    # 🔥 Redirect to where user can see the result
    return redirect(url_for('hr_head_bp.leaves', employee_id=employee.id))