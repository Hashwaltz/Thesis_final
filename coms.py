from main_app.extensions import db
from main_app.models.payroll_models import Deduction, DeductionBracket
from datetime import datetime

def seed_sss_brackets():

    sss = Deduction.query.filter_by(name="SSS Contribution").first()

    if not sss:
        print("SSS deduction not found")
        return

    brackets = [
        # salary_from, salary_to, employee_share, employer_share
        (0, 5249.99, 250, 500),
        (5250, 5749.99, 275, 550),
        (5750, 6249.99, 300, 600),
        (6250, 6749.99, 325, 650),
        (6750, 7249.99, 350, 700),
        (7250, 7749.99, 375, 750),
        (7750, 8249.99, 400, 800),
        (8250, 8749.99, 425, 850),
        (8750, 9249.99, 450, 900),
        (9250, 9749.99, 475, 950),
        (9750, 10249.99, 500, 1000),
        (10250, 10749.99, 525, 1050),
        (10750, 11249.99, 550, 1100),
        (11250, 11749.99, 575, 1150),
        (11750, 12249.99, 600, 1200),
        (12250, 12749.99, 625, 1250),
        (12750, 13249.99, 650, 1300),
        (13250, 13749.99, 675, 1350),
        (13750, 14249.99, 700, 1400),
        (14250, 14749.99, 725, 1450),
        (14750, 15249.99, 750, 1500),
        (15250, 15749.99, 775, 1550),
        (15750, 16249.99, 800, 1600),
        (16250, 16749.99, 825, 1650),
        (16750, 17249.99, 850, 1700),
        (17250, 17749.99, 875, 1750),
        (17750, 18249.99, 900, 1800),
        (18250, 18749.99, 925, 1850),
        (18750, 19249.99, 950, 1900),
        (19250, 19749.99, 975, 1950),
        (19750, 20249.99, 1000, 2000),
        (20250, 20749.99, 1025, 2050),
        (20750, 21249.99, 1050, 2100),
        (21250, 21749.99, 1075, 2150),
        (21750, 22249.99, 1100, 2200),
        (22250, 22749.99, 1125, 2250),
        (22750, 23249.99, 1150, 2300),
        (23250, 23749.99, 1175, 2350),
        (23750, 24249.99, 1200, 2400),
        (34750, 999999, 1750, 3500)
    ]

    for salary_from, salary_to, ee, er in brackets:

        bracket = DeductionBracket(
            deduction_id=sss.id,
            salary_from=salary_from,
            salary_to=salary_to,
            employee_share=ee,
            employer_share=er
        )

        db.session.add(bracket)

    db.session.commit()

    print("SSS brackets seeded successfully!")


from main_app.models.payroll_models import Deduction
from main_app.extensions import db
 # Check if GSIS already exists

def seed_gsis():
        gsis = Deduction.query.filter_by(name="GSIS Contribution").first()
        if not gsis:
            gsis = Deduction(
                name="GSIS Contribution",
                description="Government Service Insurance System contribution",
                calculation_type="percentage",  # or 'bracket' if you want brackets like SSS
                rate=0.09,  # 9% employee contribution
                floor=0,    # optional, minimum salary for calculation
                ceiling=None,  # optional, max salary for calculation
                active=True
            )
        db.session.add(gsis)
        db.session.commit()
        print("GSIS deduction seeded successfully!")



def seed_pagibig():
    # Check if Pag-IBIG already exists
    pagibig = Deduction.query.filter_by(name="Pag-IBIG Contribution").first()
    if not pagibig:
        pagibig = Deduction(
            name="Pag-IBIG Contribution",
            description="Home Development Mutual Fund contribution (HDMF)",
            calculation_type="percentage",  # simple 2% deduction
            rate=0.02,  # 2% employee contribution
            floor=0,     # optional minimum salary
            ceiling=5000,  # max salary for calculation
            active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(pagibig)
        db.session.commit()
        print("Pag-IBIG deduction seeded successfully!")
    else:
        print("Pag-IBIG deduction already exists.")