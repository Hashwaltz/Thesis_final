
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from datetime import date, datetime
from flask import render_template, request, redirect, flash, url_for
from flask_login import login_required, current_user


from main_app.models.hr_models import Employee, Leave, Department, EmploymentType
from main_app.models.payroll_models import PayrollPeriod, Payroll, Deduction, Payslip, PayrollDeduction
from main_app.utils import payroll_admin_required
from main_app.extensions import db
from main_app.functions import generate_payslip


from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp