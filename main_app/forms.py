from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, DateField, TimeField, IntegerField, FloatField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, NumberRange
from datetime import date

# ------------------------
# Authentication Forms
# ------------------------

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me') 
    submit = SubmitField('Login')

class RegistrationForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=100)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Role', choices=[
        ('admin', 'HR Admin'),
        ('officer', 'HR Officer'),
        ('dept_head', 'Department Head'),
        ('employee', 'Employee')
    ], validators=[DataRequired()])
    department = StringField('Department', validators=[Optional(), Length(max=100)])
    position = StringField('Position', validators=[Optional(), Length(max=100)])
    submit = SubmitField('Register')

# ------------------------
# Employee Forms
# ------------------------

class EmployeeForm(FlaskForm):
    employee_id = StringField('Employee ID', validators=[DataRequired(), Length(min=3, max=20)])
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=100)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=100)])
    middle_name = StringField('Middle Name', validators=[Optional(), Length(max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    address = TextAreaField('Address', validators=[Optional()])
    department = SelectField('Department', choices=[
        ('IT', 'Information Technology'),
        ('HR', 'Human Resources'),
        ('Finance', 'Finance'),
        ('Operations', 'Operations'),
        ('Marketing', 'Marketing'),
        ('Sales', 'Sales'),
        ('Admin', 'Administration')
    ], validators=[DataRequired()])
    position = StringField('Position', validators=[DataRequired(), Length(max=100)])
    salary = FloatField('Salary', validators=[Optional(), NumberRange(min=0)])
    date_hired = DateField('Date Hired', validators=[DataRequired()], default=date.today)
    date_of_birth = DateField('Date of Birth', validators=[Optional()])
    gender = SelectField('Gender', choices=[
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other')
    ], validators=[Optional()])
    marital_status = SelectField('Marital Status', choices=[
        ('Single', 'Single'),
        ('Married', 'Married'),
        ('Divorced', 'Divorced'),
        ('Widowed', 'Widowed')
    ], validators=[Optional()])
    emergency_contact = StringField('Emergency Contact', validators=[Optional(), Length(max=100)])
    emergency_phone = StringField('Emergency Phone', validators=[Optional(), Length(max=20)])
    active = BooleanField('Active', default=True)
    submit = SubmitField('Save Employee')

# ------------------------
# Attendance Forms
# ------------------------

class AttendanceForm(FlaskForm):
    employee_id = SelectField('Employee', coerce=int, validators=[DataRequired()])
    date = DateField('Date', validators=[DataRequired()], default=date.today)
    time_in = TimeField('Time In', validators=[Optional()])
    time_out = TimeField('Time Out', validators=[Optional()])
    status = SelectField('Status', choices=[
        ('Present', 'Present'),
        ('Absent', 'Absent'),
        ('Late', 'Late'),
        ('Half Day', 'Half Day')
    ], validators=[DataRequired()])
    remarks = TextAreaField('Remarks', validators=[Optional()])
    submit = SubmitField('Record Attendance')

# ------------------------
# Leave Forms
# ------------------------

class LeaveForm(FlaskForm):
    employee_id = SelectField('Employee', coerce=int, validators=[DataRequired()])
    leave_type = SelectField('Leave Type', choices=[
        ('Sick', 'Sick Leave'),
        ('Vacation', 'Vacation Leave'),
        ('Personal', 'Personal Leave'),
        ('Emergency', 'Emergency Leave'),
        ('Maternity', 'Maternity Leave'),
        ('Paternity', 'Paternity Leave')
    ], validators=[DataRequired()])
    start_date = DateField('Start Date', validators=[DataRequired()])
    end_date = DateField('End Date', validators=[DataRequired()])
    days_requested = IntegerField('Days Requested', validators=[DataRequired(), NumberRange(min=1)])
    reason = TextAreaField('Reason', validators=[DataRequired()])
    submit = SubmitField('Submit Leave Request')

class LeaveApprovalForm(FlaskForm):
    status = SelectField('Status', choices=[
        ('Approved', 'Approve'),
        ('Rejected', 'Reject')
    ], validators=[DataRequired()])
    comments = TextAreaField('Comments', validators=[Optional()])
    submit = SubmitField('Update Status')

# ------------------------
# Department Forms
# ------------------------

class DepartmentForm(FlaskForm):
    name = StringField("Department Name", validators=[DataRequired()])
    description = TextAreaField("Description")
    head_id = SelectField("Department Head", coerce=int, choices=[])
    submit = SubmitField("Submit")




class PayrollPeriodForm(FlaskForm):
    period_name = StringField('Period Name', validators=[DataRequired(), Length(min=2, max=100)])
    start_date = DateField('Start Date', validators=[DataRequired()])
    end_date = DateField('End Date', validators=[DataRequired()])
    pay_date = DateField('Pay Date', validators=[DataRequired()])
    submit = SubmitField('Create Period')

class PayrollForm(FlaskForm):
    employee_id = SelectField('Employee', coerce=int, validators=[DataRequired()])
    pay_period_start = DateField('Pay Period Start', validators=[DataRequired()])
    pay_period_end = DateField('Pay Period End', validators=[DataRequired()])
    basic_salary = FloatField('Basic Salary', validators=[DataRequired(), NumberRange(min=0)])
    overtime_hours = FloatField('Overtime Hours', validators=[Optional(), NumberRange(min=0)])
    overtime_pay = FloatField('Overtime Pay', validators=[Optional(), NumberRange(min=0)])
    holiday_pay = FloatField('Holiday Pay', validators=[Optional(), NumberRange(min=0)])
    night_differential = FloatField('Night Differential', validators=[Optional(), NumberRange(min=0)])
    other_deductions = FloatField('Other Deductions', validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField('Calculate Payroll')

class PayslipForm(FlaskForm):
    employee_id = SelectField('Employee', coerce=int, validators=[DataRequired()])
    payroll_id = SelectField('Payroll Period', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Generate Payslip')

class DeductionForm(FlaskForm):
    name = StringField('Deduction Name', validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    type = SelectField('Type', choices=[
        ('Fixed', 'Fixed Amount'),
        ('Percentage', 'Percentage'),
        ('Variable', 'Variable Amount')
    ], validators=[DataRequired()])
    amount = FloatField('Amount', validators=[Optional(), NumberRange(min=0)])
    percentage = FloatField('Percentage', validators=[Optional(), NumberRange(min=0, max=100)])
    is_mandatory = BooleanField('Mandatory Deduction')
    active = BooleanField('Active', default=True)
    submit = SubmitField('Save Deduction')

class AllowanceForm(FlaskForm):
    name = StringField('Allowance Name', validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    type = SelectField('Type', choices=[
        ('Fixed', 'Fixed Amount'),
        ('Percentage', 'Percentage'),
        ('Variable', 'Variable Amount')
    ], validators=[DataRequired()])
    amount = FloatField('Amount', validators=[Optional(), NumberRange(min=0)])
    percentage = FloatField('Percentage', validators=[Optional(), NumberRange(min=0, max=100)])
    active = BooleanField('Active', default=True)
    submit = SubmitField('Save Allowance')

class TaxForm(FlaskForm):
    min_income = FloatField('Minimum Income', validators=[DataRequired(), NumberRange(min=0)])
    max_income = FloatField('Maximum Income', validators=[DataRequired(), NumberRange(min=0)])
    tax_rate = FloatField('Tax Rate (%)', validators=[DataRequired(), NumberRange(min=0, max=100)])
    fixed_amount = FloatField('Fixed Amount', validators=[Optional(), NumberRange(min=0)])
    active = BooleanField('Active', default=True)
    submit = SubmitField('Save Tax Bracket')

class EmployeeSyncForm(FlaskForm):
    employee_id = StringField('Employee ID', validators=[DataRequired()])
    submit = SubmitField('Sync Employee')

class PayrollSummaryForm(FlaskForm):
    period_id = SelectField('Payroll Period', coerce=int, validators=[DataRequired()])
    department = SelectField('Department', validators=[Optional()])
    submit = SubmitField('Generate Summary')

class PayslipSearchForm(FlaskForm):
    employee_id = SelectField('Employee', coerce=int, validators=[Optional()])
    period_start = DateField('Period Start', validators=[Optional()])
    period_end = DateField('Period End', validators=[Optional()])
    status = SelectField('Status', choices=[
        ('', 'All'),
        ('Generated', 'Generated'),
        ('Sent', 'Sent'),
        ('Downloaded', 'Downloaded')
    ], validators=[Optional()])
    submit = SubmitField('Search')