from datetime import datetime
from main_app.extensions import db


# ============================================================
# PAYROLL PERIOD
# ============================================================

class PayrollPeriod(db.Model):
    __tablename__ = "payroll_period"

    id = db.Column(db.Integer, primary_key=True)
    period_name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    pay_date = db.Column(db.Date, nullable=False)

    status = db.Column(db.String(30), default="Open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payrolls = db.relationship(
        "Payroll",
        back_populates="period",
        cascade="all, delete-orphan"
    )


# ============================================================
# PAYROLL DEDUCTION (Defined FIRST for safety)
# ============================================================

class PayrollDeduction(db.Model):
    __tablename__ = "payroll_deduction"

    id = db.Column(db.Integer, primary_key=True)

    payroll_id = db.Column(
        db.Integer,
        db.ForeignKey("payroll.id"),
        nullable=False
    )

    deduction_name = db.Column(db.String(100))
    employee_share = db.Column(db.Float, default=0)
    employer_share = db.Column(db.Float, default=0)
    ec = db.Column(db.Float, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# PAYROLL
# ============================================================

class Payroll(db.Model):
    __tablename__ = "payroll"

    id = db.Column(db.Integer, primary_key=True)

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("employee.id"),
        nullable=False
    )

    payroll_period_id = db.Column(
        db.Integer,
        db.ForeignKey("payroll_period.id"),
        nullable=False
    )

    basic_salary = db.Column(db.Float, default=0)
    working_hours = db.Column(db.Float, default=160)
    hours_worked = db.Column(db.Float, default=0)
    days_worked = db.Column(db.Float, default=0)
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

    payslip = db.relationship(
        "Payslip",
        uselist=False,
        back_populates="payroll",
        cascade="all, delete-orphan"
    )

    deduction_breakdown = db.relationship(
        "PayrollDeduction",
        backref="payroll",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    # -----------------------------------------------------
    # COMPUTED VALUES
    # -----------------------------------------------------

    @property
    def hourly_rate(self):
        return self.basic_salary / 160 if self.basic_salary else 0

    @property
    def overtime_pay(self):
        return round(self.hourly_rate * 1.25 * self.overtime_hours, 2)
    
    @property
    def daily_rate(self):
        return (self.employee.salary or 0) / 22 if self.employee else 0

    @property
    def allowance_total(self):
        if not self.employee:
            return 0

        total = 0
        salary = self.employee.salary or 0

        for ea in self.employee.employee_allowances:
            if ea.allowance and ea.allowance.active:

                if salary >= (ea.allowance.min_salary or 0) and \
                   (ea.allowance.max_salary is None or salary <= ea.allowance.max_salary):

                    total += ea.allowance.amount

        return total
    @allowance_total.setter
    def allowance_total(self, value):
        self._allowance_total = value
    # -----------------------------------------------------
    # CORE CALCULATION ENGINE
    # -----------------------------------------------------
    def compute_days_worked(self):
        from main_app.models.hr_models import Attendance

        start = self.period.start_date
        end = self.period.end_date

        attendances = Attendance.query.filter(
            Attendance.employee_id == self.employee_id,
            Attendance.date.between(start, end)
        ).all()

        worked_days = sum(
            1 for a in attendances if a.status in ("Present", "Late")
        )

        return worked_days
    

    def compute_attendance_hours(self):
        from main_app.models.hr_models import Attendance, LateComputation
        from main_app.models.payroll_models import PayrollPeriod

        if self.period:
            start = self.period.start_date
            end = self.period.end_date
        else:
            period = PayrollPeriod.query.get(self.payroll_period_id)
            if not period:
                return 0
            start = period.start_date
            end = period.end_date

        attendances = Attendance.query.filter(
            Attendance.employee_id == self.employee_id,
            Attendance.date.between(start, end)
        ).all()

        total_hours = 0
        for att in attendances:
            if att.status == "Present":
                total_hours += 8
            elif att.status == "Late":
                late_record = LateComputation.query.filter_by(attendance_id=att.id).first()
                late_equivalent = late_record.day_equivalent if late_record else 0
                total_hours += 8 * (1 - late_equivalent)

        return round(total_hours, 2)
    
    
    def calculate(self):

        if not self.employee or not self.period:
            return 0

        # Ensure payroll object is session-bound
        if db.session.object_session(self) is None:
            db.session.add(self)

        # Clear previous breakdowns safely
        self.deduction_breakdown.delete()

        self.basic_salary = self.employee.salary or 0

        emp_type = (
            self.employee.employment_type.name
            if self.employee.employment_type
            else "Regular"
        )

        days_worked = self.compute_days_worked()

        # ===============================
        # PAYMENT ENGINE
        # ===============================

        salary = self.employee.salary or 0

        daily_rate = salary / 22 if salary else 0
        hourly_rate = daily_rate / 8

        base_pay = 0

        # Regular
        if emp_type == "Regular":
            base_pay = daily_rate * days_worked

        # Part-Time
        elif emp_type == "Part-Time":
            base_pay = hourly_rate * (self.employee.attendance_hours or 0)

        # Casual
        elif emp_type == "Casual":
            base_pay = daily_rate * days_worked

        # Job Order (JO)
        elif emp_type == "Job Order (JO)" or self.employee.employment_type_id == 5:
            base_pay = daily_rate * days_worked

        else:
            base_pay = hourly_rate * self.working_hours

        # ===============================
        # Allowances
        # ===============================

        allowance = self.allowance_total

        # ===============================
        # Gross Pay
        # ===============================

        self.gross_pay = round(
            base_pay +
            self.overtime_pay +
            self.holiday_pay +
            self.night_diff +
            allowance,
            2
        )

        # ===============================
        # Deductions Engine
        # ===============================

        total_ded = 0

        for emp_ded in self.employee.employee_deductions:

            if not emp_ded.active:
                continue

            result = emp_ded.calculate()

            total_ded += result.get("employee_share", 0)

            db.session.add(
                PayrollDeduction(
                    payroll=self,
                    deduction_name=emp_ded.deduction.name if emp_ded.deduction else "",
                    employee_share=result.get("employee_share", 0),
                    employer_share=result.get("employer_share", 0),
                    ec=result.get("ec", 0)
                )
            )

        self.total_deductions = round(total_ded, 2)
        self.net_pay = round(self.gross_pay - self.total_deductions, 2)

        return self.net_pay
    def apply_leave_credit_deductions(self, worked_days):
        from main_app.models.hr_models import LeaveCredit

        leave_credits = LeaveCredit.query.filter_by(
            employee_id=self.employee_id
        ).all()

        leave_used = sum(lc.used_credits for lc in leave_credits)

        worked_days -= leave_used

        return max(round(worked_days, 2), 0)
    
    def compute_attendance_days(self):
        from main_app.models.hr_models import Attendance
        from main_app.models.hr_models import LateComputation

        start = self.period.start_date
        end = self.period.end_date

        attendances = Attendance.query.filter(
            Attendance.employee_id == self.employee_id,
            Attendance.date.between(start, end)
        ).all()

        worked_days = 0

        for att in attendances:

            if att.status == "Present":
                worked_days += 1

            elif att.status == "Late":

                late_record = LateComputation.query.filter_by(
                    attendance_id=att.id
                ).first()

                late_equivalent = 0

                if late_record:
                    late_equivalent = late_record.day_equivalent or 0

                worked_days += (1 - late_equivalent)

        return round(worked_days, 2)

# ============================================================
# PAYSLIP
# ============================================================

class Payslip(db.Model):
    __tablename__ = "payslip"

    id = db.Column(db.Integer, primary_key=True)

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("employee.id"),
        nullable=False
    )

    payroll_id = db.Column(
        db.Integer,
        db.ForeignKey("payroll.id"),
        nullable=False
    )

    payslip_number = db.Column(db.String(50), unique=True)

    gross_pay = db.Column(db.Float)
    total_deductions = db.Column(db.Float)
    net_pay = db.Column(db.Float)

    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(30), default="Generated")

    employee = db.relationship("Employee", back_populates="payslips")
    payroll = db.relationship("Payroll", back_populates="payslip")


# ============================================================
# ALLOWANCE
# ============================================================

class Allowance(db.Model):
    __tablename__ = "allowance"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))
    amount = db.Column(db.Float)

    active = db.Column(db.Boolean, default=True)

    min_salary = db.Column(db.Float, default=0)
    max_salary = db.Column(db.Float, nullable=True)

    employees = db.relationship(
        "EmployeeAllowance",
        back_populates="allowance"
    )


# ============================================================
# DEDUCTION MASTER
# ============================================================

class Deduction(db.Model):
    __tablename__ = "deduction"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)

    calculation_type = db.Column(db.String(20), nullable=False)

    rate = db.Column(db.Float)
    ceiling = db.Column(db.Float)
    floor = db.Column(db.Float)

    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    brackets = db.relationship(
        "DeductionBracket",
        back_populates="deduction",
        cascade="all, delete-orphan"
    )

    employees = db.relationship(
        "EmployeeDeduction",
        back_populates="deduction",
        cascade="all, delete-orphan"
    )


# ============================================================
# EMPLOYEE LINK TABLES
# ============================================================

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

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("employee.id"),
        nullable=False
    )

    deduction_id = db.Column(
        db.Integer,
        db.ForeignKey("deduction.id"),
        nullable=False
    )

    override_amount = db.Column(db.Float)
    active = db.Column(db.Boolean, default=True)

    employee = db.relationship("Employee", back_populates="employee_deductions")
    deduction = db.relationship("Deduction", back_populates="employees")

    # -----------------------------------------------------
    # CALCULATION ENGINE
    # -----------------------------------------------------

    def calculate(self):

        salary = self.employee.salary or 0

        if self.override_amount is not None:
            return dict(employee_share=self.override_amount,
                        employer_share=0,
                        ec=0)

        if not self.deduction:
            return dict(employee_share=0, employer_share=0, ec=0)

        d = self.deduction

        # FIXED
        if d.calculation_type == "fixed":
            return dict(employee_share=d.rate or 0,
                        employer_share=0,
                        ec=0)

        # PERCENTAGE
        if d.calculation_type == "percentage":

            base = salary

            if d.ceiling:
                base = min(base, d.ceiling)

            if d.floor:
                base = max(base, d.floor)

            return dict(
                employee_share=round(base * (d.rate or 0), 2),
                employer_share=0,
                ec=0
            )

        # BRACKET
        if d.calculation_type == "bracket":

            for b in d.brackets:
                if b.salary_from <= salary <= b.salary_to:

                    return dict(
                        employee_share=b.employee_share or 0,
                        employer_share=b.employer_share or 0,
                        ec=b.ec or 0
                    )

        # PROGRESSIVE
        if d.calculation_type == "progressive":

            for b in d.brackets:
                if b.salary_from <= salary <= b.salary_to:

                    return dict(
                        employee_share=round(
                            salary * (b.rate or 0) +
                            (b.fixed_amount or 0),
                            2
                        ),
                        employer_share=0,
                        ec=0
                    )

        return dict(employee_share=0, employer_share=0, ec=0)


# ============================================================
# BRACKET
# ============================================================

class DeductionBracket(db.Model):
    __tablename__ = "deduction_bracket"

    id = db.Column(db.Integer, primary_key=True)

    deduction_id = db.Column(
        db.Integer,
        db.ForeignKey("deduction.id"),
        nullable=False
    )

    salary_from = db.Column(db.Float, nullable=False)
    salary_to = db.Column(db.Float, nullable=False)

    employee_share = db.Column(db.Float)
    employer_share = db.Column(db.Float)
    ec = db.Column(db.Float)

    rate = db.Column(db.Float)
    fixed_amount = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    deduction = db.relationship(
        "Deduction",
        back_populates="brackets"
    )


# ============================================================
# TAX
# ============================================================

class Tax(db.Model):

    __tablename__ = "tax"

    id = db.Column(db.Integer, primary_key=True)

    min_income = db.Column(db.Float)
    max_income = db.Column(db.Float)

    rate = db.Column(db.Float)

    fixed = db.Column(db.Float, default=0)

    def compute(self, income):

        if self.min_income <= income <= self.max_income:
            return round((income * self.rate) + (self.fixed or 0), 2)

        return 0