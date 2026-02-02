from main_app.extensions import db
from datetime import datetime
from main_app.models.hr_models import Employee


# =========================================================
# PAYROLL TABLE
# =========================================================
class Payroll(db.Model):
    __tablename__ = "payroll"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    pay_period_id = db.Column(db.Integer, db.ForeignKey('payroll_period.id'), nullable=False)
    pay_period_start = db.Column(db.Date, nullable=False)
    pay_period_end = db.Column(db.Date, nullable=False)
    basic_salary = db.Column(db.Float, nullable=False)

    # 🕒 Added for time-based computation
    working_hours = db.Column(db.Float, default=0)

    overtime_hours = db.Column(db.Float, default=0)
    overtime_pay = db.Column(db.Float, default=0)
    holiday_pay = db.Column(db.Float, default=0)
    night_differential = db.Column(db.Float, default=0)
    gross_pay = db.Column(db.Float, nullable=False, default=0)

    sss_contribution = db.Column(db.Float, default=0)
    philhealth_contribution = db.Column(db.Float, default=0)
    pagibig_contribution = db.Column(db.Float, default=0)
    tax_withheld = db.Column(db.Float, default=0)
    other_deductions = db.Column(db.Float, default=0)
    total_deductions = db.Column(db.Float, default=0)
    net_pay = db.Column(db.Float, nullable=False, default=0)

    status = db.Column(db.String(50), default="Draft")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    employee = db.relationship('Employee', back_populates='payrolls', lazy=True)
    pay_period = db.relationship('PayrollPeriod', back_populates='payrolls', lazy=True)

    def calculate_earnings(self):
        basic = self.basic_salary or 0
        work_hours = self.working_hours or 0
        overtime_hours = self.overtime_hours or 0
        holiday = self.holiday_pay or 0
        night_diff = self.night_differential or 0

        # Hourly rate
        hourly_rate = basic / 160 if basic > 0 else 0
        base_earnings = hourly_rate * work_hours

        # Overtime
        self.overtime_pay = hourly_rate * 1.25 * overtime_hours

        # Add allowances dynamically
        allowances = self.total_allowance

        # Gross pay = base + overtime + holiday + night_diff + allowances
        self.gross_pay = base_earnings + self.overtime_pay + holiday + night_diff + allowances

        # Deductions = sss + philhealth + pagibig + tax + other dynamic deductions
        dynamic_deductions = self.total_other_deductions
        self.total_deductions = sum([
            self.sss_contribution or 0,
            self.philhealth_contribution or 0,
            self.pagibig_contribution or 0,
            self.tax_withheld or 0,
            self.other_deductions or 0,
            dynamic_deductions
        ])

        # Net pay
        self.net_pay = self.gross_pay - self.total_deductions

        return {
            "hourly_rate": hourly_rate,
            "base_earnings": base_earnings,
            "overtime_pay": self.overtime_pay,
            "allowances": allowances,
            "gross_pay": self.gross_pay,
            "total_deductions": self.total_deductions,
            "net_pay": self.net_pay
        }

    def __repr__(self):
        return f'<Payroll {self.employee_id} - {self.pay_period_start} to {self.pay_period_end}>'

    def total_deductions_calc(self):
        return sum([
            self.sss_contribution or 0,
            self.philhealth_contribution or 0,
            self.pagibig_contribution or 0,
            self.tax_withheld or 0,
            self.other_deductions or 0
        ])

    def calculate_net_pay(self):
        """Compute net pay using gross_pay minus total_deductions."""
        self.calculate_total_deductions()
        self.net_pay = (self.gross_pay or 0) - self.total_deductions
        return self.net_pay
    
    @property
    def total_allowance(self):
        """Sum all active allowances for this employee."""
        if not self.employee or not hasattr(self.employee, "employee_allowances"):
            return 0
        return sum(
            ea.allowance.amount
            for ea in self.employee.employee_allowances
            if ea.allowance.active
        )

    @property
    def total_other_deductions(self):
        """Sum all active deductions for this employee."""
        if not self.employee or not hasattr(self.employee, "employee_deductions"):
            return 0
        return sum(
            ed.deduction.amount
            for ed in self.employee.employee_deductions
            if ed.deduction.active
        )

# =========================================================
# PAYSLIP
# =========================================================
class Payslip(db.Model):
    __tablename__ = "payslip"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    payroll_id = db.Column(db.Integer, db.ForeignKey('payroll.id'), nullable=False)
    payslip_number = db.Column(db.String(50), unique=True, nullable=False)
    pay_period_start = db.Column(db.Date, nullable=False)
    pay_period_end = db.Column(db.Date, nullable=False)
    basic_salary = db.Column(db.Float, nullable=False)
    overtime_pay = db.Column(db.Float, default=0)
    holiday_pay = db.Column(db.Float, default=0)
    night_differential = db.Column(db.Float, default=0)
    allowances = db.Column(db.Float, default=0)
    gross_pay = db.Column(db.Float, nullable=False)
    sss_contribution = db.Column(db.Float, default=0)
    philhealth_contribution = db.Column(db.Float, default=0)
    pagibig_contribution = db.Column(db.Float, default=0)
    tax_withheld = db.Column(db.Float, default=0)
    other_deductions = db.Column(db.Float, default=0)
    total_deductions = db.Column(db.Float, default=0)
    net_pay = db.Column(db.Float, nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    generated_by = db.Column(db.Integer)
    status = db.Column(db.String(50), default="Generated")
    approved_by = db.Column(db.Integer, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)
    claimed = db.Column(db.Boolean, default=False)



    employee = db.relationship('Employee', back_populates='payslips', lazy=True)
    payroll = db.relationship('Payroll', backref='payslips', lazy=True)

    def __repr__(self):
        return f'<Payslip {self.payslip_number}>'


# =========================================================
# DEDUCTION / ALLOWANCE / TAX
# =========================================================
class Deduction(db.Model):
    __tablename__ = "deduction"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    type = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, default=0)
    percentage = db.Column(db.Float, default=0)
    is_mandatory = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee_links = db.relationship('EmployeeDeduction', back_populates='deduction', lazy=True)

    def __repr__(self):
        return f'<Deduction {self.name}>'


class Allowance(db.Model):
    __tablename__ = "allowance"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    type = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, default=0)
    percentage = db.Column(db.Float, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee_links = db.relationship('EmployeeAllowance', back_populates='allowance', lazy=True)

    def __repr__(self):
        return f'<Allowance {self.name}>'


class Tax(db.Model):
    __tablename__ = "tax"

    id = db.Column(db.Integer, primary_key=True)
    min_income = db.Column(db.Float, nullable=False)
    max_income = db.Column(db.Float, nullable=False)
    tax_rate = db.Column(db.Float, nullable=False)
    fixed_amount = db.Column(db.Float, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Tax {self.min_income} - {self.max_income}>'


# =========================================================
# PAYROLL PERIOD
# =========================================================
class PayrollPeriod(db.Model):
    __tablename__ = 'payroll_period'

    id = db.Column(db.Integer, primary_key=True)
    period_name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    pay_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50), default="Open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payrolls = db.relationship('Payroll', back_populates='pay_period', lazy=True)

    def __repr__(self):
        return f'<PayrollPeriod {self.period_name}>'


# =========================================================
# ASSOCIATION / LINK TABLES
# =========================================================
class EmployeeDeduction(db.Model):
    __tablename__ = "employee_deductions"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    deduction_id = db.Column(db.Integer, db.ForeignKey("deduction.id"), nullable=False)

    employee = db.relationship("Employee", back_populates="employee_deductions")
    deduction = db.relationship("Deduction", back_populates="employee_links")


class EmployeeAllowance(db.Model):
    __tablename__ = "employee_allowances"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    allowance_id = db.Column(db.Integer, db.ForeignKey("allowance.id"), nullable=False)

    employee = db.relationship("Employee", back_populates="employee_allowances")
    allowance = db.relationship("Allowance", back_populates="employee_links")
