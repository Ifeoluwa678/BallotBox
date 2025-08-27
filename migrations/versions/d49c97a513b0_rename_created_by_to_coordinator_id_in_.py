"""Rename created_by to coordinator_id in Election

Revision ID: d49c97a513b0
Revises: 45189b02bf28
Create Date: 2025-08-27 08:42:40.562628

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd49c97a513b0'
down_revision = '45189b02bf28'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('election', schema=None) as batch_op:
        batch_op.drop_column('created_by')

def downgrade():
    with op.batch_alter_table('election', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=False))
        batch_op.create_foreign_key(None, 'user', ['created_by'], ['id'])

