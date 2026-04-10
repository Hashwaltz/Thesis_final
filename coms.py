from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

def create_data_dictionary():
    doc = Document()
    
    # Title
    title = doc.add_heading('CommitHub - Data Dictionary', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph('Complete database schema documentation for all models.')
    doc.add_paragraph(f'Generated: April 11, 2026')
    doc.add_page_break()
    
    def add_model_table(doc, model_name, description, fields):
        doc.add_heading(model_name, level=1)
        doc.add_paragraph(description)
        
        table = doc.add_table(rows=1, cols=5)
        table.style = 'Table Grid'
        
        # Header row
        headers = ['Column', 'Type', 'Null', 'Default', 'Description']
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            cell.paragraphs[0].runs[0].bold = True
        
        # Data rows - with safe access
        for field in fields:
            row = table.add_row().cells
            row[0].text = field.get('name', '')
            row[1].text = field.get('type', '')
            row[2].text = field.get('null', '')
            row[3].text = str(field.get('default', ''))
            row[4].text = field.get('description', '')
        
        doc.add_paragraph()
    
    # ===== USERS =====
    user_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'email', 'type': 'String(150)', 'null': 'No', 'default': 'NULL', 'description': 'Unique email for login'},
        {'name': 'password', 'type': 'String(150)', 'null': 'No', 'default': 'NULL', 'description': 'Hashed password'},
        {'name': 'first_name', 'type': 'String(100)', 'null': 'No', 'default': 'NULL', 'description': "User's first name"},
        {'name': 'last_name', 'type': 'String(100)', 'null': 'No', 'default': 'NULL', 'description': "User's last name"},
        {'name': 'role', 'type': 'String(50)', 'null': 'No', 'default': 'employee', 'description': 'Role: admin, staff, employee, officer, dept_head'},
        {'name': 'department_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to Department'},
        {'name': 'position', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': 'Job position'},
        {'name': 'active', 'type': 'Boolean', 'null': 'Yes', 'default': 'True', 'description': 'Account active status'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
        {'name': 'last_login', 'type': 'DateTime', 'null': 'Yes', 'default': 'NULL', 'description': 'Last login timestamp'},
        {'name': 'otp_code', 'type': 'String(10)', 'null': 'Yes', 'default': 'NULL', 'description': '2FA OTP code'},
        {'name': 'otp_expiry', 'type': 'DateTime', 'null': 'Yes', 'default': 'NULL', 'description': 'OTP expiration'},
        {'name': 'otp_verified', 'type': 'Boolean', 'null': 'Yes', 'default': 'False', 'description': 'OTP verification status'},
    ]
    add_model_table(doc, 'Users (users)', 'System accounts for authentication and authorization.', user_fields)
    
    # ===== EMPLOYEES =====
    employee_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'String(20)', 'null': 'No', 'default': 'NULL', 'description': 'Unique employee ID'},
        {'name': 'user_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to User (system account)'},
        {'name': 'department_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to Department'},
        {'name': 'position_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to Position'},
        {'name': 'first_name', 'type': 'String(100)', 'null': 'No', 'default': 'NULL', 'description': "First name"},
        {'name': 'last_name', 'type': 'String(100)', 'null': 'No', 'default': 'NULL', 'description': "Last name"},
        {'name': 'middle_name', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': "Middle name"},
        {'name': 'email', 'type': 'String(150)', 'null': 'No', 'default': 'NULL', 'description': 'Work email'},
        {'name': 'phone', 'type': 'String(20)', 'null': 'Yes', 'default': 'NULL', 'description': 'Contact number'},
        {'name': 'barangay', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': 'Barangay'},
        {'name': 'municipality', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': 'City/Municipality'},
        {'name': 'province', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': 'Province'},
        {'name': 'postal_code', 'type': 'String(10)', 'null': 'Yes', 'default': 'NULL', 'description': 'ZIP code'},
        {'name': 'street_address', 'type': 'String(255)', 'null': 'Yes', 'default': 'NULL', 'description': 'Street address'},
        {'name': 'salary', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Basic salary'},
        {'name': 'date_hired', 'type': 'Date', 'null': 'No', 'default': 'NULL', 'description': 'Hire date'},
        {'name': 'date_of_birth', 'type': 'Date', 'null': 'Yes', 'default': 'NULL', 'description': 'Birth date'},
        {'name': 'gender', 'type': 'String(10)', 'null': 'Yes', 'default': 'NULL', 'description': 'Gender'},
        {'name': 'marital_status', 'type': 'String(20)', 'null': 'Yes', 'default': 'NULL', 'description': 'Marital status'},
        {'name': 'emergency_contact', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': 'Emergency contact name'},
        {'name': 'emergency_phone', 'type': 'String(20)', 'null': 'Yes', 'default': 'NULL', 'description': 'Emergency contact phone'},
        {'name': 'status', 'type': 'String(20)', 'null': 'Yes', 'default': 'Active', 'description': 'Employment status'},
        {'name': 'archived', 'type': 'Boolean', 'null': 'Yes', 'default': 'False', 'description': 'Archived flag'},
        {'name': 'archived_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'NULL', 'description': 'Archive timestamp'},
        {'name': 'cs_eligibility', 'type': 'String(50)', 'null': 'Yes', 'default': 'NULL', 'description': 'Civil Service eligibility'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Record creation'},
        {'name': 'updated_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Last update'},
        {'name': 'employment_type_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to EmploymentType'},
    ]
    add_model_table(doc, 'Employees (employee)', 'Employee master data with personal and employment information.', employee_fields)
    
    # ===== PAYROLL PERIOD =====
    pp_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'period_name', 'type': 'String(100)', 'null': 'No', 'default': 'NULL', 'description': 'Period name (e.g., April 2026)'},
        {'name': 'start_date', 'type': 'Date', 'null': 'No', 'default': 'NULL', 'description': 'Period start date'},
        {'name': 'end_date', 'type': 'Date', 'null': 'No', 'default': 'NULL', 'description': 'Period end date'},
        {'name': 'pay_date', 'type': 'Date', 'null': 'No', 'default': 'NULL', 'description': 'Scheduled pay date'},
        {'name': 'status', 'type': 'String(30)', 'null': 'Yes', 'default': 'Open', 'description': 'Open/Closed/Processing'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Payroll Period (payroll_period)', 'Defines payroll periods with date ranges and status.', pp_fields)
    
    # ===== PAYROLL =====
    payroll_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'payroll_period_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to PayrollPeriod'},
        {'name': 'basic_salary', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Basic salary for period'},
        {'name': 'working_hours', 'type': 'Float', 'null': 'Yes', 'default': '160', 'description': 'Standard hours'},
        {'name': 'hours_worked', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Actual hours worked'},
        {'name': 'days_worked', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Days worked'},
        {'name': 'overtime_hours', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Overtime hours'},
        {'name': 'holiday_pay', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Holiday pay amount'},
        {'name': 'night_diff', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Night differential'},
        {'name': 'gross_pay', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Gross pay before deductions'},
        {'name': 'total_deductions', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Total deductions'},
        {'name': 'net_pay', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Net take-home pay'},
        {'name': 'status', 'type': 'String(30)', 'null': 'Yes', 'default': 'Draft', 'description': 'Draft/Approved/Paid'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
        {'name': 'allowance_total', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Total allowances'},
    ]
    add_model_table(doc, 'Payroll (payroll)', 'Individual payroll records with earnings and deductions.', payroll_fields)
    
    # ===== PAYROLL DEDUCTION =====
    pd_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'payroll_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Payroll'},
        {'name': 'deduction_name', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': 'Deduction name'},
        {'name': 'employee_share', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Employee portion'},
        {'name': 'employer_share', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Employer portion'},
        {'name': 'ec', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'EC contribution'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Payroll Deduction (payroll_deduction)', 'Itemized deduction breakdown per payroll.', pd_fields)
    
    # ===== PAYSLIP =====
    payslip_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'payroll_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Payroll'},
        {'name': 'payslip_number', 'type': 'String(50)', 'null': 'Yes', 'default': 'NULL', 'description': 'Unique reference'},
        {'name': 'gross_pay', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Gross amount'},
        {'name': 'total_deductions', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Total deductions'},
        {'name': 'net_pay', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Net amount'},
        {'name': 'generated_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Generation time'},
        {'name': 'status', 'type': 'String(30)', 'null': 'Yes', 'default': 'Generated', 'description': 'Payslip status'},
    ]
    add_model_table(doc, 'Payslip (payslip)', 'Generated payslip documents for employees.', payslip_fields)
    
    # ===== DEDUCTION =====
    ded_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'name', 'type': 'String(100)', 'null': 'No', 'default': 'NULL', 'description': 'Deduction name (SSS, etc.)'},
        {'name': 'description', 'type': 'Text', 'null': 'Yes', 'default': 'NULL', 'description': 'Description'},
        {'name': 'calculation_type', 'type': 'String(20)', 'null': 'No', 'default': 'NULL', 'description': 'fixed/percentage/bracket/progressive'},
        {'name': 'rate', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Percentage rate'},
        {'name': 'ceiling', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Max salary ceiling'},
        {'name': 'floor', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Min salary floor'},
        {'name': 'active', 'type': 'Boolean', 'null': 'Yes', 'default': 'True', 'description': 'Active status'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Deduction (deduction)', 'Master deduction types with calculation rules.', ded_fields)
    
    # ===== EMPLOYEE DEDUCTION =====
    emp_ded_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'deduction_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Deduction'},
        {'name': 'override_amount', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Custom amount override'},
        {'name': 'active', 'type': 'Boolean', 'null': 'Yes', 'default': 'True', 'description': 'Active for employee'},
    ]
    add_model_table(doc, 'Employee Deduction (employee_deductions)', 'Links employees to deductions with overrides.', emp_ded_fields)
    
    # ===== DEDUCTION BRACKET =====
    bracket_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'deduction_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Deduction'},
        {'name': 'salary_from', 'type': 'Float', 'null': 'No', 'default': 'NULL', 'description': 'Min salary for bracket'},
        {'name': 'salary_to', 'type': 'Float', 'null': 'No', 'default': 'NULL', 'description': 'Max salary for bracket'},
        {'name': 'employee_share', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Fixed employee amount'},
        {'name': 'employer_share', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Fixed employer amount'},
        {'name': 'ec', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'EC amount'},
        {'name': 'rate', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Progressive rate'},
        {'name': 'fixed_amount', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Fixed progressive amount'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Deduction Bracket (deduction_bracket)', 'Salary brackets for bracket-based deductions.', bracket_fields)
    
    # ===== ALLOWANCE =====
    allow_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'name', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': 'Allowance name'},
        {'name': 'amount', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Allowance amount'},
        {'name': 'active', 'type': 'Boolean', 'null': 'Yes', 'default': 'True', 'description': 'Active status'},
        {'name': 'min_salary', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Min salary requirement'},
        {'name': 'max_salary', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Max salary limit'},
    ]
    add_model_table(doc, 'Allowance (allowance)', 'Master allowance types.', allow_fields)
    
    # ===== EMPLOYEE ALLOWANCE =====
    emp_allow_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'allowance_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to Allowance'},
    ]
    add_model_table(doc, 'Employee Allowance (employee_allowances)', 'Links employees to allowances.', emp_allow_fields)
    
    # ===== LOAN =====
    loan_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'provider', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': 'Provider (Pag-IBIG, SSS)'},
        {'name': 'loan_type', 'type': 'String(100)', 'null': 'Yes', 'default': 'NULL', 'description': 'Loan type'},
        {'name': 'total_amount', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Total loan amount'},
        {'name': 'monthly_payment', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Monthly amortization'},
        {'name': 'remaining_balance', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Outstanding balance'},
        {'name': 'start_date', 'type': 'Date', 'null': 'Yes', 'default': 'NULL', 'description': 'Loan start date'},
        {'name': 'active', 'type': 'Boolean', 'null': 'Yes', 'default': 'True', 'description': 'Active status'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Loan (loan)', 'Employee loans with payment tracking.', loan_fields)
    
    # ===== LOAN PAYMENT =====
    loan_pay_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'loan_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Loan'},
        {'name': 'payroll_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Payroll'},
        {'name': 'amount_paid', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Payment amount'},
        {'name': 'remaining_balance', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Balance after payment'},
        {'name': 'payment_date', 'type': 'Date', 'null': 'Yes', 'default': 'NULL', 'description': 'Payment date'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Loan Payment (loan_payment)', 'Individual loan payment records.', loan_pay_fields)
    
    # ===== ATTENDANCE =====
    att_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'date', 'type': 'Date', 'null': 'No', 'default': 'today', 'description': 'Attendance date'},
        {'name': 'time_in', 'type': 'Time', 'null': 'Yes', 'default': 'NULL', 'description': 'Clock-in time'},
        {'name': 'time_out', 'type': 'Time', 'null': 'Yes', 'default': 'NULL', 'description': 'Clock-out time'},
        {'name': 'status', 'type': 'String(50)', 'null': 'Yes', 'default': 'Present', 'description': 'Present/Late/Absent'},
        {'name': 'remarks', 'type': 'Text', 'null': 'Yes', 'default': 'NULL', 'description': 'Additional notes'},
        {'name': 'working_hours', 'type': 'Float', 'null': 'Yes', 'default': '0.0', 'description': 'Calculated hours'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Attendance (attendance)', 'Daily time records with time-in/out.', att_fields)
    
    # ===== LATE COMPUTATION =====
    late_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'attendance_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Attendance'},
        {'name': 'date', 'type': 'Date', 'null': 'No', 'default': 'NULL', 'description': 'Late date'},
        {'name': 'late_days', 'type': 'Integer', 'null': 'Yes', 'default': '0', 'description': 'Late days count'},
        {'name': 'late_hours', 'type': 'Integer', 'null': 'Yes', 'default': '0', 'description': 'Late hours count'},
        {'name': 'late_minutes', 'type': 'Integer', 'null': 'Yes', 'default': '0', 'description': 'Late minutes count'},
        {'name': 'day_equivalent', 'type': 'Float', 'null': 'No', 'default': 'NULL', 'description': 'Converted to days (1h=0.125, 1m=0.002)'},
        {'name': 'remarks', 'type': 'String(255)', 'null': 'Yes', 'default': 'NULL', 'description': 'Notes'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Late Computation (late_computation)', 'Late arrival calculations in day equivalents.', late_fields)
    
    # ===== LEAVE =====
    leave_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'leave_type_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to LeaveType'},
        {'name': 'start_date', 'type': 'Date', 'null': 'No', 'default': 'NULL', 'description': 'Leave start'},
        {'name': 'end_date', 'type': 'Date', 'null': 'No', 'default': 'NULL', 'description': 'Leave end'},
        {'name': 'days_requested', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'Total days'},
        {'name': 'reason', 'type': 'Text', 'null': 'No', 'default': 'NULL', 'description': 'Reason for leave'},
        {'name': 'status', 'type': 'String(50)', 'null': 'Yes', 'default': 'Pending', 'description': 'Pending/Approved/Denied'},
        {'name': 'approved_by', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to User (approver)'},
        {'name': 'approved_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'NULL', 'description': 'Approval timestamp'},
        {'name': 'comments', 'type': 'Text', 'null': 'Yes', 'default': 'NULL', 'description': 'Approver comments'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Request time'},
        {'name': 'updated_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Last update'},
        {'name': 'paid_days', 'type': 'Integer', 'null': 'Yes', 'default': '0', 'description': 'Paid leave days'},
        {'name': 'unpaid_days', 'type': 'Integer', 'null': 'Yes', 'default': '0', 'description': 'Unpaid leave days'},
        {'name': 'canceled_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'NULL', 'description': 'Cancellation time'},
    ]
    add_model_table(doc, 'Leave (leave)', 'Employee leave requests with approval workflow.', leave_fields)
    
    # ===== LEAVE TYPE =====
    lt_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'name', 'type': 'String(100)', 'null': 'No', 'default': 'NULL', 'description': 'Type name (Vacation, Sick, etc.)'},
        {'name': 'description', 'type': 'Text', 'null': 'Yes', 'default': 'NULL', 'description': 'Description'},
        {'name': 'max_paid_days', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'Max paid days'},
        {'name': 'max_duration_days', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'Max total duration'},
    ]
    add_model_table(doc, 'Leave Type (leave_type)', 'Leave type definitions.', lt_fields)
    
    # ===== LEAVE CREDIT =====
    lc_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'leave_type_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to LeaveType'},
        {'name': 'total_credits', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Accumulated credits'},
        {'name': 'used_credits', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Used credits'},
    ]
    add_model_table(doc, 'Leave Credit (leave_credit)', 'Employee leave balances per type.', lc_fields)
    
    # ===== LEAVE CREDIT HISTORY =====
    lch_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'leave_type_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to LeaveType'},
        {'name': 'earned', 'type': 'Float', 'null': 'Yes', 'default': '0.0', 'description': 'Credits earned'},
        {'name': 'used', 'type': 'Float', 'null': 'Yes', 'default': '0.0', 'description': 'Credits used'},
        {'name': 'month', 'type': 'String(20)', 'null': 'Yes', 'default': 'NULL', 'description': 'Month-Year label'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Leave Credit History (leave_credit_history)', 'Historical leave credit transactions.', lch_fields)
    
    # ===== DEPARTMENT =====
    dept_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'name', 'type': 'String(100)', 'null': 'No', 'default': 'NULL', 'description': 'Department name (unique)'},
        {'name': 'description', 'type': 'Text', 'null': 'Yes', 'default': 'NULL', 'description': 'Description'},
        {'name': 'head_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to User (head)'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
    ]
    add_model_table(doc, 'Department (department)', 'Organizational departments.', dept_fields)
    
    # ===== POSITION =====
    pos_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'name', 'type': 'String(100)', 'null': 'No', 'default': 'NULL', 'description': 'Position name (unique)'},
        {'name': 'description', 'type': 'Text', 'null': 'Yes', 'default': 'NULL', 'description': 'Description'},
        {'name': 'department_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to Department'},
    ]
    add_model_table(doc, 'Position (position)', 'Job positions.', pos_fields)
    
    # ===== EMPLOYMENT TYPE =====
    et_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'name', 'type': 'String(50)', 'null': 'No', 'default': 'NULL', 'description': 'Type: Regular, Part-Time, Casual, JO'},
        {'name': 'description', 'type': 'Text', 'null': 'Yes', 'default': 'NULL', 'description': 'Description'},
    ]
    add_model_table(doc, 'Employment Type (employment_type)', 'Employment classifications.', et_fields)
    
    # ===== SHIFT =====
    shift_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'name', 'type': 'String(50)', 'null': 'No', 'default': 'NULL', 'description': 'Shift name'},
        {'name': 'start_time', 'type': 'Time', 'null': 'No', 'default': 'NULL', 'description': 'Start time'},
        {'name': 'end_time', 'type': 'Time', 'null': 'No', 'default': 'NULL', 'description': 'End time'},
    ]
    add_model_table(doc, 'Shift (shift)', 'Work shift definitions.', shift_fields)
    
    # ===== EMPLOYEE SHIFT =====
    es_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'shift_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Shift'},
        {'name': 'date', 'type': 'Date', 'null': 'No', 'default': 'NULL', 'description': 'Assignment date'},
        {'name': 'day_of_week', 'type': 'String(15)', 'null': 'No', 'default': 'NULL', 'description': 'Day name'},
        {'name': 'status', 'type': 'String(15)', 'null': 'No', 'default': 'active', 'description': 'Status'},
    ]
    add_model_table(doc, 'Employee Shift (employee_shift)', 'Daily shift assignments.', es_fields)
    
    # ===== JOB HISTORY =====
    jh_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'employee_id', 'type': 'Integer', 'null': 'No', 'default': 'NULL', 'description': 'FK to Employee'},
        {'name': 'effective_date', 'type': 'Date', 'null': 'No', 'default': 'NULL', 'description': 'Start date'},
        {'name': 'end_date', 'type': 'Date', 'null': 'Yes', 'default': 'NULL', 'description': 'End date'},
        {'name': 'position_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to Position'},
        {'name': 'employment_type_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to EmploymentType'},
        {'name': 'department_id', 'type': 'Integer', 'null': 'Yes', 'default': 'NULL', 'description': 'FK to Department'},
        {'name': 'salary', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Salary during period'},
        {'name': 'status', 'type': 'String(50)', 'null': 'Yes', 'default': 'NULL', 'description': 'Active/Resigned/etc.'},
        {'name': 'remarks', 'type': 'Text', 'null': 'Yes', 'default': 'NULL', 'description': 'Promotion/transfer notes'},
        {'name': 'created_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Creation timestamp'},
        {'name': 'updated_at', 'type': 'DateTime', 'null': 'Yes', 'default': 'utcnow', 'description': 'Last update'},
    ]
    add_model_table(doc, 'Job History (job_history)', 'Employment history and promotions.', jh_fields)
    
    # ===== TAX =====
    tax_fields = [
        {'name': 'id', 'type': 'Integer', 'null': 'No', 'default': 'Auto', 'description': 'Primary key'},
        {'name': 'min_income', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Bracket minimum'},
        {'name': 'max_income', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Bracket maximum'},
        {'name': 'rate', 'type': 'Float', 'null': 'Yes', 'default': 'NULL', 'description': 'Tax rate %'},
        {'name': 'fixed', 'type': 'Float', 'null': 'Yes', 'default': '0', 'description': 'Fixed tax amount'},
    ]
    add_model_table(doc, 'Tax (tax)', 'Income tax brackets and rates.', tax_fields)
    
    # Save
    doc.save('CommitHub_Data_Dictionary.docx')
    print("✓ Data dictionary created: CommitHub_Data_Dictionary.docx")

if __name__ == "__main__":
    create_data_dictionary()