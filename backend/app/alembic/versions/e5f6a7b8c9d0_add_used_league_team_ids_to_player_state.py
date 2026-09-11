"""Add used_league_ids and used_team_ids to FifotecaPlayerState

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('fifotecaplayerstate', sa.Column('used_league_ids', sa.JSON(), nullable=True, server_default='[]'))
    op.add_column('fifotecaplayerstate', sa.Column('used_team_ids', sa.JSON(), nullable=True, server_default='[]'))


def downgrade() -> None:
    op.drop_column('fifotecaplayerstate', 'used_team_ids')
    op.drop_column('fifotecaplayerstate', 'used_league_ids')
