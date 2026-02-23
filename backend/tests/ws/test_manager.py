"""Tests for WebSocket Connection Manager."""

import pytest

from app.ws.manager import ConnectionManager

# type: ignore[misc] - MockWebSocket intentionally differs from fastapi.WebSocket


class MockWebSocket:  # type: ignore[misc]
    """Mock WebSocket for testing."""

    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self.client_state = "connected"

    async def send_json(self, message: dict) -> None:
        """Mock send_json method."""
        self.sent_messages.append(message)

    async def close(self) -> None:
        """Mock close method."""
        self.client_state = "disconnected"


@pytest.fixture
def ws1() -> MockWebSocket:
    """Create a mock WebSocket instance."""
    return MockWebSocket()


@pytest.fixture
def ws2() -> MockWebSocket:
    """Create another mock WebSocket instance."""
    return MockWebSocket()


@pytest.fixture
def ws3() -> MockWebSocket:
    """Create a third mock WebSocket instance."""
    return MockWebSocket()


@pytest.fixture
def manager() -> ConnectionManager:
    """Create a ConnectionManager instance for testing."""
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect_tracks_connection(
    manager: ConnectionManager, ws1: MockWebSocket
) -> None:
    """Test that connect correctly adds connection to room set and stores metadata."""
    room_code = "ABC123"
    user_info = {"player_id": "player1", "user_id": "user1"}

    # Connect the WebSocket
    await manager.connect(room_code, ws1, user_info)

    # Verify room was created and WebSocket is in the set
    assert room_code in manager.rooms
    assert ws1 in manager.rooms[room_code]

    # Verify metadata is stored
    assert ws1 in manager.metadata
    assert manager.metadata[ws1] == user_info


@pytest.mark.asyncio
async def test_connect_multiple_connections_same_room(
    manager: ConnectionManager,
    ws1: MockWebSocket,
    ws2: MockWebSocket,
) -> None:
    """Test that multiple connections can be added to the same room."""
    room_code = "ABC123"
    user_info1 = {"player_id": "player1", "user_id": "user1"}
    user_info2 = {"player_id": "player2", "user_id": "user2"}

    # Connect both WebSockets
    await manager.connect(room_code, ws1, user_info1)
    await manager.connect(room_code, ws2, user_info2)

    # Verify both are in the room set
    assert len(manager.rooms[room_code]) == 2
    assert ws1 in manager.rooms[room_code]
    assert ws2 in manager.rooms[room_code]

    # Verify both metadata entries are stored
    assert manager.metadata[ws1] == user_info1
    assert manager.metadata[ws2] == user_info2


@pytest.mark.asyncio
async def test_disconnect_removes_connection(
    manager: ConnectionManager,
    ws1: MockWebSocket,
) -> None:
    """Test that disconnect removes connection from room set and cleans up metadata."""
    room_code = "ABC123"
    user_info = {"player_id": "player1", "user_id": "user1"}

    # Connect the WebSocket
    await manager.connect(room_code, ws1, user_info)

    # Verify it's connected
    assert ws1 in manager.rooms[room_code]
    assert ws1 in manager.metadata

    # Disconnect
    manager.disconnect(room_code, ws1)

    # Verify it's removed from metadata
    assert ws1 not in manager.metadata

    # Verify room was cleaned up if empty
    assert room_code not in manager.rooms


@pytest.mark.asyncio
async def test_disconnect_one_of_multiple_connections(
    manager: ConnectionManager,
    ws1: MockWebSocket,
    ws2: MockWebSocket,
) -> None:
    """Test that disconnecting one connection doesn't affect others."""
    room_code = "ABC123"
    user_info1 = {"player_id": "player1", "user_id": "user1"}
    user_info2 = {"player_id": "player2", "user_id": "user2"}

    # Connect both WebSockets
    await manager.connect(room_code, ws1, user_info1)
    await manager.connect(room_code, ws2, user_info2)

    # Disconnect first
    manager.disconnect(room_code, ws1)

    # Verify ws1 is removed but ws2 is still there
    assert ws1 not in manager.rooms[room_code]
    assert ws2 in manager.rooms[room_code]
    assert room_code in manager.rooms  # Room still exists

    # Verify metadata cleanup
    assert ws1 not in manager.metadata
    assert ws2 in manager.metadata


@pytest.mark.asyncio
async def test_disconnect_nonexistent_connection(
    manager: ConnectionManager,
    ws1: MockWebSocket,
) -> None:
    """Test that disconnecting a non-existent connection doesn't raise an error."""
    room_code = "ABC123"

    # Try to disconnect without connecting first - should not raise
    manager.disconnect(room_code, ws1)

    # Verify no error was raised and state is clean
    assert room_code not in manager.rooms
    assert ws1 not in manager.metadata


@pytest.mark.asyncio
async def test_disconnect_from_nonexistent_room(
    manager: ConnectionManager,
    ws1: MockWebSocket,
) -> None:
    """Test that disconnecting from a non-existent room doesn't raise an error."""
    room_code = "NONEXIST"

    # Try to disconnect from non-existent room - should not raise
    manager.disconnect(room_code, ws1)

    # Verify no error was raised
    assert room_code not in manager.rooms


@pytest.mark.asyncio
async def test_broadcast_sends_to_all(
    manager: ConnectionManager,
    ws1: MockWebSocket,
    ws2: MockWebSocket,
    ws3: MockWebSocket,
) -> None:
    """Test that broadcast sends payload to all connections in room."""
    room_code = "ABC123"
    payload = {"type": "test", "message": "hello"}

    # Connect all WebSockets
    await manager.connect(room_code, ws1, {"player_id": "player1", "user_id": "user1"})
    await manager.connect(room_code, ws2, {"player_id": "player2", "user_id": "user2"})
    await manager.connect(room_code, ws3, {"player_id": "player3", "user_id": "user3"})

    # Broadcast message
    await manager.broadcast(room_code, payload)

    # Verify all received the message
    assert payload in ws1.sent_messages
    assert payload in ws2.sent_messages
    assert payload in ws3.sent_messages


@pytest.mark.asyncio
async def test_broadcast_with_exclude(
    manager: ConnectionManager,
    ws1: MockWebSocket,
    ws2: MockWebSocket,
    ws3: MockWebSocket,
) -> None:
    """Test that broadcast with exclude works correctly."""
    room_code = "ABC123"
    payload = {"type": "test", "message": "hello"}

    # Connect all WebSockets
    await manager.connect(room_code, ws1, {"player_id": "player1", "user_id": "user1"})
    await manager.connect(room_code, ws2, {"player_id": "player2", "user_id": "user2"})
    await manager.connect(room_code, ws3, {"player_id": "player3", "user_id": "user3"})

    # Broadcast excluding ws2
    await manager.broadcast(room_code, payload, exclude=ws2)

    # Verify ws1 and ws3 received, but ws2 did not
    assert payload in ws1.sent_messages
    assert payload not in ws2.sent_messages
    assert payload in ws3.sent_messages


@pytest.mark.asyncio
async def test_broadcast_to_empty_room(manager: ConnectionManager) -> None:
    """Test that broadcasting to an empty or non-existent room doesn't raise an error."""
    room_code = "EMPTY"
    payload = {"type": "test", "message": "hello"}

    # Broadcast to non-existent room - should not raise
    await manager.broadcast(room_code, payload)

    # Create room, connect, disconnect, then broadcast (empty room)
    ws1 = MockWebSocket()
    await manager.connect(room_code, ws1, {"player_id": "player1", "user_id": "user1"})
    manager.disconnect(room_code, ws1)

    # Broadcast to now-empty room - should not raise
    await manager.broadcast(room_code, payload)


@pytest.mark.asyncio
async def test_send_to_player_targets_correctly(
    manager: ConnectionManager,
    ws1: MockWebSocket,
    ws2: MockWebSocket,
) -> None:
    """Test that send_to_player only sends to the target player."""
    room_code = "ABC123"
    payload = {"type": "test", "message": "hello"}

    # Connect both WebSockets
    await manager.connect(room_code, ws1, {"player_id": "player1", "user_id": "user1"})
    await manager.connect(room_code, ws2, {"player_id": "player2", "user_id": "user2"})

    # Send to player1 only
    await manager.send_to_player(room_code, "player1", payload)

    # Verify only ws1 received the message
    assert payload in ws1.sent_messages
    assert payload not in ws2.sent_messages


@pytest.mark.asyncio
async def test_send_to_player_nonexistent_player(
    manager: ConnectionManager,
    ws1: MockWebSocket,
) -> None:
    """Test that sending to a non-existent player doesn't raise an error."""
    room_code = "ABC123"
    payload = {"type": "test", "message": "hello"}

    # Connect one WebSocket
    await manager.connect(room_code, ws1, {"player_id": "player1", "user_id": "user1"})

    # Try to send to non-existent player - should not raise
    await manager.send_to_player(room_code, "player_nonexistent", payload)

    # Verify ws1 did not receive anything
    assert not ws1.sent_messages


@pytest.mark.asyncio
async def test_send_to_player_nonexistent_room(manager: ConnectionManager) -> None:
    """Test that sending to a non-existent room doesn't raise an error."""
    room_code = "NONEXIST"
    payload = {"type": "test", "message": "hello"}

    # Send to non-existent room - should not raise
    await manager.send_to_player(room_code, "player1", payload)


def test_get_connected_players(
    manager: ConnectionManager, ws1: MockWebSocket, ws2: MockWebSocket
) -> None:
    """Test that get_connected_players returns correct list."""
    room_code = "ABC123"

    # Empty room should return empty list
    assert manager.get_connected_players(room_code) == []

    # Connect one WebSocket
    manager.rooms[room_code] = {ws1}
    manager.metadata[ws1] = {"player_id": "player1", "user_id": "user1"}

    # Should return one player
    players = manager.get_connected_players(room_code)
    assert len(players) == 1
    assert "player1" in players

    # Connect second WebSocket
    manager.rooms[room_code].add(ws2)
    manager.metadata[ws2] = {"player_id": "player2", "user_id": "user2"}

    # Should return two players
    players = manager.get_connected_players(room_code)
    assert len(players) == 2
    assert "player1" in players
    assert "player2" in players


def test_get_connected_players_nonexistent_room(manager: ConnectionManager) -> None:
    """Test that get_connected_players returns empty list for non-existent room."""
    room_code = "NONEXIST"

    # Should return empty list
    assert manager.get_connected_players(room_code) == []


def test_get_connected_players_handles_missing_metadata(
    manager: ConnectionManager,
    ws1: MockWebSocket,
) -> None:
    """Test that get_connected_players handles connections without metadata gracefully."""
    room_code = "ABC123"

    # Add WebSocket to room but not metadata (edge case)
    manager.rooms[room_code] = {ws1}

    # Should return empty list (no player_id available)
    players = manager.get_connected_players(room_code)
    assert len(players) == 0


def test_multiple_rooms(
    manager: ConnectionManager, ws1: MockWebSocket, ws2: MockWebSocket
) -> None:
    """Test that the manager correctly handles multiple separate rooms."""
    room1 = "ROOM1"
    room2 = "ROOM2"

    # Connect ws1 to room1
    manager.rooms[room1] = {ws1}
    manager.metadata[ws1] = {"player_id": "player1", "user_id": "user1"}

    # Connect ws2 to room2
    manager.rooms[room2] = {ws2}
    manager.metadata[ws2] = {"player_id": "player2", "user_id": "user2"}

    # Verify both rooms exist separately
    assert len(manager.rooms) == 2
    assert room1 in manager.rooms
    assert room2 in manager.rooms

    # Verify player lists are separate
    assert manager.get_connected_players(room1) == ["player1"]
    assert manager.get_connected_players(room2) == ["player2"]


@pytest.mark.asyncio
async def test_singleton_instance() -> None:
    """Test that the module-level manager is a singleton instance."""
    from app.ws.manager import manager

    # Verify it's a ConnectionManager instance
    assert isinstance(manager, ConnectionManager)

    # Verify it's the same instance across imports
    from app.ws import manager as manager2

    assert manager is manager2
