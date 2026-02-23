import uuid

from fastapi import APIRouter, HTTPException
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.models import FifaLeague, FifaLeaguePublic, FifaTeam, FifaTeamPublic

router = APIRouter(prefix="/leagues", tags=["leagues"])


@router.get("/", response_model=list[FifaLeaguePublic])
def read_leagues(
    session: SessionDep, _current_user: CurrentUser
) -> list[FifaLeaguePublic]:
    """
    Retrieve all leagues.
    """
    statement = select(FifaLeague).order_by(col(FifaLeague.name).asc())
    leagues = list(session.exec(statement).all())
    return leagues  # type: ignore[return-value]


@router.get("/{id}/teams", response_model=list[FifaTeamPublic])
def read_league_teams(
    id: uuid.UUID, session: SessionDep, _current_user: CurrentUser
) -> list[FifaTeamPublic]:
    """
    Retrieve all teams in a specific league.
    """
    league = session.get(FifaLeague, id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    statement = (
        select(FifaTeam)
        .where(FifaTeam.league_id == id)
        .order_by(col(FifaTeam.name).asc())
    )
    teams = list(session.exec(statement).all())
    return teams  # type: ignore[return-value]
