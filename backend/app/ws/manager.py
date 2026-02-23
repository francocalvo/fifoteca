"""WebSocket Connection Manager for Fifoteca real-time game flow.

The ConnectionManager is a singleton that tracks WebSocket connections per room
and provides utilities for broadcasting messages and targeting specific players.
"""

from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections for multiplayer Fifoteca games.

    This singleton class maintains mappings between room codes and their
    connected WebSocket clients, along with metadata about each connection
    (player_id, user_id).
    """

    def __init__(self) -> None:
        """Initialize the connection manager."""
        self.rooms: dict[str, set[WebSocket]] = {}
        self.metadata: dict[WebSocket, dict[str, Any]] = {}

    async def connect(
        self, room_code: str, ws: WebSocket, user_info: dict[str, Any]
    ) -> None:
        """Connect a WebSocket to a room.

        Args:
            room_code: The room code to connect to.
            ws: The WebSocket connection.
            user_info: Dictionary containing player_id and user_id.
        """
        # Add WebSocket to room set
        if room_code not in self.rooms:
            self.rooms[room_code] = set()
        self.rooms[room_code].add(ws)

        # Store metadata for this WebSocket
        self.metadata[ws] = user_info

    def disconnect(self, room_code: str, ws: WebSocket) -> None:
        """Disconnect a WebSocket from a room.

        Args:
            room_code: The room code to disconnect from.
            ws: The WebSocket connection to disconnect.

        Note:
            Silently ignores attempts to disconnect a non-existent connection.
        """
        # Remove from room set if present
        if room_code in self.rooms:
            self.rooms[room_code].discard(ws)
            # Clean up empty rooms
            if not self.rooms[room_code]:
                del self.rooms[room_code]

        # Clean up metadata if present
        self.metadata.pop(ws, None)

    async def broadcast(
        self,
        room_code: str,
        payload: dict[str, Any],
        exclude: WebSocket | None = None,
    ) -> None:
        """Broadcast a message to all connections in a room.

        Args:
            room_code: The room code to broadcast to.
            payload: The JSON payload to send.
            exclude: Optional WebSocket to exclude from broadcast.

        Note:
            Silently ignores attempts to broadcast to non-existent or empty rooms.
        """
        if room_code not in self.rooms:
            return

        for ws in self.rooms[room_code]:
            if exclude is not None and ws is exclude:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                # Connection may be closed, ignore
                pass

    async def send_to_player(
        self,
        room_code: str,
        player_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Send a message to a specific player in a room.

        Args:
            room_code: The room code.
            player_id: The player ID to send to.
            payload: The JSON payload to send.

        Note:
            Silently ignores attempts to send to non-existent players or rooms.
        """
        if room_code not in self.rooms:
            return

        # Find the WebSocket for this player_id
        for ws, meta in self.metadata.items():
            if meta.get("player_id") == player_id:
                try:
                    await ws.send_json(payload)
                except Exception:
                    # Connection may be closed, ignore
                    pass
                break

    def get_connected_players(self, room_code: str) -> list[str]:
        """Get the list of connected player IDs for a room.

        Args:
            room_code: The room code.

        Returns:
            List of connected player IDs. Returns empty list for non-existent rooms.
        """
        if room_code not in self.rooms:
            return []

        player_ids: list[str] = []
        for ws in self.rooms[room_code]:
            if ws in self.metadata:
                player_id = self.metadata[ws].get("player_id")
                if player_id:
                    player_ids.append(player_id)

        return player_ids


# Module-level singleton instance
manager = ConnectionManager()
