"""Add played_at to FifotecaManualMatchRequest

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-17 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('fifotecamanualmatchrequest', sa.Column('played_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('fifotecamanualmatchrequest', 'played_at')
