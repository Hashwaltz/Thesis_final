import io
import os
import pandas as pd
from datetime import datetime
from flask import send_file

from openpyxl.drawing.image import Image as OpenpyxlImage


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
            "Name": f"{p.employee.first_name} {p.employee.last_name}",
            "Department": p.employee.department.name if p.employee.department else "-",

            "Basic Salary": safe_get(p, "basic_salary"),
            "Overtime Hours": safe_get(p, "overtime_hours"),
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
            "Pay Period": f"{getattr(p.period, 'start_date', '-') } - {getattr(p.period, 'end_date', '-')}"
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()

    # ✅ Write Excel file
    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Payroll",
            startrow=10   # ⭐ Leave space for header logo
        )

        workbook = writer.book
        worksheet = writer.sheets["Payroll"]

        # ===============================
        # ⭐ LOGO INSERTION
        # ===============================

        logo_path = r"C:\Users\pc\Desktop\Thesis_final\main_app\static\img\garay.png"

        if os.path.exists(logo_path):
            img = OpenpyxlImage(logo_path)

            img.width = 120
            img.height = 120

            worksheet.add_image(img, "A1")

        # ===============================
        # ⭐ Professional Government Header
        # ===============================

        header_lines = [
            "Republic of the Philippines",
            "MUNICIPALITY OF NORZAGARAY",
            "Province of Bulacan",
            "",
            "Municipal Hall of Norzagaray",
            "Norzagaray, Bulacan, Philippines",
            "",
            "Payroll Summary Report"
        ]

        row = 2
        for text in header_lines:
            worksheet.cell(row=row, column=3, value=text)
            row += 1

    output.seek(0)

    filename = f"Payroll_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )