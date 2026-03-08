"""Add superspin_request_proposer_id to FifotecaRoom

Revision ID: a1b2c3d4e5f6
Revises: 8eaddad2e24b
Create Date: 2026-03-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '8eaddad2e24b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('fifotecaroom', sa.Column('superspin_request_proposer_id', sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column('fifotecaroom', 'superspin_request_proposer_id')
