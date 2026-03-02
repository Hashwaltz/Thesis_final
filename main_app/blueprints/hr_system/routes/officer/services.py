from flask import render_template,flash, request, send_file, redirect, url_for
from flask_login import login_required
from sqlalchemy.orm import joinedload
from datetime import date


from main_app.models.hr_models import  Employee, EmploymentType
from main_app.helpers.decorators import hr_officer_required
from main_app.helpers.docs import generate_coe_pdf, generate_service_record_docx, generate_moa_excel

from main_app.blueprints.hr_system.routes.officer import hr_officer_bp





@hr_officer_bp.route("/Services")
@hr_officer_required
@login_required
def view_services():
    employment_types = EmploymentType.query.all()
    employees = Employee.query.all()
    return render_template("hr/officer/officer_services.html",
                           employment_types=employment_types,
                           employees=employees)

    
@hr_officer_bp.route("/generate_moa_all/<int:employment_type_id>")
@hr_officer_required
@login_required
def generate_moa_all(employment_type_id):

    if employment_type_id == 0:
        etypes = EmploymentType.query.order_by(EmploymentType.name).all()
        employees_by_type = {
            etype: Employee.query.filter_by(employment_type_id=etype.id).all()
            for etype in etypes
        }
    else:
        etype = EmploymentType.query.get_or_404(employment_type_id)
        employees_by_type = {
            etype: Employee.query.filter_by(employment_type_id=etype.id).all()
        }

    if not any(employees_by_type.values()):
        flash("No employees found for the selected type(s).", "warning")
        return redirect(url_for("hr_officer_bp.view_services"))

    file_stream = generate_moa_excel(employees_by_type)

    filename = f"MOA_List_{date.today().strftime('%Y%m%d')}.xlsx"

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )





@hr_officer_bp.route('/employees/<int:employee_id>/service_record')
@hr_officer_required
@login_required
def export_service_record(employee_id):

    employee = Employee.query.get_or_404(employee_id)

    file_stream = generate_service_record_docx(employee)

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=f"service_record_{employee.employee_id}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )





@hr_officer_bp.route("/employee/<int:employee_id>/generate-coe")
@hr_officer_required
@login_required
def generate_coe(employee_id):

    employee = Employee.query.get_or_404(employee_id)

    buffer = generate_coe_pdf(employee)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"COE_{employee.employee_id}.pdf",
        mimetype="application/pdf"
    )

