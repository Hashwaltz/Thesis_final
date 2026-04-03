from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas
from datetime import datetime, date
from io import BytesIO

from main_app.models.hr_models import Employee, JobHistory


class ServiceRecordPDFGenerator:
    def __init__(self, employee: Employee):
        self.employee = employee
        self.styles = getSampleStyleSheet()
        self.buffer = BytesIO()
        
    def _add_header(self, canvas_obj, doc):
        """Add header to each page"""
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica-Bold", 11)
        canvas_obj.drawCentredString(doc.pagesize[0]/2, 770, "Republic of the Philippines")
        canvas_obj.setFont("Helvetica-Bold", 10)
        canvas_obj.drawCentredString(doc.pagesize[0]/2, 755, "NORZAGARAY, REGION 3")
        canvas_obj.setFont("Helvetica-Bold", 14)
        canvas_obj.drawCentredString(doc.pagesize[0]/2, 730, "S E R V I C E   R E C O R D")
        canvas_obj.restoreState()
    
    def _add_footer(self, canvas_obj, doc):
        """Add footer to each page"""
        canvas_obj.saveState()
        page_width = doc.pagesize[0]
        
        canvas_obj.setFont("Helvetica", 8)
        footer_line1 = "Issued on compliance with Executive Order No. 54 dated August 10, 1954, and in accordance with Circular No. 68 dated"
        footer_line2 = "August 10, 1954 of the System."
        
        canvas_obj.drawString(56, 140, footer_line1)
        canvas_obj.drawString(56, 130, footer_line2)
        
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        canvas_obj.drawString(56, 110, current_date)
        
        canvas_obj.setFont("Helvetica-Bold", 10)
        canvas_obj.drawRightString(page_width - 56, 110, "CERTIFIED CORRECT:")
        
        canvas_obj.setLineWidth(1)
        canvas_obj.line(page_width - 200, 95, page_width - 56, 95)
        
        canvas_obj.setFont("Helvetica-Bold", 11)
        canvas_obj.drawRightString(page_width - 56, 85, "FERNANDO DG. CRUZ")
        
        canvas_obj.setFont("Helvetica-Oblique", 10)
        canvas_obj.drawRightString(page_width - 56, 73, "Acting MHRMO")
        
        page_num = canvas_obj.getPageNumber()
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.drawCentredString(page_width/2, 40, f"Page {page_num}")
        
        canvas_obj.restoreState()

    def _make_cell(self, text, align=TA_LEFT, style_name="Cell"):
        """Helper to create a properly wrapped Paragraph cell"""
        if text is None:
            text = ""
            
        cell_style = ParagraphStyle(
            f'{style_name}_{align}',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10.5,  # ~1.3x font size for comfortable line spacing
            alignment=align,
            wordWrap='LTR',
            spaceBefore=2,
            spaceAfter=2,
            leftIndent=2,
            rightIndent=2
        )
        return Paragraph(str(text), cell_style)
    
    def _get_personal_info_section(self):
        """Create personal information section"""
        styles = self.styles
        
        label_style = ParagraphStyle(
            'LabelStyle', parent=styles['Normal'],
            fontSize=10, fontName='Helvetica-Bold', leading=15,
            spaceAfter=2
        )
        value_style = ParagraphStyle(
            'ValueStyle', parent=styles['Normal'],
            fontSize=10, fontName='Helvetica', leading=15,
            spaceAfter=2
        )
        note_style = ParagraphStyle(
            'NoteStyle', parent=styles['Normal'],
            fontSize=8, fontName='Helvetica-Oblique',
            leading=10, textColor=colors.gray
        )
        
        first_name = self.employee.first_name or ""
        middle_name = self.employee.middle_name or ""
        last_name = self.employee.last_name or ""
        full_name = f"{first_name} {middle_name} {last_name}".strip()
        
        dob_str = ""
        if self.employee.date_of_birth:
            dob_str = self.employee.date_of_birth.strftime("%B %d, %Y")
        
        birth_place_parts = []
        if self.employee.municipality:
            birth_place_parts.append(self.employee.municipality)
        if self.employee.province:
            birth_place_parts.append(self.employee.province)
        birth_place = ", ".join(birth_place_parts)
        
        dob_full = f"{dob_str} - {birth_place}".strip(" - ") if dob_str or birth_place else ""
        
        bp_number = getattr(self.employee, 'bp_number', '') or ''
        tin_number = getattr(self.employee, 'tin_number', '') or ''
        
        data = [
            [Paragraph("<b>Name:</b>", label_style), Paragraph(full_name, value_style),
             Paragraph("(If married woman, give full maiden name)", note_style)],
            [Paragraph("", label_style),
             Paragraph("<font size='7' color='gray'>First Name &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Middle Name &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Last Name</font>", note_style),
             Paragraph("", note_style)],
            [Paragraph("<b>Date and place of birth:</b>", label_style),
             Paragraph(dob_full, value_style),
             Paragraph("(Date herein should be checked from birth or baptismal certificate or some other reliable documents)", note_style)],
            [Paragraph("<b>B.P. Number:</b>", label_style), Paragraph(bp_number, value_style), Paragraph("", note_style)],
            [Paragraph("<b>TIN #:</b>", label_style), Paragraph(tin_number, value_style), Paragraph("", note_style)],
        ]
        
        table = Table(data, colWidths=[1.8*inch, 3.2*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        return table
    
    def _get_certification_text(self):
        """Create certification paragraph"""
        style = ParagraphStyle(
            'CertificationText', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', alignment=TA_LEFT,
            spaceBefore=15, spaceAfter=15, leading=14,
            leftIndent=50, rightIndent=50
        )
        text = """This is to certify that the employee named hereunder actually rendered services in this Office as shown by the service record below, each line of which is supported by appointment and other papers actually issued by this Office and approved by the authorities concerned."""
        return Paragraph(text, style)
    
    def _get_job_history_table(self):
        """Create the main service record table with proper wrapping & spacing"""
        EMPLOYMENT_TYPE_MAP = {1: "Regular", 2: "Part-timer", 3: "Casual", 5: "Job Order"}
        
        job_histories = JobHistory.query.filter_by(
            employee_id=self.employee.id
        ).order_by(JobHistory.effective_date.asc()).all()
        
        rows = []
        for job in job_histories:
            from_date = job.effective_date.strftime("%Y-%m-%d") if job.effective_date else ""
            to_date = job.end_date.strftime("%Y-%m-%d") if job.end_date else "Present"
            designation = job.position.name if job.position else ""
            
            if job.employment_type and job.employment_type.name:
                status_display = job.employment_type.name
            elif job.status and str(job.status).isdigit():
                status_display = EMPLOYMENT_TYPE_MAP.get(int(job.status), str(job.status))
            elif job.status:
                status_display = str(job.status)
            else:
                status_display = ""
            
            salary = f"₱{job.salary:,.2f}" if job.salary else ""
            station = job.department.name if job.department else ""
            sep_date = job.end_date.strftime("%Y-%m-%d") if job.end_date else ""
            sep_cause = job.remarks or ""
            
            row_data = [
                self._make_cell(from_date, TA_CENTER, "Date"),
                self._make_cell(to_date, TA_CENTER, "Date"),
                self._make_cell(designation, TA_LEFT, "Text"),
                self._make_cell(status_display, TA_CENTER, "Text"),
                self._make_cell(salary, TA_RIGHT, "Number"),
                self._make_cell(station, TA_LEFT, "Text"),
                self._make_cell("", TA_CENTER),
                self._make_cell("", TA_CENTER),
                self._make_cell(sep_date, TA_CENTER, "Date"),
                self._make_cell(sep_cause, TA_LEFT, "Text"),
            ]
            rows.append(row_data)
        
        if not rows:
            rows.append([self._make_cell("", TA_CENTER) for _ in range(10)])
            
        # Header rows
        h_style = ParagraphStyle(
            'HeaderCell', parent=self.styles['Normal'],
            fontSize=7.5, fontName='Helvetica-Bold', leading=9.5,
            alignment=TA_CENTER, wordWrap='LTR', spaceBefore=1, spaceAfter=1
        )
        
        header_row1 = [
            self._make_cell("SERVICE\n(Inclusive Dates)", TA_CENTER, "Header"),
            self._make_cell("SERVICE\n(Inclusive Dates)", TA_CENTER, "Header"),
            self._make_cell("RECORD OF APPOINTMENT", TA_CENTER, "Header"),
            self._make_cell("RECORD OF APPOINTMENT", TA_CENTER, "Header"),
            self._make_cell("RECORD OF APPOINTMENT", TA_CENTER, "Header"),
            self._make_cell("OFFICE / ENTITY / DIVISION", TA_CENTER, "Header"),
            self._make_cell("OFFICE / ENTITY / DIVISION", TA_CENTER, "Header"),
            self._make_cell("Leave(s)\nwithout\nPay", TA_CENTER, "Header"),
            self._make_cell("SEPARATION (4)", TA_CENTER, "Header"),
            self._make_cell("SEPARATION (4)", TA_CENTER, "Header"),
        ]
        header_row2 = [
            self._make_cell("From", TA_CENTER, "Header"),
            self._make_cell("To", TA_CENTER, "Header"),
            self._make_cell("Designation", TA_CENTER, "Header"),
            self._make_cell("Status (1)", TA_CENTER, "Header"),
            self._make_cell("Annual Salary (2)", TA_CENTER, "Header"),
            self._make_cell("Station / Place of Assignment", TA_CENTER, "Header"),
            self._make_cell("Branch (3)", TA_CENTER, "Header"),
            self._make_cell("", TA_CENTER),
            self._make_cell("Date", TA_CENTER, "Header"),
            self._make_cell("Cause", TA_CENTER, "Header"),
        ]
        
        table_data = [header_row1, header_row2] + rows
        
        col_widths = [0.6*inch, 0.6*inch, 1.1*inch, 0.65*inch, 0.8*inch,
                     1.2*inch, 0.5*inch, 0.45*inch, 0.55*inch, 0.85*inch]
        
        table = Table(table_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 1), colors.lightgrey),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ('LINEBELOW', (0, 1), (-1, 1), 1, colors.black),
            
            # Grid & Box
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            
            # Padding & Spacing (reduced horizontal, increased vertical rhythm via leading)
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            
            # Alignment & Wrapping
            ('VALIGN', (0, 0), (1, -1), 'MIDDLE'),  # Dates centered vertically
            ('VALIGN', (2, 2), (-1, -1), 'TOP'),    # Wrapped text aligns to top
            ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.whitesmoke]),
        ]))
        return table
    
    def generate(self):
        """Generate the PDF"""
        doc = SimpleDocTemplate(
            self.buffer, pagesize=letter,
            rightMargin=50, leftMargin=50, topMargin=100, bottomMargin=60
        )
        
        story = []
        story.append(Spacer(1, 50))
        story.append(self._get_personal_info_section())
        story.append(Spacer(1, 15))
        story.append(self._get_certification_text())
        story.append(Spacer(1, 10))
        story.append(self._get_job_history_table())
        story.append(Spacer(1, 30))
        
        def page_setup(canvas_obj, doc):
            self._add_header(canvas_obj, doc)
            self._add_footer(canvas_obj, doc)
        
        doc.build(story, onFirstPage=page_setup, onLaterPages=page_setup)
        
        pdf_bytes = self.buffer.getvalue()
        self.buffer.close()
        return BytesIO(pdf_bytes)


def generate_service_record_pdf(employee: Employee):
    """Generate service record PDF"""
    generator = ServiceRecordPDFGenerator(employee)
    return generator.generate()