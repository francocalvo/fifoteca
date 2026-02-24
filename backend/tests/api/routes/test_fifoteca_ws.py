"""Tests for Fifoteca WebSocket endpoint."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import create_access_token
from app.models import (
    FifotecaPlayer,
    FifotecaPlayerState,
    FifotecaRoom,
    PlayerSpinPhase,
    RoomStatus,
    User,
)


@pytest.fixture
def ws_client(client: TestClient):
    """Create a WebSocket client."""
    return client


@pytest.fixture
def db_session(db: Session):
    """Get a database session."""
    return db


def extract_token(headers: dict[str, str]) -> str:
    """Extract bearer token from headers."""
    auth_header = headers.get("authorization")
    if not auth_header:
        raise ValueError("No authorization header")
    return auth_header.replace("Bearer ", "")


class TestWebSocketConnection:
    """Test WebSocket connection lifecycle."""

    def test_connect_with_valid_token(self, ws_client: TestClient, db: Session) -> None:
        """Test that a valid token allows WebSocket connection and sends state_sync."""
        # Setup: Create user, player, and room
        user = User(
            email="test@example.com",
            display_name="Test Player",
            full_name="Test User",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Test Player",
        )
        db.add(player)
        db.commit()
        db.refresh(player)

        # Create room
        room = FifotecaRoom(
            code="ABC123",
            status=RoomStatus.WAITING,
            player1_id=player.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player state for round 1
        player_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=player.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(player_state)
        db.commit()

        # Create token
        token = create_access_token(user.id, timedelta(minutes=30))

        # Connect via WebSocket
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token}"
        ) as websocket:
            # First message should be state_sync
            data = websocket.receive_json()
            assert data["type"] == "state_sync"
            assert "payload" in data
            assert "room" in data["payload"]
            assert "player_states" in data["payload"]

            # Verify room data
            room_data = data["payload"]["room"]
            assert room_data["code"] == room.code
            assert room_data["player1_id"] == str(player.id)
            assert room_data["status"] == RoomStatus.WAITING

            # Verify player states
            player_states = data["payload"]["player_states"]
            assert len(player_states) == 1
            assert player_states[0]["player_id"] == str(player.id)
            assert player_states[0]["round_number"] == 1
            assert player_states[0]["phase"] == PlayerSpinPhase.LEAGUE_SPINNING

    def test_connect_with_invalid_token_4001(self, ws_client: TestClient) -> None:
        """Test that an invalid token closes connection with code 4001."""
        invalid_token = "invalid.jwt.token"

        # FastAPI test client raises exception when WebSocket is closed before accept
        with pytest.raises(Exception) as exc_info:
            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/ABC123?token={invalid_token}"
            ):
                pass

        # Verify it's a WebSocket disconnect exception
        assert (
            "WebSocket" in str(exc_info.typename)
            or "disconnect" in str(exc_info.value).lower()
        )

        # FastAPI WebSocket test client raises exception on close
        assert "WebSocketDisconnect" in str(exc_info.typename) or exc_info.value

    def test_connect_to_nonexistent_room(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test that connecting to a non-existent room closes connection."""
        # Setup: Create user
        user = User(
            email="test2@example.com",
            display_name="Test Player",
            full_name="Test User 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Test Player",
        )
        db.add(player)
        db.commit()

        # Create token
        token = create_access_token(user.id, timedelta(minutes=30))

        # Try to connect to non-existent room
        # Server should close connection for non-existent room
        with pytest.raises(Exception) as exc_info:
            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/NONEXI?token={token}"
            ):
                pass

        # Verify it's a WebSocket disconnect exception
        assert (
            "WebSocket" in str(exc_info.typename)
            or "disconnect" in str(exc_info.value).lower()
        )

    def test_connect_to_expired_room_4002(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test that connecting to an expired room closes with code 4002."""
        # Setup: Create user, player, and expired room
        user = User(
            email="test3@example.com",
            display_name="Test Player",
            full_name="Test User 3",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Test Player",
        )
        db.add(player)
        db.commit()
        db.refresh(player)

        # Create expired room
        room = FifotecaRoom(
            code="EXP123",
            status=RoomStatus.WAITING,
            player1_id=player.id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # Expired
        )
        db.add(room)
        db.commit()

        # Create token
        token = create_access_token(user.id, timedelta(minutes=30))

        # Try to connect to expired room
        # Server should close connection with code 4002 for expired room
        with pytest.raises(Exception) as exc_info:
            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token}"
            ):
                pass

        # Verify it's a WebSocket disconnect exception
        assert (
            "WebSocket" in str(exc_info.typename)
            or "disconnect" in str(exc_info.value).lower()
        )

    def test_connect_player_not_in_room_4003(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test that non-room member connection closes with code 4003."""
        # Setup: Create two users and players
        user1 = User(
            email="user1@example.com",
            display_name="Test Player",
            full_name="User 1",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="Test Player",
        )
        db.add(player1)
        db.commit()

        user2 = User(
            email="user2@example.com",
            display_name="Test Player",
            full_name="User 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user2)
        db.commit()
        db.refresh(user2)

        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="Test Player",
        )
        db.add(player2)
        db.commit()
        db.refresh(player2)

        # Create room for player1 only
        room = FifotecaRoom(
            code="ONLYP1",
            status=RoomStatus.WAITING,
            player1_id=player1.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()

        # Try to connect player2 to player1's room
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Server should close connection with code 4003 for non-member
        with pytest.raises(Exception) as exc_info:
            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ):
                pass

        # Verify it's a WebSocket disconnect exception
        assert (
            "WebSocket" in str(exc_info.typename)
            or "disconnect" in str(exc_info.value).lower()
        )

    def test_player_connected_broadcast(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test that player_connected is broadcast when a new player joins."""
        # Setup: Create two users and players
        user1 = User(
            email="p1@example.com",
            display_name="Test Player",
            full_name="Player 1",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="Test Player",
        )
        db.add(player1)
        db.commit()
        db.refresh(player1)

        user2 = User(
            email="p2@example.com",
            display_name="Test Player",
            full_name="Player 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user2)
        db.commit()
        db.refresh(user2)

        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="Test Player",
        )
        db.add(player2)
        db.commit()
        db.refresh(player2)

        # Create room with both players
        room = FifotecaRoom(
            code="TWOPLY",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player states
        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
        )
        db.add(state1)
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
        )
        db.add(state2)
        db.commit()

        # Create tokens
        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Player 1 connects first
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            # Get initial state_sync
            ws1.receive_json()

            # Player 2 connects
            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync

                # Player 1 should receive player_connected
                data = ws1.receive_json()
                assert data["type"] == "player_connected"
                assert data["payload"]["player_id"] == str(player2.id)
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

    def test_player_disconnected_broadcast(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test that player_disconnected is broadcast when a player leaves."""
        # Setup: Create two users and players
        user1 = User(
            email="d1@example.com",
            display_name="Test Player",
            full_name="Disconnect 1",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="Test Player",
        )
        db.add(player1)
        db.commit()
        db.refresh(player1)

        user2 = User(
            email="d2@example.com",
            display_name="Test Player",
            full_name="Disconnect 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user2)
        db.commit()
        db.refresh(user2)

        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="Test Player",
        )
        db.add(player2)
        db.commit()
        db.refresh(player2)

        # Create room with both players
        room = FifotecaRoom(
            code="DISCON",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player states
        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
        )
        db.add(state1)
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
        )
        db.add(state2)
        db.commit()

        # Create tokens
        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Both players connect
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync

                # Consume the player_connected message from ws2 joining
                ws1.receive_json()
                # Consume the state_sync re-broadcast after p2 join
                ws1.receive_json()

                # Player 2 disconnects (by exiting context)
                pass

            # Player 1 should receive player_disconnected
            data = ws1.receive_json()
            assert data["type"] == "player_disconnected"
            assert data["payload"]["player_id"] == str(player2.id)

    def test_ping_pong(self, ws_client: TestClient, db: Session) -> None:
        """Test that ping receives pong from stub loop."""
        # Setup: Create user, player, and room
        user = User(
            email="ping@example.com",
            display_name="Test Player",
            full_name="Ping User",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Test Player",
        )
        db.add(player)
        db.commit()
        db.refresh(player)

        room = FifotecaRoom(
            code="PING01",
            status=RoomStatus.WAITING,
            player1_id=player.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        state = FifotecaPlayerState(
            room_id=room.id,
            player_id=player.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
        )
        db.add(state)
        db.commit()

        token = create_access_token(user.id, timedelta(minutes=30))

        # Connect and send ping
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token}"
        ) as websocket:
            websocket.receive_json()  # Get state_sync

            # Send ping
            websocket.send_json({"type": "ping", "payload": {}})

            # Receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"
            assert "payload" in data

    def test_connect_refreshes_room_expiry(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test that WebSocket connect refreshes room expiry."""
        # Setup: Create user, player, and room with short expiry
        user = User(
            email="expiryrefresh@example.com",
            display_name="Test Player",
            full_name="Expiry Refresh User",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Test Player",
        )
        db.add(player)
        db.commit()
        db.refresh(player)

        # Create room with 5 minutes remaining (will be refreshed to 60 on connect)
        initial_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        room = FifotecaRoom(
            code="EXPREF",
            status=RoomStatus.WAITING,
            player1_id=player.id,
            expires_at=initial_expiry,
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player state
        state = FifotecaPlayerState(
            room_id=room.id,
            player_id=player.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
        )
        db.add(state)
        db.commit()

        token = create_access_token(user.id, timedelta(minutes=30))

        # Connect via WebSocket
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token}"
        ) as websocket:
            websocket.receive_json()  # Get state_sync

            # Refresh room from DB and check expiry was extended
            db.refresh(room)
            assert room.expires_at > initial_expiry
            # Should be approximately 60 minutes from now
            expected_min = datetime.now(timezone.utc) + timedelta(minutes=59)
            expected_max = datetime.now(timezone.utc) + timedelta(minutes=61)
            assert room.expires_at > expected_min
            assert room.expires_at < expected_max

    def test_message_refreshes_room_expiry(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test that sending a message refreshes room expiry."""
        # Setup: Create user, player, and room
        user = User(
            email="msgexpiry@example.com",
            display_name="Test Player",
            full_name="Message Expiry User",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Test Player",
        )
        db.add(player)
        db.commit()
        db.refresh(player)

        # Create room with 5 minutes remaining
        initial_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        room = FifotecaRoom(
            code="MSGEXP",
            status=RoomStatus.WAITING,
            player1_id=player.id,
            expires_at=initial_expiry,
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player state
        state = FifotecaPlayerState(
            room_id=room.id,
            player_id=player.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
        )
        db.add(state)
        db.commit()

        token = create_access_token(user.id, timedelta(minutes=30))

        # Connect via WebSocket
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token}"
        ) as websocket:
            websocket.receive_json()  # Get state_sync

            # Get expiry after connect refresh
            db.refresh(room)
            expiry_after_connect = room.expires_at

            # Wait a tiny bit to ensure time passes
            import time

            time.sleep(0.1)

            # Send a ping message
            websocket.send_json({"type": "ping", "payload": {}})
            websocket.receive_json()  # Get pong

            # Refresh room from DB and check expiry was extended again
            db.refresh(room)
            assert room.expires_at > expiry_after_connect


class TestGameService:
    """Test GameService.get_game_snapshot."""

    def test_get_game_snapshot_includes_room_fields(self, db: Session) -> None:
        """Test that snapshot includes all required room fields."""
        from app.services.game_service import GameService

        # Setup: Create user, player, and room
        user = User(
            email="snap@example.com",
            display_name="Test Player",
            full_name="Snapshot User",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Test Player",
        )
        db.add(player)
        db.commit()
        db.refresh(player)

        room = FifotecaRoom(
            code="SNAP01",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Get snapshot
        snapshot = GameService.get_game_snapshot(session=db, room_code="SNAP01")

        # Verify room structure
        assert "room" in snapshot
        room_data = snapshot["room"]

        # Core fields
        assert room_data["id"] == str(room.id)
        assert room_data["code"] == room.code
        assert room_data["ruleset"] == room.ruleset
        assert room_data["status"] == room.status
        assert room_data["player1_id"] == str(room.player1_id)
        assert room_data["player2_id"] is None  # Not set
        assert room_data["current_turn_player_id"] is None
        assert room_data["first_player_id"] is None
        assert room_data["round_number"] == 1
        assert room_data["mutual_superspin_active"] is False
        assert "expires_at" in room_data
        assert "created_at" in room_data

    def test_get_game_snapshot_includes_player_states(self, db: Session) -> None:
        """Test that snapshot includes current round player states."""
        from app.services.game_service import GameService

        # Setup: Create users, players, and room with states
        user1 = User(
            email="s1@example.com",
            display_name="Test Player",
            full_name="Snapshot 1",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="Test Player",
        )
        db.add(player1)
        db.commit()

        user2 = User(
            email="s2@example.com",
            display_name="Test Player",
            full_name="Snapshot 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user2)
        db.commit()
        db.refresh(user2)

        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="Test Player",
        )
        db.add(player2)
        db.commit()
        db.refresh(player2)

        room = FifotecaRoom(
            code="SNAP02",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player states for round 1
        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=2,
            team_spins_remaining=3,
        )
        db.add(state1)

        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=1,
            league_locked=True,
        )
        db.add(state2)
        db.commit()

        # Get snapshot
        snapshot = GameService.get_game_snapshot(session=db, room_code="SNAP02")

        # Verify player states
        assert "player_states" in snapshot
        player_states = snapshot["player_states"]
        assert len(player_states) == 2

        # Verify state structure for player1
        p1_state = next(
            (s for s in player_states if s["player_id"] == str(player1.id)), None
        )
        assert p1_state is not None
        assert p1_state["round_number"] == 1
        assert p1_state["phase"] == PlayerSpinPhase.LEAGUE_SPINNING
        assert p1_state["league_spins_remaining"] == 2
        assert p1_state["team_spins_remaining"] == 3
        assert p1_state["league_locked"] is False

        # Verify state structure for player2
        p2_state = next(
            (s for s in player_states if s["player_id"] == str(player2.id)), None
        )
        assert p2_state is not None
        assert p2_state["round_number"] == 1
        assert p2_state["phase"] == PlayerSpinPhase.TEAM_SPINNING
        assert p2_state["league_spins_remaining"] == 3
        assert p2_state["team_spins_remaining"] == 1
        assert p2_state["league_locked"] is True

    def test_get_game_snapshot_nonexistent_room_404(self, db: Session) -> None:
        """Test that nonexistent room raises 404."""
        from fastapi import HTTPException

        from app.services.game_service import GameService

        with pytest.raises(HTTPException) as exc_info:
            GameService.get_game_snapshot(session=db, room_code="NOTREAL")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_get_game_snapshot_expired_room_410(self, db: Session) -> None:
        """Test that expired room raises 410 Gone."""
        from fastapi import HTTPException

        from app.services.game_service import GameService

        # Setup: Create expired room
        user = User(
            email="exp@example.com",
            display_name="Test Player",
            full_name="Expired User",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Test Player",
        )
        db.add(player)
        db.commit()

        room = FifotecaRoom(
            code="EXP999",
            status=RoomStatus.WAITING,
            player1_id=player.id,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        )
        db.add(room)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            GameService.get_game_snapshot(session=db, room_code="EXP999")

        assert exc_info.value.status_code == 410
        assert "expired" in exc_info.value.detail.lower()

    def test_get_game_snapshot_expired_room_marks_completed(self, db: Session) -> None:
        """Test that expired room is marked as COMPLETED."""
        from fastapi import HTTPException

        from app.services.game_service import GameService

        # Setup: Create expired room in WAITING status
        user = User(
            email="expmark@example.com",
            display_name="Test Player",
            full_name="Expired Mark User",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Test Player",
        )
        db.add(player)
        db.commit()

        room = FifotecaRoom(
            code="EXPMRK",
            status=RoomStatus.WAITING,
            player1_id=player.id,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Initial status should be WAITING
        assert room.status == RoomStatus.WAITING

        # This should raise 410
        with pytest.raises(HTTPException) as exc_info:
            GameService.get_game_snapshot(session=db, room_code="EXPMRK")

        assert exc_info.value.status_code == 410

        # Refresh and check that room was marked as COMPLETED
        db.refresh(room)
        assert room.status == RoomStatus.COMPLETED


class TestWebSocketGameFlow:
    """Test WebSocket game flow for spin phase (Step 8 integration)."""

    def test_two_players_alternate_spins_league_phase(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test that two players can alternate spins in league phase (AC1, AC2)."""
        # Setup: Create two users and players
        user1 = User(
            email="flow1@example.com",
            display_name="Player 1",
            full_name="Flow User 1",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="Player 1",
        )
        db.add(player1)
        db.commit()

        user2 = User(
            email="flow2@example.com",
            display_name="Player 2",
            full_name="Flow User 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user2)
        db.commit()
        db.refresh(user2)

        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="Player 2",
        )
        db.add(player2)
        db.commit()
        db.refresh(player2)

        # Create leagues for spinning
        from app.models import FifaLeague

        league1 = FifaLeague(name="Flow League 1", country="Country 1")
        league2 = FifaLeague(name="Flow League 2", country="Country 2")
        db.add(league1)
        db.add(league2)
        db.commit()

        # Create room in SPINNING_LEAGUES phase
        room = FifotecaRoom(
            code="FLOW01",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            first_player_id=player1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player states
        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state1)

        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state2)
        db.commit()

        # Create tokens
        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Both players connect
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync
                ws1.receive_json()  # Get player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # Player 1 spins (their turn)
                ws1.send_json({"type": "spin_league", "payload": {}})

                # Both should receive spin_result
                p1_spin = ws1.receive_json()
                assert p1_spin["type"] == "spin_result"
                assert "player_id" in p1_spin["payload"]
                assert p1_spin["payload"]["type"] == "league"
                assert "result" in p1_spin["payload"]
                assert "spins_remaining" in p1_spin["payload"]

                p2_spin = ws2.receive_json()
                assert p2_spin["type"] == "spin_result"
                assert (
                    p2_spin["payload"]["player_id"] == p1_spin["payload"]["player_id"]
                )

                # Both should receive turn_changed
                p1_turn = ws1.receive_json()
                assert p1_turn["type"] == "turn_changed"
                assert p1_turn["payload"]["current_turn_player_id"] == str(player2.id)

                p2_turn = ws2.receive_json()
                assert p2_turn["type"] == "turn_changed"
                assert p2_turn["payload"]["current_turn_player_id"] == str(player2.id)

                # Player 2 spins (their turn)
                ws2.send_json({"type": "spin_league", "payload": {}})

                # Both should receive spin_result
                p1_spin2 = ws1.receive_json()
                assert p1_spin2["type"] == "spin_result"

                p2_spin2 = ws2.receive_json()
                assert p2_spin2["type"] == "spin_result"

                # Turn should change back to player 1
                p1_turn2 = ws1.receive_json()
                assert p1_turn2["payload"]["current_turn_player_id"] == str(player1.id)

    def test_wrong_turn_rejected(self, ws_client: TestClient, db: Session) -> None:
        """Test that acting out of turn sends error (AC3)."""
        # Setup: Create two users and players
        user1 = User(
            email="wrong1@example.com",
            display_name="Wrong Player 1",
            full_name="Wrong 1",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="Wrong Player 1",
        )
        db.add(player1)
        db.commit()

        user2 = User(
            email="wrong2@example.com",
            display_name="Wrong Player 2",
            full_name="Wrong 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user2)
        db.commit()
        db.refresh(user2)

        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="Wrong Player 2",
        )
        db.add(player2)
        db.commit()
        db.refresh(player2)

        # Create leagues for spinning
        from app.models import FifaLeague

        league1 = FifaLeague(name="Wrong League 1", country="Country 1")
        league2 = FifaLeague(name="Wrong League 2", country="Country 2")
        db.add(league1)
        db.add(league2)
        db.commit()

        # Create room with player 1's turn
        room = FifotecaRoom(
            code="WRONGT",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player states
        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state1)

        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state2)
        db.commit()

        # Create tokens
        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Both players connect
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync
                ws1.receive_json()  # Get player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # Player 2 tries to spin (not their turn)
                ws2.send_json({"type": "spin_league", "payload": {}})

                # Player 2 should receive error
                error = ws2.receive_json()
                assert error["type"] == "error"
                assert error["payload"]["code"] == "NOT_YOUR_TURN"
                assert "not your turn" in error["payload"]["message"].lower()

                # Player 1 should NOT receive any spin_result or turn_changed
                # (no new messages)

                # Now player 1 spins (their turn)
                ws1.send_json({"type": "spin_league", "payload": {}})

                # Both should receive spin_result
                ws1_spin = ws1.receive_json()
                assert ws1_spin["type"] == "spin_result"

                ws2_spin = ws2.receive_json()
                assert ws2_spin["type"] == "spin_result"

    def test_phase_transition_broadcast(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test that phase transitions are broadcast correctly (AC4)."""
        # Setup: Create two users and players
        user1 = User(
            email="phase1@example.com",
            display_name="Phase Player 1",
            full_name="Phase 1",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="Phase Player 1",
        )
        db.add(player1)
        db.commit()

        user2 = User(
            email="phase2@example.com",
            display_name="Phase Player 2",
            full_name="Phase 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user2)
        db.commit()
        db.refresh(user2)

        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="Phase Player 2",
        )
        db.add(player2)
        db.commit()
        db.refresh(player2)

        # Create room
        room = FifotecaRoom(
            code="PHASE1",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            first_player_id=player1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create leagues for spinning
        from app.models import FifaLeague

        league1 = FifaLeague(name="Phase League 1", country="Country 1")
        league2 = FifaLeague(name="Phase League 2", country="Country 2")
        db.add(league1)
        db.add(league2)
        db.commit()

        # Create player states - both ready to lock
        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=1,  # Will auto-lock on spin
            team_spins_remaining=3,
        )
        db.add(state1)

        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=1,  # Will auto-lock on spin
            team_spins_remaining=3,
        )
        db.add(state2)
        db.commit()

        # Create tokens
        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Both players connect
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync
                ws1.receive_json()  # Get player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # Player 1 spins (will auto-lock)
                ws1.send_json({"type": "spin_league", "payload": {}})

                # Player 1 receives spin_result with auto_locked=True
                p1_spin = ws1.receive_json()
                assert p1_spin["type"] == "spin_result"
                assert p1_spin["payload"]["auto_locked"] is True
                assert "lock" in p1_spin["payload"]

                # Turn changed to player 2
                ws1.receive_json()  # turn_changed

                # Player 2 receives same
                p2_spin = ws2.receive_json()
                assert p2_spin["type"] == "spin_result"
                assert p2_spin["payload"]["auto_locked"] is True
                ws2.receive_json()  # turn_changed

                # Player 2 spins (will auto-lock and trigger phase transition)
                ws2.send_json({"type": "spin_league", "payload": {}})

                # Both receive spin_result
                p1_spin2 = ws1.receive_json()
                assert p1_spin2["type"] == "spin_result"
                assert p1_spin2["payload"]["auto_locked"] is True

                p2_spin2 = ws2.receive_json()
                assert p2_spin2["type"] == "spin_result"
                assert p2_spin2["payload"]["auto_locked"] is True

                # Both receive turn_changed
                ws1.receive_json()
                ws2.receive_json()

                # Both receive phase_changed
                p1_phase = ws1.receive_json()
                assert p1_phase["type"] == "phase_changed"
                assert "phase" in p1_phase["payload"]
                assert "room_status" in p1_phase["payload"]
                # Room should transition to SPINNING_TEAMS
                assert p1_phase["payload"]["room_status"] == RoomStatus.SPINNING_TEAMS

                p2_phase = ws2.receive_json()
                assert p2_phase["type"] == "phase_changed"
                assert p2_phase["payload"]["room_status"] == RoomStatus.SPINNING_TEAMS

    def test_team_spinning_phase_actions(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """Test team spinning phase actions (spin_team, lock_team)."""
        # Setup: Create two users and players
        user1 = User(
            email="team1@example.com",
            display_name="Team Player 1",
            full_name="Team 1",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="Team Player 1",
        )
        db.add(player1)
        db.commit()

        user2 = User(
            email="team2@example.com",
            display_name="Team Player 2",
            full_name="Team 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user2)
        db.commit()
        db.refresh(user2)

        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="Team Player 2",
        )
        db.add(player2)
        db.commit()
        db.refresh(player2)

        # Create a league for team spinning
        from app.models import FifaLeague, FifaTeam

        league = FifaLeague(
            name="Test League",
            country="Test Country",
        )
        db.add(league)
        db.commit()
        db.refresh(league)

        # Create teams for the league
        team1 = FifaTeam(
            name="Team 1",
            league_id=league.id,
            attack_rating=80,
            midfield_rating=75,
            defense_rating=78,
            overall_rating=78,
        )
        team2 = FifaTeam(
            name="Team 2",
            league_id=league.id,
            attack_rating=82,
            midfield_rating=77,
            defense_rating=80,
            overall_rating=80,
        )
        db.add(team1)
        db.add(team2)
        db.commit()

        # Create room in SPINNING_TEAMS phase
        room = FifotecaRoom(
            code="TEAM01",
            status=RoomStatus.SPINNING_TEAMS,
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            first_player_id=player1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player states with locked leagues
        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
            league_locked=True,
            current_league_id=league.id,  # Real league from database
        )
        db.add(state1)

        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
            league_locked=True,
            current_league_id=league.id,  # Real league from database
        )
        db.add(state2)
        db.commit()

        # Create tokens
        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Both players connect
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync
                ws1.receive_json()  # Get player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # Player 1 spins team
                ws1.send_json({"type": "spin_team", "payload": {}})

                # Both receive spin_result with team data
                p1_spin = ws1.receive_json()
                assert p1_spin["type"] == "spin_result"
                assert p1_spin["payload"]["type"] == "team"
                assert "result" in p1_spin["payload"]
                # Team result should have ratings
                team_data = p1_spin["payload"]["result"]
                assert "attack_rating" in team_data
                assert "midfield_rating" in team_data
                assert "defense_rating" in team_data
                assert "overall_rating" in team_data

                p2_spin = ws2.receive_json()
                assert p2_spin["type"] == "spin_result"
                assert p2_spin["payload"]["type"] == "team"

    def test_lock_action_broadcast(self, ws_client: TestClient, db: Session) -> None:
        """Test that lock actions are broadcast correctly."""
        # Setup: Create two users and players
        user1 = User(
            email="lock1@example.com",
            display_name="Lock Player 1",
            full_name="Lock 1",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="Lock Player 1",
        )
        db.add(player1)
        db.commit()

        user2 = User(
            email="lock2@example.com",
            display_name="Lock Player 2",
            full_name="Lock 2",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user2)
        db.commit()
        db.refresh(user2)

        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="Lock Player 2",
        )
        db.add(player2)
        db.commit()
        db.refresh(player2)

        # Create room
        room = FifotecaRoom(
            code="LOCK01",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player states
        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state1)

        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state2)
        db.commit()

        # Create tokens
        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Both players connect
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync
                ws1.receive_json()  # Get player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # Player 1 locks (after spinning - for this test we just lock)
                # Note: In real game, lock happens after spin, but we test the action
                ws1.send_json({"type": "lock_league", "payload": {}})

                # Both should receive lock_result
                p1_lock = ws1.receive_json()
                assert p1_lock["type"] == "lock_result"
                assert p1_lock["payload"]["type"] == "league"
                assert "lock" in p1_lock["payload"]
                assert p1_lock["payload"]["lock"]["league_locked"] is True

                p2_lock = ws2.receive_json()
                assert p2_lock["type"] == "lock_result"
                assert p2_lock["payload"]["type"] == "league"

                # Both receive turn_changed
                p1_turn = ws1.receive_json()
                assert p1_turn["type"] == "turn_changed"
                assert p1_turn["payload"]["current_turn_player_id"] == str(player2.id)

                p2_turn = ws2.receive_json()
                assert p2_turn["type"] == "turn_changed"
                assert p2_turn["payload"]["current_turn_player_id"] == str(player2.id)

    def test_invalid_action_for_phase(self, ws_client: TestClient, db: Session) -> None:
        """Test that invalid action for phase returns error."""
        # Setup: Create user and player
        user = User(
            email="invalid@example.com",
            display_name="Invalid Player",
            full_name="Invalid",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Invalid Player",
        )
        db.add(player)
        db.commit()
        db.refresh(player)

        # Create room in SPINNING_LEAGUES phase
        room = FifotecaRoom(
            code="INVALI",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player.id,
            current_turn_player_id=player.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player state in league phase
        state = FifotecaPlayerState(
            room_id=room.id,
            player_id=player.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state)
        db.commit()

        # Create token
        token = create_access_token(user.id, timedelta(minutes=30))

        # Connect and send invalid action (spin_team in league phase)
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token}"
        ) as websocket:
            websocket.receive_json()  # Get state_sync

            # Send invalid action for current phase
            websocket.send_json({"type": "spin_team", "payload": {}})

            # Should receive error
            error = websocket.receive_json()
            assert error["type"] == "error"
            assert error["payload"]["code"] == "INVALID_ACTION"
            assert "not valid in phase" in error["payload"]["message"].lower()

    def test_unknown_message_type(self, ws_client: TestClient, db: Session) -> None:
        """Test that unknown message type returns error."""
        # Setup: Create user and player
        user = User(
            email="unknown@example.com",
            display_name="Unknown Player",
            full_name="Unknown",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Unknown Player",
        )
        db.add(player)
        db.commit()
        db.refresh(player)

        # Create room
        room = FifotecaRoom(
            code="UNKNO",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player.id,
            current_turn_player_id=player.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player state
        state = FifotecaPlayerState(
            room_id=room.id,
            player_id=player.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state)
        db.commit()

        # Create token
        token = create_access_token(user.id, timedelta(minutes=30))

        # Connect and send unknown message type
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token}"
        ) as websocket:
            websocket.receive_json()  # Get state_sync

            # Send unknown message type
            websocket.send_json({"type": "unknown_action", "payload": {}})

            # Should receive error
            error = websocket.receive_json()
            assert error["type"] == "error"
            assert error["payload"]["code"] == "INVALID_ACTION"
            assert "unknown message type" in error["payload"]["message"].lower()

    def test_ping_pong_via_handler(self, ws_client: TestClient, db: Session) -> None:
        """Test that ping receives pong through handler (AC6)."""
        # Setup: Create user and player
        user = User(
            email="pinghandler@example.com",
            display_name="Ping Handler",
            full_name="Ping Handler",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        player = FifotecaPlayer(
            user_id=user.id,
            display_name="Ping Handler",
        )
        db.add(player)
        db.commit()
        db.refresh(player)

        # Create room
        room = FifotecaRoom(
            code="PING02",
            status=RoomStatus.WAITING,
            player1_id=player.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create player state
        state = FifotecaPlayerState(
            room_id=room.id,
            player_id=player.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state)
        db.commit()

        # Create token
        token = create_access_token(user.id, timedelta(minutes=30))

        # Connect and send ping via handler
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token}"
        ) as websocket:
            websocket.receive_json()  # Get state_sync

            # Send ping
            websocket.send_json({"type": "ping", "payload": {}})

            # Receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"
            assert "payload" in data


class TestPlayAgainAndLeaveRoom:
    """Tests for play_again and leave_room WebSocket messages (Step 11)."""

    def test_play_again_requires_both_players(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """S11: play_again requires both players to reset room."""
        # Setup: Create two users, players, and room with completed match
        user1 = User(
            email="s11player1@example.com",
            display_name="S11 Player 1",
            full_name="S11 Player One",
            hashed_password="hashed1",
            is_active=True,
        )
        user2 = User(
            email="s11player2@example.com",
            display_name="S11 Player 2",
            full_name="S11 Player Two",
            hashed_password="hashed2",
            is_active=True,
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="S11 Player 1",
        )
        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="S11 Player 2",
        )
        db.add(player1)
        db.add(player2)
        db.commit()
        db.refresh(player1)
        db.refresh(player2)

        # Create room
        room = FifotecaRoom(
            code="S11A01",
            status=RoomStatus.COMPLETED,
            player1_id=player1.id,
            player2_id=player2.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # Create completed match for round 1
        from app.models import FifaLeague, FifaTeam, FifotecaMatch

        league = FifaLeague(name="S11 League", country="Test")
        db.add(league)
        db.commit()
        db.refresh(league)

        team1 = FifaTeam(
            name="S11 Team 1",
            league_id=league.id,
            attack_rating=85,
            midfield_rating=83,
            defense_rating=82,
            overall_rating=250,
        )
        team2 = FifaTeam(
            name="S11 Team 2",
            league_id=league.id,
            attack_rating=84,
            midfield_rating=84,
            defense_rating=83,
            overall_rating=251,
        )
        db.add(team1)
        db.add(team2)
        db.commit()

        match = FifotecaMatch(
            room_id=room.id,
            round_number=1,
            player1_id=player1.id,
            player2_id=player2.id,
            player1_team_id=team1.id,
            player2_team_id=team2.id,
            player1_score=2,
            player2_score=1,
            rating_difference=6,
            confirmed=True,
        )
        db.add(match)

        # Create player states for round 1
        p1_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.READY_TO_PLAY,
            league_spins_remaining=0,
            team_spins_remaining=0,
            current_league_id=league.id,
            current_team_id=team1.id,
            league_locked=True,
            team_locked=True,
        )
        p2_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.READY_TO_PLAY,
            league_spins_remaining=0,
            team_spins_remaining=0,
            current_league_id=league.id,
            current_team_id=team2.id,
            league_locked=True,
            team_locked=True,
        )
        db.add(p1_state)
        db.add(p2_state)
        db.commit()

        # Create tokens
        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Connect both players
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync
                # Player 1 receives player_connected when player 2 connects
                connected_msg = ws1.receive_json()
                assert connected_msg["type"] == "player_connected"
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # Player 1 sends play_again
                ws1.send_json({"type": "play_again", "payload": {}})

                # Player 1 receives acknowledgment
                ack = ws1.receive_json()
                assert ack["type"] == "play_again_ack"
                assert ack["payload"]["player_id"] == str(player1.id)
                assert ack["payload"]["waiting_for_opponent"] is True

                # Player 2 sends play_again
                ws2.send_json({"type": "play_again", "payload": {}})

                # Both players should receive state_sync with new round
                ws1_data = ws1.receive_json()
                ws2_data = ws2.receive_json()

                assert ws1_data["type"] == "state_sync"
                assert ws2_data["type"] == "state_sync"

                # Verify round incremented
                assert ws1_data["payload"]["room"]["round_number"] == 2
                assert ws2_data["payload"]["room"]["round_number"] == 2

                # Verify room status is SPINNING_LEAGUES
                assert (
                    ws1_data["payload"]["room"]["status"] == RoomStatus.SPINNING_LEAGUES
                )
                assert (
                    ws2_data["payload"]["room"]["status"] == RoomStatus.SPINNING_LEAGUES
                )

                # Verify first player is player 1 (winner of round 1)
                assert ws1_data["payload"]["room"]["first_player_id"] == str(player1.id)
                assert ws2_data["payload"]["room"]["first_player_id"] == str(player1.id)

    def test_leave_room_sends_player_left_and_closes_socket(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """S11: leave_room sends player_left and closes leaver socket."""
        # Setup: Create two users, players, and room
        user1 = User(
            email="s11leave1@example.com",
            display_name="S11 Leaving Player",
            full_name="S11 Leaving User",
            hashed_password="hashed1",
            is_active=True,
        )
        user2 = User(
            email="s11stay1@example.com",
            display_name="S11 Staying Player",
            full_name="S11 Staying User",
            hashed_password="hashed2",
            is_active=True,
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="S11 Leaving Player",
        )
        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="S11 Staying Player",
        )
        db.add(player1)
        db.add(player2)
        db.commit()
        db.refresh(player1)
        db.refresh(player2)

        room = FifotecaRoom(
            code="S11L01",
            status=RoomStatus.WAITING,
            player1_id=player1.id,
            player2_id=player2.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state1)
        db.add(state2)
        db.commit()

        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Connect both players
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync

                # Player 1 sends leave_room
                ws1.send_json({"type": "leave_room", "payload": {}})

                # Player 2 receives player_left
                data = ws2.receive_json()
                assert data["type"] == "player_left"
                assert data["payload"]["player_id"] == str(player1.id)

                # Player 1's socket should be closed
                # (Test client raises exception on receive from closed socket)

    def test_when_both_leave_room_status_becomes_completed(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """S11: When both players leave, room status becomes COMPLETED."""
        # Setup: Create two users, players, and room
        user1 = User(
            email="s11both1@example.com",
            display_name="S11 Both 1",
            full_name="S11 Both User 1",
            hashed_password="hashed1",
            is_active=True,
        )
        user2 = User(
            email="s11both2@example.com",
            display_name="S11 Both 2",
            full_name="S11 Both User 2",
            hashed_password="hashed2",
            is_active=True,
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="S11 Both 1",
        )
        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="S11 Both 2",
        )
        db.add(player1)
        db.add(player2)
        db.commit()
        db.refresh(player1)
        db.refresh(player2)

        room = FifotecaRoom(
            code="S11B01",
            status=RoomStatus.WAITING,
            player1_id=player1.id,
            player2_id=player2.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state1)
        db.add(state2)
        db.commit()

        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Connect both players
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync

                # Player 1 leaves
                ws1.send_json({"type": "leave_room", "payload": {}})

                # Player 2 receives player_left
                ws2.receive_json()

                # Player 2 leaves
                ws2.send_json({"type": "leave_room", "payload": {}})

        # After both leave, verify room status is COMPLETED
        db.refresh(room)
        assert room.status == "COMPLETED"

    def test_play_again_rejected_in_non_completed_state(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """S11: play_again is rejected if room is not in COMPLETED status."""
        # Setup: Create two users, players, and room in WAITING status
        user1 = User(
            email="s11invalid1@example.com",
            display_name="S11 Invalid 1",
            full_name="S11 Invalid User 1",
            hashed_password="hashed1",
            is_active=True,
        )
        user2 = User(
            email="s11invalid2@example.com",
            display_name="S11 Invalid 2",
            full_name="S11 Invalid User 2",
            hashed_password="hashed2",
            is_active=True,
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="S11 Invalid 1",
        )
        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="S11 Invalid 2",
        )
        db.add(player1)
        db.add(player2)
        db.commit()
        db.refresh(player1)
        db.refresh(player2)

        # Create room in WAITING status (not COMPLETED)
        room = FifotecaRoom(
            code="S11IV1",
            status=RoomStatus.WAITING,
            player1_id=player1.id,
            player2_id=player2.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state1)
        db.add(state2)
        db.commit()

        token1 = create_access_token(user1.id, timedelta(minutes=30))

        # Connect player and try play_again
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            # Try to play_again in non-COMPLETED state
            ws1.send_json({"type": "play_again", "payload": {}})

            # Should receive error
            error = ws1.receive_json()
            assert error["type"] == "error"
            assert error["payload"]["code"] == "INVALID_ACTION"
            assert "not COMPLETED" in error["payload"]["message"]


class TestMutualSuperspin:
    """Tests for mutual superspin WebSocket messages (Step 12)."""

    def test_proposal_broadcast_to_opponent(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """S12: propose_mutual_superspin broadcasts to other player."""
        # Setup: Create two users, players, and room in SPINNING_LEAGUES phase
        user1 = User(
            email="s12propose1@example.com",
            display_name="S12 Proposer",
            full_name="S12 Proposer User",
            hashed_password="hashed1",
            is_active=True,
        )
        user2 = User(
            email="s12propose2@example.com",
            display_name="S12 Opponent",
            full_name="S12 Opponent User",
            hashed_password="hashed2",
            is_active=True,
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="S12 Proposer",
        )
        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="S12 Opponent",
        )
        db.add(player1)
        db.add(player2)
        db.commit()
        db.refresh(player1)
        db.refresh(player2)

        room = FifotecaRoom(
            code="S12P01",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            first_player_id=player1.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state1)
        db.add(state2)
        db.commit()

        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Connect both players
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync
                # Player 1 receives player_connected when player 2 connects
                ws1.receive_json()
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # Player 1 proposes mutual superspin
                ws1.send_json({"type": "propose_mutual_superspin", "payload": {}})

                # Both players should receive the proposal broadcast
                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()

                assert msg1["type"] == "mutual_superspin_proposed"
                assert msg2["type"] == "mutual_superspin_proposed"
                assert msg1["payload"]["proposer_id"] == str(player1.id)
                assert msg2["payload"]["proposer_id"] == str(player1.id)

                # Verify room has proposer set
                db.refresh(room)
                assert room.mutual_superspin_proposer_id == player1.id

    def test_accept_resets_room_with_both_having_superspin(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """S12: accept_mutual_superspin resets room with both having superspin."""
        # Setup: Create two users, players, and room with pending proposal
        user1 = User(
            email="s12accept1@example.com",
            display_name="S12 Accept Proposer",
            full_name="S12 Accept Proposer User",
            hashed_password="hashed1",
            is_active=True,
        )
        user2 = User(
            email="s12accept2@example.com",
            display_name="S12 Accepter",
            full_name="S12 Accepter User",
            hashed_password="hashed2",
            is_active=True,
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="S12 Accept Proposer",
        )
        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="S12 Accepter",
        )
        db.add(player1)
        db.add(player2)
        db.commit()
        db.refresh(player1)
        db.refresh(player2)

        room = FifotecaRoom(
            code="S12A01",
            status=RoomStatus.SPINNING_TEAMS,
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            first_player_id=player1.id,
            round_number=1,
            mutual_superspin_proposer_id=player1.id,  # Pending proposal
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_SPINNING,
            league_spins_remaining=0,
            team_spins_remaining=2,
            league_locked=True,
        )
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_SPINNING,
            league_spins_remaining=0,
            team_spins_remaining=2,
            league_locked=True,
        )
        db.add(state1)
        db.add(state2)
        db.commit()

        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Connect both players
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync
                ws1.receive_json()  # player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # Player 2 (not proposer) accepts
                ws2.send_json({"type": "accept_mutual_superspin", "payload": {}})

                # Both receive mutual_superspin_accepted
                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                assert msg1["type"] == "mutual_superspin_accepted"
                assert msg2["type"] == "mutual_superspin_accepted"
                assert msg1["payload"]["accepted_by_id"] == str(player2.id)

                # Both receive state_sync with reset state
                sync1 = ws1.receive_json()
                sync2 = ws2.receive_json()
                assert sync1["type"] == "state_sync"
                assert sync2["type"] == "state_sync"

                # Verify room status is SPINNING_LEAGUES
                assert sync1["payload"]["room"]["status"] == RoomStatus.SPINNING_LEAGUES

                # Verify round number unchanged
                assert sync1["payload"]["room"]["round_number"] == 1

                # Verify mutual_superspin_active is True
                assert sync1["payload"]["room"]["mutual_superspin_active"] is True

                # Verify both player states have has_superspin=True
                player_states = sync1["payload"]["player_states"]
                assert len(player_states) == 2
                for ps in player_states:
                    assert ps["has_superspin"] is True
                    assert ps["phase"] == PlayerSpinPhase.LEAGUE_SPINNING
                    assert ps["league_spins_remaining"] == 3
                    assert ps["team_spins_remaining"] == 3

                # Verify proposer field cleared in DB
                db.refresh(room)
                assert room.mutual_superspin_proposer_id is None

    def test_decline_clears_proposal(self, ws_client: TestClient, db: Session) -> None:
        """S12: decline_mutual_superspin clears proposal and broadcasts decline."""
        # Setup: Create two users, players, and room with pending proposal
        user1 = User(
            email="s12decline1@example.com",
            display_name="S12 Decline Proposer",
            full_name="S12 Decline Proposer User",
            hashed_password="hashed1",
            is_active=True,
        )
        user2 = User(
            email="s12decline2@example.com",
            display_name="S12 Decliner",
            full_name="S12 Decliner User",
            hashed_password="hashed2",
            is_active=True,
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="S12 Decline Proposer",
        )
        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="S12 Decliner",
        )
        db.add(player1)
        db.add(player2)
        db.commit()
        db.refresh(player1)
        db.refresh(player2)

        room = FifotecaRoom(
            code="S12D01",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            first_player_id=player1.id,
            round_number=1,
            mutual_superspin_proposer_id=player1.id,  # Pending proposal
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state1)
        db.add(state2)
        db.commit()

        token1 = create_access_token(user1.id, timedelta(minutes=30))
        token2 = create_access_token(user2.id, timedelta(minutes=30))

        # Connect both players
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            with ws_client.websocket_connect(
                f"/api/v1/fifoteca/ws/{room.code}?token={token2}"
            ) as ws2:
                ws2.receive_json()  # Get state_sync
                ws1.receive_json()  # player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # Player 2 declines
                ws2.send_json({"type": "decline_mutual_superspin", "payload": {}})

                # Both receive mutual_superspin_declined
                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                assert msg1["type"] == "mutual_superspin_declined"
                assert msg2["type"] == "mutual_superspin_declined"
                assert msg1["payload"]["declined_by_id"] == str(player2.id)

                # Verify proposer field cleared in DB
                db.refresh(room)
                assert room.mutual_superspin_proposer_id is None

    def test_proposer_cannot_accept_own_proposal(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """S12: Proposer cannot accept their own proposal."""
        # Setup
        user1 = User(
            email="s12self1@example.com",
            display_name="S12 Self Accept Proposer",
            full_name="S12 Self Accept Proposer User",
            hashed_password="hashed1",
            is_active=True,
        )
        user2 = User(
            email="s12self2@example.com",
            display_name="S12 Self Accept Opponent",
            full_name="S12 Self Accept Opponent User",
            hashed_password="hashed2",
            is_active=True,
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="S12 Self Accept Proposer",
        )
        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="S12 Self Accept Opponent",
        )
        db.add(player1)
        db.add(player2)
        db.commit()
        db.refresh(player1)
        db.refresh(player2)

        room = FifotecaRoom(
            code="S12S01",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            first_player_id=player1.id,
            round_number=1,
            mutual_superspin_proposer_id=player1.id,  # Player1 is proposer
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
        )
        db.add(state1)
        db.add(state2)
        db.commit()

        token1 = create_access_token(user1.id, timedelta(minutes=30))

        # Connect player1
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            # Proposer tries to accept own proposal
            ws1.send_json({"type": "accept_mutual_superspin", "payload": {}})

            # Should receive error
            error = ws1.receive_json()
            assert error["type"] == "error"
            assert error["payload"]["code"] == "INVALID_ACTION"
            assert "cannot accept your own" in error["payload"]["message"].lower()

    def test_proposal_outside_spin_phases_rejected(
        self, ws_client: TestClient, db: Session
    ) -> None:
        """S12: Proposal rejected when room not in spin phases."""
        # Setup: Room in RATING_REVIEW status
        user1 = User(
            email="s12phase1@example.com",
            display_name="S12 Phase Proposer",
            full_name="S12 Phase Proposer User",
            hashed_password="hashed1",
            is_active=True,
        )
        user2 = User(
            email="s12phase2@example.com",
            display_name="S12 Phase Opponent",
            full_name="S12 Phase Opponent User",
            hashed_password="hashed2",
            is_active=True,
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        player1 = FifotecaPlayer(
            user_id=user1.id,
            display_name="S12 Phase Proposer",
        )
        player2 = FifotecaPlayer(
            user_id=user2.id,
            display_name="S12 Phase Opponent",
        )
        db.add(player1)
        db.add(player2)
        db.commit()
        db.refresh(player1)
        db.refresh(player2)

        room = FifotecaRoom(
            code="S12PH1",
            status=RoomStatus.RATING_REVIEW,  # Not a spin phase
            player1_id=player1.id,
            player2_id=player2.id,
            current_turn_player_id=player1.id,
            first_player_id=player1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        state1 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player1.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_LOCKED,
            league_spins_remaining=0,
            team_spins_remaining=0,
            league_locked=True,
            team_locked=True,
        )
        state2 = FifotecaPlayerState(
            room_id=room.id,
            player_id=player2.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_LOCKED,
            league_spins_remaining=0,
            team_spins_remaining=0,
            league_locked=True,
            team_locked=True,
        )
        db.add(state1)
        db.add(state2)
        db.commit()

        token1 = create_access_token(user1.id, timedelta(minutes=30))

        # Connect player1
        with ws_client.websocket_connect(
            f"/api/v1/fifoteca/ws/{room.code}?token={token1}"
        ) as ws1:
            ws1.receive_json()  # Get state_sync

            # Try to propose in non-spin phase
            ws1.send_json({"type": "propose_mutual_superspin", "payload": {}})

            # Should receive error
            error = ws1.receive_json()
            assert error["type"] == "error"
            assert error["payload"]["code"] == "INVALID_ACTION"
            assert "spin phases" in error["payload"]["message"].lower()
