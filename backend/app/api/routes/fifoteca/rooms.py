"""Room management endpoints for Fifoteca."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlmodel import and_, col, select

from app.api.deps import CurrentUser, SessionDep
from app.crud import get_player_by_user_id
from app.models import (
    FifotecaPlayer,
    FifotecaPlayerState,
    FifotecaRoom,
    FifotecaRoomPublic,
    FifotecaRoomWithStatesPublic,
    PlayerSpinPhase,
    RoomStatus,
)

router = APIRouter(prefix="/rooms", tags=["rooms"])


def check_room_expiry(room: FifotecaRoom, session: SessionDep) -> None:
    """Check if room is expired and handle accordingly.

    If room is expired:
    - Mark room status as COMPLETED if not already
    - Raise HTTPException with 410 Gone

    Args:
        room: The room to check.
        session: Database session.

    Raises:
        HTTPException: 410 Gone if room has expired.
    """
    now = datetime.now(timezone.utc)
    if room.expires_at < now:
        # Mark as completed if not already
        if room.status != RoomStatus.COMPLETED:
            room.status = RoomStatus.COMPLETED
            session.add(room)
            session.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Room has expired",
        )


# Charset for room codes (removed ambiguous characters: I, O, 0, 1)
ROOM_CODE_CHARSET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH = 6


def generate_room_code() -> str:
    """Generate a random 6-character room code."""
    return "".join(secrets.choice(ROOM_CODE_CHARSET) for _ in range(ROOM_CODE_LENGTH))


@router.post("", response_model=FifotecaRoomPublic)
def create_room(
    session: SessionDep,
    current_user: CurrentUser,
    ruleset: str = "homebrew",
) -> FifotecaRoom:
    """
    Create a new game room.

    Generates a unique 6-character room code and initializes the room
    in WAITING status. Room expires after 60 minutes.
    """
    # Ensure player profile exists
    player = get_player_by_user_id(session=session, user_id=current_user.id)
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player profile not found. Create a profile first.",
        )

    # Generate unique code
    while True:
        code = generate_room_code()
        # Check if code exists among active (non-expired) rooms
        now = datetime.now(timezone.utc)
        statement = select(FifotecaRoom).where(
            and_(FifotecaRoom.code == code, col(FifotecaRoom.expires_at) > now)
        )
        existing_room = session.exec(statement).first()

        if not existing_room:
            break  # Found unique code

    # Create room
    room = FifotecaRoom(
        code=code,
        ruleset=ruleset,
        status=RoomStatus.WAITING,
        player1_id=player.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
    )
    session.add(room)
    session.commit()
    session.refresh(room)

    return room


@router.post("/join/{code}", response_model=FifotecaRoomPublic)
def join_room(
    code: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> FifotecaRoom:
    """
    Join an existing game room.

    Validates that the room exists, is in WAITING status, is not full,
    and the player is not trying to join their own room.
    On successful join, initializes player states for both players.
    """
    # Ensure player profile exists
    player = get_player_by_user_id(session=session, user_id=current_user.id)
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player profile not found. Create a profile first.",
        )

    # Get room
    statement = select(FifotecaRoom).where(FifotecaRoom.code == code)
    room = session.exec(statement).first()

    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )

    # Check if room has expired (returns 410 if expired)
    check_room_expiry(room, session)

    # Check for self-join (player1 trying to join their own room)
    if room.player1_id == player.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot join your own room",
        )

    # Check room status
    if room.status != RoomStatus.WAITING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Room is not accepting joins. Status: {room.status}",
        )

    # Check if room is full
    if room.player2_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room is already full",
        )

    # Update room
    room.player2_id = player.id
    room.status = RoomStatus.SPINNING_LEAGUES
    room.current_turn_player_id = room.player1_id
    room.first_player_id = room.player1_id
    session.add(room)
    session.commit()
    session.refresh(room)

    # Initialize player states for both players, transferring any protection
    # from previous games into superspin for this round.
    player1 = session.get(FifotecaPlayer, room.player1_id)
    player1_state = FifotecaPlayerState(
        room_id=room.id,
        player_id=room.player1_id,
        round_number=1,
        phase=PlayerSpinPhase.LEAGUE_SPINNING,
        league_spins_remaining=3,
        team_spins_remaining=3,
        has_superspin=player1.has_protection if player1 else False,
    )
    session.add(player1_state)

    player2_state = FifotecaPlayerState(
        room_id=room.id,
        player_id=player.id,
        round_number=1,
        phase=PlayerSpinPhase.LEAGUE_SPINNING,
        league_spins_remaining=3,
        team_spins_remaining=3,
        has_superspin=player.has_protection,
    )
    session.add(player2_state)

    # Clear has_protection after transferring to round state
    if player1 and player1.has_protection:
        player1.has_protection = False
        session.add(player1)
    if player.has_protection:
        player.has_protection = False
        session.add(player)

    session.commit()
    session.refresh(room)

    return room


@router.get("/{code}", response_model=FifotecaRoomWithStatesPublic)
def get_room(
    code: str,
    session: SessionDep,
) -> dict:
    """
    Get room state including player states.

    Used for reconnection and state synchronization.
    Returns 404 if room doesn't exist, 410 if room has expired.
    """
    # Get room
    statement = select(FifotecaRoom).where(FifotecaRoom.code == code)
    room = session.exec(statement).first()

    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )

    # Check if room has expired (returns 410 if expired)
    check_room_expiry(room, session)

    # Get player states if they exist
    statement = select(FifotecaPlayerState).where(
        and_(
            FifotecaPlayerState.room_id == room.id,
            FifotecaPlayerState.round_number == room.round_number,
        )
    )
    player_states = session.exec(statement).all()

    # Build response
    room_dict = {
        "id": room.id,
        "code": room.code,
        "ruleset": room.ruleset,
        "status": room.status,
        "player1_id": room.player1_id,
        "player2_id": room.player2_id,
        "current_turn_player_id": room.current_turn_player_id,
        "first_player_id": room.first_player_id,
        "round_number": room.round_number,
        "mutual_superspin_active": room.mutual_superspin_active,
        "expires_at": room.expires_at,
        "created_at": room.created_at,
        "player_states": player_states,
    }

    return room_dict
