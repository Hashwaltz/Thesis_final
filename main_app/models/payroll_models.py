from datetime import datetime
from main_app.extensions import db
from main_app.models.hr_models import Employee

# ================= PAYROLL PERIOD ==================
class PayrollPeriod(db.Model):
    __tablename__ = "payroll_period"

    id = db.Column(db.Integer, primary_key=True)
    period_name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    pay_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(30), default="Open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payrolls = db.relationship("Payroll", back_populates="period", cascade="all, delete-orphan")


# ================= PAYROLL ==================
class Payroll(db.Model):
    __tablename__ = "payroll"

    id = db.Column(db.Integer, primary_key=True)

    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    payroll_period_id = db.Column(db.Integer, db.ForeignKey("payroll_period.id"), nullable=False)

    basic_salary = db.Column(db.Float, default=0)
    working_hours = db.Column(db.Float, default=160)
    overtime_hours = db.Column(db.Float, default=0)
    holiday_pay = db.Column(db.Float, default=0)
    night_diff = db.Column(db.Float, default=0)

    gross_pay = db.Column(db.Float, default=0)
    total_deductions = db.Column(db.Float, default=0)
    net_pay = db.Column(db.Float, default=0)

    status = db.Column(db.String(30), default="Draft")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", back_populates="payrolls")
    period = db.relationship("PayrollPeriod", back_populates="payrolls")
    payslip = db.relationship("Payslip", uselist=False, back_populates="payroll", cascade="all, delete-orphan")

    # ================= COMPUTED VALUES =================
    @property
    def hourly_rate(self):
        """Hourly rate based on standard 160 hours/month."""
        return self.basic_salary / 160 if self.basic_salary else 0

    @property
    def overtime_pay(self):
        """1.25x hourly rate for overtime."""
        return round(self.hourly_rate * 1.25 * self.overtime_hours, 2)

    @property
    def allowance_total(self):
        """Sum of active allowances considering salary brackets."""
        if not self.employee:
            return 0
        total = 0
        for ea in self.employee.employee_allowances:
            if ea.allowance.active:
                min_salary = ea.allowance.min_salary or 0
                max_salary = ea.allowance.max_salary
                salary = self.employee.salary or 0
                if salary >= min_salary and (max_salary is None or salary <= max_salary):
                    total += ea.allowance.amount
        return total

    @property
    def deduction_total(self):
        """Sum of all deductions calculated dynamically by bracket or fixed amount."""
        if not self.employee:
            return 0
        return sum(d.calculate() for d in self.employee.employee_deductions if d.active)

    def calculate(self):
        """Calculate full payroll dynamically."""
        self.basic_salary = self.employee.salary or 0

        base_pay = self.hourly_rate * self.working_hours

        self.gross_pay = round(
            base_pay +
            self.overtime_pay +
            self.holiday_pay +
            self.night_diff +
            self.allowance_total,
            2
        )

        self.total_deductions = round(self.deduction_total, 2)
        self.net_pay = round(self.gross_pay - self.total_deductions, 2)

        return self.net_pay


# ================= PAYSLIP ==================
class Payslip(db.Model):
    __tablename__ = "payslip"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    payroll_id = db.Column(db.Integer, db.ForeignKey("payroll.id"), nullable=False)

    payslip_number = db.Column(db.String(50), unique=True)
    gross_pay = db.Column(db.Float)
    total_deductions = db.Column(db.Float)
    net_pay = db.Column(db.Float)

    generated_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", back_populates="payslips")
    payroll = db.relationship("Payroll", back_populates="payslip")


# ================= MASTER TABLES ==================
class Allowance(db.Model):
    __tablename__ = "allowance"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    amount = db.Column(db.Float)
    active = db.Column(db.Boolean, default=True)
    min_salary = db.Column(db.Float, default=0)
    max_salary = db.Column(db.Float, nullable=True)

    employees = db.relationship("EmployeeAllowance", back_populates="allowance")


class Deduction(db.Model):
    __tablename__ = "deduction"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True)
    min_salary = db.Column(db.Float, default=0)
    max_salary = db.Column(db.Float, nullable=True)
    employees = db.relationship("EmployeeDeduction", back_populates="deduction")


# ================= LINK TABLES ==================
class EmployeeAllowance(db.Model):
    __tablename__ = "employee_allowances"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"))
    allowance_id = db.Column(db.Integer, db.ForeignKey("allowance.id"))

    employee = db.relationship("Employee", back_populates="employee_allowances")
    allowance = db.relationship("Allowance", back_populates="employees")


class EmployeeDeduction(db.Model):
    __tablename__ = "employee_deductions"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"))
    deduction_id = db.Column(db.Integer, db.ForeignKey("deduction.id"))

    amount = db.Column(db.Float, default=0)
    active = db.Column(db.Boolean, default=True)

    employee = db.relationship("Employee", back_populates="employee_deductions")
    deduction = db.relationship("Deduction", back_populates="employees")

    def calculate(self):
        """Calculate deduction based on employee salary and bracket."""
        if not self.active:
            return 0

        salary = self.employee.salary or 0
        # Use employee-specific amount if set
        if self.amount and self.amount > 0:
            return self.amount

        # Otherwise, calculate based on bracket
        d = self.deduction
        # Example: fixed 5% for bracket (you can customize per deduction)
        # You can later add min_salary/max_salary to Deduction if needed
        return round(salary * 0.05, 2)


# ================= TAX TABLE ==================
class Tax(db.Model):
    __tablename__ = "tax"

    id = db.Column(db.Integer, primary_key=True)
    min_income = db.Column(db.Float)
    max_income = db.Column(db.Float)
    rate = db.Column(db.Float)  # e.g., 0.2 for 20%
    fixed = db.Column(db.Float, default=0)

    def compute(self, income):
        """Compute tax for a given income based on bracket."""
        if self.min_income <= income <= self.max_income:
            return round((income * self.rate) + self.fixed, 2)
        return 0
