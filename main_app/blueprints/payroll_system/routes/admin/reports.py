from flask import render_template, request, make_response
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy import or_  
from reportlab.lib.units import inch
from io import StringIO

from main_app.extensions import db
from main_app.models.payroll_models import Payroll, PayrollPeriod, PayrollDeduction
from main_app.models.hr_models import Employee, Department
from main_app.helpers.decorators import payroll_admin_required

from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp


@payroll_admin_bp.route('/earnings-deduction-report')
@payroll_admin_required
@login_required
def earnings_deduction_report():
    """
    Generate earnings and deduction report filtered by provider:
    - SSS, GSIS, PHIC, Tax, Loans
    """
    
    # ===== GET FILTERS =====
    provider = request.args.get('provider', '', type=str).strip().upper()
    department_id = request.args.get('department_id', type=int)
    period_id = request.args.get('period_id', type=int)
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)
    search = request.args.get('search', '', type=str).strip()
    page = request.args.get('page', 1, type=int)
    
    # ===== PROVIDER MAPPING =====
    PROVIDER_KEYWORDS = {
        'SSS': ['SSS', 'SOCIAL SECURITY'],
        'GSIS': ['GSIS', 'GOVERNMENT SERVICE'],
        'PHIC': ['PHILHEALTH', 'PHIC', 'HEALTH'],
        'TAX': ['TAX', 'WITHHOLDING', 'BIR'],
        'PAGIBIG': ['PAG-IBIG', 'HDMF', 'HOUSING'],
        'LOAN': ['LOAN', 'SALARY LOAN', 'EMERGENCY LOAN', 'MPL']
    }
    
    # ===== BASE QUERY =====
    query = Payroll.query.options(
        joinedload(Payroll.employee).joinedload(Employee.department),
        joinedload(Payroll.period),
        joinedload(Payroll.deduction_breakdown)
    )
    
    # ===== APPLY PERIOD FILTER =====
    if period_id:
        query = query.filter(Payroll.payroll_period_id == period_id)
    elif date_from or date_to:
        query = query.join(PayrollPeriod, Payroll.payroll_period_id == PayrollPeriod.id)
        
        if date_from:
            try:
                from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
                query = query.filter(PayrollPeriod.start_date >= from_date)
            except (ValueError, TypeError):
                pass
                
        if date_to:
            try:
                to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
                query = query.filter(PayrollPeriod.end_date <= to_date)
            except (ValueError, TypeError):
                pass
    
    # ===== APPLY DEPARTMENT FILTER =====
    if department_id:
        query = query.join(Employee).filter(Employee.department_id == department_id)
    
    # ===== APPLY SEARCH FILTER =====
    if search:
        search_pattern = f"%{search}%"
        query = query.join(Employee).filter(
            or_(
                Employee.first_name.ilike(search_pattern),
                Employee.last_name.ilike(search_pattern),
                Employee.employee_id.ilike(search_pattern)
            )
        )
    
    # ===== FILTER BY PROVIDER =====
    if provider and provider in PROVIDER_KEYWORDS:
        keywords = PROVIDER_KEYWORDS[provider]
        payroll_ids_with_deductions = db.session.query(PayrollDeduction.payroll_id).filter(
            or_(*[PayrollDeduction.deduction_name.ilike(f"%{kw}%") for kw in keywords])
        ).distinct()
        query = query.filter(Payroll.id.in_(payroll_ids_with_deductions))
    
    # ===== PAGINATE =====
    per_page = 20
    payrolls_paginated = query.order_by(Payroll.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    # ===== PROCESS DATA FOR DISPLAY =====
    report_data = []
    total_earnings = 0
    total_deductions = 0
    total_net_pay = 0
    
    for payroll in payrolls_paginated.items:
        employee = payroll.employee
        if not employee:
            continue
            
        # Compute initials for avatar (✅ FIX: Pre-compute in Python)
        full_name = employee.get_full_name() or f"{employee.first_name} {employee.last_name}"
        name_parts = full_name.strip().split()
        initials = ''
        if name_parts:
            initials = name_parts[0][0].upper() if name_parts[0] else 'E'
            if len(name_parts) > 1 and name_parts[-1]:
                initials += name_parts[-1][0].upper()
        else:
            initials = 'E'
        
        # Get provider-specific deductions
        provider_deductions = []
        provider_total = 0
        
        if payroll.deduction_breakdown:
            for deduction in payroll.deduction_breakdown:
                if provider:
                    keywords = PROVIDER_KEYWORDS.get(provider, [])
                    deduction_name = (deduction.deduction_name or "").upper()
                    
                    if any(kw in deduction_name for kw in keywords):
                        provider_deductions.append({
                            'name': deduction.deduction_name or 'Unknown',
                            'employee_share': deduction.employee_share or 0,
                            'employer_share': deduction.employer_share or 0,
                            'ec': deduction.ec or 0
                        })
                        provider_total += deduction.employee_share or 0
                else:
                    provider_deductions.append({
                        'name': deduction.deduction_name or 'Unknown',
                        'employee_share': deduction.employee_share or 0,
                        'employer_share': deduction.employer_share or 0,
                        'ec': deduction.ec or 0
                    })
                    provider_total += deduction.employee_share or 0
        
        # Calculate earnings components (✅ Safe property access)
        overtime_pay = getattr(payroll, 'overtime_pay', 0) or 0
        
        earnings = {
            'basic_salary': payroll.basic_salary or 0,
            'overtime': overtime_pay,
            'holiday_pay': payroll.holiday_pay or 0,
            'night_diff': payroll.night_diff or 0,
            'allowances': payroll.allowance_total or 0,
            'gross_pay': payroll.gross_pay or 0
        }
        
        report_data.append({
            'payroll_id': payroll.id,
            'employee_id': employee.employee_id or 'N/A',
            'employee_name': full_name,
            'employee_initials': initials,  # ✅ Pass pre-computed initials
            'department': employee.department.name if employee.department else 'N/A',
            'period': payroll.period.period_name if payroll.period else 'N/A',
            'period_start': payroll.period.start_date if payroll.period else None,
            'period_end': payroll.period.end_date if payroll.period else None,
            'earnings': earnings,
            'deductions': provider_deductions,
            'provider_total': provider_total,
            'total_deductions': payroll.total_deductions or 0,
            'net_pay': payroll.net_pay or 0,
            'status': payroll.status or 'Unknown'
        })
        
        # Accumulate totals
        total_earnings += earnings['gross_pay']
        total_deductions += provider_total if provider else (payroll.total_deductions or 0)
        total_net_pay += payroll.net_pay or 0
    
    # ===== GET SUMMARY STATISTICS =====
    count = len(report_data)
    summary_stats = {
        'total_employees': count,
        'total_earnings': round(total_earnings, 2),
        'total_provider_deductions': round(total_deductions, 2),
        'total_net_pay': round(total_net_pay, 2),
        'average_earnings': round(total_earnings / count, 2) if count > 0 else 0,
        'average_deductions': round(total_deductions / count, 2) if count > 0 else 0
    }
    
    # ===== DEPARTMENT BREAKDOWN =====
    dept_breakdown = db.session.query(
        Department.name,
        db.func.count(Payroll.id).label('employee_count'),
        db.func.sum(Payroll.gross_pay).label('total_earnings'),
        db.func.sum(Payroll.total_deductions).label('total_deductions')
    ).select_from(Payroll)\
     .join(Employee, Payroll.employee_id == Employee.id)\
     .join(Department, Employee.department_id == Department.id, isouter=True)
    
    if period_id:
        dept_breakdown = dept_breakdown.filter(Payroll.payroll_period_id == period_id)
    
    if provider and provider in PROVIDER_KEYWORDS:
        keywords = PROVIDER_KEYWORDS[provider]
        payroll_ids = db.session.query(PayrollDeduction.payroll_id).filter(
            or_(*[PayrollDeduction.deduction_name.ilike(f"%{kw}%") for kw in keywords])
        ).distinct()
        dept_breakdown = dept_breakdown.filter(Payroll.id.in_(payroll_ids))
    
    dept_breakdown = dept_breakdown.group_by(Department.id).all()
    
    # ===== DROPDOWN DATA =====
    departments = Department.query.order_by(Department.name).all()
    payroll_periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()
    
    # ===== PROVIDER OPTIONS =====
    provider_options = [
        {'value': '', 'label': 'All Providers'},
        {'value': 'SSS', 'label': 'SSS (Social Security)'},
        {'value': 'GSIS', 'label': 'GSIS (Government Service)'},
        {'value': 'PHIC', 'label': 'PhilHealth'},
        {'value': 'TAX', 'label': 'Withholding Tax'},
        {'value': 'PAGIBIG', 'label': 'Pag-IBIG/HDMF'},
        {'value': 'LOAN', 'label': 'Loans'}
    ]
    
    return render_template(
        'payroll/admin/reports/earnings_deduction_report.html',
        report_data=report_data,
        pagination=payrolls_paginated,
        summary_stats=summary_stats,
        departments=departments,
        payroll_periods=payroll_periods,
        provider_options=provider_options,
        selected_provider=provider,
        selected_department=department_id,
        selected_period=period_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        dept_breakdown=dept_breakdown
    )




@payroll_admin_bp.route('/earnings-deduction-export-pdf')
@payroll_admin_required
@login_required
def export_earnings_deduction_pdf():
    """Export earnings and deduction report as professional PDF"""
    from flask_login import current_user
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    from flask import send_file
    
    provider = request.args.get('provider', '', type=str).strip().upper()
    department_id = request.args.get('department_id', type=int)
    period_id = request.args.get('period_id', type=int)
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)
    search = request.args.get('search', '', type=str).strip()
    
    PROVIDER_KEYWORDS = {
        'SSS': ['SSS', 'SOCIAL SECURITY'],
        'GSIS': ['GSIS', 'GOVERNMENT SERVICE'],
        'PHIC': ['PHILHEALTH', 'PHIC', 'HEALTH'],
        'TAX': ['TAX', 'WITHHOLDING', 'BIR'],
        'PAGIBIG': ['PAG-IBIG', 'HDMF', 'HOUSING'],
        'LOAN': ['LOAN', 'SALARY LOAN', 'EMERGENCY LOAN', 'MPL']
    }
    
    # Build query
    query = Payroll.query.options(
        joinedload(Payroll.employee).joinedload(Employee.department),
        joinedload(Payroll.period),
        joinedload(Payroll.deduction_breakdown)
    )
    
    if period_id:
        query = query.filter(Payroll.payroll_period_id == period_id)
    elif date_from or date_to:
        query = query.join(PayrollPeriod, Payroll.payroll_period_id == PayrollPeriod.id)
        if date_from:
            try:
                query = query.filter(PayrollPeriod.start_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
            except (ValueError, TypeError):
                pass
        if date_to:
            try:
                query = query.filter(PayrollPeriod.end_date <= datetime.strptime(date_to, "%Y-%m-%d").date())
            except (ValueError, TypeError):
                pass
    
    if department_id:
        query = query.join(Employee).filter(Employee.department_id == department_id)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.join(Employee).filter(
            or_(
                Employee.first_name.ilike(search_pattern),
                Employee.last_name.ilike(search_pattern),
                Employee.employee_id.ilike(search_pattern)
            )
        )
    
    if provider and provider in PROVIDER_KEYWORDS:
        keywords = PROVIDER_KEYWORDS[provider]
        payroll_ids = db.session.query(PayrollDeduction.payroll_id).filter(
            or_(*[PayrollDeduction.deduction_name.ilike(f"%{kw}%") for kw in keywords])
        ).distinct()
        query = query.filter(Payroll.id.in_(payroll_ids))
    
    payrolls = query.all()
    payrolls.sort(key=lambda p: (
        (p.employee.last_name or '').lower(), 
        (p.employee.first_name or '').lower()
    ) if p.employee else ('', ''))
    
    # Process data
    report_rows = []
    total_basic = total_overtime = total_holiday = 0
    total_night_diff = total_allowances = total_gross = 0
    total_provider_ded = total_deductions = total_net = 0
    
    for payroll in payrolls:
        employee = payroll.employee
        if not employee:
            continue
        
        provider_total = 0
        if payroll.deduction_breakdown:
            for deduction in payroll.deduction_breakdown:
                if provider:
                    keywords = PROVIDER_KEYWORDS.get(provider, [])
                    deduction_name = (deduction.deduction_name or "").upper()
                    if any(kw in deduction_name for kw in keywords):
                        provider_total += deduction.employee_share or 0
                else:
                    provider_total += deduction.employee_share or 0
        
        overtime_pay = getattr(payroll, 'overtime_pay', 0) or 0
        basic = payroll.basic_salary or 0
        holiday = payroll.holiday_pay or 0
        night_diff = payroll.night_diff or 0
        allowances = payroll.allowance_total or 0
        gross = payroll.gross_pay or 0
        deductions = payroll.total_deductions or 0
        net = payroll.net_pay or 0
        
        total_basic += basic
        total_overtime += overtime_pay
        total_holiday += holiday
        total_night_diff += night_diff
        total_allowances += allowances
        total_gross += gross
        total_provider_ded += provider_total
        total_deductions += deductions
        total_net += net
        
        # Truncate long department names
        dept_name = employee.department.name if employee.department else ''
        if len(dept_name) > 15:
            dept_name = dept_name[:15] + '...'
            
        report_rows.append({
            'employee_id': employee.employee_id or '',
            'employee_name': f"{employee.last_name or ''}, {employee.first_name or ''}".strip(),
            'department': dept_name,
            'pay_period': payroll.period.period_name if payroll.period else '',
            'basic_salary': basic,
            'overtime': overtime_pay,
            'holiday_pay': holiday,
            'night_diff': night_diff,
            'allowances': allowances,
            'gross_pay': gross,
            'provider_deduction': provider_total,
            'total_deductions': deductions,
            'net_pay': net,
            'status': payroll.status or ''
        })
    
    # Create PDF in memory
    buffer = BytesIO()
    
    # ✅ FIX: Reduced margins to 0.25 inch to give more width
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.25*inch,
        leftMargin=0.25*inch,
        topMargin=0.5*inch,
        bottomMargin=0.75*inch
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#374151'),
        spaceAfter=3,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # ===== HEADER SECTION =====
    elements.append(Spacer(1, 0.2*inch))
    
    header_lines = [
        Paragraph("Republic of the Philippines", subtitle_style),
        Paragraph("MUNICIPALITY OF NORZAGARAY", title_style),
        Paragraph("Province of Bulacan", subtitle_style),
        Spacer(1, 0.1*inch),
        Paragraph("OFFICE OF THE MUNICIPAL TREASURER", 
                ParagraphStyle('HeaderSub', parent=styles['Normal'], fontSize=10, 
                             textColor=colors.HexColor('#1e40af'), alignment=TA_CENTER, fontName='Helvetica-Bold')),
        Paragraph("PAYROLL AND COMPENSATION DIVISION",
                ParagraphStyle('HeaderSub2', parent=styles['Normal'], fontSize=9, 
                             textColor=colors.HexColor('#6b7280'), alignment=TA_CENTER)),
    ]
    elements.extend(header_lines)
    elements.append(Spacer(1, 0.25*inch))
    
    # Report title
    elements.append(Paragraph("EARNINGS AND DEDUCTION REPORT", title_style))
    period_name = PayrollPeriod.query.get(period_id).period_name if period_id and PayrollPeriod.query.get(period_id) else "All Periods"
    elements.append(Paragraph(f"Pay Period: {period_name}", subtitle_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Report metadata box
    try:
        generated_by = current_user.employee_profile.get_full_name() if hasattr(current_user, 'employee_profile') and current_user.employee_profile else "System"
    except:
        generated_by = "System"
    
    meta_data = [
        ['Date Generated:', datetime.now().strftime("%B %d, %Y at %I:%M %p")],
        ['Generated By:', generated_by],
        ['Provider Filter:', f"{provider or 'All Providers'}"],
        ['Total Records:', f"{len(report_rows)} employee(s)"],
    ]
    
    meta_table = Table(meta_data, colWidths=[1.8*inch, 4.5*inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#374151')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#9ca3af')),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 0.25*inch))
    
    # ===== MAIN DATA TABLE =====
    table_data = []
    
    headers = [
        'Emp ID', 'Employee Name', 'Department',
        'Basic', 'OT', 'Holiday', 'Night Diff', 'Allow',
        'Gross', f'{provider}' if provider else 'Provider',
        'Total Ded', 'Net Pay', 'Status'
    ]
    table_data.append(headers)
    
    for row in report_rows:
        table_data.append([
            row['employee_id'],
            row['employee_name'],
            row['department'],
            f"₱{row['basic_salary']:,.0f}",
            f"₱{row['overtime']:,.0f}",
            f"₱{row['holiday_pay']:,.0f}",
            f"₱{row['night_diff']:,.0f}",
            f"₱{row['allowances']:,.0f}",
            f"₱{row['gross_pay']:,.2f}",
            f"₱{row['provider_deduction']:,.2f}",
            f"₱{row['total_deductions']:,.2f}",
            f"₱{row['net_pay']:,.2f}",
            row['status']
        ])
    
    # ✅ FIX: Calculated column widths to fit exactly within 10.5 inches
    col_widths = [
        0.6*inch,   # Emp ID
        1.5*inch,   # Name
        1.0*inch,   # Dept
        0.65*inch,  # Basic
        0.55*inch,  # OT
        0.6*inch,   # Holiday
        0.7*inch,   # Night Diff
        0.6*inch,   # Allow
        0.8*inch,   # Gross
        0.8*inch,   # Provider
        0.8*inch,   # Total Ded
        0.8*inch,   # Net Pay
        0.55*inch   # Status
    ]
    
    data_table = Table(table_data, colWidths=col_widths)
    data_table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        
        # Body
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),  # ✅ Smaller font size
        ('ALIGN', (3, 1), (-2, -1), 'RIGHT'),
        ('ALIGN', (0, 1), (2, -1), 'LEFT'),
        ('ALIGN', (-1, 1), (-1, -1), 'CENTER'),
        
        # Row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#e5e7eb')),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#1e40af')),
        
        # Padding
        ('PADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(data_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # ===== SUMMARY SECTION =====
    elements.append(Paragraph("SUMMARY", subtitle_style))
    elements.append(Spacer(1, 0.1*inch))
    
    summary_data = [
        ['Total Employees:', str(len(report_rows))],
        ['Total Basic Salary:', f"₱{total_basic:,.2f}"],
        ['Total Overtime:', f"₱{total_overtime:,.2f}"],
        ['Total Gross Pay:', f"₱{total_gross:,.2f}"],
        [f"Total {provider}:" if provider else "Total Provider:", f"₱{total_provider_ded:,.2f}"],
        ['Total All Deductions:', f"₱{total_deductions:,.2f}"],
        ['★★ TOTAL NET PAY ★★', f"₱{total_net:,.2f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -2), colors.HexColor('#f9fafb')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dbeafe')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (-2, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#374151')),
        ('TEXTCOLOR', (-2, -1), (-1, -1), colors.HexColor('#1e40af')),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#9ca3af')),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(summary_table)
    
    # Statistics
    if report_rows:
        elements.append(Spacer(1, 0.2*inch))
        net_pays = [r['net_pay'] for r in report_rows]
        stats_data = [
            ['Average Net Pay:', f"₱{sum(net_pays)/len(net_pays):,.2f}"],
            ['Highest Net Pay:', f"₱{max(net_pays):,.2f}"],
            ['Lowest Net Pay:', f"₱{min(net_pays):,.2f}"],
        ]
        stats_table = Table(stats_data, colWidths=[2.5*inch, 2*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eff6ff')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e40af')),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bfdbfe')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#93c5fd')),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(stats_table)
    
    # ===== SIGNATURE SECTION =====
    elements.append(Spacer(1, 0.6*inch))
    
    sig_data = [
        ['_________________________', '_________________________', '_________________________'],
        ['Prepared by:', 'Verified by:', 'Approved by:'],
        ['Payroll Officer', 'Municipal Treasurer', 'Municipal Mayor'],
    ]
    sig_table = Table(sig_data, colWidths=[2.3*inch, 2.3*inch, 2.3*inch])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 2), 8),
        ('TEXTCOLOR', (0, 1), (-1, 2), colors.HexColor('#374151')),
        ('TOPPADDING', (0, 0), (-1, 0), 25),
        ('BOTTOMPADDING', (0, 2), (-1, 2), 3),
    ]))
    elements.append(sig_table)
    
    # Header/Footer function
    def add_header_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.setFillColor(colors.HexColor('#6b7280'))
        
        page_num = canvas_obj.getPageNumber()
        canvas_obj.drawRightString(doc_obj.pagesize[0] - 0.25*inch, 0.35*inch, f"Page {page_num}")
        canvas_obj.drawString(0.25*inch, 0.35*inch, "CONFIDENTIAL - OFFICIAL USE ONLY")
        
        canvas_obj.setStrokeColor(colors.HexColor('#d1d5db'))
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(0.25*inch, 0.5*inch, doc_obj.pagesize[0] - 0.25*inch, 0.5*inch)
        canvas_obj.line(0.25*inch, doc_obj.pagesize[1] - 0.5*inch, doc_obj.pagesize[0] - 0.25*inch, doc_obj.pagesize[1] - 0.5*inch)
        
        canvas_obj.restoreState()
    
    doc.build(elements, onFirstPage=lambda c, d: add_header_footer(c, d), onLaterPages=lambda c, d: add_header_footer(c, d))
    
    buffer.seek(0)
    filename = f"Earnings_Deduction_Report_{provider or 'ALL'}_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )


@payroll_admin_bp.route('/deduction-detail-report')
@payroll_admin_required
@login_required
def deduction_detail_report():
    """
    View detailed deduction contributions by provider and period
    Flow: Select Provider -> Select Period -> View Employee Deductions
    """
    
    # ===== GET FILTERS =====
    provider = request.args.get('provider', '', type=str).strip().upper()
    period_id = request.args.get('period_id', type=int)
    department_id = request.args.get('department_id', type=int)
    search = request.args.get('search', '', type=str).strip()
    page = request.args.get('page', 1, type=int)
    
    # Provider mapping with keywords
    PROVIDER_KEYWORDS = {
        'SSS': ['SSS', 'SOCIAL SECURITY'],
        'GSIS': ['GSIS', 'GOVERNMENT SERVICE'],
        'PHIC': ['PHILHEALTH', 'PHIC', 'HEALTH'],
        'TAX': ['TAX', 'WITHHOLDING', 'BIR'],
        'PAGIBIG': ['PAG-IBIG', 'HDMF', 'HOUSING']
    }
    
    # Base query for payrolls with deductions
    query = Payroll.query.options(
        joinedload(Payroll.employee).joinedload(Employee.department),
        joinedload(Payroll.period),
        joinedload(Payroll.deduction_breakdown)
    )
    
    # Apply period filter (required)
    if period_id:
        query = query.filter(Payroll.payroll_period_id == period_id)
    
    # Apply department filter
    if department_id:
        query = query.join(Employee).filter(Employee.department_id == department_id)
    
    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        query = query.join(Employee).filter(
            or_(
                Employee.first_name.ilike(search_pattern),
                Employee.last_name.ilike(search_pattern),
                Employee.employee_id.ilike(search_pattern)
            )
        )
    
    payrolls = query.all()
    
    # Filter and process deduction data
    deduction_records = []
    total_employee_share = 0
    total_employer_share = 0
    total_ec = 0
    
    for payroll in payrolls:
        employee = payroll.employee
        if not employee:
            continue
        
        # Check each deduction breakdown
        if payroll.deduction_breakdown:
            for deduction in payroll.deduction_breakdown:
                deduction_name = (deduction.deduction_name or "").upper()
                
                # Check if this deduction matches the selected provider
                if provider and provider in PROVIDER_KEYWORDS:
                    keywords = PROVIDER_KEYWORDS[provider]
                    if not any(kw in deduction_name for kw in keywords):
                        continue  # Skip if doesn't match provider
                
                # Calculate employee share
                emp_share = deduction.employee_share or 0
                emp_share_total = deduction.employer_share or 0
                ec_share = deduction.ec or 0
                
                deduction_records.append({
                    'payroll_id': payroll.id,
                    'employee_id': employee.employee_id,
                    'employee_name': employee.get_full_name(),
                    'department': employee.department.name if employee.department else 'N/A',
                    'period': payroll.period.period_name if payroll.period else 'N/A',
                    'deduction_name': deduction.deduction_name or 'Unknown',
                    'employee_share': emp_share,
                    'employer_share': emp_share_total,
                    'ec': ec_share,
                    'total_contribution': emp_share + emp_share_total + ec_share,
                    'status': payroll.status
                })
                
                total_employee_share += emp_share
                total_employer_share += emp_share_total
                total_ec += ec_share
    
    # Sort by employee name
    deduction_records.sort(key=lambda x: x['employee_name'])
    
    # Pagination
    per_page = 20
    total_records = len(deduction_records)
    total_pages = (total_records + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_records = deduction_records[start_idx:end_idx]
    
    # Get dropdown data
    departments = Department.query.order_by(Department.name).all()
    payroll_periods = PayrollPeriod.query.order_by(
        PayrollPeriod.start_date.desc()
    ).all()
    
    # Provider options
    provider_options = [
        {'value': '', 'label': 'All Providers'},
        {'value': 'SSS', 'label': 'SSS (Social Security)'},
        {'value': 'GSIS', 'label': 'GSIS (Government Service)'},
        {'value': 'PHIC', 'label': 'PhilHealth'},
        {'value': 'TAX', 'label': 'Withholding Tax'},
        {'value': 'PAGIBIG', 'label': 'Pag-IBIG/HDMF'}
    ]
    
    # Summary stats
    summary_stats = {
        'total_employees': len(set(r['employee_id'] for r in deduction_records)),
        'total_records': total_records,
        'total_employee_share': round(total_employee_share, 2),
        'total_employer_share': round(total_employer_share, 2),
        'total_ec': round(total_ec, 2),
        'total_contributions': round(total_employee_share + total_employer_share + total_ec, 2)
    }
    
    return render_template(
        'payroll/admin/reports/deduction_detail_report.html',
        records=paginated_records,
        pagination={
            'page': page,
            'total_pages': total_pages,
            'total_records': total_records,
            'per_page': per_page,
            'has_prev': page > 1,
            'has_next': page < total_pages
        },
        summary_stats=summary_stats,
        departments=departments,
        payroll_periods=payroll_periods,
        provider_options=provider_options,
        selected_provider=provider,
        selected_period=period_id,
        selected_department=department_id,
        search=search
    )


@payroll_admin_bp.route('/deduction-detail-export-pdf')
@payroll_admin_required
@login_required
def export_deduction_detail_pdf():
    """Export deduction detail report as PDF"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    from flask import send_file
    
    provider = request.args.get('provider', '', type=str).strip().upper()
    period_id = request.args.get('period_id', type=int)
    department_id = request.args.get('department_id', type=int)
    
    PROVIDER_KEYWORDS = {
        'SSS': ['SSS', 'SOCIAL SECURITY'],
        'GSIS': ['GSIS', 'GOVERNMENT SERVICE'],
        'PHIC': ['PHILHEALTH', 'PHIC', 'HEALTH'],
        'TAX': ['TAX', 'WITHHOLDING', 'BIR'],
        'PAGIBIG': ['PAG-IBIG', 'HDMF', 'HOUSING']
    }
    
    # Build query
    query = Payroll.query.options(
        joinedload(Payroll.employee).joinedload(Employee.department),
        joinedload(Payroll.period),
        joinedload(Payroll.deduction_breakdown)
    )
    
    if period_id:
        query = query.filter(Payroll.payroll_period_id == period_id)
    
    if department_id:
        query = query.join(Employee).filter(Employee.department_id == department_id)
    
    payrolls = query.all()
    
    # Process data
    deduction_records = []
    total_employee_share = 0
    total_employer_share = 0
    total_ec = 0
    
    for payroll in payrolls:
        employee = payroll.employee
        if not employee:
            continue
        
        if payroll.deduction_breakdown:
            for deduction in payroll.deduction_breakdown:
                deduction_name = (deduction.deduction_name or "").upper()
                
                if provider and provider in PROVIDER_KEYWORDS:
                    keywords = PROVIDER_KEYWORDS[provider]
                    if not any(kw in deduction_name for kw in keywords):
                        continue
                
                emp_share = deduction.employee_share or 0
                emp_share_total = deduction.employer_share or 0
                ec_share = deduction.ec or 0
                
                deduction_records.append({
                    'employee_id': employee.employee_id,
                    'employee_name': f"{employee.last_name}, {employee.first_name}",
                    'department': employee.department.name if employee.department else '',
                    'deduction_name': deduction.deduction_name or 'Unknown',
                    'employee_share': emp_share,
                    'employer_share': emp_share_total,
                    'ec': ec_share,
                    'total': emp_share + emp_share_total + ec_share
                })
                
                total_employee_share += emp_share
                total_employer_share += emp_share_total
                total_ec += ec_share
    
    # Sort records
    deduction_records.sort(key=lambda x: x['employee_name'])
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.25*inch,
        leftMargin=0.25*inch,
        topMargin=0.5*inch,
        bottomMargin=0.75*inch
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#374151'),
        spaceAfter=3,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Header
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("Republic of the Philippines", subtitle_style))
    elements.append(Paragraph("MUNICIPALITY OF NORZAGARAY", title_style))
    elements.append(Paragraph("Province of Bulacan", subtitle_style))
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("OFFICE OF THE MUNICIPAL TREASURER", 
            ParagraphStyle('HeaderSub', parent=styles['Normal'], fontSize=10, 
                         textColor=colors.HexColor('#1e40af'), alignment=TA_CENTER, fontName='Helvetica-Bold')))
    elements.append(Spacer(1, 0.2*inch))
    
    # Report title
    provider_label = provider or 'ALL PROVIDERS'
    period_name = PayrollPeriod.query.get(period_id).period_name if period_id and PayrollPeriod.query.get(period_id) else "All Periods"
    
    elements.append(Paragraph(f"{provider_label} DEDUCTION DETAIL REPORT", title_style))
    elements.append(Paragraph(f"Pay Period: {period_name}", subtitle_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Metadata
    meta_data = [
        ['Date Generated:', datetime.now().strftime("%B %d, %Y at %I:%M %p")],
        ['Provider:', provider_label],
        ['Total Records:', f"{len(deduction_records)} deduction(s)"],
        ['Total Employees:', str(len(set(r['employee_id'] for r in deduction_records)))],
    ]
    
    meta_table = Table(meta_data, colWidths=[1.8*inch, 4.5*inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#9ca3af')),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 0.25*inch))
    
    # Main table
    table_data = [['Employee ID', 'Employee Name', 'Department', 'Deduction', 'Employee Share', 'Employer Share', 'EC', 'Total']]
    
    for rec in deduction_records:
        table_data.append([
            rec['employee_id'],
            rec['employee_name'],
            rec['department'][:15] + '...' if len(rec['department']) > 15 else rec['department'],
            rec['deduction_name'],
            f"₱{rec['employee_share']:,.2f}",
            f"₱{rec['employer_share']:,.2f}",
            f"₱{rec['ec']:,.2f}",
            f"₱{rec['total']:,.2f}"
        ])
    
    col_widths = [0.7*inch, 1.8*inch, 1.2*inch, 1.5*inch, 1*inch, 1*inch, 0.8*inch, 1*inch]
    
    data_table = Table(table_data, colWidths=col_widths)
    data_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#e5e7eb')),
        ('PADDING', (0, 0), (-1, -1), 2),
    ]))
    
    elements.append(data_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Summary
    elements.append(Paragraph("SUMMARY OF CONTRIBUTIONS", subtitle_style))
    elements.append(Spacer(1, 0.1*inch))
    
    summary_data = [
        ['Total Employee Share:', f"₱{total_employee_share:,.2f}"],
        ['Total Employer Share:', f"₱{total_employer_share:,.2f}"],
        ['Total EC:', f"₱{total_ec:,.2f}"],
        ['★★ TOTAL CONTRIBUTIONS ★★', f"₱{total_employee_share + total_employer_share + total_ec:,.2f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -2), colors.HexColor('#f9fafb')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dbeafe')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (-2, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (-2, -1), (-1, -1), colors.HexColor('#1e40af')),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#9ca3af')),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(summary_table)
    
    # Build PDF
    def add_header_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.setFillColor(colors.HexColor('#6b7280'))
        page_num = canvas_obj.getPageNumber()
        canvas_obj.drawRightString(doc_obj.pagesize[0] - 0.25*inch, 0.35*inch, f"Page {page_num}")
        canvas_obj.drawString(0.25*inch, 0.35*inch, "CONFIDENTIAL - OFFICIAL USE ONLY")
        canvas_obj.restoreState()
    
    doc.build(elements, onFirstPage=lambda c, d: add_header_footer(c, d), onLaterPages=lambda c, d: add_header_footer(c, d))
    
    buffer.seek(0)
    filename = f"{provider or 'ALL'}_Deduction_Detail_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')