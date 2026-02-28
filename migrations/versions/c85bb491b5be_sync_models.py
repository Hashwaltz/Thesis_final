"""sync models

Revision ID: c85bb491b5be
Revises: 3c9f3607e2fc
Create Date: 2026-02-28 10:44:06.375714
"""

from alembic import op
import sqlalchemy as sa

revision = 'c85bb491b5be'
down_revision = '3c9f3607e2fc'
branch_labels = None
depends_on = None


# =========================
# UPGRADE
# =========================
def upgrade():

    # ===== deduction_bracket =====
    op.create_table(
        'deduction_bracket',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('deduction_id', sa.Integer(), nullable=False),
        sa.Column('salary_from', sa.Float(), nullable=False),
        sa.Column('salary_to', sa.Float(), nullable=False),
        sa.Column('employee_share', sa.Float(), nullable=True),
        sa.Column('employer_share', sa.Float(), nullable=True),
        sa.Column('ec', sa.Float(), nullable=True),
        sa.Column('rate', sa.Float(), nullable=True),
        sa.Column('fixed_amount', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),

        sa.ForeignKeyConstraint(
            ['deduction_id'],
            ['deduction.id'],
            name='fk_deduction_bracket_deduction_id'
        ),

        sa.PrimaryKeyConstraint('id')
    )

    # ===== payroll_deduction =====
    op.create_table(
        'payroll_deduction',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payroll_id', sa.Integer(), nullable=False),
        sa.Column('deduction_name', sa.String(length=100)),
        sa.Column('employee_share', sa.Float()),
        sa.Column('employer_share', sa.Float()),
        sa.Column('ec', sa.Float()),
        sa.Column('created_at', sa.DateTime()),

        sa.ForeignKeyConstraint(
            ['payroll_id'],
            ['payroll.id'],
            name='fk_payroll_deduction_payroll_id'
        ),

        sa.PrimaryKeyConstraint('id')
    )

    # ===== deduction table =====
    with op.batch_alter_table('deduction', schema=None) as batch_op:

        batch_op.add_column(sa.Column('description', sa.Text()))
        batch_op.add_column(sa.Column('calculation_type', sa.String(length=20), nullable=False))
        batch_op.add_column(sa.Column('rate', sa.Float()))
        batch_op.add_column(sa.Column('ceiling', sa.Float()))
        batch_op.add_column(sa.Column('floor', sa.Float()))
        batch_op.add_column(sa.Column('created_at', sa.DateTime()))

        batch_op.alter_column(
            'name',
            existing_type=sa.VARCHAR(length=100),
            nullable=False
        )

        # ⭐ FIXED UNIQUE CONSTRAINT NAME
        batch_op.create_unique_constraint(
            "uq_deduction_name",
            ["name"]
        )

        batch_op.drop_column('max_salary')
        batch_op.drop_column('min_salary')

    # ===== employee_deductions =====
    with op.batch_alter_table('employee_deductions', schema=None) as batch_op:

        batch_op.add_column(sa.Column('override_amount', sa.Float()))

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

        batch_op.drop_column('amount')

    # ===== tax =====
    with op.batch_alter_table('tax', schema=None) as batch_op:
        batch_op.drop_column('fixed')


# =========================
# DOWNGRADE
# =========================
def downgrade():

    with op.batch_alter_table('tax', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fixed', sa.FLOAT()))

    with op.batch_alter_table('employee_deductions', schema=None) as batch_op:

        batch_op.add_column(sa.Column('amount', sa.FLOAT()))

        batch_op.alter_column(
            'deduction_id',
            existing_type=sa.INTEGER(),
            nullable=True
        )

        batch_op.alter_column(
            'employee_id',
            existing_type=sa.INTEGER(),
            nullable=True
        )

        batch_op.drop_column('override_amount')

    with op.batch_alter_table('deduction', schema=None) as batch_op:

        batch_op.add_column(sa.Column('min_salary', sa.FLOAT()))
        batch_op.add_column(sa.Column('max_salary', sa.FLOAT()))

        batch_op.drop_constraint(
            "uq_deduction_name",
            type_="unique"
        )

        batch_op.alter_column(
            'name',
            existing_type=sa.VARCHAR(length=100),
            nullable=True
        )

        batch_op.drop_column('created_at')
        batch_op.drop_column('floor')
        batch_op.drop_column('ceiling')
        batch_op.drop_column('rate')
        batch_op.drop_column('calculation_type')
        batch_op.drop_column('description')

    op.drop_table('payroll_deduction')
    op.drop_table('deduction_bracket')