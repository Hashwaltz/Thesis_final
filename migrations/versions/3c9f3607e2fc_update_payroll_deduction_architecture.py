"""update payroll deduction architecture

Revision ID: 3c9f3607e2fc
Revises: c168c3ad9e33
Create Date: 2026-02-28 09:08:57.057121
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '3c9f3607e2fc'
down_revision = 'c168c3ad9e33'
branch_labels = None
depends_on = None


def upgrade():

    # ================= deduction_bracket =================
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

    # ================= payroll_deduction =================
    op.create_table(
        'payroll_deduction',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payroll_id', sa.Integer(), nullable=False),
        sa.Column('deduction_name', sa.String(length=100), nullable=True),
        sa.Column('employee_share', sa.Float(), nullable=True),
        sa.Column('employer_share', sa.Float(), nullable=True),
        sa.Column('ec', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),

        sa.ForeignKeyConstraint(
            ['payroll_id'],
            ['payroll.id'],
            name='fk_payroll_deduction_payroll_id'
        ),

        sa.PrimaryKeyConstraint('id')
    )

    # ================= deduction table modification =================
    with op.batch_alter_table('deduction', schema=None) as batch_op:

        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('calculation_type', sa.String(length=20), nullable=False))
        batch_op.add_column(sa.Column('rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('ceiling', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('floor', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))

        batch_op.alter_column(
            'name',
            existing_type=sa.VARCHAR(length=100),
            nullable=False
        )

        # ✅ Correct unique constraint naming
        batch_op.create_unique_constraint(
            'uq_deduction_name',
            ['name']
        )

        # Drop old columns
        batch_op.drop_column('max_salary')
        batch_op.drop_column('min_salary')

    # ================= employee_deductions =================
    with op.batch_alter_table('employee_deductions', schema=None) as batch_op:

        batch_op.add_column(
            sa.Column('override_amount', sa.Float(), nullable=True)
        )

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

    # ================= tax =================
    with op.batch_alter_table('tax', schema=None) as batch_op:
        batch_op.drop_column('fixed')


def downgrade():

    # ================= tax rollback =================
    with op.batch_alter_table('tax', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('fixed', sa.FLOAT(), nullable=True)
        )

    # ================= employee_deductions rollback =================
    with op.batch_alter_table('employee_deductions', schema=None) as batch_op:

        batch_op.add_column(
            sa.Column('amount', sa.FLOAT(), nullable=True)
        )

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

    # ================= deduction rollback =================
    with op.batch_alter_table('deduction', schema=None) as batch_op:

        batch_op.add_column(sa.Column('min_salary', sa.FLOAT(), nullable=True))
        batch_op.add_column(sa.Column('max_salary', sa.FLOAT(), nullable=True))

        batch_op.drop_constraint(
            'uq_deduction_name',
            type_='unique'
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