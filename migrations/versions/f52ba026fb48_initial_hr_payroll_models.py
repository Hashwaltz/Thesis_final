"""initial HR + Payroll models

Revision ID: f52ba026fb48
Revises: ee3e65a96dd9
Create Date: 2026-02-11 11:27:30.890014

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f52ba026fb48'
down_revision = 'ee3e65a96dd9'
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------
    # Allowance table changes
    # ------------------------------
    with op.batch_alter_table('allowance', schema=None) as batch_op:
        batch_op.alter_column('name', existing_type=sa.VARCHAR(length=100), nullable=True)
        batch_op.drop_column('type')
        batch_op.drop_column('percentage')
        batch_op.drop_column('created_at')
        batch_op.drop_column('description')

    # ------------------------------
    # Deduction table changes
    # ------------------------------
    with op.batch_alter_table('deduction', schema=None) as batch_op:
        batch_op.alter_column('name', existing_type=sa.VARCHAR(length=100), nullable=True)
        batch_op.drop_column('created_at')
        batch_op.drop_column('type')
        batch_op.drop_column('is_mandatory')
        batch_op.drop_column('description')
        batch_op.drop_column('percentage')

    # ------------------------------
    # Employee allowances
    # ------------------------------
    with op.batch_alter_table('employee_allowances', schema=None) as batch_op:
        batch_op.alter_column('employee_id', existing_type=sa.INTEGER(), nullable=True)
        batch_op.alter_column('allowance_id', existing_type=sa.INTEGER(), nullable=True)

    # ------------------------------
    # Employee deductions
    # ------------------------------
    with op.batch_alter_table('employee_deductions', schema=None) as batch_op:
        batch_op.alter_column('employee_id', existing_type=sa.INTEGER(), nullable=True)
        batch_op.alter_column('deduction_id', existing_type=sa.INTEGER(), nullable=True)

    # ------------------------------
    # Payroll table changes
    # ------------------------------
    with op.batch_alter_table('payroll', schema=None) as batch_op:
        # Add NOT NULL column with temporary default for existing rows
        batch_op.add_column(
            sa.Column('payroll_period_id', sa.Integer(), nullable=False, server_default='1')
        )
        batch_op.add_column(sa.Column('night_diff', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('sss', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('philhealth', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('pagibig', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('tax', sa.Float(), nullable=True))
        batch_op.alter_column('basic_salary', existing_type=sa.FLOAT(), nullable=True)
        batch_op.alter_column('gross_pay', existing_type=sa.FLOAT(), nullable=True)
        batch_op.alter_column('net_pay', existing_type=sa.FLOAT(), nullable=True)
        batch_op.alter_column('status', existing_type=sa.VARCHAR(length=50), type_=sa.String(length=30), existing_nullable=True)

        # Explicitly name the foreign key
        batch_op.create_foreign_key(
            "fk_payroll_payroll_period", "payroll_period", ["payroll_period_id"], ["id"]
        )

        batch_op.drop_column('philhealth_contribution')
        batch_op.drop_column('tax_withheld')
        batch_op.drop_column('other_deductions')
        batch_op.drop_column('pay_period_start')
        batch_op.drop_column('pagibig_contribution')
        batch_op.drop_column('overtime_pay')
        batch_op.drop_column('pay_period_id')
        batch_op.drop_column('pay_period_end')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('sss_contribution')
        batch_op.drop_column('night_differential')

    # Remove the temporary server default
    with op.batch_alter_table('payroll', schema=None) as batch_op:
        batch_op.alter_column('payroll_period_id', server_default=None)

    # ------------------------------
    # Payroll period table
    # ------------------------------
    with op.batch_alter_table('payroll_period', schema=None) as batch_op:
        batch_op.alter_column('status', existing_type=sa.VARCHAR(length=50), type_=sa.String(length=30), existing_nullable=True)

    # ------------------------------
    # Payslip table
    # ------------------------------
    with op.batch_alter_table('payslip', schema=None) as batch_op:
        batch_op.alter_column('payslip_number', existing_type=sa.VARCHAR(length=50), nullable=True)
        batch_op.alter_column('gross_pay', existing_type=sa.FLOAT(), nullable=True)
        batch_op.alter_column('net_pay', existing_type=sa.FLOAT(), nullable=True)

        batch_op.drop_column('philhealth_contribution')
        batch_op.drop_column('claimed')
        batch_op.drop_column('tax_withheld')
        batch_op.drop_column('other_deductions')
        batch_op.drop_column('pay_period_start')
        batch_op.drop_column('allowances')
        batch_op.drop_column('pagibig_contribution')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('overtime_pay')
        batch_op.drop_column('status')
        batch_op.drop_column('holiday_pay')
        batch_op.drop_column('rejection_reason')
        batch_op.drop_column('pay_period_end')
        batch_op.drop_column('sss_contribution')
        batch_op.drop_column('generated_by')
        batch_op.drop_column('basic_salary')
        batch_op.drop_column('approved_by')
        batch_op.drop_column('night_differential')

    # ------------------------------
    # Tax table
    # ------------------------------
    with op.batch_alter_table('tax', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('fixed', sa.Float(), nullable=True))
        batch_op.alter_column('min_income', existing_type=sa.FLOAT(), nullable=True)
        batch_op.alter_column('max_income', existing_type=sa.FLOAT(), nullable=True)
        batch_op.drop_column('fixed_amount')
        batch_op.drop_column('created_at')
        batch_op.drop_column('tax_rate')
        batch_op.drop_column('active')


def downgrade():
    # Reverse upgrade operations
    with op.batch_alter_table('tax', schema=None) as batch_op:
        batch_op.add_column(sa.Column('active', sa.BOOLEAN(), nullable=True))
        batch_op.add_column(sa.Column('tax_rate', sa.FLOAT(), nullable=False))
        batch_op.add_column(sa.Column('created_at', sa.DATETIME(), nullable=True))
        batch_op.add_column(sa.Column('fixed_amount', sa.FLOAT(), nullable=True))
        batch_op.alter_column('max_income', existing_type=sa.FLOAT(), nullable=False)
        batch_op.alter_column('min_income', existing_type=sa.FLOAT(), nullable=False)
        batch_op.drop_column('fixed')
        batch_op.drop_column('rate')

    with op.batch_alter_table('payslip', schema=None) as batch_op:
        batch_op.add_column(sa.Column('night_differential', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('approved_by', sa.INTEGER(), nullable=True))
        batch_op.add_column(sa.Column('basic_salary', sa.FLOAT(), nullable=False))
        batch_op.add_column(sa.Column('generated_by', sa.INTEGER(), nullable=True))
        batch_op.add_column(sa.Column('sss_contribution', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('pay_period_end', sa.DATE(), nullable=False))
        batch_op.add_column(sa.Column('rejection_reason', sa.VARCHAR(length=255), nullable=True))
        batch_op.add_column(sa.Column('holiday_pay', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('status', sa.VARCHAR(length=50), nullable=True))
        batch_op.add_column(sa.Column('overtime_pay', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DATETIME(), nullable=True))
        batch_op.add_column(sa.Column('pagibig_contribution', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('allowances', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('pay_period_start', sa.DATE(), nullable=False))
        batch_op.add_column(sa.Column('other_deductions', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('tax_withheld', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('claimed', sa.BOOLEAN(), nullable=True))
        batch_op.add_column(sa.Column('philhealth_contribution', sa.FLOAT(), nullable=True))
        batch_op.alter_column('net_pay', existing_type=sa.FLOAT(), nullable=False)
        batch_op.alter_column('gross_pay', existing_type=sa.FLOAT(), nullable=False)
        batch_op.alter_column('payslip_number', existing_type=sa.VARCHAR(length=50), nullable=False)

    with op.batch_alter_table('payroll_period', schema=None) as batch_op:
        batch_op.alter_column('status', existing_type=sa.String(length=30), type_=sa.VARCHAR(length=50), existing_nullable=True)

    with op.batch_alter_table('payroll', schema=None) as batch_op:
        batch_op.drop_constraint("fk_payroll_payroll_period", type_='foreignkey')
        batch_op.add_column(sa.Column('night_differential', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('sss_contribution', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DATETIME(), nullable=True))
        batch_op.add_column(sa.Column('pay_period_end', sa.DATE(), nullable=False))
        batch_op.add_column(sa.Column('pay_period_id', sa.INTEGER(), nullable=False))
        batch_op.add_column(sa.Column('overtime_pay', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('pagibig_contribution', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('pay_period_start', sa.DATE(), nullable=False))
        batch_op.add_column(sa.Column('other_deductions', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('tax_withheld', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('philhealth_contribution', sa.FLOAT(), nullable=True))
        batch_op.alter_column('status', existing_type=sa.String(length=30), type_=sa.VARCHAR(length=50), existing_nullable=True)
        batch_op.alter_column('net_pay', existing_type=sa.FLOAT(), nullable=False)
        batch_op.alter_column('gross_pay', existing_type=sa.FLOAT(), nullable=False)
        batch_op.alter_column('basic_salary', existing_type=sa.FLOAT(), nullable=False)
        batch_op.drop_column('tax')
        batch_op.drop_column('pagibig')
        batch_op.drop_column('philhealth')
        batch_op.drop_column('sss')
        batch_op.drop_column('night_diff')
        batch_op.drop_column('payroll_period_id')

    # Employee deductions
    with op.batch_alter_table('employee_deductions', schema=None) as batch_op:
        batch_op.alter_column('deduction_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.alter_column('employee_id', existing_type=sa.INTEGER(), nullable=False)

    # Employee allowances
    with op.batch_alter_table('employee_allowances', schema=None) as batch_op:
        batch_op.alter_column('allowance_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.alter_column('employee_id', existing_type=sa.INTEGER(), nullable=False)

    # Deduction
    with op.batch_alter_table('deduction', schema=None) as batch_op:
        batch_op.add_column(sa.Column('percentage', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('description', sa.TEXT(), nullable=True))
        batch_op.add_column(sa.Column('is_mandatory', sa.BOOLEAN(), nullable=True))
        batch_op.add_column(sa.Column('type', sa.VARCHAR(length=50), nullable=False))
        batch_op.add_column(sa.Column('created_at', sa.DATETIME(), nullable=True))
        batch_op.alter_column('name', existing_type=sa.VARCHAR(length=100), nullable=False)

    # Allowance
    with op.batch_alter_table('allowance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.TEXT(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DATETIME(), nullable=True))
        batch_op.add_column(sa.Column('percentage', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('type', sa.VARCHAR(length=50), nullable=False))
        batch_op.alter_column('name', existing_type=sa.VARCHAR(length=100), nullable=False)
