from main_app.extensions import db
from main_app import create_app
from main_app.models.hr_models import Employee, Attendance, LateComputation, extract_late_from_attendance
from datetime import date, timedelta, time
import random

app = create_app()

def random_time(start_hour=7, end_hour=8):
    hour = random.randint(start_hour, end_hour - 1)
    minute = random.randint(0, 59)
    return time(hour, minute)

def random_late_time():
    return time(8, random.randint(1, 15))

def generate_attendance_jan_to_nov():
    with app.app_context():
        employees = Employee.query.all()
        start_date = date(2025, 1, 1)
        end_date = date(2025, 11, 30)

        holidays = [
            date(2025, 1, 1), date(2025, 2, 25), date(2025, 3, 31),
            date(2025, 4, 9), date(2025, 5, 1), date(2025, 6, 12),
            date(2025, 8, 21), date(2025, 8, 25),
            date(2025, 11, 1), date(2025, 11, 2),
        ]

        attendance_objs = []

        # ------------------------------
        # Step 1: Generate Attendance
        # ------------------------------
        for emp in employees:
            current = start_date
            while current <= end_date:
                month_days = []
                month = current.month
                while current.month == month and current <= end_date:
                    if current.weekday() < 5 and current not in holidays:
                        month_days.append(current)
                    current += timedelta(days=1)
                if not month_days:
                    continue

                late_days = random.sample(month_days, min(7, len(month_days)))
                remaining = [d for d in month_days if d not in late_days]
                leave_days = random.sample(remaining, min(2, len(remaining)))
                remaining = [d for d in remaining if d not in leave_days]
                absent_days = random.sample(remaining, min(2, len(remaining)))

                for day in month_days:
                    if day in late_days:
                        status = "Late"
                        time_in = random_late_time()
                        time_out = time(17, 0)
                        remarks = "Late arrival"
                    elif day in leave_days:
                        status = "On Leave"
                        time_in = None
                        time_out = None
                        remarks = "Approved leave"
                    elif day in absent_days:
                        status = "Absent"
                        time_in = None
                        time_out = None
                        remarks = "Absent without notice"
                    else:
                        status = "Present"
                        time_in = random_time()
                        time_out = time(17, 0)
                        remarks = None

                    attendance_objs.append(
                        Attendance(
                            employee_id=emp.id,
                            date=day,
                            time_in=time_in,
                            time_out=time_out,
                            status=status,
                            remarks=remarks
                        )
                    )

        # Bulk insert all Attendance
        db.session.bulk_save_objects(attendance_objs)
        db.session.commit()
        print("✅ Attendance generated successfully!")

        # ------------------------------
        # Step 2: Generate LateComputation
        # ------------------------------
        late_objs = []
        all_attendances = Attendance.query.all()
        for att in all_attendances:
            late_data = extract_late_from_attendance(att)
            if late_data:
                # Avoid duplicates
                existing = LateComputation.query.filter_by(attendance_id=att.id).first()
                if not existing:
                    late_objs.append(
                        LateComputation(
                            employee_id=att.employee_id,
                            attendance_id=att.id,
                            date=att.date,
                            late_days=0,
                            late_hours=late_data["late_hours"],
                            late_minutes=late_data["late_minutes"],
                            day_equivalent=late_data["day_equivalent"],
                            remarks="Auto-generated from attendance"
                        )
                    )

        # Bulk insert all LateComputation
        db.session.bulk_save_objects(late_objs)
        db.session.commit()
        print("✅ LateComputation generated successfully!")

if __name__ == "__main__":
    generate_attendance_jan_to_nov()
