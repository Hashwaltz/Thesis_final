import io
import os
from io import BytesIO
import pandas as pd
from datetime import date
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from flask import current_app, send_file
from datetime import datetime
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle
)


from main_app.models.hr_models import Employee
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib import colors



def generate_moa_excel(
    employees_by_type,
    agency_name="LGU-NORZAGARAY, BULACAN",
    regional_office="3",
    report_prefix="LIST OF"
):
    
    wb = Workbook()

    bold_center = Font(bold=True)
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )
    gray_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

    for i, (etype, employees) in enumerate(employees_by_type.items()):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = etype.name[:28]

        # ===== MAIN HEADER =====
        ws.merge_cells("A1:K1")
        ws["A1"] = f"{report_prefix} {etype.name.upper()} PERSONNEL"
        ws["A1"].font = Font(bold=True, size=14)
        ws["A1"].alignment = Alignment(horizontal="center")

        ws.merge_cells("A2:K2")
        ws["A2"] = f"(As of {date.today().strftime('%B %d, %Y')})"
        ws["A2"].font = Font(italic=True)
        ws["A2"].alignment = Alignment(horizontal="center")

        # ===== AGENCY INFO =====
        ws.append([])
        ws.append(["Agency name:", agency_name])
        ws.append(["Regional Office No:", regional_office])
        ws.append([])

        start_row = ws.max_row + 1

        # ===== TWO-LEVEL HEADER =====
        ws.merge_cells(f"A{start_row}:A{start_row+1}")
        ws.merge_cells(f"B{start_row}:D{start_row}")
        ws.merge_cells(f"E{start_row}:E{start_row+1}")
        ws.merge_cells(f"F{start_row}:F{start_row+1}")
        ws.merge_cells(f"G{start_row}:G{start_row+1}")
        ws.merge_cells(f"H{start_row}:H{start_row+1}")
        ws.merge_cells(f"I{start_row}:I{start_row+1}")
        ws.merge_cells(f"J{start_row}:K{start_row}")

        ws[f"A{start_row}"] = "NO."
        ws[f"B{start_row}"] = "Name of Personnel"
        ws[f"E{start_row}"] = "DATE OF BIRTH\n(MM/DD/YYYY)"
        ws[f"F{start_row}"] = "SEX\n(pls. select)"
        ws[f"G{start_row}"] = "Level of CS Eligibility\n(pls. select)"
        ws[f"H{start_row}"] = "WORK STATUS\n(pls. select)"
        ws[f"I{start_row}"] = f"No. of Years of Service as {etype.name} personnel"
        ws[f"J{start_row}"] = "NATURE OF WORK"

        ws[f"B{start_row+1}"] = "SURNAME"
        ws[f"C{start_row+1}"] = "FIRST NAME/\nEXTENSION NAME"
        ws[f"D{start_row+1}"] = "MIDDLE INITIAL"
        ws[f"J{start_row+1}"] = "Pls select"
        ws[f"K{start_row+1}"] = "Please specify"

        # ===== STYLE HEADER =====
        for row in ws.iter_rows(min_row=start_row, max_row=start_row+1, min_col=1, max_col=11):
            for cell in row:
                cell.font = bold_center
                cell.alignment = center_align
                cell.border = thin_border
                cell.fill = gray_fill

        # ===== TABLE BODY =====
        for idx, emp in enumerate(employees, start=1):
            ws.append([
                idx,
                emp.last_name or "",
                emp.first_name or "",
                emp.middle_name or "",
                emp.date_of_birth.strftime("%m/%d/%Y") if emp.date_of_birth else "",
                emp.gender or "",
                getattr(emp, "cs_eligibility", "No eligibility"),
                emp.status or "Active",
                emp.get_working_duration() if hasattr(emp, "get_working_duration") else "",
                emp.position.name if emp.position else "",
                "",
            ])

        # ===== AUTO WIDTH =====
        for i_col, col in enumerate(ws.columns, start=1):
            max_length = max((len(str(cell.value)) for cell in col if cell.value), default=0)
            ws.column_dimensions[get_column_letter(i_col)].width = max_length + 2

    file_stream = BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)

    return file_stream


def generate_excel_employees(
    data,
    headers,
    title="REPORT",
    agency_name="LGU-NORZAGARAY, BULACAN",
    regional_office="3"
):
    """
    Universal Excel Report Generator

    data → list of lists
    headers → list of column headers
    """

    wb = Workbook()
    ws = wb.active

    bold_center = Font(bold=True)
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )

    gray_fill = PatternFill(
        start_color="D9D9D9",
        end_color="D9D9D9",
        fill_type="solid"
    )

    # ===== HEADER =====
    ws.merge_cells(f"A1:{get_column_letter(len(headers))}1")
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")

    ws.merge_cells(f"A2:{get_column_letter(len(headers))}2")
    ws["A2"] = f"(As of {date.today().strftime('%B %d, %Y')})"
    ws["A2"].alignment = Alignment(horizontal="center")

    ws.append([])
    ws.append(["Agency name:", agency_name])
    ws.append(["Regional Office No:", regional_office])
    ws.append([])

    start_row = ws.max_row + 1

    # ===== TABLE HEADER =====
    ws.append(headers)

    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=start_row, column=col)
        cell.font = bold_center
        cell.alignment = center_align
        cell.border = thin_border
        cell.fill = gray_fill

    # ===== BODY DATA =====
    for row in data:
        ws.append(row)

    # ===== AUTO WIDTH =====
    for i_col, col in enumerate(ws.columns, start=1):
        max_length = max(
            (len(str(cell.value)) for cell in col if cell.value),
            default=0
        )
        ws.column_dimensions[get_column_letter(i_col)].width = max_length + 2

    file_stream = BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)

    return file_stream

def generate_service_record_docx(employee):
    doc = Document()

    # ================= HEADER =================
    p1 = doc.add_paragraph("Republic of the Philippines")
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p2 = doc.add_paragraph("NORZAGARAY, REGION 3")
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.runs[0].bold = True

    title = doc.add_paragraph("S E R V I C E   R E C O R D")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.runs[0].bold = True

    doc.add_paragraph("")

    # ================= NAME SECTION =================
    doc.add_paragraph("Name :")
    table_name = doc.add_table(rows=1, cols=3)
    table_name.style = "Table Grid"
    table_name.rows[0].cells[0].text = "First Name"
    table_name.rows[0].cells[1].text = "Middle Name"
    table_name.rows[0].cells[2].text = "Last Name"

    row = table_name.add_row().cells
    row[0].text = employee.first_name or ""
    row[1].text = employee.middle_name or ""
    row[2].text = employee.last_name or ""

    doc.add_paragraph("(If married woman, give full maiden name)")

    birth = employee.date_of_birth.strftime("%B %d, %Y") if employee.date_of_birth else ""
    doc.add_paragraph(f"Date and place of birth : {birth}")
    doc.add_paragraph("(Date herein should be checked from birth or baptismal certificate or some other reliable documents)")
    doc.add_paragraph("B.P. Number: __________________")
    doc.add_paragraph("TIN # : __________________")
    doc.add_paragraph("")

    # ================= CERTIFICATION =================
    cert = doc.add_paragraph(
        "This is to certify that the employee named hereunder actually rendered services in this Office as shown by the "
        "service record below, each line of which is supported by appointment and other papers actually issued by this "
        "Office and approved by the authorities concerned."
    )
    cert.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.add_paragraph("")

    # ================= SERVICE RECORD TABLE =================
    table = doc.add_table(rows=2, cols=10)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # ---- TOP HEADER ----
    top = table.rows[0].cells
    top[0].text = "SERVICE (Inclusive Dates)"
    top[1].text = ""  # merged later
    top[2].text = "RECORD OF APPOINTMENT"
    top[3].text = "OFFICE / ENTITY / DIVISION"
    top[4].text = "Leave(s)"
    top[5].text = ""
    top[6].text = "SEPARATION"
    top[7].text = ""
    top[8].text = "Remarks"
    top[9].text = ""

    # Merge top row cells as per format
    top[0].merge(top[1])
    top[4].merge(top[5])
    top[6].merge(top[7])

    # ---- SECOND HEADER ----
    second = table.rows[1].cells
    second[0].text = "From"
    second[1].text = "To"
    second[2].text = "Designation / Status (1)"
    second[3].text = "Station / Place of Assignment"
    second[4].text = "With Pay"
    second[5].text = "Without Pay"
    second[6].text = "Date"
    second[7].text = "Cause"
    second[8].text = ""
    second[9].text = ""

    # ================= JOB HISTORY DATA =================
    histories = sorted(employee.job_history, key=lambda x: x.effective_date)

    for h in histories:
        row = table.add_row().cells
        row[0].text = h.effective_date.strftime("%b %d, %Y") if h.effective_date else ""
        row[1].text = h.end_date.strftime("%b %d, %Y") if h.end_date else "Present"

        designation = h.position.name if h.position else ""
        if h.employment_type:
            designation += f" ({h.employment_type.name})"
        row[2].text = designation

        row[3].text = h.department.name if h.department else ""
        row[4].text = ""
        row[5].text = ""
        row[6].text = ""
        row[7].text = ""
        row[8].text = h.remarks or ""
        row[9].text = ""

    doc.add_paragraph("")

    # ================= ISSUED STATEMENT =================
    issue = doc.add_paragraph(
        "Issued on compliance with Executive Order No. 54 dated August 10, 1954, and in accordance with Circular No. 68 dated August 10, 1954 of the System."
    )
    issue.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.add_paragraph("")

    # ================= SIGNATURE =================
    doc.add_paragraph("CERTIFIED CORRECT:")
    doc.add_paragraph("")
    doc.add_paragraph("FERNANDO DG. CRUZ")
    doc.add_paragraph("Acting MHRMO")
    doc.add_paragraph("")

    # ================= DATE + PAGE =================
    doc.add_paragraph(date.today().strftime("%A, %B %d, %Y"))
    doc.add_paragraph("Page 1 of 1")

    # ================= FONT STANDARD =================
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(11)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def generate_coe_pdf(employee, fields=None):
    """
    Generate COE PDF for a given employee.
    `fields` is a list of fields to include. E.g. ['position', 'department', 'deductions']
    """
    fields = fields or []

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=50, leftMargin=50, topMargin=40, bottomMargin=60)
    styles = getSampleStyleSheet()
    center_style = ParagraphStyle("Center", parent=styles["Normal"], alignment=TA_CENTER, fontSize=11)
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], alignment=TA_CENTER, spaceAfter=20)
    right_style = ParagraphStyle("Right", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=10)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], alignment=TA_CENTER, leading=18, fontSize=11)

    # Logo
    logo_path = os.path.join(current_app.root_path, "static", "img", "garay.png")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=70, height=70)
        header_table = Table([[logo]], colWidths=[450], hAlign="CENTER")
    else:
        header_table = Table([[""]], colWidths=[450])

    header_text = """
    Republic of the Philippines<br/>
    Province of Bulacan<br/>
    MUNICIPALITY OF NORZAGARAY<br/>
    HUMAN RESOURCE MANAGEMENT OFFICE
    """

    separator = Table([[""]], colWidths=[450])
    separator.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.darkblue),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2)
    ]))

    today_date = datetime.now().strftime("%B %d, %Y")
    date_paragraph = Paragraph(today_date, right_style)

    # Gender title
    gender = (employee.gender or "").lower()
    if gender == "male":
        title_prefix = "Mr."
    elif gender == "female":
        title_prefix = "Ms."
    else:
        title_prefix = "Mr./Ms."
    display_name = f"{title_prefix} {employee.last_name}"

    # Model data
    position_name = employee.position.name if employee.position else "N/A"
    department_name = employee.department.name if employee.department else "N/A"
    employment_type = employee.employment_type.name if employee.employment_type else "N/A"
    hire_date = employee.date_hired.strftime("%B %d, %Y") if employee.date_hired else "N/A"
    end_date = "Present" if employee.status == "Active" else (employee.status or "N/A")
    working_duration = employee.get_working_duration()

    # Fetch deductions from EmployeeDeductions table if requested
    deductions_text = ""
    if "deductions" in fields:
        deductions = []
        for ed in getattr(employee, "employee_deductions", []):  # relationship Employee.employee_deductions
            deduction_name = ed.deduction.name if ed.deduction else "N/A"
            deductions.append(f"{deduction_name}")
        if deductions:
            deductions_text = ", ".join(deductions)
        else:
            deductions_text = "No deductions linked."

    # Build body text
    body_lines = [f"<b>TO WHOM IT MAY CONCERN:</b><br/><br/>",
                  f"This is to certify that <b>{display_name}</b>,"]

    if "position" in fields:
        body_lines.append(f"a <b>{position_name}</b>")
    if "department" in fields:
        body_lines.append(f"under the <b>{department_name}</b>")
    if "employment_type" in fields:
        body_lines.append(f"is employed as <b>{employment_type}</b> status in this office.")

    if "hire_date" in fields or "end_date" in fields or "working_duration" in fields:
        body_lines.append("<br/><br/>")
        if "hire_date" in fields:
            body_lines.append(f"Working since <b>{hire_date}</b>")
        if "end_date" in fields:
            body_lines.append(f"up to <b>{end_date}</b>")
        if "working_duration" in fields:
            body_lines.append(f"with total duration of <b>{working_duration}</b>.")

    if deductions_text:
        body_lines.append(f"<br/><br/>Deductions: {deductions_text}")

    body_lines.append(f"<br/><br/>This certification is issued upon the request of {display_name} for whatever legal purpose this may serve.")
    body_text = " ".join(body_lines)

    signature_block = Paragraph("""
    <br/><br/><br/>
    <b>FERNANDO DG. CRUZ</b><br/>
    Acting MHRMO
    """, right_style)

    story = [
        header_table,
        Paragraph(header_text, center_style),
        Spacer(1, 6),
        separator,
        Spacer(1, 20),
        date_paragraph,
        Spacer(1, 20),
        Paragraph("CERTIFICATION", title_style),
        Paragraph(body_text, body_style),
        signature_block
    ]

    doc.build(story)
    buffer.seek(0)
    return buffer







""""

def generate_leave_print_pdf_route(
    leave,
    employee,
    filename_prefix="Leave_Form"
):
   
    Reusable leave form PDF generator wrapper
   

    pdf_buffer = io.BytesIO()

    # ----------------------------
    # Create PDF Document
    # ----------------------------
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter
    )

    # ---------------------------------------------------
    # IMPORTANT
    # Replace this with your real PDF content generator
    # Example assumes you already have:
    # generate_csform4_quadrants_pdf()
    # ---------------------------------------------------

    from main_app.helpers.docs import generate_csform4_quadrants_pdf

    pdf_buffer = generate_csform4_quadrants_pdf(
        leave,
        employee
    )

    filename = f"{filename_prefix}_{employee.last_name}_{leave.id}.pdf"

    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )
    """


def safe_get(obj, attr, default=0):
    return getattr(obj, attr, default) or default




def export_payroll_excel(query):

    payrolls = query.all()
    data = []

    for p in payrolls:

        total_linked_deductions = sum(
            (ed.deduction.rate or 0)
            for ed in getattr(p.employee, "employee_deductions", [])
            if ed.deduction and ed.deduction.active
        )

        total_allowances = sum(
            (ea.allowance.amount or 0)
            for ea in getattr(p.employee, "employee_allowances", [])
            if ea.allowance and ea.allowance.active
        )

        total_deductions = safe_get(p, "total_deductions") + total_linked_deductions
        gross_pay_with_allowances = safe_get(p, "gross_pay") + total_allowances

        data.append({
            "Employee ID": p.employee.employee_id,
            "Employee Name": f"{p.employee.first_name} {p.employee.last_name}",
            "Department": p.employee.department.name if p.employee.department else "-",

            "Basic Salary": safe_get(p, "basic_salary"),
            "Overtime Pay": safe_get(p, "overtime_pay"),
            "Holiday Pay": safe_get(p, "holiday_pay"),
            "Night Differential": safe_get(p, "night_diff"),
            "Allowances": total_allowances,

            "Gross Pay": gross_pay_with_allowances,

            "SSS": 0,
            "PhilHealth": 0,
            "Pag-IBIG": 0,
            "Tax Withheld": safe_get(p, "tax_withheld"),
            "Other Deductions": safe_get(p, "other_deductions"),
            "Linked Deductions": total_linked_deductions,

            "Total Deductions": total_deductions,
            "Net Pay": safe_get(p, "net_pay"),

            "Status": safe_get(p, "status"),
            "Pay Period": f"{getattr(p.period,'start_date','-')} - {getattr(p.period,'end_date','-')}"
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Payroll",
            startrow=12
        )

        workbook = writer.book
        worksheet = writer.sheets["Payroll"]

        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
        from openpyxl.drawing.image import Image as OpenpyxlImage

        # ==========================================
        # Logo
        # ==========================================

        logo_path = r"C:\Users\pc\Desktop\Thesis_final\main_app\static\img\garay.png"

        if os.path.exists(logo_path):
            logo = OpenpyxlImage(logo_path)
            logo.width = 110
            logo.height = 110
            worksheet.add_image(logo, "A1")

        # ==========================================
        # Government Header
        # ==========================================

        worksheet.merge_cells("A2:P2")
        worksheet["A2"] = "Republic of the Philippines"

        worksheet.merge_cells("A3:P3")
        worksheet["A3"] = "MUNICIPALITY OF NORZAGARAY"

        worksheet.merge_cells("A4:P4")
        worksheet["A4"] = "Province of Bulacan"

        worksheet.merge_cells("A6:P6")
        worksheet["A6"] = "Municipal Hall of Norzagaray"

        worksheet.merge_cells("A7:P7")
        worksheet["A7"] = "Norzagaray, Bulacan"

        worksheet.merge_cells("A9:P9")
        worksheet["A9"] = "PAYROLL SUMMARY REPORT"

        header_font = Font(size=12, bold=True)
        title_font = Font(size=16, bold=True)

        for cell in ["A2","A3","A4","A6","A7"]:
            worksheet[cell].alignment = Alignment(horizontal="center")
            worksheet[cell].font = header_font

        worksheet["A9"].alignment = Alignment(horizontal="center")
        worksheet["A9"].font = title_font

        # ==========================================
        # Table Header Styling
        # ==========================================

        header_row = 13

        fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

        for cell in worksheet[header_row]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
            cell.fill = fill

        # ==========================================
        # Borders
        # ==========================================

        thin = Side(style="thin")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for row in worksheet.iter_rows(
            min_row=header_row,
            max_row=worksheet.max_row,
            min_col=1,
            max_col=worksheet.max_column
        ):
            for cell in row:
                cell.border = border

        # ==========================================
        # Currency Format
        # ==========================================

        currency_columns = [
            "D","E","F","G","H","I","J","K","L","M","N","O"
        ]

        for col in currency_columns:
            for row in range(header_row+1, worksheet.max_row+1):
                worksheet[f"{col}{row}"].number_format = '₱#,##0.00'

        # ==========================================
        # Auto Column Width
        # ==========================================

        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter

            for cell in column:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    pass

            worksheet.column_dimensions[column_letter].width = max_length + 3

    output.seek(0)

    filename = f"Payroll_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )



# ======================================================
# PAYROLL SUMMARY REPORT
# ======================================================

def payroll_summary_report(payrolls):

    data = []

    for p in payrolls:

        data.append({
            "Employee ID": p.employee.employee_id,
            "Employee Name": f"{p.employee.first_name} {p.employee.last_name}",
            "Department": p.employee.department.name if p.employee.department else "-",

            "Basic Salary": p.basic_salary,
            "Overtime Pay": p.overtime_pay,
            "Holiday Pay": p.holiday_pay,
            "Night Differential": p.night_diff,
            "Gross Pay": p.gross_pay,

            "Total Deductions": p.total_deductions,
            "Net Pay": p.net_pay,

            "Payroll Period":
            f"{p.period.start_date} - {p.period.end_date}"
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Payroll Summary")

    output.seek(0)

    filename = f"Payroll_Summary_{datetime.now().strftime('%Y%m%d')}.xlsx"

    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# DEDUCTION SUMMARY REPORT
# ======================================================

def deduction_summary_report(payrolls):

    deductions = {}

    for p in payrolls:

        for d in p.deduction_breakdown:

            name = d.deduction_name

            deductions.setdefault(name, 0)

            deductions[name] += d.employee_share

    data = [
        {"Deduction": k, "Total": v}
        for k, v in deductions.items()
    ]

    df = pd.DataFrame(data)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Deduction Summary")

    output.seek(0)

    filename = f"Deduction_Summary_{datetime.now().strftime('%Y%m%d')}.xlsx"

    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# EMPLOYEE PAYROLL HISTORY
# ======================================================

def employee_payroll_history(employee):

    data = []

    for p in employee.payrolls:

        data.append({
            "Payroll Period": f"{p.period.start_date} - {p.period.end_date}",
            "Gross Pay": p.gross_pay,
            "Total Deductions": p.total_deductions,
            "Net Pay": p.net_pay,
            "Status": p.status
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Payroll History")

    output.seek(0)

    filename = f"Payroll_History_{employee.employee_id}.xlsx"

    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )






# ======================================================
# EMPLOYEES BY YEARS OF SERVICE REPORT
# ======================================================

def export_employees_by_year_of_service(employees):
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"

    # --- HEADER SECTION ---
    ws.merge_cells("A1:H1")
    ws["A1"] = "LIST OF PERSONNEL"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")

    ws.merge_cells("A2:H2")
    ws["A2"] = f"(As of {date.today().strftime('%B %d, %Y')})"
    ws["A2"].alignment = Alignment(horizontal="center")

    ws["A4"] = "Agency name:"
    ws["B4"] = "LGU-NORZAGARAY, BULACAN"

    ws["A5"] = "Regional Office No:"
    ws["B5"] = "3"

    # --- TABLE HEADER ---
    headers = [
        "Full Name",
        "Email",
        "Phone",
        "Department",
        "Position",
        "Date Hired",
        "Years of Service",
        "Barangay"
    ]

    ws.append([])  # blank row
    ws.append(headers)

    # Apply bold font to header row
    header_row = ws.max_row
    for cell in ws[header_row]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # --- EMPLOYEE DATA ---
    for e in employees:
        ws.append([
            e.get_full_name(),
            e.email,
            e.phone or "-",
            e.department.name if e.department else "-",
            e.position.name if e.position else "-",
            e.date_hired.strftime("%Y-%m-%d") if e.date_hired else "-",
            e.get_working_duration(),
            e.barangay or "-"
        ])

    # --- Auto-fit column widths safely ---
    for column_cells in ws.columns:
        max_length = 0
        col_letter = get_column_letter(column_cells[0].column)
        for cell in column_cells:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max_length + 2

    # --- Save to in-memory buffer ---
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="Employee_Report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )