from datetime import datetime, date
from flask import flash
from sqlalchemy import func
import random
import string

from main_app.models.hr_models import Employee, LeaveCredit, Attendance
from main_app.extensions import db


def compute_days_worked(self):

    if not self.employee or not self.period:
        return 0

    emp_type = self.employee.employment_type.name if self.employee.employment_type else "Regular"

    # Attendance inside payroll period
    attendance_query = Attendance.query.filter(
        Attendance.employee_id == self.employee_id,
        Attendance.date.between(
            self.period.start_date,
            self.period.end_date
        ),
        Attendance.status != "Absent"
    )

    # Count attendance days
    total_days = attendance_query.count()

    # ===============================
    # Employment Type Rules
    # ===============================

    # Regular → Paid monthly rate → count present working days
    if emp_type == "Regular":
        return total_days

    # Part-Time → Hourly rate → use working hours
    elif emp_type == "Part-Time":
        total_hours = attendance_query.with_entities(
            func.sum(Attendance.working_hours)
        ).scalar() or 0

        return round(total_hours, 2)

    # Casual → Daily rate + leave credits
    elif emp_type == "Casual":
        return total_days

    # Job Order → Daily rate no leave credits
    elif emp_type == "Job Order (JO)":
        return total_days

    return total_days

HOUR_TO_DAY = 0.125
MINUTE_TO_DAY = 0.002
def convert_leave_to_points(days=0, hours=0, minutes=0):
    """
    Convert leave usage into fractional day points.
    Matches CSC equivalent table.
    """
    return round(
        days +
        (hours * HOUR_TO_DAY) +
        (minutes * MINUTE_TO_DAY),
        3
    )
# CSC standard monthly accrual
MONTHLY_VL = 1.25
MONTHLY_SL = 1.25

def compute_monthly_leave_credit(employee: Employee):
    """
    Auto compute leave credits based on service duration.
    """

    if not employee.date_hired:
        return

    today = date.today()

    # Working duration
    years = today.year - employee.date_hired.year
    months = today.month - employee.date_hired.month

    total_months = (years * 12) + months

    if total_months <= 0:
        return

    # Total credit earned
    total_vl = total_months * MONTHLY_VL
    total_sl = total_months * MONTHLY_SL

    # Update or create leave credit record
    vl = LeaveCredit.query.filter_by(
        employee_id=employee.id,
        leave_type_id=1   # ← assume 1 = Vacation Leave
    ).first()

    sl = LeaveCredit.query.filter_by(
        employee_id=employee.id,
        leave_type_id=2   # ← assume 2 = Sick Leave
    ).first()

    if vl:
        vl.total_credits = total_vl
    else:
        db.session.add(
            LeaveCredit(
                employee_id=employee.id,
                leave_type_id=1,
                total_credits=total_vl
            )
        )

    if sl:
        sl.total_credits = total_sl
    else:
        db.session.add(
            LeaveCredit(
                employee_id=employee.id,
                leave_type_id=2,
                total_credits=total_sl
            )
        )

    db.session.commit()
class ServiceRegistry:
    """
    Central registry for HR document services
    """

    services = []

    @classmethod
    def register(cls, name, description, icon, endpoint):
        cls.services.append({
            "name": name,
            "description": description,
            "icon": icon,
            "endpoint": endpoint
        })

    @classmethod
    def get_services(cls):
        return cls.services


# --- Safely parse dates ---
def parse_date(date_str, field_name):
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if not (1900 <= date.year <= 2100):
            raise ValueError(f"{field_name} year out of valid range.")
        return date
    
    except ValueError as e:
        flash(f"Invalid {field_name}: {e}", "danger")
    return None



# ----------------- CONFIG -----------------
ALLOWED_EXTENSIONS = {'xls', 'xlsx'}
UPLOAD_FOLDER = "uploads/attendance"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



def generate_password(length=12):
    if length < 12:
        raise ValueError("Password length must be at least 12 characters")

    # Character sets
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?"

    # Ensure at least one of each
    password = [
        random.choice(lowercase),
        random.choice(uppercase),
        random.choice(digits),
        random.choice(symbols)
    ]

    # Fill the rest
    all_chars = lowercase + uppercase + digits + symbols
    password += random.choices(all_chars, k=length - 4)

    # Shuffle for randomness
    random.shuffle(password)

    return ''.join(password)