from datetime import datetime
from flask import flash
from main_app.models.payroll_models import Payslip
from main_app.extensions import db

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


# =========================================================
# HELPER FUNCTION
# =========================================================
def generate_payslip(payroll, generated_by_id=None):
    payslip = Payslip(
        employee_id=payroll.employee_id,
        payroll_id=payroll.id,
        payslip_number=f"PS-{payroll.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        pay_period_start=payroll.pay_period_start,
        pay_period_end=payroll.pay_period_end,
        basic_salary=payroll.basic_salary,
        overtime_pay=payroll.overtime_pay,
        holiday_pay=payroll.holiday_pay,
        night_differential=payroll.night_differential,
        gross_pay=payroll.gross_pay,
        sss_contribution=payroll.sss_contribution,
        philhealth_contribution=payroll.philhealth_contribution,
        pagibig_contribution=payroll.pagibig_contribution,
        tax_withheld=payroll.tax_withheld,
        total_deductions=payroll.total_deductions,
        net_pay=payroll.net_pay,
        generated_by=generated_by_id
    )
    db.session.add(payslip)
    return payslip
