import io
import os
from io import BytesIO
from datetime import date
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
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
    title = doc.add_paragraph("S E R V I C E   R E C O R D")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.runs[0].bold = True
    title.runs[0].font.size = Pt(14)

    para1 = doc.add_paragraph("Republic of the Philippines")
    para1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para1.runs[0].font.size = Pt(11)

    para2 = doc.add_paragraph("NORZAGARAY, REGION 3")
    para2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para2.runs[0].bold = True
    para2.runs[0].font.size = Pt(11)

    doc.add_paragraph("")

    # ================= EMPLOYEE INFO =================
    doc.add_paragraph(
        f"Name : {employee.last_name.upper()}, "
        f"{employee.first_name.upper()} "
        f"{employee.middle_name or ''}"
    )

    birth_date = employee.date_of_birth.strftime('%B %d, %Y') if employee.date_of_birth else ''
    doc.add_paragraph(f"Date and place of birth : {birth_date}")

    doc.add_paragraph("(If married woman, give full maiden name)")
    doc.add_paragraph("(Date herein should be checked from birth or baptismal certificate)")
    doc.add_paragraph("B.P. Number: __________     TIN #: __________")
    doc.add_paragraph("")

    # ================= CERTIFICATION =================
    cert_text = (
        "This is to certify that the employee named hereunder actually rendered services "
        "in this Office as shown by the service record below."
    )

    cert_para = doc.add_paragraph(cert_text)
    cert_para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    doc.add_paragraph("")

    # ================= SERVICE TABLE =================
    headers = [
        "From", "To", "Designation Status",
        "Annual Salary", "Station / Assignment",
        "Branch", "Leave(s) w/out Pay", "Cause"
    ]

    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"

    for i, text in enumerate(headers):
        table.rows[0].cells[i].text = text

    # Add current employment record
    row = table.add_row().cells

    row[0].text = employee.date_hired.strftime('%b %d, %Y') if employee.date_hired else ''
    row[1].text = "Present"
    row[2].text = employee.position.name if employee.position else ''
    row[3].text = str(employee.salary or '')
    row[4].text = employee.department.name if employee.department else ''
    row[5].text = ""
    row[6].text = ""
    row[7].text = ""

    doc.add_paragraph("")

    # ================= FOOTER =================
    footer = (
        "Issued in compliance with official civil service service record standards."
    )

    footer_para = doc.add_paragraph(footer)
    footer_para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    doc.add_paragraph("CERTIFIED CORRECT:")
    doc.add_paragraph("FERNANDO DG. CRUZ")
    doc.add_paragraph("Acting MHRMO")

    doc.add_paragraph(f"Date Generated: {date.today().strftime('%B %d, %Y')}")

    # Normalize font size
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(11)

    # Save to buffer
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return buffer    




def generate_coe_pdf(employee):
    """
    Reusable COE PDF generator
    Returns BytesIO buffer
    """

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=50,
        leftMargin=50,
        topMargin=40,
        bottomMargin=60
    )

    styles = getSampleStyleSheet()

    # ---------- Styles ----------

    center_style = ParagraphStyle(
        "Center",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=11
    )

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        spaceAfter=20
    )

    right_style = ParagraphStyle(
        "Right",
        parent=styles["Normal"],
        alignment=TA_RIGHT,
        fontSize=10
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        leading=18,
        fontSize=11
    )

    # ---------- Logo ----------

    logo_path = os.path.join(
        current_app.root_path,
        "static",
        "img",
        "garay.png"
    )

    if os.path.exists(logo_path):
        logo = Image(logo_path, width=70, height=70)
        header_table = Table([[logo]], colWidths=[450], hAlign="CENTER")
    else:
        header_table = Table([[""]], colWidths=[450])

    # ---------- Header Text ----------

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

    # ---------- Date ----------

    today_date = datetime.now().strftime("%B %d, %Y")
    date_paragraph = Paragraph(today_date, right_style)

    # ---------- Gender Prefix ----------

    gender = (employee.gender or "").lower()

    if gender == "male":
        title_prefix = "Mr."
    elif gender == "female":
        title_prefix = "Ms."
    else:
        title_prefix = "Mr./Ms."

    display_name = f"{title_prefix} {employee.last_name}"

    # ---------- Model Data ----------

    department_name = employee.department.name if employee.department else "N/A"
    position_name = employee.position.name if employee.position else "N/A"
    employment_type = employee.employment_type.name if employee.employment_type else "N/A"

    hire_date = employee.date_hired.strftime("%B %d, %Y") if employee.date_hired else "N/A"

    end_date = "Present" if employee.status == "Active" else (employee.status or "N/A")

    working_duration = employee.get_working_duration()

    # ---------- Body Text ----------

    body_text = f"""
    <b>TO WHOM IT MAY CONCERN:</b><br/><br/>

    This is to certify that <b>{display_name}</b>,
    a <b>{position_name}</b> under the <b>{department_name}</b>,
    is employed as <b>{employment_type}</b> status in this office.

    <br/><br/>

    This employee has been working since <b>{hire_date}</b>
    up to <b>{end_date}</b> with a total working duration of
    <b>{working_duration}</b>.

    <br/><br/>

    This certification is issued upon the request of {display_name}
    for whatever legal purpose this may serve.
    """

    # ---------- Signature ----------

    signature_block = Paragraph("""
    <br/><br/><br/>
    <b>FERNANDO DG. CRUZ</b><br/>
    Acting MHRMO
    """, right_style)

    # ---------- Build Story ----------

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





def generate_leave_print_pdf_route(
    leave,
    employee,
    filename_prefix="Leave_Form"
):
    """
    Reusable leave form PDF generator wrapper
    """

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