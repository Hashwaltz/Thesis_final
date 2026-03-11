"""Add allowance_total to payroll

Revision ID: a2b0d1678a8e
Revises: b0141988e844
Create Date: 2026-03-10 22:01:16.661222

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2b0d1678a8e'
down_revision = 'b0141988e844'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('payroll', sa.Column('allowance_total', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('payroll', 'allowance_total')


