"""WebSocket endpoint for Fifoteca real-time game flow."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import select

from app.core import security
from app.core.config import settings
from app.crud import get_player_by_user_id
from app.models import TokenPayload, User
from app.services.game_service import GameService
from app.ws import handlers, manager

router = APIRouter(prefix="/ws", tags=["ws"])

# Room expiry duration in minutes
ROOM_EXPIRY_MINUTES = 60


@router.websocket("/{room_code}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    token: str = Query(...),
) -> None:
    """WebSocket endpoint for Fifoteca room connections.

    Validates JWT token, verifies room membership, sends initial state,
    and manages the message receive loop.

    Connection flow:
    1. Validate JWT (before accept) - close 4001 if invalid
    2. Validate room exists - close if not found
    3. Validate room not expired - close 4002 if expired
    4. Validate player belongs to room - close 4003 if not
    5. Accept connection
    6. Register with ConnectionManager
    7. Send state_sync snapshot
    8. Broadcast player_connected to room
    9. Enter message loop (stub handler for now)
    10. On disconnect, cleanup and broadcast player_disconnected
    """
    # Create database session for this connection
    from app.api.deps import get_db

    db_gen = get_db()
    session = next(db_gen)

    player_id = None

    try:
        # Step 1: Validate JWT before accept()
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
            )
            token_data = TokenPayload(**payload)
        except (InvalidTokenError, ValidationError):
            await websocket.close(code=4001)
            return

        # Get user from token
        user = session.get(User, token_data.sub)
        if not user:
            await websocket.close(code=4001)
            return

        if not user.is_active:
            await websocket.close(code=4001)
            return

        # Get player profile
        player = get_player_by_user_id(session=session, user_id=user.id)
        if not player:
            await websocket.close(code=4001)
            return

        # Step 2: Validate room exists
        from app.models import FifotecaRoom

        room_statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
        room = session.exec(room_statement).first()

        if not room:
            await websocket.close(code=1008)  # Policy violation
            return

        # Step 3: Validate room not expired
        now = datetime.now(timezone.utc)
        if room.expires_at < now:
            await websocket.close(code=4002)
            return

        # Step 4: Validate player belongs to room
        if room.player1_id != player.id and room.player2_id != player.id:
            await websocket.close(code=4003)
            return

        player_id = str(player.id)

        # Step 5: Accept connection
        await websocket.accept()

        # Refresh room expiry on successful connect
        room.expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=ROOM_EXPIRY_MINUTES
        )
        session.add(room)
        session.commit()

        # Step 6: Register with ConnectionManager
        await manager.connect(
            room_code,
            websocket,
            {"player_id": player_id, "user_id": str(user.id)},
        )

        # Step 7: Send state_sync snapshot
        snapshot = GameService.get_game_snapshot(session=session, room_code=room_code)
        await websocket.send_json({"type": "state_sync", "payload": snapshot})

        # Step 8: Broadcast player_connected to room (exclude self)
        await manager.broadcast(
            room_code,
            {
                "type": "player_connected",
                "payload": {"player_id": player_id},
            },
            exclude=websocket,
        )

        # Step 8b: Re-fetch and broadcast state_sync to existing connections
        # so they pick up any room changes (e.g. player2 joined → status changed).
        # We re-fetch the snapshot to ensure it reflects the latest DB state,
        # since the room may have been modified by the REST join endpoint
        # between P1's initial state_sync and P2's connection.
        session.expire_all()
        fresh_snapshot = GameService.get_game_snapshot(
            session=session, room_code=room_code
        )
        await manager.broadcast(
            room_code,
            {"type": "state_sync", "payload": fresh_snapshot},
            exclude=websocket,
        )

        # Step 9: Message loop with game action handler
        try:
            while True:
                data = await websocket.receive_json()
                # Delegate to handler module
                await handlers.handle_message(
                    session=session,
                    room_code=room_code,
                    player_id=player_id,
                    data=data,
                    websocket=websocket,
                )

        except WebSocketDisconnect:
            # Normal disconnect
            pass

    finally:
        # Step 10: Cleanup on disconnect
        if player_id:
            # Check if player intentionally left room (flag set by leave_room handler)
            intentionally_left = getattr(websocket.state, "left_room", False)

            manager.disconnect(room_code, websocket)

            # Only broadcast player_disconnected if not intentional leave
            # (intentional leave already sent player_left broadcast)
            if not intentionally_left:
                await manager.broadcast(
                    room_code,
                    {
                        "type": "player_disconnected",
                        "payload": {"player_id": player_id},
                    },
                )

        # Close database session
        try:
            next(db_gen, None)
        except StopIteration:
            pass
