"""Fifoteca manual match request endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session, or_, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    FifaTeam,
    FifotecaManualMatchRequest,
    FifotecaMatch,
    FifotecaMatchPublic,
    FifotecaPlayer,
    ManualMatchCreateRequest,
    ManualMatchDeleteRequest,
    ManualMatchEditRequest,
    ManualMatchRequestPublic,
    ManualMatchRequestsPublic,
    ManualMatchRequestStatus,
    ManualMatchRequestType,
    Message,
)
from app.ws.global_manager import global_manager

router = APIRouter(prefix="/manual-matches", tags=["manual-matches"])

# Request expiry time in hours
REQUEST_EXPIRY_HOURS = 24


def get_player_by_user_id(session: Session, user_id: uuid.UUID) -> FifotecaPlayer:
    """Get player profile by user ID."""
    statement = select(FifotecaPlayer).where(FifotecaPlayer.user_id == user_id)
    player = session.exec(statement).first()

    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found"
        )

    return player


def build_request_public(
    request: FifotecaManualMatchRequest,
    players_map: dict[uuid.UUID, FifotecaPlayer],
    teams_map: dict[uuid.UUID, FifaTeam],
    matches_map: dict[uuid.UUID, FifotecaMatch] | None = None,
    current_player_id: uuid.UUID | None = None,
) -> ManualMatchRequestPublic:
    """Build public representation of a manual match request."""
    requester = players_map.get(request.requester_id)
    responder = players_map.get(request.responder_id)

    result = ManualMatchRequestPublic(
        id=request.id,
        request_type=request.request_type,
        status=request.status,
        requester_id=request.requester_id,
        requester_display_name=requester.display_name if requester else "Unknown",
        responder_id=request.responder_id,
        responder_display_name=responder.display_name if responder else "Unknown",
        created_at=request.created_at,
        expires_at=request.expires_at,
    )

    if request.request_type == ManualMatchRequestType.CREATE:
        if request.requester_team_id:
            requester_team = teams_map.get(request.requester_team_id)
            if requester_team:
                result.requester_team_name = requester_team.name
                result.requester_team_rating = requester_team.overall_rating
        if request.responder_team_id:
            responder_team = teams_map.get(request.responder_team_id)
            if responder_team:
                result.responder_team_name = responder_team.name
                result.responder_team_rating = responder_team.overall_rating
        result.requester_score = request.requester_score
        result.responder_score = request.responder_score
        result.rating_difference = request.rating_difference

    elif request.request_type in (
        ManualMatchRequestType.EDIT,
        ManualMatchRequestType.DELETE,
    ):
        result.original_match_id = request.original_match_id
        if request.original_match_id and matches_map:
            original_match = matches_map.get(request.original_match_id)
            if original_match and current_player_id:
                # Determine perspective
                is_requester_p1 = original_match.player1_id == request.requester_id
                if is_requester_p1:
                    result.current_requester_score = original_match.player1_score
                    result.current_responder_score = original_match.player2_score
                else:
                    result.current_requester_score = original_match.player2_score
                    result.current_responder_score = original_match.player1_score

        if request.request_type == ManualMatchRequestType.EDIT:
            result.new_requester_score = request.new_requester_score
            result.new_responder_score = request.new_responder_score

    return result


@router.post("/create", response_model=ManualMatchRequestPublic)
async def create_manual_match_request(
    data: ManualMatchCreateRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> ManualMatchRequestPublic:
    """Create a manual match request.

    Creates a request that must be accepted by the opponent.
    """
    player = get_player_by_user_id(session, current_user.id)

    # Get opponent player
    opponent = session.get(FifotecaPlayer, data.opponent_id)
    if not opponent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Opponent not found"
        )

    # Validate teams exist
    my_team = session.get(FifaTeam, data.my_team_id)
    opponent_team = session.get(FifaTeam, data.opponent_team_id)

    if not my_team or not opponent_team:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid team(s)"
        )

    # Calculate rating difference
    rating_difference = abs(my_team.overall_rating - opponent_team.overall_rating)

    # Create request
    now = datetime.now(timezone.utc)
    request = FifotecaManualMatchRequest(
        requester_id=player.id,
        responder_id=opponent.id,
        request_type=ManualMatchRequestType.CREATE,
        status=ManualMatchRequestStatus.PENDING,
        requester_team_id=data.my_team_id,
        responder_team_id=data.opponent_team_id,
        requester_score=data.my_score,
        responder_score=data.opponent_score,
        rating_difference=rating_difference,
        created_at=now,
        expires_at=now + timedelta(hours=REQUEST_EXPIRY_HOURS),
    )

    session.add(request)
    session.commit()
    session.refresh(request)

    # Build response
    players_map = {player.id: player, opponent.id: opponent}
    teams_map = {my_team.id: my_team, opponent_team.id: opponent_team}
    result = build_request_public(request, players_map, teams_map)

    # Notify opponent via WebSocket
    await global_manager.send_to_user(
        str(opponent.user_id),
        {
            "type": "manual_match_request_received",
            "payload": {
                "request_id": str(request.id),
                "request_type": request.request_type,
                "requester_display_name": player.display_name,
                "requester_team_name": my_team.name,
                "responder_team_name": opponent_team.name,
                "requester_score": data.my_score,
                "responder_score": data.opponent_score,
                "rating_difference": rating_difference,
                "expires_at": request.expires_at.isoformat(),
            },
        },
    )

    return result


@router.post("/edit", response_model=ManualMatchRequestPublic)
async def create_edit_request(
    data: ManualMatchEditRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> ManualMatchRequestPublic:
    """Create a request to edit an existing match's scores."""
    player = get_player_by_user_id(session, current_user.id)

    # Get the match
    match = session.get(FifotecaMatch, data.match_id)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
        )

    # Validate player is a participant
    if player.id not in (match.player1_id, match.player2_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this match",
        )

    # Determine opponent
    is_player1 = player.id == match.player1_id
    opponent_id = match.player2_id if is_player1 else match.player1_id
    opponent = session.get(FifotecaPlayer, opponent_id)

    if not opponent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Opponent not found"
        )

    # Check no pending edit/delete request for this match
    existing = session.exec(
        select(FifotecaManualMatchRequest).where(
            FifotecaManualMatchRequest.original_match_id == data.match_id,
            FifotecaManualMatchRequest.status == ManualMatchRequestStatus.PENDING,
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A pending request already exists for this match",
        )

    # Create request
    now = datetime.now(timezone.utc)
    request = FifotecaManualMatchRequest(
        requester_id=player.id,
        responder_id=opponent_id,
        request_type=ManualMatchRequestType.EDIT,
        status=ManualMatchRequestStatus.PENDING,
        original_match_id=data.match_id,
        new_requester_score=data.new_my_score,
        new_responder_score=data.new_opponent_score,
        created_at=now,
        expires_at=now + timedelta(hours=REQUEST_EXPIRY_HOURS),
    )

    session.add(request)
    session.commit()
    session.refresh(request)

    # Get current scores for notification
    current_my_score = match.player1_score if is_player1 else match.player2_score
    current_opponent_score = match.player2_score if is_player1 else match.player1_score

    # Build response
    players_map = {player.id: player, opponent_id: opponent}
    matches_map = {match.id: match}
    result = build_request_public(
        request, players_map, {}, matches_map, player.id
    )

    # Notify opponent
    await global_manager.send_to_user(
        str(opponent.user_id),
        {
            "type": "manual_match_request_received",
            "payload": {
                "request_id": str(request.id),
                "request_type": request.request_type,
                "requester_display_name": player.display_name,
                "match_id": str(data.match_id),
                "current_requester_score": current_my_score,
                "current_responder_score": current_opponent_score,
                "new_requester_score": data.new_my_score,
                "new_responder_score": data.new_opponent_score,
                "expires_at": request.expires_at.isoformat(),
            },
        },
    )

    return result


@router.post("/delete", response_model=ManualMatchRequestPublic)
async def create_delete_request(
    data: ManualMatchDeleteRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> ManualMatchRequestPublic:
    """Create a request to delete an existing match."""
    player = get_player_by_user_id(session, current_user.id)

    # Get the match
    match = session.get(FifotecaMatch, data.match_id)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
        )

    # Validate player is a participant
    if player.id not in (match.player1_id, match.player2_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this match",
        )

    # Determine opponent
    is_player1 = player.id == match.player1_id
    opponent_id = match.player2_id if is_player1 else match.player1_id
    opponent = session.get(FifotecaPlayer, opponent_id)

    if not opponent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Opponent not found"
        )

    # Check no pending edit/delete request for this match
    existing = session.exec(
        select(FifotecaManualMatchRequest).where(
            FifotecaManualMatchRequest.original_match_id == data.match_id,
            FifotecaManualMatchRequest.status == ManualMatchRequestStatus.PENDING,
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A pending request already exists for this match",
        )

    # Get team names for notification
    my_team = session.get(FifaTeam, match.player1_team_id if is_player1 else match.player2_team_id)
    opponent_team = session.get(FifaTeam, match.player2_team_id if is_player1 else match.player1_team_id)

    # Create request
    now = datetime.now(timezone.utc)
    request = FifotecaManualMatchRequest(
        requester_id=player.id,
        responder_id=opponent_id,
        request_type=ManualMatchRequestType.DELETE,
        status=ManualMatchRequestStatus.PENDING,
        original_match_id=data.match_id,
        created_at=now,
        expires_at=now + timedelta(hours=REQUEST_EXPIRY_HOURS),
    )

    session.add(request)
    session.commit()
    session.refresh(request)

    # Build response
    players_map = {player.id: player, opponent_id: opponent}
    matches_map = {match.id: match}
    result = build_request_public(
        request, players_map, {}, matches_map, player.id
    )

    # Notify opponent
    await global_manager.send_to_user(
        str(opponent.user_id),
        {
            "type": "manual_match_request_received",
            "payload": {
                "request_id": str(request.id),
                "request_type": request.request_type,
                "requester_display_name": player.display_name,
                "match_id": str(data.match_id),
                "requester_team_name": my_team.name if my_team else None,
                "responder_team_name": opponent_team.name if opponent_team else None,
                "expires_at": request.expires_at.isoformat(),
            },
        },
    )

    return result


@router.get("", response_model=ManualMatchRequestsPublic)
def list_manual_match_requests(
    current_user: CurrentUser,
    session: SessionDep,
) -> ManualMatchRequestsPublic:
    """List pending manual match requests for the current player."""
    player = get_player_by_user_id(session, current_user.id)
    now = datetime.now(timezone.utc)

    # Get pending requests where player is requester or responder
    statement = select(FifotecaManualMatchRequest).where(
        FifotecaManualMatchRequest.status == ManualMatchRequestStatus.PENDING,
        FifotecaManualMatchRequest.expires_at > now,
        or_(
            FifotecaManualMatchRequest.requester_id == player.id,
            FifotecaManualMatchRequest.responder_id == player.id,
        ),
    )
    requests = session.exec(statement).all()

    if not requests:
        return ManualMatchRequestsPublic(incoming=[], outgoing=[])

    # Collect IDs for bulk lookup
    player_ids: set[uuid.UUID] = set()
    team_ids: set[uuid.UUID] = set()
    match_ids: set[uuid.UUID] = set()

    for req in requests:
        player_ids.add(req.requester_id)
        player_ids.add(req.responder_id)
        if req.requester_team_id:
            team_ids.add(req.requester_team_id)
        if req.responder_team_id:
            team_ids.add(req.responder_team_id)
        if req.original_match_id:
            match_ids.add(req.original_match_id)

    # Bulk fetch
    players_map: dict[uuid.UUID, FifotecaPlayer] = {}
    if player_ids:
        players = session.exec(
            select(FifotecaPlayer).where(FifotecaPlayer.id.in_(player_ids))  # type: ignore
        ).all()
        players_map = {p.id: p for p in players}

    teams_map: dict[uuid.UUID, FifaTeam] = {}
    if team_ids:
        teams = session.exec(
            select(FifaTeam).where(FifaTeam.id.in_(team_ids))  # type: ignore
        ).all()
        teams_map = {t.id: t for t in teams}

    matches_map: dict[uuid.UUID, FifotecaMatch] = {}
    if match_ids:
        matches = session.exec(
            select(FifotecaMatch).where(FifotecaMatch.id.in_(match_ids))  # type: ignore
        ).all()
        matches_map = {m.id: m for m in matches}

    # Build response
    incoming: list[ManualMatchRequestPublic] = []
    outgoing: list[ManualMatchRequestPublic] = []

    for req in requests:
        public = build_request_public(
            req, players_map, teams_map, matches_map, player.id
        )
        if req.responder_id == player.id:
            incoming.append(public)
        else:
            outgoing.append(public)

    return ManualMatchRequestsPublic(incoming=incoming, outgoing=outgoing)


@router.post("/{id}/accept", response_model=Message)
async def accept_manual_match_request(
    id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> Message:
    """Accept a manual match request."""
    player = get_player_by_user_id(session, current_user.id)

    # Get request
    request = session.get(FifotecaManualMatchRequest, id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )

    # Validate responder
    if request.responder_id != player.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the responder for this request",
        )

    # Check not expired
    now = datetime.now(timezone.utc)
    if now > request.expires_at:
        request.status = ManualMatchRequestStatus.EXPIRED
        session.add(request)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Request has expired"
        )

    # Check still pending
    if request.status != ManualMatchRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is not pending (status: {request.status})",
        )

    # Process based on request type
    requester = session.get(FifotecaPlayer, request.requester_id)
    message = ""

    if request.request_type == ManualMatchRequestType.CREATE:
        # Create the match
        match = FifotecaMatch(
            room_id=uuid.uuid4(),  # Dummy room ID for manual matches
            round_number=1,
            player1_id=request.requester_id,
            player2_id=request.responder_id,
            player1_team_id=request.requester_team_id,
            player2_team_id=request.responder_team_id,
            player1_score=request.requester_score,
            player2_score=request.responder_score,
            rating_difference=request.rating_difference or 0,
            submitted_by_id=request.requester_id,
            confirmed=True,
        )

        # Update player stats
        if request.requester_score is not None and request.responder_score is not None:
            if request.requester_score > request.responder_score:
                if requester:
                    requester.total_wins += 1
                    session.add(requester)
                player.total_losses += 1
            elif request.responder_score > request.requester_score:
                if requester:
                    requester.total_losses += 1
                    session.add(requester)
                player.total_wins += 1
            else:
                if requester:
                    requester.total_draws += 1
                    session.add(requester)
                player.total_draws += 1

        session.add(match)
        session.add(player)
        message = "Manual match created successfully"

    elif request.request_type == ManualMatchRequestType.EDIT:
        # Update the match scores
        match = session.get(FifotecaMatch, request.original_match_id)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original match not found",
            )

        # Determine perspective
        is_requester_p1 = match.player1_id == request.requester_id

        # Get old scores for stat adjustment
        old_p1_score = match.player1_score
        old_p2_score = match.player2_score

        # Set new scores
        if is_requester_p1:
            match.player1_score = request.new_requester_score
            match.player2_score = request.new_responder_score
        else:
            match.player1_score = request.new_responder_score
            match.player2_score = request.new_requester_score

        # Adjust player stats
        p1 = session.get(FifotecaPlayer, match.player1_id)
        p2 = session.get(FifotecaPlayer, match.player2_id)

        # Reverse old result
        if old_p1_score is not None and old_p2_score is not None:
            if old_p1_score > old_p2_score:
                if p1:
                    p1.total_wins -= 1
                if p2:
                    p2.total_losses -= 1
            elif old_p2_score > old_p1_score:
                if p1:
                    p1.total_losses -= 1
                if p2:
                    p2.total_wins -= 1
            else:
                if p1:
                    p1.total_draws -= 1
                if p2:
                    p2.total_draws -= 1

        # Apply new result
        new_p1_score = match.player1_score
        new_p2_score = match.player2_score
        if new_p1_score is not None and new_p2_score is not None:
            if new_p1_score > new_p2_score:
                if p1:
                    p1.total_wins += 1
                if p2:
                    p2.total_losses += 1
            elif new_p2_score > new_p1_score:
                if p1:
                    p1.total_losses += 1
                if p2:
                    p2.total_wins += 1
            else:
                if p1:
                    p1.total_draws += 1
                if p2:
                    p2.total_draws += 1

        if p1:
            session.add(p1)
        if p2:
            session.add(p2)
        session.add(match)
        message = "Match scores updated successfully"

    elif request.request_type == ManualMatchRequestType.DELETE:
        # Delete the match and reverse stats
        match = session.get(FifotecaMatch, request.original_match_id)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original match not found",
            )

        # Reverse stats
        p1 = session.get(FifotecaPlayer, match.player1_id)
        p2 = session.get(FifotecaPlayer, match.player2_id)

        if match.player1_score is not None and match.player2_score is not None:
            if match.player1_score > match.player2_score:
                if p1:
                    p1.total_wins -= 1
                if p2:
                    p2.total_losses -= 1
            elif match.player2_score > match.player1_score:
                if p1:
                    p1.total_losses -= 1
                if p2:
                    p2.total_wins -= 1
            else:
                if p1:
                    p1.total_draws -= 1
                if p2:
                    p2.total_draws -= 1

        if p1:
            session.add(p1)
        if p2:
            session.add(p2)

        session.delete(match)
        message = "Match deleted successfully"

    # Mark request as accepted
    request.status = ManualMatchRequestStatus.ACCEPTED
    session.add(request)
    session.commit()

    # Notify requester
    if requester:
        await global_manager.send_to_user(
            str(requester.user_id),
            {
                "type": "manual_match_request_accepted",
                "payload": {
                    "request_id": str(request.id),
                    "request_type": request.request_type,
                    "responder_display_name": player.display_name,
                },
            },
        )

    return Message(message=message)


@router.post("/{id}/decline", response_model=Message)
async def decline_manual_match_request(
    id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> Message:
    """Decline a manual match request."""
    player = get_player_by_user_id(session, current_user.id)

    # Get request
    request = session.get(FifotecaManualMatchRequest, id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )

    # Validate responder
    if request.responder_id != player.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the responder for this request",
        )

    # Check still pending
    if request.status != ManualMatchRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is not pending (status: {request.status})",
        )

    # Mark as declined
    request.status = ManualMatchRequestStatus.DECLINED
    session.add(request)
    session.commit()

    # Notify requester
    requester = session.get(FifotecaPlayer, request.requester_id)
    if requester:
        await global_manager.send_to_user(
            str(requester.user_id),
            {
                "type": "manual_match_request_declined",
                "payload": {
                    "request_id": str(request.id),
                    "request_type": request.request_type,
                    "responder_display_name": player.display_name,
                },
            },
        )

    return Message(message="Request declined")


@router.delete("/{id}", response_model=Message)
async def cancel_manual_match_request(
    id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> Message:
    """Cancel a pending manual match request (requester only)."""
    player = get_player_by_user_id(session, current_user.id)

    # Get request
    request = session.get(FifotecaManualMatchRequest, id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )

    # Validate requester
    if request.requester_id != player.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the requester for this request",
        )

    # Check still pending
    if request.status != ManualMatchRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is not pending (status: {request.status})",
        )

    # Mark as cancelled
    request.status = ManualMatchRequestStatus.CANCELLED
    session.add(request)
    session.commit()

    return Message(message="Request cancelled")
