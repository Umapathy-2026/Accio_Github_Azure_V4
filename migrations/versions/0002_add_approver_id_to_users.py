"""add_approver_id_to_users — comprehensive legacy-to-new migration

This migration handles the case where the database was created by the old
schema (with manager_id, scope string columns) and 0001 was only stamped
but never applied.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03 10:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def table_has_column(table, column):
    """Check if a column exists in the table (works across SQLite and MSSQL)."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return any(c['name'] == column for c in inspector.get_columns(table))


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_names = inspector.get_table_names()

    # =====================================================================
    # 1. Create new tables (idempotent — skip if already exist)
    # =====================================================================
    if 'scopes' not in table_names:
        op.create_table('scopes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=50), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name')
        )

    if 'user_scopes' not in table_names:
        op.create_table('user_scopes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('scope_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['scope_id'], ['scopes.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'scope_id', name='uq_user_scope')
        )

    if 'categories' not in table_names:
        op.create_table('categories',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('scope_id', sa.Integer(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['scope_id'], ['scopes.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', 'scope_id', name='uq_category_scope')
        )

    # =====================================================================
    # 2. Rename manager_id → approver_id on users (legacy schema)
    # =====================================================================
    if table_has_column('users', 'manager_id') and not table_has_column('users', 'approver_id'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.alter_column('manager_id', new_column_name='approver_id')

    # =====================================================================
    # 3. Drop scope column from users (legacy schema)
    # =====================================================================
    if table_has_column('users', 'scope'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_column('scope')

    # =====================================================================
    # 4. Convert issue_forms.scope string → scope_id FK
    # =====================================================================
    if table_has_column('issue_forms', 'scope') and not table_has_column('issue_forms', 'scope_id'):
        op.drop_column('issue_forms', 'scope')
        op.add_column('issue_forms', sa.Column('scope_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_issue_forms_scope_id', 'issue_forms', 'scopes', ['scope_id'], ['id'])
        op.add_column('issue_forms', sa.Column('category_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_issue_forms_category_id', 'issue_forms', 'categories', ['category_id'], ['id'])
        op.add_column('issue_forms', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'))
        op.add_column('issue_forms', sa.Column('created_at', sa.DateTime(), nullable=True))

    # =====================================================================
    # 5. Widen ticket.scope from String(10) → String(50) (idempotent: MSSQL
    #    allows ALTER COLUMN; SQLite batch mode handles it)
    # =====================================================================
    if table_has_column('tickets', 'scope'):
        # Check the current type — skip if already String(50)
        from sqlalchemy import inspect as sa_inspect
        col_info = [c for c in sa_inspect(conn).get_columns('tickets') if c['name'] == 'scope']
        if col_info and str(col_info[0].get('type', '')) == 'VARCHAR(10)':
            with op.batch_alter_table('tickets') as batch_op:
                batch_op.alter_column('scope', type_=sa.String(50), nullable=False, server_default='')


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_names = inspector.get_table_names()

    # Reverse issue_forms changes
    if table_has_column('issue_forms', 'scope_id'):
        op.drop_constraint('fk_issue_forms_scope_id', 'issue_forms', type_='foreignkey')
        op.drop_column('issue_forms', 'scope_id')
        op.add_column('issue_forms', sa.Column('scope', sa.String(length=10), nullable=False, server_default=''))
    if table_has_column('issue_forms', 'category_id'):
        op.drop_constraint('fk_issue_forms_category_id', 'issue_forms', type_='foreignkey')
        op.drop_column('issue_forms', 'category_id')
    if table_has_column('issue_forms', 'is_deleted'):
        op.drop_column('issue_forms', 'is_deleted')
    if table_has_column('issue_forms', 'created_at'):
        op.drop_column('issue_forms', 'created_at')

    # Drop new tables
    if 'user_scopes' in table_names:
        op.drop_table('user_scopes')
    if 'categories' in table_names:
        op.drop_table('categories')
    if 'scopes' in table_names:
        op.drop_table('scopes')

    # Reverse ticket scope
    if table_has_column('tickets', 'scope'):
        with op.batch_alter_table('tickets') as batch_op:
            batch_op.alter_column('scope', type_=sa.String(10), nullable=False, server_default='')

    # Reverse user columns
    if table_has_column('users', 'approver_id') and not table_has_column('users', 'manager_id'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.alter_column('approver_id', new_column_name='manager_id')
    if not table_has_column('users', 'scope'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.add_column(sa.Column('scope', sa.String(length=10), nullable=False, server_default=''))