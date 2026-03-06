from datetime import datetime, date
from flask import flash


from main_app.models.hr_models import Employee, LeaveCredit
from main_app.extensions import db

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
