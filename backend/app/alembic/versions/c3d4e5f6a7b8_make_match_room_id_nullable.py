"""Make FifotecaMatch.room_id nullable for manual matches

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6g7
Create Date: 2026-03-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('fifotecamatch', 'room_id',
                     existing_type=sa.Uuid(),
                     nullable=True)


def downgrade() -> None:
    op.alter_column('fifotecamatch', 'room_id',
                     existing_type=sa.Uuid(),
                     nullable=False)
