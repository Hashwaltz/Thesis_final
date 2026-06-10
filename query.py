from datetime import date, time, timedelta
import random

from main_app import create_app
from main_app.extensions import db
from main_app.models.hr_models import Employee, Attendance

# =========================================================
# CREATE FLASK APP CONTEXT
# =========================================================
app = create_app()

with app.app_context():

    # =====================================================
    # DATE RANGE
    # =====================================================
    start_date = date(2026, 1, 1)
    end_date = date(2026, 12, 31)

    # =====================================================
    # GET ALL EMPLOYEES
    # =====================================================
    employees = Employee.query.all()

    if not employees:
        print("No employees found.")
        exit()

    current_date = start_date

    total_created = 0

    while current_date <= end_date:

        # Skip Sundays
        if current_date.weekday() != 6:

            for employee in employees:

                # Randomize attendance status
                chance = random.randint(1, 100)

                # 5% absent
                if chance <= 5:
                    attendance = Attendance(
                        employee_id=employee.id,
                        date=current_date,
                        status="Absent",
                        remarks="Auto-generated absence"
                    )

                else:
                    # Random late minutes
                    late_minutes = random.randint(0, 45)

                    # Base time in = 8:00 AM
                    hour = 8
                    minute = late_minutes

                    # Handle overflow
                    if minute >= 60:
                        hour += 1
                        minute -= 60

                    time_in = time(hour, minute)

                    # Time out = 5:00 PM
                    time_out = time(17, 0)

                    status = "Late" if late_minutes > 0 else "Present"

                    attendance = Attendance(
                        employee_id=employee.id,
                        date=current_date,
                        time_in=time_in,
                        time_out=time_out,
                        status=status,
                        remarks="Auto-generated attendance"
                    )

                db.session.add(attendance)
                total_created += 1

        current_date += timedelta(days=1)

    db.session.commit()

    print(f"Successfully created {total_created} attendance records for 2026.")