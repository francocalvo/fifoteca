"""Global WebSocket endpoint for Fifoteca (invites, presence)."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import select

from app.core import security
from app.core.config import settings
from app.crud import get_player_by_user_id
from app.models import FifotecaRoom, TokenPayload, User
from app.ws.global_manager import global_manager

router = APIRouter(prefix="/ws", tags=["global-ws"])

INVITE_EXPIRY_SECONDS = 30


@dataclass
class InviteInfo:
    invite_id: str
    room_code: str
    inviter_id: str
    inviter_player_id: str
    inviter_display_name: str
    invitee_id: str
    expires_at: float
    expiry_task: asyncio.Task | None = field(default=None, repr=False)


# In-memory invite tracking
pending_invites: dict[str, InviteInfo] = {}
# Track one pending invite per (inviter, room) to avoid spam
active_invite_by_room: dict[str, str] = {}  # "{inviter_id}:{room_code}" -> invite_id


async def _expire_invite(invite_id: str) -> None:
    """Auto-expire an invite after timeout."""
    invite = pending_invites.get(invite_id)
    if not invite:
        return

    await asyncio.sleep(INVITE_EXPIRY_SECONDS)

    # Check if still pending
    if invite_id not in pending_invites:
        return

    # Clean up
    del pending_invites[invite_id]
    key = f"{invite.inviter_id}:{invite.room_code}"
    active_invite_by_room.pop(key, None)

    # Notify both parties
    await global_manager.send_to_user(
        invite.inviter_id,
        {
            "type": "invite_expired",
            "payload": {"invite_id": invite_id, "invitee_id": invite.invitee_id},
        },
    )
    await global_manager.send_to_user(
        invite.invitee_id,
        {
            "type": "invite_expired",
            "payload": {"invite_id": invite_id},
        },
    )


async def _handle_send_invite(
    session, user_id: str, player_id: str, display_name: str, payload: dict
) -> None:
    """Handle send_invite message."""
    invitee_id = payload.get("invitee_id")
    room_code = payload.get("room_code")

    if not invitee_id or not room_code:
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "INVALID_INVITE", "message": "Missing invitee_id or room_code"}},
        )
        return

    # Validate room exists and is WAITING
    statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
    room = session.exec(statement).first()

    if not room or room.status != "WAITING":
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "INVALID_INVITE", "message": "Room not found or not in waiting status"}},
        )
        return

    # Check no duplicate invite for this room from this inviter
    key = f"{user_id}:{room_code}"
    if key in active_invite_by_room:
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "INVITE_PENDING", "message": "An invite is already pending for this room"}},
        )
        return

    # Check invitee is connected
    if not global_manager.is_connected(invitee_id):
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "USER_OFFLINE", "message": "Player is not online"}},
        )
        return

    # Create invite
    invite_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).timestamp()
    invite = InviteInfo(
        invite_id=invite_id,
        room_code=room_code,
        inviter_id=user_id,
        inviter_player_id=player_id,
        inviter_display_name=display_name,
        invitee_id=invitee_id,
        expires_at=now + INVITE_EXPIRY_SECONDS,
    )

    pending_invites[invite_id] = invite
    active_invite_by_room[key] = invite_id

    # Schedule expiry
    invite.expiry_task = asyncio.create_task(_expire_invite(invite_id))

    # Send to invitee
    await global_manager.send_to_user(
        invitee_id,
        {
            "type": "invite_received",
            "payload": {
                "invite_id": invite_id,
                "room_code": room_code,
                "inviter_display_name": display_name,
                "expires_in": INVITE_EXPIRY_SECONDS,
            },
        },
    )

    # Confirm to inviter
    await global_manager.send_to_user(
        user_id,
        {
            "type": "invite_sent",
            "payload": {
                "invite_id": invite_id,
                "invitee_id": invitee_id,
            },
        },
    )


async def _handle_accept_invite(session, user_id: str, payload: dict) -> None:
    """Handle accept_invite message."""
    invite_id = payload.get("invite_id")
    if not invite_id or invite_id not in pending_invites:
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "INVITE_NOT_FOUND", "message": "Invite not found or expired"}},
        )
        return

    invite = pending_invites[invite_id]

    # Validate accepter is the invitee
    if invite.invitee_id != user_id:
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "INVALID_ACTION", "message": "You are not the invitee"}},
        )
        return

    # Check not expired
    now = datetime.now(timezone.utc).timestamp()
    if now > invite.expires_at:
        del pending_invites[invite_id]
        key = f"{invite.inviter_id}:{invite.room_code}"
        active_invite_by_room.pop(key, None)
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "INVITE_EXPIRED", "message": "Invite has expired"}},
        )
        return

    # Join room (reuse join logic)
    room_code = invite.room_code
    statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
    room = session.exec(statement).first()

    if not room or room.status != "WAITING" or room.player2_id is not None:
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "ROOM_UNAVAILABLE", "message": "Room is no longer available"}},
        )
        # Clean up
        _cleanup_invite(invite_id)
        return

    # Get invitee's player
    from app.models import FifotecaPlayer

    player_statement = select(FifotecaPlayer).where(
        FifotecaPlayer.user_id == uuid.UUID(user_id)
    )
    player = session.exec(player_statement).first()

    if not player:
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "NO_PROFILE", "message": "Player profile not found"}},
        )
        _cleanup_invite(invite_id)
        return

    # Self-join check
    if room.player1_id == player.id:
        await global_manager.send_to_user(
            user_id,
            {"type": "error", "payload": {"code": "INVALID_ACTION", "message": "Cannot join your own room"}},
        )
        _cleanup_invite(invite_id)
        return

    # Perform room join using shared logic
    from app.services.game_service import GameService

    GameService.join_player_to_room(session, room, player)

    # Clean up invite
    _cleanup_invite(invite_id)

    # Notify inviter
    await global_manager.send_to_user(
        invite.inviter_id,
        {
            "type": "invite_accepted",
            "payload": {"invite_id": invite_id, "room_code": room_code},
        },
    )

    # Tell invitee to navigate to lobby/game
    await global_manager.send_to_user(
        user_id,
        {
            "type": "join_room_redirect",
            "payload": {"room_code": room_code},
        },
    )


async def _handle_decline_invite(user_id: str, payload: dict) -> None:
    """Handle decline_invite message."""
    invite_id = payload.get("invite_id")
    if not invite_id or invite_id not in pending_invites:
        return

    invite = pending_invites[invite_id]

    # Validate decliner is the invitee
    if invite.invitee_id != user_id:
        return

    _cleanup_invite(invite_id)

    # Notify inviter
    await global_manager.send_to_user(
        invite.inviter_id,
        {
            "type": "invite_declined",
            "payload": {"invite_id": invite_id, "invitee_id": invite.invitee_id},
        },
    )


def _cleanup_invite(invite_id: str) -> None:
    """Remove an invite and cancel its expiry task."""
    invite = pending_invites.pop(invite_id, None)
    if invite:
        key = f"{invite.inviter_id}:{invite.room_code}"
        active_invite_by_room.pop(key, None)
        if invite.expiry_task and not invite.expiry_task.done():
            invite.expiry_task.cancel()


@router.websocket("/global")
async def global_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """Global WebSocket endpoint for Fifoteca (invites, presence)."""
    from app.api.deps import get_db

    db_gen = get_db()
    session = next(db_gen)

    user_id = None

    try:
        # Validate JWT
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
            )
            token_data = TokenPayload(**payload)
        except (InvalidTokenError, ValidationError):
            await websocket.close(code=4001)
            return

        user = session.get(User, token_data.sub)
        if not user or not user.is_active:
            await websocket.close(code=4001)
            return

        player = get_player_by_user_id(session=session, user_id=user.id)
        if not player:
            await websocket.close(code=4001)
            return

        user_id = str(user.id)
        player_id = str(player.id)
        display_name = player.display_name

        await websocket.accept()
        await global_manager.connect(user_id, websocket)

        # Message loop
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            msg_payload = data.get("payload", {})

            if message_type == "ping":
                await websocket.send_json({"type": "pong", "payload": {}})
            elif message_type == "send_invite":
                await _handle_send_invite(session, user_id, player_id, display_name, msg_payload)
            elif message_type == "accept_invite":
                await _handle_accept_invite(session, user_id, msg_payload)
            elif message_type == "decline_invite":
                await _handle_decline_invite(user_id, msg_payload)

    except WebSocketDisconnect:
        pass
    finally:
        if user_id:
            global_manager.disconnect(user_id)
        try:
            next(db_gen, None)
        except StopIteration:
            pass
