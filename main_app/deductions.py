# payroll_deductions.py
from typing import Dict

def compute_sss_deduction(salary: float) -> dict:
    # SSS 2025 minimum & maximum Salary Credit (MSC)
    min_msc = 5000
    max_msc = 35000

    # Find MSC: floor & ceiling
    effective_msc = max(min_msc, min(salary, max_msc))

    # Contribution shares
    employee_share = effective_msc * 0.05
    employer_share = effective_msc * 0.10
    total = employee_share + employer_share

    return {
        "salary": salary,
        "msc": effective_msc,
        "employee_share": round(employee_share, 2),
        "employer_share": round(employer_share, 2),
        "total": round(total, 2),
    }

# ------------------------
# PhilHealth Contribution
# ------------------------
def compute_philhealth_deduction(salary: float) -> dict:
    """
    Compute PhilHealth contribution for a given monthly salary.
    - Contribution rate: 5% of salary (split 50/50)
    - Salary floor: 10,000
    - Salary ceiling: 100,000
    """
    min_salary = 10_000
    max_salary = 100_000
    effective_salary = max(min_salary, min(salary, max_salary))
    total_premium = effective_salary * 0.05
    employee_share = total_premium / 2
    employer_share = total_premium / 2
    return {
        "salary": salary,
        "effective_salary": effective_salary,
        "total_premium": round(total_premium,2),
        "employee_share": round(employee_share,2),
        "employer_share": round(employer_share,2)
    }

# ------------------------
# Pag-IBIG Contribution
# ------------------------
def compute_pagibig_deduction(salary: float) -> dict:
    """
    Compute Pag-IBIG contribution.
    - Salary <= 1,500: fixed 100
    - Salary > 1,500: 2% of salary
    - Max salary considered: 5,000
    - Split 50/50 between employee and employer
    """
    max_salary = 5_000
    effective_salary = min(salary, max_salary)
    if effective_salary <= 1_500:
        total_contribution = 100
    else:
        total_contribution = effective_salary * 0.02
    employee_share = total_contribution / 2
    employer_share = total_contribution / 2
    return {
        "salary": salary,
        "effective_salary": effective_salary,
        "total_contribution": round(total_contribution,2),
        "employee_share": round(employee_share,2),
        "employer_share": round(employer_share,2)
    }

# ------------------------
# GSIS Contribution
# ------------------------
def compute_gsis_deduction(salary: float, employee_percent=0.09) -> dict:
    """
    Compute GSIS contribution.
    - Employee: usually 9% of salary
    - Employer: usually 12% of salary
    """
    employee_share = salary * employee_percent
    employer_share = salary * 0.12
    total = employee_share + employer_share
    return {
        "salary": salary,
        "employee_share": round(employee_share,2),
        "employer_share": round(employer_share,2),
        "total": round(total,2)
    }

# ------------------------
# MENPC / Coop Contribution
# ------------------------
def compute_menpc_deduction(salary: float, rate=0.01) -> dict:
    """
    Coop / MENPC contribution, usually 1% of salary
    """
    total = salary * rate
    return {
        "salary": salary,
        "employee_share": round(total,2),
        "total": round(total,2)
    }

# ------------------------
# Pag-IBIG Loans
# ------------------------
def compute_pagibig_loan(salary: float, loan_type: str="short-term") -> float:
    """
    Pag-IBIG loan deduction
    - short-term: 2%
    - calamity: 1%
    - emergency: 1.5%
    """
    rates = {"short-term": 0.02, "calamity": 0.01, "emergency": 0.015}
    rate = rates.get(loan_type, 0.02)
    return round(salary * rate,2)

# ------------------------
# Withholding Tax (simplified TRAIN table)
# ------------------------
def compute_withholding_tax(salary: float) -> float:
    """
    Simplified monthly withholding tax based on TRAIN 2023-2026
    """
    monthly_salary = salary
    if monthly_salary <= 250_000/12:
        return 0
    elif monthly_salary <= 400_000/12:
        excess = monthly_salary - (250_000/12)
        return round(0.20 * excess,2)
    elif monthly_salary <= 800_000/12:
        excess = monthly_salary - (400_000/12)
        return round((30_000/12) + 0.25 * excess,2)
    elif monthly_salary <= 2_000_000/12:
        excess = monthly_salary - (800_000/12)
        return round((130_000/12) + 0.30 * excess,2)
    elif monthly_salary <= 8_000_000/12:
        excess = monthly_salary - (2_000_000/12)
        return round((490_000/12) + 0.32 * excess,2)
    else:
        excess = monthly_salary - (8_000_000/12)
        return round((2_410_000/12) + 0.35 * excess,2)

# ------------------------
# Combine All Deductions
# ------------------------
def compute_all_deductions(salary: float) -> dict:
    """
    Combine all deductions into a single dictionary
    """
    return {
        "SSS": compute_sss_deduction(salary),
        "PhilHealth": compute_philhealth_deduction(salary),
        "PagIBIG": compute_pagibig_deduction(salary),
        "GSIS": compute_gsis_deduction(salary),
        "MENPC": compute_menpc_deduction(salary),
        "PagIBIG_Loan": {
            "ShortTerm": compute_pagibig_loan(salary, "short-term"),
            "Calamity": compute_pagibig_loan(salary, "calamity"),
            "Emergency": compute_pagibig_loan(salary, "emergency")
        },
        "WithholdingTax": compute_withholding_tax(salary)
    }


def compute_jo_withholding_tax(gross_pay: float) -> float:
    """
    Simplified TRAIN withholding tax for Job Order employees.
    Assumes monthly equivalent.
    """

    TAX_FREE_MONTHLY = 250_000 / 12  # 20,833.33

    if gross_pay <= TAX_FREE_MONTHLY:
        return 0.00

    excess = gross_pay - TAX_FREE_MONTHLY
    return round(excess * 0.20, 2)


# main_app/utils/payroll_utils.py (or wherever you keep helper functions)
def compute_regular_withholding_tax(gross_pay: float) -> float:
    """
    Compute withholding tax for regular employees.
    Example: flat 10% of gross pay. Adjust logic as needed.
    """
    if gross_pay <= 0:
        return 0.0
    tax_rate = 0.10  # 10% flat rate, change if needed
    return round(gross_pay * tax_rate, 2)
