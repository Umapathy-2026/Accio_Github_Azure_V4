"""add entra_oid to users

Revision ID: 0003
Revises: 0002
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('entra_oid', sa.String(36), nullable=True))
    op.create_index('ix_users_entra_oid', 'users', ['entra_oid'], unique=True)


def downgrade():
    op.drop_index('ix_users_entra_oid', table_name='users')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('entra_oid')