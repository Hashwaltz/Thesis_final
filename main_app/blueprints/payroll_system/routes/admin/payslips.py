
from datetime import  datetime
from flask import render_template, request, redirect, flash, url_for, jsonify
from flask_login import login_required, current_user


from main_app.models.payroll_models import  Payroll, Payslip
from main_app.helpers.decorators import payroll_admin_required
from main_app.extensions import db
from main_app.functions import generate_payslip

from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp


# =========================================================
# MARK AS CLAIMED (FIXED: NO "Distributed")
# =========================================================
@payroll_admin_bp.route('/payslips/claim/<int:payslip_id>', methods=['POST'])
@payroll_admin_required
@login_required
def claim_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)

    if payslip.status == "CLAIMED":
        return jsonify({"message": "Already claimed"}), 200

    payslip.status = "CLAIMED"
    payslip.claimed_at = datetime.utcnow()
    payslip.claimed_by = current_user.id  # optional but recommended

    db.session.commit()

    return jsonify({"message": "Payslip marked as claimed"}), 200


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
# REVIEW PAYSLIPS
# =========================================================
@payroll_admin_bp.route('/payslips/review', methods=['GET', 'POST'])
@payroll_admin_required
@login_required
def review_payslips():

    if request.method == 'POST':
        action = request.form.get('action')

        # BULK APPROVE
        if action == 'approve_all':
            payslips = Payslip.query.filter(Payslip.status == "GENERATED").all()

            for p in payslips:
                p.status = "APPROVED"
                p.approved_by = current_user.id
                p.approved_at = datetime.utcnow()

            db.session.commit()
            flash("All generated payslips approved successfully.", "success")
            return redirect(url_for('payroll_admin_bp.review_payslips'))

        # SINGLE ACTION
        payslip_id = request.form.get('payslip_id')
        decision = request.form.get('decision')
        reason = request.form.get('reason', '').strip()

        payslip = Payslip.query.get_or_404(payslip_id)

        if payslip.status in ["APPROVED", "REJECTED", "CLAIMED"]:
            flash(f"Payslip already {payslip.status.lower()}.", "info")
            return redirect(url_for('payroll_admin_bp.review_payslips'))

        if decision == 'approve':
            payslip.status = "APPROVED"
            payslip.approved_by = current_user.id
            payslip.approved_at = datetime.utcnow()
            payslip.rejection_reason = None

        elif decision == 'reject':
            payslip.status = "REJECTED"
            payslip.rejection_reason = reason or "No reason provided"
            payslip.approved_by = current_user.id
            payslip.approved_at = datetime.utcnow()

        db.session.commit()
        return redirect(url_for('payroll_admin_bp.review_payslips'))

    payslips = Payslip.query.order_by(Payslip.generated_at.desc()).all()
    return render_template(
        'payroll/admin/payslips/review_payslips.html',
        payslips=payslips
    )


# =========================================================
# APPROVE PAYSLIP (SINGLE)
# =========================================================
@payroll_admin_bp.route('/payslips/approve/<int:payslip_id>', methods=['POST'])
@payroll_admin_required
@login_required
def approve_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)

    if payslip.status in ["APPROVED", "REJECTED", "CLAIMED"]:
        flash(f"Payslip already {payslip.status.lower()}.", "info")
        return redirect(url_for('payroll_admin_bp.view_payslips'))

    payslip.status = "APPROVED"
    payslip.approved_by = current_user.id
    payslip.approved_at = datetime.utcnow()

    db.session.commit()

    flash("Payslip approved successfully.", "success")
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

    if payslip.status in ["APPROVED", "REJECTED", "CLAIMED"]:
        flash(f"Payslip already {payslip.status.lower()}.", "info")
        return redirect(url_for('payroll_admin_bp.view_payslips'))

    payslip.status = "REJECTED"
    payslip.rejection_reason = reason or "No reason provided"
    payslip.approved_by = current_user.id
    payslip.approved_at = datetime.utcnow()

    db.session.commit()

    flash("Payslip rejected successfully.", "warning")
    return redirect(url_for('payroll_admin_bp.view_payslips'))