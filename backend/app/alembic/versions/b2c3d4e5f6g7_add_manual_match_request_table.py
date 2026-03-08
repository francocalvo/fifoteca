"""Add FifotecaManualMatchRequest table

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-08 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'fifotecamanualmatchrequest',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('requester_id', sa.Uuid(), nullable=False),
        sa.Column('responder_id', sa.Uuid(), nullable=False),
        sa.Column('request_type', sa.String(), nullable=False, server_default='create'),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('requester_team_id', sa.Uuid(), nullable=True),
        sa.Column('responder_team_id', sa.Uuid(), nullable=True),
        sa.Column('requester_score', sa.Integer(), nullable=True),
        sa.Column('responder_score', sa.Integer(), nullable=True),
        sa.Column('rating_difference', sa.Integer(), nullable=True),
        sa.Column('original_match_id', sa.Uuid(), nullable=True),
        sa.Column('new_requester_score', sa.Integer(), nullable=True),
        sa.Column('new_responder_score', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['requester_id'], ['fifotecaplayer.id'], ),
        sa.ForeignKeyConstraint(['responder_id'], ['fifotecaplayer.id'], ),
        sa.ForeignKeyConstraint(['requester_team_id'], ['fifateam.id'], ),
        sa.ForeignKeyConstraint(['responder_team_id'], ['fifateam.id'], ),
        sa.ForeignKeyConstraint(['original_match_id'], ['fifotecamatch.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('fifotecamanualmatchrequest')
