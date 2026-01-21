from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from main_app.models.users import PayrollUser
from main_app.models.payroll_models import Employee, Payroll, Payslip, PayrollPeriod
from main_app.utils import admin_required, staff_required, sync_employee_from_hr, sync_all_employees_from_hr
from main_app.extensions import db
from datetime import datetime, date
from flask_login import UserMixin

payroll_api_bp = Blueprint('payroll_api', __name__)


class PayrollUser(UserMixin):
    """Proxy user loaded from HR system. Payroll DB does not store accounts."""

    def __init__(self, id, email, first_name, last_name, role, active=True, department=None, position=None):
        self.id = id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.active = active
        self.department = department
        self.position = position

    def __repr__(self):
        return f'<PayrollUser {self.email}>'

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def is_admin(self):
        return self.role == "admin"

    def is_staff(self):
        return self.role in ["staff", "admin"]
    


@payroll_api_bp.route('/employees')
@login_required
def get_employees():
    """Get all employees for API consumption"""
    try:
        employees = Employee.query.filter_by(active=True).all()
        employee_data = []
        
        for emp in employees:
            employee_data.append({
                'id': emp.id,
                'employee_id': emp.employee_id,
                'first_name': emp.first_name,
                'last_name': emp.last_name,
                'middle_name': emp.middle_name,
                'email': emp.email,
                'phone': emp.phone,
                'department': emp.department,
                'position': emp.position,
                'basic_salary': emp.basic_salary,
                'date_hired': emp.date_hired.isoformat() if emp.date_hired else None,
                'active': emp.active,
                'created_at': emp.created_at.isoformat(),
                'updated_at': emp.updated_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'data': employee_data,
            'count': len(employee_data)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@payroll_api_bp.route('/employees/<int:employee_id>')
@login_required
def get_employee(employee_id):
    """Get specific employee by ID"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        employee_data = {
            'id': employee.id,
            'employee_id': employee.employee_id,
            'first_name': employee.first_name,
            'last_name': employee.last_name,
            'middle_name': employee.middle_name,
            'email': employee.email,
            'phone': employee.phone,
            'department': employee.department,
            'position': employee.position,
            'basic_salary': employee.basic_salary,
            'date_hired': employee.date_hired.isoformat() if employee.date_hired else None,
            'active': employee.active,
            'created_at': employee.created_at.isoformat(),
            'updated_at': employee.updated_at.isoformat()
        }
        
        return jsonify({
            'success': True,
            'data': employee_data
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@payroll_api_bp.route('/employees/sync', methods=['POST'])
@login_required
@admin_required
def sync_employees():
    """Sync employees from HR system"""
    try:
        hr_employees = sync_all_employees_from_hr()
        
        if not hr_employees:
            return jsonify({
                'success': False,
                'error': 'No employees found in HR system or sync failed'
            }), 400
        
        synced_count = 0
        for emp_data in hr_employees:
            # Check if employee already exists
            existing_employee = Employee.query.filter_by(employee_id=emp_data['employee_id']).first()
            
            if not existing_employee:
                employee = Employee(
                    employee_id=emp_data['employee_id'],
                    first_name=emp_data['first_name'],
                    last_name=emp_data['last_name'],
                    middle_name=emp_data.get('middle_name'),
                    email=emp_data['email'],
                    phone=emp_data.get('phone'),
                    department=emp_data['department'],
                    position=emp_data['position'],
                    basic_salary=emp_data.get('salary', 0),
                    date_hired=datetime.strptime(emp_data['date_hired'], '%Y-%m-%d').date() if emp_data.get('date_hired') else date.today(),
                    active=emp_data.get('active', True)
                )
                db.session.add(employee)
                synced_count += 1
            else:
                # Update existing employee
                existing_employee.first_name = emp_data['first_name']
                existing_employee.last_name = emp_data['last_name']
                existing_employee.middle_name = emp_data.get('middle_name')
                existing_employee.email = emp_data['email']
                existing_employee.phone = emp_data.get('phone')
                existing_employee.department = emp_data['department']
                existing_employee.position = emp_data['position']
                existing_employee.basic_salary = emp_data.get('salary', 0)
                existing_employee.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully synced {synced_count} employees',
            'synced_count': synced_count
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@payroll_api_bp.route('/payroll')
@login_required
def get_payroll():
    """Get payroll records"""
    try:
        employee_id = request.args.get('employee_id')
        period_id = request.args.get('period_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        query = Payroll.query
        
        if employee_id:
            query = query.filter_by(employee_id=employee_id)
        
        if period_id:
            query = query.filter_by(id=period_id)
        
        if start_date:
            query = query.filter(Payroll.pay_period_start >= datetime.strptime(start_date, '%Y-%m-%d').date())
        
        if end_date:
            query = query.filter(Payroll.pay_period_end <= datetime.strptime(end_date, '%Y-%m-%d').date())
        
        payrolls = query.all()
        
        payroll_data = []
        for payroll in payrolls:
            payroll_data.append({
                'id': payroll.id,
                'employee_id': payroll.employee_id,
                'pay_period_start': payroll.pay_period_start.isoformat(),
                'pay_period_end': payroll.pay_period_end.isoformat(),
                'basic_salary': payroll.basic_salary,
                'overtime_hours': payroll.overtime_hours,
                'overtime_pay': payroll.overtime_pay,
                'holiday_pay': payroll.holiday_pay,
                'night_differential': payroll.night_differential,
                'gross_pay': payroll.gross_pay,
                'sss_contribution': payroll.sss_contribution,
                'philhealth_contribution': payroll.philhealth_contribution,
                'pagibig_contribution': payroll.pagibig_contribution,
                'tax_withheld': payroll.tax_withheld,
                'other_deductions': payroll.other_deductions,
                'total_deductions': payroll.total_deductions,
                'net_pay': payroll.net_pay,
                'status': payroll.status,
                'created_at': payroll.created_at.isoformat(),
                'updated_at': payroll.updated_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'data': payroll_data,
            'count': len(payroll_data)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@payroll_api_bp.route('/payslips')
@login_required
def get_payslips():
    """Get payslip records"""
    try:
        employee_id = request.args.get('employee_id')
        status = request.args.get('status')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        query = Payslip.query
        
        if employee_id:
            query = query.filter_by(employee_id=employee_id)
        
        if status:
            query = query.filter_by(status=status)
        
        if start_date:
            query = query.filter(Payslip.pay_period_start >= datetime.strptime(start_date, '%Y-%m-%d').date())
        
        if end_date:
            query = query.filter(Payslip.pay_period_end <= datetime.strptime(end_date, '%Y-%m-%d').date())
        
        payslips = query.all()
        
        payslip_data = []
        for payslip in payslips:
            payslip_data.append({
                'id': payslip.id,
                'employee_id': payslip.employee_id,
                'payslip_number': payslip.payslip_number,
                'pay_period_start': payslip.pay_period_start.isoformat(),
                'pay_period_end': payslip.pay_period_end.isoformat(),
                'basic_salary': payslip.basic_salary,
                'overtime_pay': payslip.overtime_pay,
                'holiday_pay': payslip.holiday_pay,
                'night_differential': payslip.night_differential,
                'allowances': payslip.allowances,
                'gross_pay': payslip.gross_pay,
                'sss_contribution': payslip.sss_contribution,
                'philhealth_contribution': payslip.philhealth_contribution,
                'pagibig_contribution': payslip.pagibig_contribution,
                'tax_withheld': payslip.tax_withheld,
                'other_deductions': payslip.other_deductions,
                'total_deductions': payslip.total_deductions,
                'net_pay': payslip.net_pay,
                'status': payslip.status,
                'generated_at': payslip.generated_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'data': payslip_data,
            'count': len(payslip_data)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@payroll_api_bp.route('/periods')
@login_required
def get_periods():
    """Get payroll periods"""
    try:
        periods = PayrollPeriod.query.all()
        
        period_data = []
        for period in periods:
            period_data.append({
                'id': period.id,
                'period_name': period.period_name,
                'start_date': period.start_date.isoformat(),
                'end_date': period.end_date.isoformat(),
                'pay_date': period.pay_date.isoformat(),
                'status': period.status,
                'created_at': period.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'data': period_data,
            'count': len(period_data)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@payroll_api_bp.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })


