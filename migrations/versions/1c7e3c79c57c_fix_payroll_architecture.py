"""fix payroll architecture

Revision ID: 1c7e3c79c57c
Revises: 43cc6a5c8326
Create Date: 2026-02-28 11:47:29.854446

"""

from alembic import op
import sqlalchemy as sa


# ========================
# Migration Identity
# ========================

revision = '1c7e3c79c57c'
down_revision = '43cc6a5c8326'
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # -----------------------------
    # Deduction Bracket Table
    # -----------------------------
    if not sa.inspect(op.get_bind()).has_table("deduction_bracket"):

        op.create_table(
            'deduction_bracket',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('deduction_id', sa.Integer(), nullable=False),

            sa.Column('salary_from', sa.Float(), nullable=False),
            sa.Column('salary_to', sa.Float(), nullable=False),

            sa.Column('employee_share', sa.Float()),
            sa.Column('employer_share', sa.Float()),
            sa.Column('ec', sa.Float()),

            sa.Column('rate', sa.Float()),
            sa.Column('fixed_amount', sa.Float()),

            sa.Column('created_at', sa.DateTime()),

            sa.ForeignKeyConstraint(
                ['deduction_id'],
                ['deduction.id'],
                name="fk_deduction_bracket_deduction"
            )
        )

    # -----------------------------
    # Payroll Deduction Table
    # -----------------------------
    if not sa.inspect(op.get_bind()).has_table("payroll_deduction"):

        op.create_table(
            'payroll_deduction',
            sa.Column('id', sa.Integer(), primary_key=True),

            sa.Column('payroll_id', sa.Integer(), nullable=False),

            sa.Column('deduction_name', sa.String(100)),

            sa.Column('employee_share', sa.Float(), server_default="0"),
            sa.Column('employer_share', sa.Float(), server_default="0"),
            sa.Column('ec', sa.Float(), server_default="0"),

            sa.Column('created_at', sa.DateTime()),

            sa.ForeignKeyConstraint(
                ['payroll_id'],
                ['payroll.id'],
                name="fk_payroll_deduction_payroll"
            )
        )

    # -----------------------------
    # Deduction Table Alteration
    # -----------------------------
    with op.batch_alter_table('deduction') as batch_op:

        batch_op.add_column(sa.Column(
            'description',
            sa.Text(),
            nullable=True
        ))

        batch_op.add_column(sa.Column(
            'calculation_type',
            sa.String(20),
            nullable=False,
            server_default="fixed"
        ))

        batch_op.add_column(sa.Column(
            'rate',
            sa.Float(),
            nullable=True
        ))

        batch_op.add_column(sa.Column(
            'ceiling',
            sa.Float(),
            nullable=True
        ))

        batch_op.add_column(sa.Column(
            'floor',
            sa.Float(),
            nullable=True
        ))

        batch_op.add_column(sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=True
        ))

        # Named constraint (VERY IMPORTANT)
        batch_op.create_unique_constraint(
            "uq_deduction_name",
            ["name"]
        )

        batch_op.alter_column(
            'name',
            existing_type=sa.VARCHAR(length=100),
            nullable=False
        )

        # Remove old architecture fields
        if column_exists(batch_op, 'min_salary'):
            batch_op.drop_column('min_salary')

        if column_exists(batch_op, 'max_salary'):
            batch_op.drop_column('max_salary')

    # -----------------------------
    # Employee Deduction Table
    # -----------------------------
    with op.batch_alter_table('employee_deductions') as batch_op:

        batch_op.add_column(sa.Column(
            'override_amount',
            sa.Float(),
            nullable=True
        ))

        batch_op.alter_column(
            'employee_id',
            existing_type=sa.INTEGER(),
            nullable=False
        )

        batch_op.alter_column(
            'deduction_id',
            existing_type=sa.INTEGER(),
            nullable=False
        )

        if column_exists(batch_op, 'amount'):
            batch_op.drop_column('amount')


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    with op.batch_alter_table('employee_deductions') as batch_op:

        batch_op.add_column(sa.Column(
            'amount',
            sa.FLOAT(),
            nullable=True
        ))

        batch_op.drop_column('override_amount')

    with op.batch_alter_table('deduction') as batch_op:

        batch_op.add_column(sa.Column(
            'max_salary',
            sa.FLOAT(),
            nullable=True
        ))

        batch_op.add_column(sa.Column(
            'min_salary',
            sa.FLOAT(),
            nullable=True
        ))

        batch_op.drop_constraint(
            "uq_deduction_name",
            type_='unique'
        )

        batch_op.drop_column('created_at')
        batch_op.drop_column('floor')
        batch_op.drop_column('ceiling')
        batch_op.drop_column('rate')
        batch_op.drop_column('calculation_type')
        batch_op.drop_column('description')

    op.drop_table('payroll_deduction')
    op.drop_table('deduction_bracket')


# ============================================================
# Helper Function
# ============================================================

def column_exists(batch_op, column_name):
    """Safe column existence checker"""
    try:
        columns = [c.name for c in batch_op.impl.table.columns]
        return column_name in columns
    except:
        return False