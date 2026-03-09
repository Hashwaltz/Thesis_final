
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




# =========================================================
# MARK AS DISTRIBUTED / CLAIMED
# =========================================================
@payroll_admin_bp.route('/payslips/distribute/<int:payslip_id>', methods=['POST'])
@payroll_admin_required
@login_required
def distribute_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)

    if payslip.status == "Distributed":
        flash("Payslip already marked as distributed (claimed).", "info")
        return redirect(url_for('payroll_admin_bp.view_payslips'))

    payslip.status = "Distributed"
    payslip.claimed = True  # ✅ Mark as claimed when distributed
    payslip.distributed_at = datetime.utcnow()
    db.session.commit()

    flash(f"Payslip {payslip.payslip_number} marked as distributed and claimed.", "success")
    return redirect(url_for('payroll_admin_bp.view_payslips'))



# =========================================================
# GENERATE SINGLE PAYSLIP
# =========================================================
@payroll_admin_bp.route('/payslips/generate/<int:payroll_id>', methods=['POST'])
@payroll_admin_required
@login_required
def generate_single_payslip(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)

    existing = Payslip.query.filter_by(payroll_id=payroll.id).first()
    if existing:
        flash("Payslip already exists for this employee.", "info")
        return redirect(url_for('payroll_admin_bp.view_payslips'))

    payslip = generate_payslip(payroll, current_user.id)
    db.session.add(payslip)
    db.session.commit()

    flash(f"Payslip generated for employee ID {payroll.employee_id}.", "success")
    return redirect(url_for('payroll_admin_bp.view_payslips'))



# =========================================================
# REVIEW & APPROVE PAYSLIPS (TABLE VIEW)
# =========================================================
@payroll_admin_bp.route('/payslips/review', methods=['GET', 'POST'])
@payroll_admin_required
@login_required
def review_payslips():
    if request.method == 'POST':
        action = request.form.get('action')

        # Bulk approve all
        if action == 'approve_all':
            payslips = Payslip.query.filter(Payslip.status == "Generated").all()
            for p in payslips:
                p.status = "Approved"
                p.approved_by = current_user.id
                p.approved_at = datetime.utcnow()
            db.session.commit()
            flash(f"All generated payslips approved successfully.", "success")
            return redirect(url_for('payroll_admin_bp.review_payslips'))

        # Individual approve/reject
        payslip_id = request.form.get('payslip_id')
        decision = request.form.get('decision')
        reason = request.form.get('reason', '').strip()
        payslip = Payslip.query.get_or_404(payslip_id)

        if payslip.status in ["Approved", "Rejected", "Distributed"]:
            flash(f"Payslip {payslip.payslip_number} already {payslip.status.lower()}.", "info")
            return redirect(url_for('payroll_admin_bp.review_payslips'))

        if decision == 'approve':
            payslip.status = "Approved"
            payslip.approved_by = current_user.id
            payslip.approved_at = datetime.utcnow()
            payslip.rejection_reason = None
            flash(f"Payslip {payslip.payslip_number} approved.", "success")
        elif decision == 'reject':
            payslip.status = "Rejected"
            payslip.approved_by = current_user.id
            payslip.approved_at = datetime.utcnow()
            payslip.rejection_reason = reason or "No reason provided."
            flash(f"Payslip {payslip.payslip_number} rejected.", "danger")

        db.session.commit()
        return redirect(url_for('payroll_admin_bp.review_payslips'))

    # GET: Load table
    payslips = Payslip.query.order_by(Payslip.generated_at.desc()).all()
    return render_template('payroll/admin/payslips/review_payslips.html', payslips=payslips)

# =========================================================
# APPROVE PAYSLIP
# =========================================================
@payroll_admin_bp.route('/payslips/approve/<int:payslip_id>', methods=['POST'])
@payroll_admin_required
@login_required
def approve_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)

    if payslip.status in ["Approved", "Rejected", "Distributed"]:
        flash(f"Payslip {payslip.payslip_number} has already been {payslip.status.lower()}.", "info")
        return redirect(url_for('payroll_admin_bp.view_payslips'))

    payslip.status = "Approved"
    payslip.approved_by = current_user.id
    payslip.approved_at = datetime.utcnow()
    db.session.commit()

    flash(f"Payslip {payslip.payslip_number} approved successfully.", "success")
    return redirect(url_for('payroll_admin_bp.view_payslips'))


# =========================================================
# REJECT PAYSLIP
# =========================================================
@payroll_admin_bp.route('/payslips/reject/<int:payslip_id>', methods=['POST'])
@payroll_admin_required
@login_required
def reject_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    reason = request.form.get('reason', '').strip()

    if payslip.status in ["Approved", "Rejected", "Distributed"]:
        flash(f"Payslip {payslip.payslip_number} has already been {payslip.status.lower()}.", "info")
        return redirect(url_for('payroll_admin_bp.view_payslips'))

    payslip.status = "Rejected"
    payslip.rejection_reason = reason or "No reason provided"
    db.session.commit()

    flash(f"Payslip {payslip.payslip_number} rejected. Reason: {payslip.rejection_reason}", "warning")
    return redirect(url_for('payroll_admin_bp.view_payslips'))





