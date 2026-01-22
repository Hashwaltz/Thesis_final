from datetime import datetime, date, timedelta
from functools import wraps
from flask import current_app, request, jsonify, abort
from flask_login import current_user
from main_app.models.hr_models import Department, Employee, Leave, LeaveType, LeaveCredit
from main_app.extensions import db
from main_app.models.user import User
from main_app.models.payroll_models import  Employee as PayrollEmployee, Payroll, Payslip, PayrollPeriod  
import requests
import zipfile, tempfile, shutil, re
import pandas as pd
from sqlalchemy import func, case
# utils/pdf_generator.py 
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, portrait
from reportlab.lib.units import inch
import io, os
from flask import current_app
import matplotlib.pyplot as plt
from twilio.rest import Client




# ------------------------
# Role-based decorators
# ------------------------

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'hr_admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def hr_officer_required(f):
    """Decorator to require HR officer role or higher"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['hr_admin', 'officer']:
            return jsonify({'error': 'HR Officer access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def leave_officer_required(f):
    """Decorator to require HR officer role or higher"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['hr_admin', 'officer', 'leave_officer']:
            return jsonify({'error': 'Leave Officer access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def dept_head_required(f):
    """Decorator to require department head role or higher"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['hr_admin', 'officer', 'leave_officer', 'dept_head']:
            return jsonify({'error': 'Department Head access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def employee_required(f):
    """Decorator to require employee or staff role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['employee', 'staff']:
            return jsonify({'error': 'Employee access required'}), 403
        return f(*args, **kwargs)
    return decorated_function



def payroll_admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'payroll_admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role.lower() not in ["staff", "officer", "dept_head", "admin"]:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function



# ------------------------
# Date & Leave Utilities
# ------------------------

def calculate_working_days(start_date, end_date):
    """Calculate working days between two dates (excluding weekends)"""
    if start_date > end_date:
        return 0
    
    working_days = 0
    current_date = start_date
    
    while current_date <= end_date:
        # Monday = 0, Sunday = 6
        if current_date.weekday() < 5:
            working_days += 1
        current_date += timedelta(days=1)
    
    return working_days

def generate_employee_id(department_id):
    dept = Department.query.get(department_id)
    if not dept:
        dept_code = 'EM'
    else:
        dept_code = ''.join([word[0] for word in dept.name.split()[:2]]).upper()
        if len(dept_code) < 2:
            dept_code = dept.name[:2].upper()

    new_num = 1
    while True:
        new_id = f"{dept_code}-{new_num:04d}"
        exists = Employee.query.filter_by(employee_id=new_id).first()
        if not exists:
            break
        new_num += 1

    return new_id


def send_notification_email(to_email, subject, message):
    """Send notification email (placeholder for email functionality)"""
    print(f"Email to {to_email}: {subject} - {message}")
    return True



def get_attendance_summary(employee_id, start_date, end_date):
    """Get attendance summary for a single employee in a date range"""
    from .models.hr_models import Attendance

    query = Attendance.query.filter(
        Attendance.date >= start_date,
        Attendance.date <= end_date
    )

    if employee_id:
        query = query.filter(Attendance.employee_id == employee_id)

    attendances = query.all()

    return {
        'total_days': len(attendances),
        'present': len([a for a in attendances if a.status == 'Present']),
        'absent': len([a for a in attendances if a.status == 'Absent']),
        'late': len([a for a in attendances if a.status == 'Late']),
        'half_day': len([a for a in attendances if a.status == 'Half Day'])
    }

def get_attendance_chart_data(employee_id=None, start_date=None, end_date=None):
    """
    Get attendance data for charts.
    Returns dict with:
    - dates: list of dates in range
    - present, absent, late, half_day: counts per day
    """
    from .models.hr_models import Attendance
    from datetime import timedelta

    if not start_date or not end_date:
        return {
            'dates': [],
            'present': [],
            'absent': [],
            'late': [],
            'half_day': []
        }

    # Get all attendance records in the range
    query = Attendance.query.filter(
        Attendance.date >= start_date,
        Attendance.date <= end_date
    )
    if employee_id:
        query = query.filter(Attendance.employee_id == employee_id)

    attendances = query.all()

    # Build a dictionary keyed by date for faster lookup
    attendance_by_date = {a.date: a.status for a in attendances}

    # Prepare chart arrays
    dates = []
    present_arr = []
    absent_arr = []
    late_arr = []
    half_day_arr = []

    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date.strftime("%Y-%m-%d"))
        status = attendance_by_date.get(current_date, "Absent")  # Default to Absent if no record

        present_arr.append(1 if status == "Present" else 0)
        absent_arr.append(1 if status == "Absent" else 0)
        late_arr.append(1 if status == "Late" else 0)
        half_day_arr.append(1 if status == "Half Day" else 0)

        current_date += timedelta(days=1)

    return {
        'dates': dates,
        'present': present_arr,
        'absent': absent_arr,
        'late': late_arr,
        'half_day': half_day_arr
    }



def get_department_attendance_summary(department_id, start_date, end_date):
    """Get aggregated attendance summary for a department in a date range"""
    from .models.hr_models import Attendance, Employee

    query = Attendance.query.join(Employee).filter(
        Employee.department_id == department_id,
        Attendance.date >= start_date,
        Attendance.date <= end_date
    )

    # Totals
    total_present = query.filter(Attendance.status == "Present").count()
    total_absent = query.filter(Attendance.status == "Absent").count()
    total_late = query.filter(Attendance.status == "Late").count()
    total_half_day = query.filter(Attendance.status == "Half Day").count()

    # Daily breakdown for charts
    daily_records = (
        query.with_entities(
            Attendance.date,
            func.sum(case((Attendance.status == "Present", 1), else_=0)),
            func.sum(case((Attendance.status == "Absent", 1), else_=0)),
            func.sum(case((Attendance.status == "Late", 1), else_=0))
        )
        .group_by(Attendance.date)
        .order_by(Attendance.date)
        .all()
    )


    return {
        "total_present": total_present,
        "total_absent": total_absent,
        "total_late": total_late,
        "total_half_day": total_half_day,
        "dates": [str(r[0]) for r in daily_records],
        "present_counts": [int(r[1]) for r in daily_records],
        "absent_counts": [int(r[2]) for r in daily_records],
        "late_counts": [int(r[3]) for r in daily_records],
    }


def get_leave_balance(employee_id, leave_type):
    """Get leave balance for an employee (placeholder)"""
    default_balances = {
        'Sick': 15,
        'Vacation': 20,
        'Personal': 5,
        'Emergency': 3,
        'Maternity': 90,
        'Paternity': 7
    }
    return default_balances.get(leave_type, 0)

def sync_with_payroll(employee_data):
    """Sync employee data with payroll system"""
    try:
        payroll_url = current_app.config.get('PAYROLL_SYSTEM_URL', 'http://localhost:5000')
        response = requests.post(
            f"{payroll_url}/api/payroll/employee/sync",
            json=employee_data,
            timeout=30
        )
        return response.status_code == 200
    except requests.RequestException:
        return False

def format_currency(amount):
    """Format amount as currency"""
    return f"₱{amount:,.2f}"

def get_current_month_range():
    """Get start and end dates of current month"""
    today = date.today()
    start_date = date(today.year, today.month, 1)
    
    if today.month == 12:
        end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)
    
    return start_date, end_date




# ----------------- HELPER FUNCTIONS -----------------
def unlock_xlsx(file_path, unlocked_path):
    tmpdir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            z.extractall(tmpdir)

        # remove protection tags
        pat = re.compile(r"<(sheetProtection|workbookProtection)\b[^>]*/>", re.IGNORECASE)
        targets = []

        wb = os.path.join(tmpdir, "xl", "workbook.xml")
        if os.path.exists(wb):
            targets.append(wb)

        wsdir = os.path.join(tmpdir, "xl", "worksheets")
        if os.path.isdir(wsdir):
            for f in os.listdir(wsdir):
                if f.endswith(".xml"):
                    targets.append(os.path.join(wsdir, f))

        for f in targets:
            with open(f, "r", encoding="utf-8") as fh:
                txt = fh.read()
            new = pat.sub("", txt)
            if new != txt:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(new)

        # rezip as unlocked xlsx
        with zipfile.ZipFile(unlocked_path, "w", zipfile.ZIP_DEFLATED) as z:
            for folder, _, files in os.walk(tmpdir):
                for file in files:
                    full = os.path.join(folder, file)
                    arc = os.path.relpath(full, tmpdir).replace("\\", "/")
                    z.write(full, arc)
    finally:
        shutil.rmtree(tmpdir)




def load_excel_to_df(file_path):
    unlocked_path = file_path.replace(".xlsx", "_unlocked.xlsx")
    try:
        unlock_xlsx(file_path, unlocked_path)
        df = pd.read_excel(unlocked_path)
    except Exception:
        df = pd.read_excel(file_path)
    return df


def get_leave_balance(employee_id, leave_type_name):
    """Return remaining leave credits"""
    leave_type = LeaveType.query.filter_by(name=leave_type_name).first()
    if not leave_type:
        return 0
    credit = LeaveCredit.query.filter_by(employee_id=employee_id, leave_type_id=leave_type.id).first()
    if not credit:
        return 0
    return credit.remaining_credits()


# Long Bond: 8.5 x 13 inches -> points (72 points/inch)
PAGE_WIDTH = 8.5 * 72   # 612
PAGE_HEIGHT = 13 * 72   # 936

def _safe_image_path(filename):
    return os.path.join(current_app.root_path, "static", "img", filename)



def generate_csform4_quadrants_pdf(leave, employee):
    """
    Generates an in-memory PDF (Long Bond, 4-quadrant) with the CS Form background
    and the leave/employee data stamped into each quadrant.
    Returns an io.BytesIO buffer ready to send_file().
    """

    def safe(value, default=""):
        """Convert any value to string safely."""
        if value is None:
            return default
        return str(value)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

    # Load background images
    form_bg_path = _safe_image_path("form_bg.png")
    logo_path = _safe_image_path("logo.png")

    quad_w = PAGE_WIDTH / 2
    quad_h = PAGE_HEIGHT / 2

    quadrants = [
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
    ]

    c.setFont("Helvetica", 9)

    # Safe employee fields
    department_name = safe(getattr(employee.department, "name", None), "Human Resource Management Office")
    position_name = safe(getattr(employee.position, "name", None), "")
    salary_str = ""
    try:
        salary_str = f"₱{float(employee.salary):,.2f}"
    except:
        salary_str = safe(employee.salary)

    # Safe name fields
    last = safe(employee.last_name).upper()
    first = safe(employee.first_name).title()
    middle = safe(employee.middle_name)

    fullname_str = f"{last:<20} {first} {middle}"

    # Safe dates
    start_date = leave.start_date.strftime("%B %d, %Y") if leave.start_date else ""
    end_date = leave.end_date.strftime("%B %d, %Y") if leave.end_date else ""
    inclusive_dates = f"{start_date} to {end_date}" if start_date and end_date else ""

    filing_date_str = start_date

    # Leave type
    chosen_type = ""
    if hasattr(leave, "leave_type") and leave.leave_type:
        chosen_type = safe(leave.leave_type.name)
    else:
        chosen_type = safe(leave.leave_type_id)

    # Leave type offsets
    leave_map = {
        "Vacation Leave": 0,
        "Mandatory/Forced Leave": -16,
        "Sick Leave": -32,
        "Maternity Leave": -48,
        "Paternity Leave": -64,
        "Special Privilege Leave": -80,
        "Solo Parent Leave": -96,
        "Study Leave": -112,
        "10-Day VAWC Leave": -128,
        "Rehabilitation Privilege": -144,
        "Special Emergency (Calamity) Leave": -160,
        "Adoption Leave": -176,
        "Others": -192,
    }

    # Leave credits
    vac_total = safe(getattr(employee, "vacation_total", None) or getattr(employee, "vacation_credits", None) or 0)
    sick_total = safe(getattr(employee, "sick_total", None) or getattr(employee, "sick_credits", None) or 0)

    # Approver
    approver = safe(getattr(leave, "approver_name", None) or getattr(employee, "approver", None), "FERNANDO DG. CRUZ")
    mayor_name = "HON. MARIA ELENA L. GERMAR"

    # Render 4 quadrants
    for col, row in quadrants:
        origin_x = col * quad_w
        origin_y = PAGE_HEIGHT - (row + 1) * quad_h

        # Background
        if os.path.exists(form_bg_path):
            try:
                c.drawImage(form_bg_path, origin_x, origin_y,
                            width=quad_w, height=quad_h, mask='auto')
            except:
                pass

        # Logo
        if os.path.exists(logo_path):
            try:
                c.drawImage(
                    logo_path,
                    origin_x + 10,
                    origin_y + quad_h - 50,
                    width=40,
                    height=40,
                    mask='auto'
                )
            except:
                pass

        # === TEXT FIELDS ===
        text_x = origin_x + 80
        text_y_top = origin_y + quad_h - 40

        c.setFont("Helvetica", 8.5)

        # 1. Department
        c.drawString(text_x, text_y_top, "1. OFFICE/DEPARTMENT:")
        c.drawString(text_x + 140, text_y_top, department_name)

        # 2. Name
        name_y = text_y_top - 18
        c.drawString(text_x, name_y, "2. NAME:")
        c.drawString(text_x + 70, name_y, fullname_str)

        # 3. Date of filing
        filing_y = name_y - 18
        c.drawString(text_x, filing_y, "3. DATE OF FILING:")
        c.drawString(text_x + 100, filing_y, filing_date_str)

        # 4. Position
        c.drawString(text_x + 260, filing_y, "4. POSITION:")
        c.drawString(text_x + 320, filing_y, position_name)

        # 5. Salary
        salary_y = filing_y - 16
        c.drawString(text_x + 260, salary_y, "5. SALARY:")
        c.drawString(text_x + 320, salary_y, salary_str)

        # Leave type "X"
        c.setFont("Helvetica-Bold", 12)
        offset = leave_map.get(chosen_type, None)

        if offset is None:
            for k in leave_map:
                if k.lower().split()[0] in chosen_type.lower():
                    offset = leave_map[k]
                    break
        if offset is None:
            offset = 0

        x_mark_x = origin_x + 52
        x_mark_y = origin_y + quad_h - 140 + offset
        c.drawString(x_mark_x, x_mark_y, "X")

        c.setFont("Helvetica", 8)

        # 6.C Days + inclusive dates
        c.drawString(origin_x + 40, origin_y + 170, "6.C NUMBER OF WORKING DAYS APPLIED FOR:")
        c.drawString(origin_x + 300, origin_y + 170, safe(leave.days_requested))

        c.drawString(origin_x + 40, origin_y + 150, "INCLUSIVE DATES:")
        c.drawString(origin_x + 140, origin_y + 150, inclusive_dates)

        # Signature line
        c.line(origin_x + quad_w - 170, origin_y + 130, origin_x + quad_w - 20, origin_y + 130)
        c.setFont("Helvetica", 7.5)
        c.drawString(origin_x + quad_w - 140, origin_y + 116, "(Signature of Applicant)")

        # 7.A Leave credits
        cert_y = origin_y + 110
        c.setFont("Helvetica", 8)
        c.drawString(origin_x + 40, cert_y, "7.A CERTIFICATION OF LEAVE CREDITS:")
        c.drawString(origin_x + 140, cert_y, f"As of {start_date.replace(str(leave.start_date.day)+',', '') if leave.start_date else ''}")
        c.drawString(origin_x + 40, cert_y - 14, f"Total Earned (Vacation): {vac_total}")
        c.drawString(origin_x + 220, cert_y - 14, f"Total Earned (Sick): {sick_total}")

        # 7.B Recommendation
        rec_y = origin_y + 30
        c.drawString(origin_x + quad_w * 0.58, rec_y + 20, "7.B RECOMMENDATION:")
        c.drawString(origin_x + quad_w * 0.58, rec_y, "For approval ____   For disapproval due to: ___________________")

        # Approving Officer
        c.drawString(origin_x + 40, origin_y + 20, approver)
        c.drawString(origin_x + 40, origin_y + 8, "(Authorized Officer)")

        # Mayor
        c.drawString(origin_x + quad_w * 0.44, origin_y + 8, mayor_name)
        c.drawString(origin_x + quad_w * 0.55, origin_y - 4, "Municipal Mayor")

        c.setFont("Helvetica", 9)

    # Finish
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def build_safe_attendance_chart(raw_chart):
    """
    Ensures attendance chart data is ALWAYS JSON serializable
    Prevents 'Undefined is not JSON serializable'
    """
    if raw_chart is None:
        raw_chart = {}

    return {
        "dates": raw_chart.get("dates") or [],
        "present_counts": raw_chart.get("present_counts") or [],
        "absent_counts": raw_chart.get("absent_counts") or [],
        "late_counts": raw_chart.get("late_counts") or []
    }




# ==============================
# CONSTANTS (PH STANDARD)
# ==============================

WORK_HOURS_PER_DAY = 8
MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = WORK_HOURS_PER_DAY * MINUTES_PER_HOUR


# ==============================
# CORE CONVERSIONS
# ==============================

def hours_to_day_fraction(hours: float) -> float:
    """
    Convert working hours to fraction of a day.
    """
    if hours < 0:
        raise ValueError("Hours cannot be negative")

    return round(hours / WORK_HOURS_PER_DAY, 6)



def minutes_to_day_fraction(minutes: int) -> float:
    """
    Convert working minutes to fraction of a day.
    """
    if minutes < 0:
        raise ValueError("Minutes cannot be negative")

    return round(minutes / MINUTES_PER_DAY, 6)


def time_to_day_fraction(hours: int = 0, minutes: int = 0) -> float:
    """
    Convert hours and minutes to fraction of a day.
    """
    if hours < 0 or minutes < 0:
        raise ValueError("Hours and minutes must be non-negative")

    total_minutes = (hours * MINUTES_PER_HOUR) + minutes
    return round(total_minutes / MINUTES_PER_DAY, 6)


def day_fraction_to_time(day_fraction: float) -> tuple:
    """
    Convert fraction of a day to hours and minutes.
    """
    if day_fraction < 0:
        raise ValueError("Day fraction cannot be negative")

    total_minutes = round(day_fraction * MINUTES_PER_DAY)
    hours = total_minutes // MINUTES_PER_HOUR
    minutes = total_minutes % MINUTES_PER_HOUR

    return hours, minutes


# ==============================
# HR / PAYROLL HELPERS
# ==============================

def compute_leave_equivalent(hours: int = 0, minutes: int = 0) -> float:
    """
    Compute leave equivalent in day fraction.
    Used for SL / VL / CTO.
    """
    return time_to_day_fraction(hours, minutes)


def compute_attendance_equivalent(time_in_minutes: int) -> float:
    """
    Convert biometric total minutes to day fraction.
    """
    if time_in_minutes < 0:
        raise ValueError("Time in minutes cannot be negative")

    return round(time_in_minutes / MINUTES_PER_DAY, 6)


def is_full_day(hours: int = 0, minutes: int = 0) -> bool:
    """
    Check if rendered time is equivalent to a full working day.
    """
    return (hours * MINUTES_PER_HOUR + minutes) >= MINUTES_PER_DAY


# ==============================
# ROUNDING (OPTIONAL – CSC STYLE)
# ==============================

def round_day_fraction(day_fraction: float, precision: int = 3) -> float:
    """
    Round day fraction for payroll or CSC reports.
    """
    return round(day_fraction, precision)


def compute_payroll_from_excel(row):
    """
    Compute payroll using the logic shown in the sample payroll Excel file
    and standard PH contribution formulas.
    """

    # --- 1️⃣ Basic Pay ---
    basic_salary = row['Monthly Rate']  # Monthly salary
    daily_rate = basic_salary / 22  # assuming 22 working days
    hourly_rate = daily_rate / 8

    overtime_hours = row.get('Overtime Hours', 0)
    holiday_hours = row.get('Holiday Hours', 0)
    night_hours = row.get('Night Hours', 0)

    # --- 2️⃣ Earnings ---
    overtime_pay = overtime_hours * hourly_rate * 1.25          # 25% OT premium
    holiday_pay = holiday_hours * hourly_rate * 2.0              # 200% for regular holiday
    night_differential = night_hours * hourly_rate * 0.10        # 10% of hourly rate

    gross_pay = basic_salary + overtime_pay + holiday_pay + night_differential

    # --- 3️⃣ Mandatory Deductions (estimated PH computation) ---
    sss_contribution = calculate_sss_contribution(basic_salary)
    philhealth_contribution = calculate_philhealth_contribution(basic_salary)
    pagibig_contribution = calculate_pagibig_contribution(basic_salary)
    tax_withheld = calculate_tax_withheld(gross_pay)

    # --- 4️⃣ Totals ---
    total_deductions = sss_contribution + philhealth_contribution + pagibig_contribution + tax_withheld
    net_pay = gross_pay - total_deductions

    return {
        "basic_salary": basic_salary,
        "overtime_pay": overtime_pay,
        "holiday_pay": holiday_pay,
        "night_differential": night_differential,
        "gross_pay": gross_pay,
        "sss_contribution": sss_contribution,
        "philhealth_contribution": philhealth_contribution,
        "pagibig_contribution": pagibig_contribution,
        "tax_withheld": tax_withheld,
        "total_deductions": total_deductions,
        "net_pay": net_pay
    }


# === Helper Functions ===
def calculate_sss_contribution(salary):
    """Approximate SSS contribution (2025 rates)."""
    if salary <= 3250:
        return 135
    elif salary >= 24750:
        return 1125
    else:
        return 0.045 * salary  # 4.5% (employee share)

def calculate_philhealth_contribution(salary):
    """PhilHealth 2025: 5% of monthly basic salary, divided equally (employee share = 2.5%)."""
    base = min(max(salary, 10000), 100000)  # salary floor/ceiling
    return (base * 0.05) / 2

def calculate_pagibig_contribution(salary):
    """Pag-IBIG: 1% or 2% depending on salary."""
    if salary <= 1500:
        return salary * 0.01
    else:
        return salary * 0.02

def calculate_tax_withheld(gross_pay):
    """Approximate tax using PH TRAIN law brackets."""
    if gross_pay <= 20833:
        return 0
    elif gross_pay <= 33333:
        return (gross_pay - 20833) * 0.20
    elif gross_pay <= 66667:
        return 2500 + (gross_pay - 33333) * 0.25
    elif gross_pay <= 166667:
        return 10833 + (gross_pay - 66667) * 0.30
    elif gross_pay <= 666667:
        return 40833.33 + (gross_pay - 166667) * 0.32
    else:
        return 200833.33 + (gross_pay - 666667) * 0.35

def calculate_overtime_pay(basic_salary, overtime_hours):
    """Calculate overtime pay"""
    hourly_rate = basic_salary / 8 / 22  # Assuming 8 hours per day, 22 working days per month
    return overtime_hours * hourly_rate * 1.25  # 25% overtime premium

def calculate_holiday_pay(basic_salary, holiday_hours):
    """Calculate holiday pay"""
    hourly_rate = basic_salary / 8 / 22
    return holiday_hours * hourly_rate * 2.0  # Double pay for holidays

def calculate_night_differential(basic_salary, night_hours):
    """Calculate night differential pay"""
    hourly_rate = basic_salary / 8 / 22
    return night_hours * hourly_rate * 0.10  # 10% night differential

def generate_payslip_number(employee_id, pay_period_start):
    """Generate unique payslip number"""
    year = pay_period_start.year
    month = pay_period_start.month
    return f"PS{year}{month:02d}{employee_id:04d}"

def sync_employee_from_hr(employee_id):
    """Sync employee data from HR system"""
    try:
        hr_url = current_app.config.get('HR_SYSTEM_URL', 'http://localhost:5001')
        response = requests.get(
            f"{hr_url}/api/hr/employees/{employee_id}",
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return data['data']
        return None
    except requests.RequestException:
        return None

def sync_all_employees_from_hr():
    """Sync all employees from HR system"""
    try:
        hr_url = current_app.config.get('HR_SYSTEM_URL', 'http://localhost:5001')
        response = requests.get(
            f"{hr_url}/api/hr/employees",
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return data['data']
        return []
    except requests.RequestException:
        return []

def format_currency(amount):
    """Format amount as currency"""
    return f"₱{amount:,.2f}"

def get_payroll_periods():
    """Get current payroll periods"""
    from main_app.models.payroll_models import PayrollPeriod
    return PayrollPeriod.query.filter_by(status='Open').all()

def calculate_payroll_summary(period_id, department=None):
    """Calculate payroll summary for a period"""
    from main_app.models.payroll_models import Payroll, Employee
    
    query = Payroll.query.filter_by(id=period_id)
    
    if department:
        query = query.join(Employee).filter(Employee.department == department)
    
    payrolls = query.all()
    
    summary = {
        'total_employees': len(payrolls),
        'total_gross_pay': sum(p.gross_pay for p in payrolls),
        'total_deductions': sum(p.total_deductions for p in payrolls),
        'total_net_pay': sum(p.net_pay for p in payrolls),
        'total_sss': sum(p.sss_contribution for p in payrolls),
        'total_philhealth': sum(p.philhealth_contribution for p in payrolls),
        'total_pagibig': sum(p.pagibig_contribution for p in payrolls),
        'total_tax': sum(p.tax_withheld for p in payrolls)
    }
    
    return summary

def send_payslip_notification(employee_email, payslip_number):
    """Send payslip notification email"""
    # This would integrate with your email service
    print(f"Payslip notification sent to {employee_email}: {payslip_number}")
    return True


def get_payroll_summary():
    """Return summary stats and department data."""
    total_employees = Employee.query.count()
    total_payrolls = Payroll.query.count()
    total_net_pay = Payroll.query.with_entities(func.sum(Payroll.net_pay)).scalar() or 0
    pending = Payroll.query.filter_by(status="Pending").count()
    approved = Payroll.query.filter_by(status="Approved").count()
    rejected = Payroll.query.filter_by(status="Rejected").count()

    dept_data = []
    departments = Department.query.all()
    for dept in departments:
        dept_payrolls = Payroll.query.join(Employee).filter(Employee.department_id == dept.id).count()
        dept_net = Payroll.query.join(Employee).filter(Employee.department_id == dept.id).with_entities(func.sum(Payroll.net_pay)).scalar() or 0
        dept_data.append({'department': dept.name, 'payrolls': dept_payrolls, 'net_pay': dept_net})

    summary = {
        'total_employees': total_employees,
        'total_payrolls': total_payrolls,
        'total_net_pay': total_net_pay,
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        'departments': dept_data
    }
    return summary

def generate_ai_report(summary):
    """Use g4f client to generate AI insights."""
    client = Client()
    dept_summary = ", ".join([f"{d['department']} ({d['payrolls']} payrolls, ₱{d['net_pay']:,.2f})" for d in summary['departments']])
    features = """
    Features:
    - Dashboard overview
    - Employee Payroll Details
    - Add Employee Payroll
    - Payroll Period Management
    - Process Payroll
    - View Payroll History
    - Manage Deductions & Allowances
    - Generate, Approve, Distribute Payslips
    - Payroll Reports
    """

    prompt = f"""
    Payroll Stats:
    Total employees: {summary['total_employees']}
    Total payroll entries: {summary['total_payrolls']}
    Total net pay: ₱{summary['total_net_pay']:,.2f}
    Pending: {summary['pending']}
    Approved: {summary['approved']}
    Rejected: {summary['rejected']}
    Department summary: {dept_summary}

    Based on the payroll system features:
    {features}

    Generate a management report with:
    1. Insights and trends
    2. Department highlights
    3. Suggestions for improvement
    4. Key takeaways
    """

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        web_search=False
    )
    return response.choices[0].message.content

def generate_department_chart(summary):
    """Generate bar chart for departments' net pay."""
    df = pd.DataFrame(summary['departments'])
    plt.figure(figsize=(8,5))
    plt.bar(df['department'], df['net_pay'], color='skyblue')
    plt.xticks(rotation=45, ha='right')
    plt.ylabel("Net Pay (₱)")
    plt.title("Department Net Pay Summary")
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf





def generate_payroll_insights():
    client = Client()

    # Aggregate payroll data
    total_employees = Employee.query.count()
    total_payrolls = Payroll.query.count()
    total_net_pay = Payroll.query.with_entities(func.sum(Payroll.net_pay)).scalar() or 0
    pending_payslips = Payroll.query.filter_by(status="Pending").count()
    approved_payslips = Payroll.query.filter_by(status="Approved").count()
    rejected_payslips = Payroll.query.filter_by(status="Rejected").count()

    # Department level summary
    dept_summary = []
    departments = Department.query.all()
    for dept in departments:
        dept_payrolls = Payroll.query.join(Employee).filter(Employee.department_id == dept.id).count()
        dept_net_pay = Payroll.query.join(Employee).filter(Employee.department_id == dept.id).with_entities(func.sum(Payroll.net_pay)).scalar() or 0
        dept_summary.append(f"{dept.name}: {dept_payrolls} payrolls, ₱{dept_net_pay:,.2f} net pay")

    # Features/Functions context
    features = """
    Features to consider in insights:
    - Dashboard: overview and quick insights
    - View Employee Payroll Details: search/filter by employee
    - Add Employees Payroll: manual input for salary, deductions, allowances
    - Payroll Period Management: cutoff periods
    - Process Payroll: auto compute salaries
    - View Payroll History: reference and audit past payrolls
    - Manage Deductions & Allowances: SSS, PhilHealth, Pag-IBIG, bonuses
    - Generate, Approve, Distribute Payslips
    - Payroll reports: summary, leave, earnings, deduction, compliance
    """

    prompt = f"""
    I have payroll data with the following stats:
    - Total employees: {total_employees}
    - Total payroll entries: {total_payrolls}
    - Total net pay disbursed: ₱{total_net_pay:,.2f}
    - Pending payslips: {pending_payslips}
    - Approved payslips: {approved_payslips}
    - Rejected payslips: {rejected_payslips}
    - Department summary:
      {', '.join(dept_summary)}

    Based on the payroll system features:
    {features}

    Generate a concise management report with:
    1. Insights and trends on payroll efficiency
    2. Departmental highlights
    3. Suggestions for improvement
    4. Key takeaways for management
    """

    # Generate AI report
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        web_search=False
    )

    insights = response.choices[0].message.content
    return insights

def get_current_payroll_period():
    """Get current payroll period"""
    today = date.today()
    
    period = PayrollPeriod.query.filter(
        PayrollPeriod.start_date <= today,
        PayrollPeriod.end_date >= today,
        PayrollPeriod.status == 'Open'
    ).first()
    
    return period

def create_payroll_period(period_name, start_date, end_date, pay_date):
    """Create a new payroll period"""
    period = PayrollPeriod(
        period_name=period_name,
        start_date=start_date,
        end_date=end_date,
        pay_date=pay_date
    )
    
    try:
        db.session.add(period)
        db.session.commit()
        return period
    except Exception as e:
        db.session.rollback()
        return None

def process_payroll_for_employee(employee_id, period_id):
    """Process payroll for a specific employee"""
    
    employee = Employee.query.get(employee_id)
    period = PayrollPeriod.query.get(period_id)
    
    if not employee or not period:
        return None
    
    # Calculate basic salary (assuming monthly)
    basic_salary = employee.basic_salary
    
    # Calculate overtime pay (if any)
    overtime_hours = 0  # This would come from attendance system
    overtime_pay = calculate_overtime_pay(basic_salary, overtime_hours)
    
    # Calculate holiday pay (if any)
    holiday_pay = 0  # This would come from attendance system
    
    # Calculate night differential (if any)
    night_differential = 0  # This would come from attendance system
    
    # Calculate gross pay
    gross_pay = basic_salary + overtime_pay + holiday_pay + night_differential
    
    # Calculate deductions
    sss_contribution = calculate_sss_contribution(basic_salary)
    philhealth_contribution = calculate_philhealth_contribution(basic_salary)
    pagibig_contribution = calculate_pagibig_contribution(basic_salary)
    tax_withheld = calculate_tax_withheld(gross_pay)
    
    total_deductions = sss_contribution + philhealth_contribution + pagibig_contribution + tax_withheld
    
    # Calculate net pay
    net_pay = gross_pay - total_deductions
    
    # Create payroll record
    payroll = Payroll(
        employee_id=employee_id,
        pay_period_start=period.start_date,
        pay_period_end=period.end_date,
        basic_salary=basic_salary,
        overtime_hours=overtime_hours,
        overtime_pay=overtime_pay,
        holiday_pay=holiday_pay,
        night_differential=night_differential,
        gross_pay=gross_pay,
        sss_contribution=sss_contribution,
        philhealth_contribution=philhealth_contribution,
        pagibig_contribution=pagibig_contribution,
        tax_withheld=tax_withheld,
        total_deductions=total_deductions,
        net_pay=net_pay
    )
    
    try:
        db.session.add(payroll)
        db.session.commit()
        return payroll
    except Exception as e:
        db.session.rollback()
        return None


