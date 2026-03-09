from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required


from main_app.extensions import db
from main_app.models.payroll_models import Deduction, DeductionBracket
from main_app.helpers.decorators import payroll_admin_required

from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp

# =========================================================
# ADD BRACKET
# =========================================================

@payroll_admin_bp.route("/deduction/<int:deduction_id>/brackets/add", methods=["POST"])
@login_required
@payroll_admin_required
def add_bracket(deduction_id):

    deduction = Deduction.query.get_or_404(deduction_id)

    salary_from = float(request.form.get("salary_from", 0))
    salary_to = float(request.form.get("salary_to", 0))
    employee_share = float(request.form.get("employee_share", 0))
    employer_share = float(request.form.get("employer_share", 0))

    bracket = DeductionBracket(
        deduction_id=deduction.id,
        salary_from=salary_from,
        salary_to=salary_to,
        employee_share=employee_share,
        employer_share=employer_share
    )

    db.session.add(bracket)
    db.session.commit()

    flash("Bracket added successfully", "success")

    return redirect(
        url_for("payroll_admin_bp.deduction_brackets",
                deduction_id=deduction.id)
    )


# =========================================================
# DELETE BRACKET
# =========================================================

@payroll_admin_bp.route("/bracket/<int:bracket_id>/delete")
@login_required
@payroll_admin_required
def delete_bracket(bracket_id):

    bracket = DeductionBracket.query.get_or_404(bracket_id)

    deduction_id = bracket.deduction_id

    db.session.delete(bracket)
    db.session.commit()

    flash("Bracket deleted", "success")

    return redirect(
        url_for(
            "payroll_admin_bp.deduction_brackets",
            deduction_id=deduction_id
        )
    )