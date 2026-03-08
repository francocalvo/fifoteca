"""Global WebSocket Connection Manager for Fifoteca.

Manages user-level WebSocket connections (not tied to a specific room)
for features like invites and presence.
"""

from typing import Any

from fastapi import WebSocket


class GlobalConnectionManager:
    """Manages global WebSocket connections keyed by user_id."""

    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Register a user's global WebSocket connection."""
        # Close existing connection if any
        if user_id in self.connections:
            try:
                await self.connections[user_id].close(code=4010)
            except Exception:
                pass
        self.connections[user_id] = websocket

    def disconnect(self, user_id: str) -> None:
        """Remove a user's global WebSocket connection."""
        self.connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> bool:
        """Send a message to a specific user. Returns True if sent."""
        ws = self.connections.get(user_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            self.disconnect(user_id)
            return False

    def is_connected(self, user_id: str) -> bool:
        """Check if a user has an active global WebSocket."""
        return user_id in self.connections


global_manager = GlobalConnectionManager()
