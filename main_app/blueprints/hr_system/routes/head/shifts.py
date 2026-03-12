from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from datetime import datetime, timedelta, date

from main_app.extensions import db
from main_app.models.hr_models import Employee, EmployeeShift, Shift
from main_app.helpers.decorators import dept_head_required


from main_app.blueprints.hr_system.routes.head import hr_head_bp




@hr_head_bp.route("/current-shifts")
@login_required
@dept_head_required
def current_shifts():
    dept = current_user.managed_department
    if not dept:
        flash("You are not assigned as a department head.", "error")
        return redirect(url_for("hr_head_bp.dashboard"))

    today = datetime.today()
    today_str = today.strftime('%A')  # e.g., 'Monday'

    # Build a dict of employee_id -> list of active shifts
    current_shifts = {}
    for emp in dept.employees:
        shifts = EmployeeShift.query.filter_by(employee_id=emp.id, status="active").all()
        if shifts:
            current_shifts[emp.id] = shifts

    return render_template(
        "hr/head/current_shifts.html",
        employees=dept.employees,
        current_shifts=current_shifts,
        today=today
    )


@hr_head_bp.route("/assign-shifts", methods=["GET", "POST"])
@login_required
@dept_head_required
def assign_shifts():
    dept = current_user.managed_department
    if not dept:
        flash("You are not assigned as a department head.", "error")
        return redirect(url_for("hr_head_bp.dashboard"))

    employees = dept.employees
    shifts = Shift.query.order_by(Shift.start_time).all()
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    if request.method == "POST":
        employee_id = request.form.get("employee_id")
        shift_id = request.form.get("shift_id")
        start_date_str = request.form.get("start_date")
        selected_days = request.form.getlist("weekdays")  # Multiple checkboxes

        if not employee_id or not shift_id or not start_date_str or not selected_days:
            flash("All fields including selected weekdays are required.", "error")
            return redirect(url_for("hr_head_bp.assign_shifts"))

        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = start_date + timedelta(days=6)  # default 1-week schedule

        # 1️⃣ Deactivate all previous shifts for this employee
        EmployeeShift.query.filter_by(employee_id=employee_id, status="active").update({"status": "inactive"})

        # 2️⃣ Insert the new active shifts
        current_date = start_date
        while current_date <= end_date:
            day_name = current_date.strftime("%A")
            if day_name in selected_days:
                new_shift = EmployeeShift(
                    employee_id=employee_id,
                    shift_id=shift_id,
                    date=current_date,
                    day_of_week=day_name,
                    status="active"
                )
                db.session.add(new_shift)
            current_date += timedelta(days=1)

        db.session.commit()
        flash("Shift reassigned successfully. All previous shifts are now inactive.", "success")
        return redirect(url_for("hr_head_bp.current_shifts"))

    return render_template(
        "hr/head/assign_shifts.html",
        employees=employees,
        shifts=shifts,
        weekdays=weekdays
    )


@hr_head_bp.route("/shift-history")
@login_required
@dept_head_required
def shift_history():
    # Get department
    dept = current_user.managed_department
    if not dept:
        flash("You are not assigned as a department head.", "error")
        return redirect(url_for("hr_head_bp.dashboard"))

    # All employees in department
    employees = dept.employees
    employee_ids = [e.id for e in employees]

    # Filter params
    selected_employee = request.args.get("employee_id")
    selected_status = request.args.get("status", "all").lower()

    # Start query
    query = EmployeeShift.query.filter(EmployeeShift.employee_id.in_(employee_ids))

    # Apply employee filter only if provided
    if selected_employee and selected_employee.isdigit():
        query = query.filter(EmployeeShift.employee_id == int(selected_employee))

    # Apply status filter only if not "all"
    if selected_status in ["active", "inactive"]:
        query = query.filter(EmployeeShift.status == selected_status)

    # Order by date descending
    shifts = query.order_by(EmployeeShift.date.desc()).all()

    return render_template(
        "hr/head/shift_history.html",
        shifts=shifts,
        employees=employees,
        selected_employee=int(selected_employee) if selected_employee and selected_employee.isdigit() else None,
        selected_status=selected_status
    )