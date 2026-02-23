"""Player profile endpoints for Fifoteca."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.crud import create_player, get_player_by_user_id
from app.models import FifotecaPlayer, FifotecaPlayerPublic

router = APIRouter(prefix="/players", tags=["players"])


@router.post("/me", response_model=FifotecaPlayerPublic)
def create_or_get_player_profile(
    session: SessionDep, current_user: CurrentUser
) -> FifotecaPlayer:
    """
    Create or get the current user's player profile.

    If a profile already exists for the current user, returns the existing profile.
    Otherwise, creates a new profile with default stats (0/0/0).

    Display name is derived from user.full_name or user.email.
    """
    # Check if player profile already exists
    existing_player = get_player_by_user_id(session=session, user_id=current_user.id)
    if existing_player:
        return existing_player

    # Create new profile
    display_name = current_user.full_name or current_user.email
    player = create_player(
        session=session, user_id=current_user.id, display_name=display_name
    )
    return player


@router.get("/me", response_model=FifotecaPlayerPublic)
def get_player_profile(
    session: SessionDep, current_user: CurrentUser
) -> FifotecaPlayer:
    """
    Get the current user's player profile with stats.

    Returns 404 if profile does not exist (use POST /me to create).
    """
    player = get_player_by_user_id(session=session, user_id=current_user.id)
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found"
        )
    return player
