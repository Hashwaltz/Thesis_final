from main_app.extensions import db
from calendar import monthrange
from datetime import datetime, date, time
from sqlalchemy import event
# =========================================================
# HR MODELS
# =========================================================

class Employee(db.Model):
    __tablename__ = "employee"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_employee_user_id'), unique=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id', name='fk_employee_department_id'))
    position_id = db.Column(db.Integer, db.ForeignKey('position.id', name='fk_employee_position_id'))

    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    barangay = db.Column(db.String(100))
    municipality = db.Column(db.String(100))
    province = db.Column(db.String(100))
    postal_code = db.Column(db.String(10))
    street_address = db.Column(db.String(255))
    salary = db.Column(db.Float)
    date_hired = db.Column(db.Date, nullable=False)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    marital_status = db.Column(db.String(20))
    emergency_contact = db.Column(db.String(100))
    emergency_phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default="Active")
    archived = db.Column(db.Boolean, default=False)
    archived_at = db.Column(db.DateTime)
    # Check if this exists:
    cs_eligibility = db.Column(db.String(50))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship("User", back_populates="employee_profile", uselist=False)
    department = db.relationship("Department", back_populates="employees", foreign_keys=[department_id])
    position = db.relationship("Position", back_populates="employees", foreign_keys=[position_id])
    attendances = db.relationship("Attendance", back_populates="employee", lazy=True)
    leaves = db.relationship("Leave", back_populates="employee", lazy=True)
    # Employee model
    leave_credits = db.relationship("LeaveCredit", back_populates="employee", lazy=True)
    # Payroll-related relationships
    payrolls = db.relationship("Payroll", back_populates="employee", lazy=True)
    payslips = db.relationship("Payslip", back_populates="employee", lazy=True)
    employee_deductions = db.relationship("EmployeeDeduction", back_populates="employee", lazy=True, cascade="all, delete-orphan")
    employee_allowances = db.relationship("EmployeeAllowance", back_populates="employee", lazy=True, cascade="all, delete-orphan")
    employment_type_id = db.Column(db.Integer, db.ForeignKey("employment_type.id", name="fk_employee_employment_type_id"))
    employment_type = db.relationship("EmploymentType", back_populates="employees", foreign_keys=[employment_type_id])



    # ✅ Convenient relationships (view-only)
    deductions = db.relationship(
        "Deduction",
        secondary="employee_deductions",
        viewonly=True,
        lazy="joined"
    )
    allowances = db.relationship(
        "Allowance",
        secondary="employee_allowances",
        viewonly=True,
        lazy="joined"
    )

    def __repr__(self):
        return f"<Employee {self.employee_id}: {self.first_name} {self.last_name}>"

    def get_full_name(self):
        return f"{self.last_name}, {self.first_name} {self.middle_name or ''}".strip()
    
    def get_full_address(self):
        """Conveniently returns formatted full address."""
        parts = [self.street_address, self.barangay, self.municipality, self.province, self.postal_code]
        return ', '.join([p for p in parts if p])


    @property
    def years_of_service(self):
        """Returns total years of service."""
        if not self.date_hired:
            return 0

        today = date.today()

        years = today.year - self.date_hired.year - (
            (today.month, today.day) < (self.date_hired.month, self.date_hired.day)
        )

        return years
    
    def get_working_duration(self):
        if not self.date_hired:
            return "-"

        today = date.today()

        years = today.year - self.date_hired.year
        months = today.month - self.date_hired.month
        days = today.day - self.date_hired.day

        # Adjust negatives
        if days < 0:
            months -= 1
            days += 30

        if months < 0:
            years -= 1
            months += 12

        parts = []

        if years:
            parts.append(f"{years} year{'s' if years != 1 else ''}")

        if months:
            parts.append(f"{months} month{'s' if months != 1 else ''}")

        if days:
            parts.append(f"{days} day{'s' if days != 1 else ''}")

        return " and ".join(parts) if parts else "0 days"
    

    def use_leave(self, leave_type_name: str, days_used: float, month: int, year: int):
        """
        Deduct leave usage from total credits and create history.
        """
        leave_type = LeaveType.query.filter_by(name=leave_type_name).first()
        if not leave_type:
            raise ValueError("Invalid leave type")

        leave_credit = LeaveCredit.query.filter_by(employee_id=self.id, leave_type_id=leave_type.id).first()
        if not leave_credit:
            raise ValueError("Employee has no leave credit for this type")

        leave_credit.used_credits += days_used

        # Record history
        history = LeaveCreditHistory(
            employee_id=self.id,
            leave_type_id=leave_type.id,
            earned=0,
            used=days_used,
            month=f"{month}-{year}"
        )
        db.session.add(history)
        db.session.commit()
# =========================================================
# ATTENDANCE
# =========================================================
class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    time_in = db.Column(db.Time)
    time_out = db.Column(db.Time)
    status = db.Column(db.String(50), default="Present")
    remarks = db.Column(db.Text)
    working_hours = db.Column(db.Float, default=0.0)    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", back_populates="attendances")

    def __repr__(self):
        return f"<Attendance {self.employee_id} - {self.date}>"
    
    def get_shift(self):
            """Return the employee's shift for this attendance date."""
            daily_shift = EmployeeShift.query.filter_by(employee_id=self.employee_id, date=self.date).first()
            if daily_shift:
                return daily_shift.shift
            return getattr(self.employee, "shift", None)  # fallback to default shift

    def check_late(self):
        shift = self.get_shift()
        if not shift or not self.time_in:
            return
        if self.time_in > shift.start_time:
            self.status = "Late"
            self.remarks = f"Late - Time In: {self.time_in.strftime('%I:%M %p')}"
        else:
            self.status = "Present"

    def calculate_working_hours(self):
        shift = self.get_shift()
        if not shift or not self.time_in or not self.time_out:
            self.working_hours = 0.0
            return

        work_start = datetime.combine(self.date, shift.start_time)
        work_end = datetime.combine(self.date, shift.end_time)
        actual_in = datetime.combine(self.date, self.time_in)
        actual_out = datetime.combine(self.date, self.time_out)

        start = max(actual_in, work_start)
        end = min(actual_out, work_end)

        if end <= start:
            self.working_hours = 0.0
            return

        total_hours = (end - start).total_seconds() / 3600
        self.working_hours = round(total_hours - 1, 2) if total_hours > 4 else round(total_hours, 2)
# =========================================================
# EVENT LISTENERS: Auto calculate hours before save
# =========================================================
@event.listens_for(Attendance, "before_insert")
@event.listens_for(Attendance, "before_update")
def calculate_hours_before_save(mapper, connection, target):
    """
    Automatically calculate working hours before saving Attendance record.
    This ensures the working_hours field is always up-to-date.
    """
    target.calculate_working_hours()


# =========================================================
# LEAVE
# =========================================================
class Leave(db.Model):
    __tablename__ = "leave"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_type.id", name="fk_leave_leave_type_id"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days_requested = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default="Pending")
    approved_by = db.Column(db.Integer, db.ForeignKey("user.id", name="fk_leave_approved_by"))
    approved_at = db.Column(db.DateTime)
    comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    paid_days = db.Column(db.Integer, default=0)
    unpaid_days = db.Column(db.Integer, default=0)


    employee = db.relationship("Employee", back_populates="leaves")
    leave_type = db.relationship("LeaveType", back_populates="leaves", foreign_keys=[leave_type_id])
    approver = db.relationship("User", back_populates="approved_leaves", foreign_keys=[approved_by])
    
    def __repr__(self):
        return f"<Leave {self.employee_id} - {self.leave_type_id}>"
    
    def compute_paid_leave(leave):
        leave_type = leave.leave_type

        if not leave_type.max_paid_days:
            leave.paid_days = 0
            leave.unpaid_days = leave.days_requested
            return

        if leave.days_requested <= leave_type.max_paid_days:
            leave.paid_days = leave.days_requested
            leave.unpaid_days = 0
        else:
            leave.paid_days = leave_type.max_paid_days
            leave.unpaid_days = leave.days_requested - leave_type.max_paid_days


# =========================================================
# DEPARTMENT / POSITION / LEAVE TYPE
# =========================================================
class Department(db.Model):
    __tablename__ = "department"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    head_id = db.Column(db.Integer, db.ForeignKey("user.id", name="fk_department_head_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    head = db.relationship("User", back_populates="managed_department", foreign_keys=[head_id])
    employees = db.relationship("Employee", back_populates="department", lazy=True)
    positions = db.relationship("Position", back_populates="department", lazy=True)

    def __repr__(self):
        return f"<Department {self.name}>"


class Position(db.Model):
    __tablename__ = "position"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id", name="fk_position_department_id"))
    

    department = db.relationship("Department", back_populates="positions", foreign_keys=[department_id])
    employees = db.relationship("Employee", back_populates="position", lazy=True)

    def __repr__(self):
        return f"<Position {self.name}>"


class LeaveType(db.Model):
    __tablename__ = 'leave_type'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    max_paid_days = db.Column(db.Integer)   # e.g. 105 for maternity
    max_duration_days = db.Column(db.Integer)  # total allowed leave
    leaves = db.relationship('Leave', back_populates='leave_type', lazy=True)
        
    # LeaveType model
    leave_credits = db.relationship("LeaveCredit", back_populates="leave_type", lazy=True)
    def __repr__(self):
        return f'<LeaveType {self.name}>'



class EmploymentType(db.Model):
    __tablename__ = "employment_type"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # e.g. 'Regular', 'Part-Time', 'Casual'
    description = db.Column(db.Text)

    # Relationship
    employees = db.relationship("Employee", back_populates="employment_type", lazy=True)

    def __repr__(self):
        return f"<EmploymentType {self.name}>"



class LeaveCredit(db.Model):
    __tablename__ = "leave_credit"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_type.id"), nullable=False)
    total_credits = db.Column(db.Float, default=0)   # accumulated leave
    used_credits = db.Column(db.Float, default=0)    # used leave

    employee = db.relationship("Employee", back_populates="leave_credits")
    leave_type = db.relationship("LeaveType", back_populates="leave_credits")

    def remaining_credits(self):
        return self.total_credits - self.used_credits
    
    def add_credits(self, amount):
        self.total_credits += amount

    def use_credits(self, amount):
        self.used_credits += amount



# =========================================================
# CONSTANTS (MATCHES EXCEL FILE)
# =========================================================
WORK_HOURS_PER_DAY = 8
WORK_MINUTES_PER_DAY = 480
HOUR_TO_DAY = 0.125     # 1 / 8
MINUTE_TO_DAY = 0.002   # Excel rounded equivalent


# =========================================================
# MODEL: LateComputation (Excel Table Row Equivalent)
# =========================================================
class LateComputation(db.Model):
    __tablename__ = "late_computation"

    id = db.Column(db.Integer, primary_key=True)

    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    attendance_id = db.Column(db.Integer, db.ForeignKey("attendance.id"), nullable=False, unique=True)

    date = db.Column(db.Date, nullable=False)

    # Raw values (Excel Columns)
    late_days = db.Column(db.Integer, default=0)
    late_hours = db.Column(db.Integer, default=0)
    late_minutes = db.Column(db.Integer, default=0)

    # Final Excel Result Column
    day_equivalent = db.Column(db.Float, nullable=False)

    remarks = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<LateComputation Emp:{self.employee_id} {self.date} = {self.day_equivalent}>"


# =========================================================
# CORE COMPUTATION (EXACT EXCEL LOGIC)
# =========================================================
def compute_late_day_equivalent(days=0, hours=0, minutes=0):
    """
    Matches Excel table exactly:
    - 1 Day    = 1.000
    - 1 Hour   = 0.125
    - 1 Minute = 0.002
    """
    return round(
        (days * 1.0) +
        (hours * HOUR_TO_DAY) +
        (minutes * MINUTE_TO_DAY),
        3
    )


# =========================================================
# ATTENDANCE → LATE CONVERSION
# =========================================================
def extract_late_from_attendance(attendance: Attendance):
    """
    Converts time-in to late hours/minutes
    Official time-in: 8:00 AM
    """
    if not attendance.time_in:
        return None

    if attendance.time_in <= time(8, 0):
        return None

    official = datetime.combine(attendance.date, time(8, 0))
    actual = datetime.combine(attendance.date, attendance.time_in)

    total_minutes = int((actual - official).total_seconds() / 60)

    hours = total_minutes // 60
    minutes = total_minutes % 60

    day_equiv = compute_late_day_equivalent(0, hours, minutes)

    return {
        "late_days": 0,
        "late_hours": hours,
        "late_minutes": minutes,
        "day_equivalent": day_equiv
    }


# =========================================================
# EVENT LISTENER – AUTO CREATE / UPDATE LATE RECORD
# =========================================================
@event.listens_for(Attendance, "after_insert")
@event.listens_for(Attendance, "after_update")
def generate_late_computation(mapper, connection, target):
    late_data = extract_late_from_attendance(target)

    if not late_data:
        return

    existing = LateComputation.query.filter_by(attendance_id=target.id).first()

    if existing:
        existing.late_hours = late_data["late_hours"]
        existing.late_minutes = late_data["late_minutes"]
        existing.day_equivalent = late_data["day_equivalent"]
        existing.remarks = "Updated from attendance"
    else:
        record = LateComputation(
            employee_id=target.employee_id,
            attendance_id=target.id,
            date=target.date,
            late_days=0,
            late_hours=late_data["late_hours"],
            late_minutes=late_data["late_minutes"],
            day_equivalent=late_data["day_equivalent"],
            remarks="Auto-generated from attendance"
        )
        db.session.add(record)

    db.session.commit()




class JobHistory(db.Model):
    __tablename__ = "job_history"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)

    effective_date = db.Column(db.Date, nullable=False)  # Start of appointment
    end_date = db.Column(db.Date, nullable=True)         # End date (if separated)

    position_id = db.Column(db.Integer, db.ForeignKey("position.id"), nullable=True)
    employment_type_id = db.Column(db.Integer, db.ForeignKey("employment_type.id"), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True)

    salary = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), nullable=True)  # Active / Resigned / Terminated / LWOP
    remarks = db.Column(db.Text)                      # Promotions, transfers, cause of separation

    # Relationships
    employee = db.relationship("Employee", backref="job_history", lazy=True)
    position = db.relationship("Position", lazy=True)
    employment_type = db.relationship("EmploymentType", lazy=True)
    department = db.relationship("Department", lazy=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<JobHistory {self.employee.get_full_name()} {self.effective_date} - {self.end_date or 'Present'}>"




class Shift(db.Model):
    __tablename__ = "shift"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # e.g., Morning, Afternoon
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    def __repr__(self):
        return f"<Shift {self.name} ({self.start_time} - {self.end_time})>"
    



class EmployeeShift(db.Model):
    __tablename__ = "employee_shift"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey("shift.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    day_of_week = db.Column(db.String(15), nullable=False)
    status = db.Column(db.String(15), nullable=False, default="active")  

    employee = db.relationship("Employee", backref="daily_shifts", lazy=True)
    shift = db.relationship("Shift", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("employee_id", "date", name="uq_employee_date_shift"),
    )

    def __repr__(self):
        return f"<EmployeeShift {self.employee.get_full_name()} {self.date} -> {self.shift.name}>"
    


class LeaveCreditHistory(db.Model):
    __tablename__ = "leave_credit_history"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_type.id"), nullable=False)
    
    earned = db.Column(db.Float, default=0.0)    # positive when earned
    used = db.Column(db.Float, default=0.0)      # positive when leave is taken
    month = db.Column(db.String(20))             # e.g., "Nov 2026"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref="leave_credit_history", lazy=True)
    leave_type = db.relationship("LeaveType", lazy=True)

    def __repr__(self):
        return f"<LeaveCreditHistory Emp:{self.employee_id} Leave:{self.leave_type_id} Earned:{self.earned} Used:{self.used}>"
    