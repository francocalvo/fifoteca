"""Fifoteca match endpoints for score submission and confirmation."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session, or_, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    FifaTeam,
    FifotecaMatch,
    FifotecaMatchDetail,
    FifotecaMatchHistoryPublic,
    FifotecaMatchPublic,
    FifotecaPlayer,
    FifotecaRoom,
    MatchesPublic,
    MatchScoreSubmit,
    RoomStatus,
)

router = APIRouter(prefix="/matches", tags=["matches"])


def get_player_by_user_id(session: Session, user_id: uuid.UUID) -> FifotecaPlayer:
    """Get player profile by user ID.

    Args:
        session: Database session.
        user_id: The user ID.

    Returns:
        The FifotecaPlayer.

    Raises:
        HTTPException: If player not found (404).
    """
    statement = select(FifotecaPlayer).where(FifotecaPlayer.user_id == user_id)
    player = session.exec(statement).first()

    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found"
        )

    return player


def get_match_by_id(session: Session, match_id: uuid.UUID) -> FifotecaMatch:
    """Get match by ID.

    Args:
        session: Database session.
        match_id: The match ID.

    Returns:
        The FifotecaMatch.

    Raises:
        HTTPException: If match not found (404).
    """
    match = session.get(FifotecaMatch, match_id)

    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
        )

    return match


def validate_match_participation(match: FifotecaMatch, player_id: uuid.UUID) -> None:
    """Validate that player is a participant in the match.

    Args:
        match: The match.
        player_id: The player ID.

    Raises:
        HTTPException: If player is not a participant (403).
    """
    if player_id != match.player1_id and player_id != match.player2_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this match",
        )


@router.post("/{id}/score", response_model=FifotecaMatchPublic)
async def submit_match_score(
    id: uuid.UUID,
    score_data: MatchScoreSubmit,
    current_user: CurrentUser,
    session: SessionDep,
) -> FifotecaMatchPublic:
    """Submit scores for a match.

    Only participants can submit scores. Scores can only be submitted once
    while the room is in MATCH_IN_PROGRESS status.

    Args:
        id: The match ID.
        score_data: The scores (player1_score, player2_score).
        current_user: The authenticated user.
        session: Database session.

    Returns:
        The updated match.

    Raises:
        HTTPException: If player not participant (403).
        HTTPException: If match already confirmed (400).
        HTTPException: If scores already submitted (400).
        HTTPException: If room not in MATCH_IN_PROGRESS (400).
    """
    # Get player and match
    player = get_player_by_user_id(session, current_user.id)
    match = get_match_by_id(session, id)

    # Validate participation
    validate_match_participation(match, player.id)

    # Check match not already confirmed
    if match.confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Match already confirmed",
        )

    # Check scores not already submitted
    if match.submitted_by_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scores already submitted",
        )

    # Check room status
    room = session.get(FifotecaRoom, match.room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )

    if room.status != RoomStatus.MATCH_IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room not in MATCH_IN_PROGRESS status",
        )

    # Submit scores
    match.player1_score = score_data.player1_score
    match.player2_score = score_data.player2_score
    match.submitted_by_id = player.id

    # Update room status
    room.status = RoomStatus.SCORE_SUBMITTED

    session.add(match)
    session.add(room)
    session.commit()
    session.refresh(match)

    # Broadcast score submission to room
    from app.ws import manager

    await manager.broadcast(
        room.code,
        {
            "type": "score_submitted",
            "payload": {
                "match_id": str(match.id),
                "submitted_by": str(player.id),
                "p1_score": match.player1_score,
                "p2_score": match.player2_score,
            },
        },
    )

    # Return as public schema
    return FifotecaMatchPublic.model_validate(match)


@router.post("/{id}/confirm", response_model=FifotecaMatchPublic)
async def confirm_match_result(
    id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> FifotecaMatchPublic:
    """Confirm match result and update player statistics.

    Only the non-submitting participant can confirm. Confirmation updates
    player win/loss/draw totals and sets room to COMPLETED.

    Args:
        id: The match ID.
        current_user: The authenticated user.
        session: Database session.

    Returns:
        The confirmed match.

    Raises:
        HTTPException: If player not participant (403).
        HTTPException: If scores not submitted (400).
        HTTPException: If match already confirmed (400).
        HTTPException: If submitting player tries to confirm (403).
    """
    # Get player and match
    player = get_player_by_user_id(session, current_user.id)
    match = get_match_by_id(session, id)

    # Validate participation
    validate_match_participation(match, player.id)

    # Check scores submitted
    if match.submitted_by_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scores not submitted yet",
        )

    # Check not already confirmed
    if match.confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Match already confirmed",
        )

    # Only non-submitting player can confirm
    if match.submitted_by_id == player.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot confirm your own score submission",
        )

    # Determine outcome
    winner_id = None
    if match.player1_score is not None and match.player2_score is not None:
        if match.player1_score > match.player2_score:
            # Player 1 wins
            winner_id = match.player1_id
            p1 = session.get(FifotecaPlayer, match.player1_id)
            p2 = session.get(FifotecaPlayer, match.player2_id)
            if p1:
                p1.total_wins += 1
                session.add(p1)
            if p2:
                p2.total_losses += 1
                session.add(p2)
        elif match.player2_score > match.player1_score:
            # Player 2 wins
            winner_id = match.player2_id
            p1 = session.get(FifotecaPlayer, match.player1_id)
            p2 = session.get(FifotecaPlayer, match.player2_id)
            if p1:
                p1.total_losses += 1
                session.add(p1)
            if p2:
                p2.total_wins += 1
                session.add(p2)
        else:
            # Draw
            p1 = session.get(FifotecaPlayer, match.player1_id)
            p2 = session.get(FifotecaPlayer, match.player2_id)
            if p1:
                p1.total_draws += 1
                session.add(p1)
            if p2:
                p2.total_draws += 1
                session.add(p2)

    # Mark match confirmed
    match.confirmed = True

    # Update room status
    room = session.get(FifotecaRoom, match.room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )

    room.status = RoomStatus.COMPLETED
    session.add(match)
    session.add(room)
    session.commit()
    session.refresh(match)

    # Build stats summary
    stats_summary = {}
    if match.player1_id:
        p1 = session.get(FifotecaPlayer, match.player1_id)
        if p1:
            stats_summary["player1_stats"] = {
                "wins": p1.total_wins,
                "losses": p1.total_losses,
                "draws": p1.total_draws,
            }
    if match.player2_id:
        p2 = session.get(FifotecaPlayer, match.player2_id)
        if p2:
            stats_summary["player2_stats"] = {
                "wins": p2.total_wins,
                "losses": p2.total_losses,
                "draws": p2.total_draws,
            }

    # Broadcast match result to room
    from app.ws import manager

    await manager.broadcast(
        room.code,
        {
            "type": "match_result",
            "payload": {
                "match_id": str(match.id),
                "winner_id": str(winner_id) if winner_id else None,
                "p1_score": match.player1_score,
                "p2_score": match.player2_score,
                "confirmed": True,
                "stats_updated": stats_summary,
            },
        },
    )

    # Return as public schema
    return FifotecaMatchPublic.model_validate(match)


@router.get("", response_model=MatchesPublic)
def list_matches(
    current_user: CurrentUser,
    session: SessionDep,
) -> MatchesPublic:
    """List all matches for the current player.

    Returns matches where the player is either player1 or player2,
    sorted by creation date (newest first). Each match includes
    enriched data from the current player's perspective.

    Args:
        current_user: The authenticated user.
        session: Database session.

    Returns:
        List of matches with opponent/team names and result from player's view.
    """
    # Get player
    player = get_player_by_user_id(session, current_user.id)

    # Get matches where player is participant
    statement = select(FifotecaMatch).where(
        or_(
            FifotecaMatch.player1_id == player.id,
            FifotecaMatch.player2_id == player.id,
        )
    )
    statement = statement.order_by(FifotecaMatch.created_at.desc())  # type: ignore[attr-defined]

    matches = session.exec(statement).all()

    if not matches:
        return MatchesPublic(data=[], count=0)

    # Collect all player IDs and team IDs for bulk lookup
    player_ids: set[uuid.UUID] = set()
    team_ids: set[uuid.UUID] = set()
    for m in matches:
        player_ids.add(m.player1_id)
        player_ids.add(m.player2_id)
        team_ids.add(m.player1_team_id)
        team_ids.add(m.player2_team_id)

    # Bulk fetch players and teams
    players_map: dict[uuid.UUID, FifotecaPlayer] = {}
    if player_ids:
        players = session.exec(
            select(FifotecaPlayer).where(FifotecaPlayer.id.in_(player_ids))  # type: ignore[attr-defined]
        ).all()
        players_map = {p.id: p for p in players}

    teams_map: dict[uuid.UUID, FifaTeam] = {}
    if team_ids:
        teams = session.exec(
            select(FifaTeam).where(FifaTeam.id.in_(team_ids))  # type: ignore[attr-defined]
        ).all()
        teams_map = {t.id: t for t in teams}

    # Build enriched history rows
    history_rows: list[FifotecaMatchHistoryPublic] = []
    for match in matches:
        # Determine perspective: is current player player1 or player2?
        is_player1 = match.player1_id == player.id

        if is_player1:
            opponent_id = match.player2_id
            my_team_id = match.player1_team_id
            opponent_team_id = match.player2_team_id
            my_score = match.player1_score
            opponent_score = match.player2_score
        else:
            opponent_id = match.player1_id
            my_team_id = match.player2_team_id
            opponent_team_id = match.player1_team_id
            my_score = match.player2_score
            opponent_score = match.player1_score

        # Get opponent display name
        opponent = players_map.get(opponent_id)
        opponent_name = opponent.display_name if opponent else "Unknown player"

        # Get team names
        my_team = teams_map.get(my_team_id)
        my_team_name = my_team.name if my_team else "Unknown team"

        opponent_team = teams_map.get(opponent_team_id)
        opponent_team_name = opponent_team.name if opponent_team else "Unknown team"

        # Determine result
        result = "draw"
        if my_score is not None and opponent_score is not None:
            if my_score > opponent_score:
                result = "win"
            elif my_score < opponent_score:
                result = "loss"

        history_rows.append(
            FifotecaMatchHistoryPublic(
                id=match.id,
                created_at=match.created_at,
                round_number=match.round_number,
                rating_difference=match.rating_difference,
                confirmed=match.confirmed,
                opponent_display_name=opponent_name,
                my_team_name=my_team_name,
                opponent_team_name=opponent_team_name,
                my_score=my_score,
                opponent_score=opponent_score,
                result=result,
            )
        )

    return MatchesPublic(data=history_rows, count=len(history_rows))


@router.get("/{id}", response_model=FifotecaMatchDetail)
def get_match(
    id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> FifotecaMatchDetail:
    """Get detailed match information.

    Only participants can view match details.

    Args:
        id: The match ID.
        current_user: The authenticated user.
        session: Database session.

    Returns:
        Detailed match information.

    Raises:
        HTTPException: If player not participant (403).
        HTTPException: If match not found (404).
    """
    from app.models import FifaTeam

    # Get player and match
    player = get_player_by_user_id(session, current_user.id)
    match = get_match_by_id(session, id)

    # Validate participation
    validate_match_participation(match, player.id)

    # Fetch teams to get league IDs
    p1_team = session.get(FifaTeam, match.player1_team_id)
    p2_team = session.get(FifaTeam, match.player2_team_id)

    if not p1_team or not p2_team:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Match team data not found",
        )

    # Build detail response with league IDs
    return FifotecaMatchDetail(
        id=match.id,
        room_id=match.room_id,
        round_number=match.round_number,
        player1_id=match.player1_id,
        player2_id=match.player2_id,
        player1_team_id=match.player1_team_id,
        player2_team_id=match.player2_team_id,
        player1_league_id=p1_team.league_id,
        player2_league_id=p2_team.league_id,
        player1_score=match.player1_score,
        player2_score=match.player2_score,
        rating_difference=match.rating_difference,
        protection_awarded_to_id=match.protection_awarded_to_id,
        submitted_by_id=match.submitted_by_id,
        confirmed=match.confirmed,
        created_at=match.created_at,
    )
