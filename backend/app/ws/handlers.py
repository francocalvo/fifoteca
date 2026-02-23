"""WebSocket message handlers for Fifoteca real-time game flow.

This module provides a dispatcher that routes WebSocket messages to appropriate
game service handlers and broadcasts results to connected clients.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from sqlmodel import select

from app.models import FifotecaRoom
from app.services.game_service import (
    GameActionError,
    GameService,
    InvalidActionError,
    NotYourTurnError,
    check_room_expiry,
)
from app.services.spin_service import SpecialSpinError
from app.ws import manager

# Room expiry duration in minutes
ROOM_EXPIRY_MINUTES = 60

# Per-room readiness tracking for play_again flow
# Keys: room_code (str), Values: set of player IDs (UUID) who requested play again
_play_again_readiness: dict[str, set[uuid.UUID]] = {}


async def handle_message(
    session,
    room_code: str,
    player_id: str,
    data: dict,
    websocket: WebSocket,
) -> None:
    """Dispatch WebSocket message to appropriate handler.

    Args:
        session: Database session.
        room_code: The room code for game.
        player_id: The player ID of the message sender.
        data: The incoming WebSocket message (must contain 'type' and optional 'payload').
        websocket: The WebSocket connection of the sender (for direct responses).
    """
    # Refresh room expiry on any activity
    statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
    room = session.exec(statement).first()

    if not room:
        await _send_error(websocket, "ROOM_NOT_FOUND", "Room not found")
        return

    # Check if room has expired - if so, close with 4002 and mark completed
    try:
        check_room_expiry(room, session)
    except HTTPException:
        # Room is expired - close the connection with code 4002
        await websocket.close(code=4002)
        return

    # Refresh expiry on activity
    room.expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ROOM_EXPIRY_MINUTES
    )
    session.add(room)
    session.commit()

    # Parse message safely
    message_type = data.get("type")

    # Route to handler based on message type
    if message_type == "ping":
        await _handle_ping(websocket)
    elif message_type == "play_again":
        await _handle_play_again(session, room_code, player_id, websocket)
    elif message_type == "leave_room":
        await _handle_leave_room(session, room_code, player_id, websocket)
    elif message_type in (
        "spin_league",
        "lock_league",
        "spin_team",
        "lock_team",
        "use_superspin",
        "use_parity_spin",
        "ready_to_play",
    ):
        await _handle_game_action(
            session, room_code, player_id, message_type, websocket
        )
    elif message_type == "propose_mutual_superspin":
        await _handle_propose_mutual_superspin(session, room_code, player_id, websocket)
    elif message_type == "accept_mutual_superspin":
        await _handle_accept_mutual_superspin(session, room_code, player_id, websocket)
    elif message_type == "decline_mutual_superspin":
        await _handle_decline_mutual_superspin(session, room_code, player_id, websocket)
    else:
        # Unknown message type
        await _send_error(
            websocket, "INVALID_ACTION", f"Unknown message type: {message_type}"
        )


async def _handle_ping(websocket: WebSocket) -> None:
    """Handle ping message by sending pong.

    Args:
        websocket: The WebSocket connection to send pong to.
    """
    await websocket.send_json({"type": "pong", "payload": {}})


async def _handle_play_again(
    session,
    room_code: str,
    player_id: str,
    websocket: WebSocket,
) -> None:
    """Handle play_again message for post-match new round flow.

    When both room participants request play_again:
    - Reset room for new round
    - Broadcast state_sync to all room members

    Args:
        session: Database session.
        room_code: The room code.
        player_id: The player ID requesting play again.
        websocket: The WebSocket connection of the requesting player.
    """
    try:
        # Load room
        statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
        room = session.exec(statement).first()

        if not room:
            await _send_error(websocket, "ROOM_NOT_FOUND", "Room not found")
            return

        # Parse player_id as UUID
        player_uuid = uuid.UUID(player_id)

        # Validate player is room participant
        if room.player1_id != player_uuid and room.player2_id != player_uuid:
            await _send_error(
                websocket, "NOT_A_PARTICIPANT", "You are not a room participant"
            )
            return

        # Validate room is in a post-match state (COMPLETED)
        # play_again should only be allowed after a match has concluded
        if room.status != "COMPLETED":
            await _send_error(
                websocket,
                "INVALID_ACTION",
                f"Cannot play again: room is in {room.status} status, not COMPLETED",
            )
            return

        # Record readiness for this room
        if room_code not in _play_again_readiness:
            _play_again_readiness[room_code] = set()
        _play_again_readiness[room_code].add(player_uuid)

        # Check if both players are ready
        both_ready = (
            room.player1_id in _play_again_readiness[room_code]
            and room.player2_id in _play_again_readiness[room_code]
        )

        if both_ready:
            # Reset room for new round
            GameService.reset_room_for_new_round(session, room)

            # Clear readiness tracking for this room
            if room_code in _play_again_readiness:
                del _play_again_readiness[room_code]

            # Get game snapshot
            snapshot = GameService.get_game_snapshot(
                session=session, room_code=room_code
            )

            # Broadcast state_sync to all room members
            await manager.broadcast(
                room_code,
                {"type": "state_sync", "payload": snapshot},
            )
        else:
            # Not both ready yet - send acknowledgment to requester
            await websocket.send_json(
                {
                    "type": "play_again_ack",
                    "payload": {"player_id": player_id, "waiting_for_opponent": True},
                }
            )

    except HTTPException as e:
        await _send_error(websocket, "ROOM_ERROR", str(e.detail))
    except Exception as e:
        await _send_error(websocket, "INTERNAL_ERROR", str(e))


async def _handle_leave_room(
    session,
    room_code: str,
    player_id: str,
    websocket: WebSocket,
) -> None:
    """Handle leave_room message for intentional room departure.

    - Disconnect sender from room
    - Broadcast player_left to remaining room members
    - Mark room as COMPLETED if no players remain
    - Raise WebSocketDisconnect to signal message loop to exit

    Args:
        session: Database session.
        room_code: The room code.
        player_id: The player ID leaving the room.
        websocket: The WebSocket connection to close.
    """
    try:
        # Load room
        statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
        room = session.exec(statement).first()

        if not room:
            # Room doesn't exist, just return
            return

        # Mark websocket state to prevent duplicate disconnect event
        # This is checked in ws.py's finally block
        websocket.state.left_room = True  # type: ignore[attr-defined]

        # Remove sender connection via manager
        manager.disconnect(room_code, websocket)

        # Broadcast player_left to remaining room members
        await manager.broadcast(
            room_code,
            {
                "type": "player_left",
                "payload": {"player_id": player_id},
            },
        )

        # Check if any players remain connected
        remaining_players = manager.get_connected_players(room_code)

        if not remaining_players:
            # No players remain - mark room as COMPLETED
            room.status = "COMPLETED"
            session.add(room)
            session.commit()

        # Raise WebSocketDisconnect to signal message loop to exit
        # This triggers the normal disconnect handling in ws.py
        raise WebSocketDisconnect(code=1000, reason="Left room")

    except WebSocketDisconnect:
        # Re-raise to propagate to the message loop in ws.py
        raise
    except Exception:  # noqa: BLE001
        # Log error but don't prevent disconnect
        # If websocket is already closed, this is fine
        pass


async def _handle_propose_mutual_superspin(
    session,
    room_code: str,
    player_id: str,
    websocket: WebSocket,
) -> None:
    """Handle propose_mutual_superspin message.

    Validates room is in SPINNING_LEAGUES or SPINNING_TEAMS phase,
    sets mutual_superspin_proposer_id, and broadcasts to room.

    Args:
        session: Database session.
        room_code: The room code.
        player_id: The player ID proposing mutual superspin.
        websocket: The WebSocket connection of the proposer.
    """
    try:
        # Load room
        statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
        room = session.exec(statement).first()

        if not room:
            await _send_error(websocket, "ROOM_NOT_FOUND", "Room not found")
            return

        # Parse player_id as UUID
        player_uuid = uuid.UUID(player_id)

        # Validate player is room participant
        if room.player1_id != player_uuid and room.player2_id != player_uuid:
            await _send_error(
                websocket, "NOT_A_PARTICIPANT", "You are not a room participant"
            )
            return

        # Validate room is in a spin phase
        if room.status not in ("SPINNING_LEAGUES", "SPINNING_TEAMS"):
            await _send_error(
                websocket,
                "INVALID_ACTION",
                f"Mutual superspin can only be proposed during spin phases, current status: {room.status}",
            )
            return

        # Check if there's already a pending proposal
        if room.mutual_superspin_proposer_id is not None:
            await _send_error(
                websocket,
                "INVALID_ACTION",
                "A mutual superspin proposal is already pending",
            )
            return

        # Set proposer
        room.mutual_superspin_proposer_id = player_uuid
        session.add(room)
        session.commit()

        # Broadcast proposal to room
        await manager.broadcast(
            room_code,
            {
                "type": "mutual_superspin_proposed",
                "payload": {"proposer_id": player_id},
            },
        )

    except Exception as e:
        await _send_error(websocket, "INTERNAL_ERROR", str(e))


async def _handle_accept_mutual_superspin(
    session,
    room_code: str,
    player_id: str,
    websocket: WebSocket,
) -> None:
    """Handle accept_mutual_superspin message.

    Validates pending proposal exists and accepter is not proposer,
    resets room with both having superspin, broadcasts acceptance.

    Args:
        session: Database session.
        room_code: The room code.
        player_id: The player ID accepting mutual superspin.
        websocket: The WebSocket connection of the accepter.
    """
    try:
        # Load room
        statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
        room = session.exec(statement).first()

        if not room:
            await _send_error(websocket, "ROOM_NOT_FOUND", "Room not found")
            return

        # Parse player_id as UUID
        player_uuid = uuid.UUID(player_id)

        # Validate player is room participant
        if room.player1_id != player_uuid and room.player2_id != player_uuid:
            await _send_error(
                websocket, "NOT_A_PARTICIPANT", "You are not a room participant"
            )
            return

        # Validate pending proposal exists
        if room.mutual_superspin_proposer_id is None:
            await _send_error(
                websocket,
                "INVALID_ACTION",
                "No pending mutual superspin proposal to accept",
            )
            return

        # Validate accepter is not proposer
        if room.mutual_superspin_proposer_id == player_uuid:
            await _send_error(
                websocket,
                "INVALID_ACTION",
                "You cannot accept your own mutual superspin proposal",
            )
            return

        # Reset room for mutual superspin
        GameService.reset_room_for_mutual_superspin(session, room)

        # Broadcast acceptance
        await manager.broadcast(
            room_code,
            {
                "type": "mutual_superspin_accepted",
                "payload": {"accepted_by_id": player_id},
            },
        )

        # Get game snapshot and broadcast state_sync
        snapshot = GameService.get_game_snapshot(session=session, room_code=room_code)
        await manager.broadcast(
            room_code,
            {"type": "state_sync", "payload": snapshot},
        )

    except Exception as e:
        await _send_error(websocket, "INTERNAL_ERROR", str(e))


async def _handle_decline_mutual_superspin(
    session,
    room_code: str,
    player_id: str,
    websocket: WebSocket,
) -> None:
    """Handle decline_mutual_superspin message.

    Validates pending proposal exists, clears proposal, broadcasts decline.

    Args:
        session: Database session.
        room_code: The room code.
        player_id: The player ID declining mutual superspin.
        websocket: The WebSocket connection of the decliner.
    """
    try:
        # Load room
        statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
        room = session.exec(statement).first()

        if not room:
            await _send_error(websocket, "ROOM_NOT_FOUND", "Room not found")
            return

        # Parse player_id as UUID
        player_uuid = uuid.UUID(player_id)

        # Validate player is room participant
        if room.player1_id != player_uuid and room.player2_id != player_uuid:
            await _send_error(
                websocket, "NOT_A_PARTICIPANT", "You are not a room participant"
            )
            return

        # Validate pending proposal exists
        if room.mutual_superspin_proposer_id is None:
            await _send_error(
                websocket,
                "INVALID_ACTION",
                "No pending mutual superspin proposal to decline",
            )
            return

        # Clear proposal
        room.mutual_superspin_proposer_id = None
        session.add(room)
        session.commit()

        # Broadcast decline
        await manager.broadcast(
            room_code,
            {
                "type": "mutual_superspin_declined",
                "payload": {"declined_by_id": player_id},
            },
        )

    except Exception as e:
        await _send_error(websocket, "INTERNAL_ERROR", str(e))


async def _handle_game_action(
    session,
    room_code: str,
    player_id: str,
    action_type: str,
    websocket: WebSocket,
) -> None:
    """Handle game action (spin_league, lock_league, spin_team, lock_team, special spins, ready).

    Args:
        session: Database session.
        room_code: The room code.
        player_id: The player ID performing action.
        action_type: The type of action.
        websocket: The WebSocket connection of the acting player.
    """
    try:
        # Parse player_id as UUID
        player_uuid = uuid.UUID(player_id)

        # Call GameService.handle_action
        result = GameService.handle_action(
            session=session,
            room_code=room_code,
            player_id=player_uuid,
            action_type=action_type,
        )

        # Extract result fields
        action_result = result["result"]
        auto_locked = result.get("auto_locked", False)
        current_turn_player_id = result.get("current_turn_player_id")
        phase_transitioned = result.get("phase_transitioned", False)
        room_status = result.get("room_status")
        rating_review = result.get("rating_review")
        match_id = result.get("match_id")

        # Build appropriate message based on action type
        acting_player_id = result.get("player_id")
        if action_type in (
            "spin_league",
            "spin_team",
            "use_superspin",
            "use_parity_spin",
        ):
            message_type = "spin_result"
            message_payload = _build_spin_result_payload(
                action_type, action_result, auto_locked, acting_player_id
            )
        elif action_type in ("lock_league", "lock_team"):
            message_type = "lock_result"
            message_payload = _build_lock_result_payload(
                action_type, action_result, acting_player_id
            )
        elif action_type == "ready_to_play":
            # ready_to_play doesn't broadcast a specific action result
            message_type = None
            message_payload = None
        else:
            # Unknown action type - shouldn't happen due to earlier validation
            await _send_error(
                websocket, "INVALID_ACTION", f"Unknown action: {action_type}"
            )
            return

        # Broadcast action result to all room members (except ready_to_play)
        if message_type and message_payload:
            await manager.broadcast(
                room_code,
                {"type": message_type, "payload": message_payload},
            )

        # Broadcast rating review if available
        if rating_review:
            await manager.broadcast(
                room_code,
                {"type": "rating_review", "payload": rating_review},
            )

        # Broadcast turn change
        await manager.broadcast(
            room_code,
            {
                "type": "turn_changed",
                "payload": {"current_turn_player_id": current_turn_player_id},
            },
        )

        # Broadcast phase transition if it occurred
        if phase_transitioned:
            payload = {"phase": room_status, "room_status": room_status}
            if match_id:
                payload["match_id"] = match_id
            await manager.broadcast(
                room_code,
                {
                    "type": "phase_changed",
                    "payload": payload,
                },
            )

    except NotYourTurnError as e:
        # Send error to acting player only
        await _send_error(websocket, e.code, e.detail)
    except InvalidActionError as e:
        # Send error to acting player only
        await _send_error(websocket, e.code, e.detail)
    except GameActionError as e:
        # Send error to acting player only
        await _send_error(websocket, e.code, e.detail)
    except SpecialSpinError as e:
        # Special spin validation error
        await _send_error(websocket, "SPECIAL_SPIN_ERROR", str(e))
    except HTTPException as e:
        # Room not found/expired - should not happen after connection validation
        await _send_error(websocket, "ROOM_ERROR", str(e.detail))


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    """Send error message to WebSocket client.

    Args:
        websocket: The WebSocket connection to send error to.
        code: The error code (deterministic, for client mapping).
        message: The error message.
    """
    await websocket.send_json(
        {"type": "error", "payload": {"code": code, "message": message}}
    )


def _build_spin_result_payload(
    action_type: str, action_result: dict, auto_locked: bool, player_id: str | None
) -> dict:
    """Build payload for spin_result message.

    Args:
        action_type: The action type (spin_league, spin_team, use_superspin, use_parity_spin).
        action_result: The action result from GameService.
        auto_locked: Whether auto-lock occurred.
        player_id: The player ID who performed action.

    Returns:
        The spin_result payload with league/team data and optional lock info.
    """
    payload = {"player_id": player_id, "auto_locked": auto_locked}

    if action_type in ("spin_league", "spin_team"):
        payload["spins_remaining"] = action_result.get("spins_remaining")
    elif action_type in ("use_superspin", "use_parity_spin"):
        payload["was_fallback"] = action_result.get("was_fallback")

    if action_type == "spin_league":
        payload["type"] = "league"
        payload["result"] = action_result.get("league", {})
    elif action_type == "spin_team":
        payload["type"] = "team"
        payload["result"] = action_result.get("team", {})
    elif action_type in ("use_superspin", "use_parity_spin"):
        payload["type"] = "team"
        payload["result"] = action_result.get("team", {})

    # Include lock info if auto-locked
    if auto_locked and "lock" in action_result:
        payload["lock"] = action_result["lock"]

    return payload


def _build_lock_result_payload(
    action_type: str, action_result: dict, player_id: str | None
) -> dict:
    """Build payload for lock_result message.

    Args:
        action_type: The action type (lock_league or lock_team).
        action_result: The action result from GameService.
        player_id: The player ID who performed action.

    Returns:
        The lock_result payload with lock confirmation.
    """
    payload = {
        "player_id": player_id,
        "lock": action_result.get("lock", {}),
    }

    if action_type == "lock_league":
        payload["type"] = "league"
    else:  # lock_team
        payload["type"] = "team"

    return payload
