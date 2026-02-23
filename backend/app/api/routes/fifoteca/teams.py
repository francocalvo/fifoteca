import uuid

from fastapi import APIRouter, Query
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.models import FifaTeam, FifaTeamPublic

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/", response_model=list[FifaTeamPublic])
def read_teams(
    session: SessionDep,
    _current_user: CurrentUser,
    league_id: uuid.UUID | None = Query(
        default=None, description="Filter by league ID"
    ),
    min_rating: int | None = Query(
        default=None, ge=0, description="Minimum overall rating"
    ),
    max_rating: int | None = Query(
        default=None, ge=0, description="Maximum overall rating"
    ),
) -> list[FifaTeamPublic]:
    """
    Retrieve teams with optional filtering by league and rating range.
    """
    statement = select(FifaTeam)

    # Apply filters
    if league_id is not None:
        statement = statement.where(FifaTeam.league_id == league_id)
    if min_rating is not None:
        statement = statement.where(FifaTeam.overall_rating >= min_rating)
    if max_rating is not None:
        statement = statement.where(FifaTeam.overall_rating <= max_rating)

    statement = statement.order_by(col(FifaTeam.name).asc())
    teams = list(session.exec(statement).all())
    return teams  # type: ignore[return-value]
