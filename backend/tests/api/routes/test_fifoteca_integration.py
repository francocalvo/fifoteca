"""Step 21 Backend Integration Tests for Fifoteca.

These tests provide comprehensive end-to-end coverage of:
1. Full game flow: create room -> join -> spin/lock -> rating review -> ready -> match
2. Room lifecycle: create -> join -> play -> play_again -> leave
3. Edge cases: wrong turn, self-join, reconnect, expired room, special spin

Tests use real REST endpoints and WebSocket connections against the test DB.
Each test is idempotent with unique emails/codes generated per test.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.security import create_access_token
from app.models import (
    FifaLeague,
    FifaTeam,
    FifotecaMatch,
    FifotecaPlayer,
    FifotecaPlayerState,
    FifotecaRoom,
    PlayerSpinPhase,
    RoomStatus,
    User,
)

# =============================================================================
# Helper Functions
# =============================================================================


def _uid() -> str:
    """Generate a short unique ID for test isolation."""
    return str(uuid.uuid4())[:8]


def create_test_user(
    db: Session, email: str, display_name: str
) -> tuple[User, FifotecaPlayer]:
    """Create a test user with FifotecaPlayer profile."""
    user = User(
        email=email,
        display_name=display_name,
        full_name=display_name,
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    player = FifotecaPlayer(
        user_id=user.id,
        display_name=display_name,
    )
    db.add(player)
    db.commit()
    db.refresh(player)

    return user, player


def create_league_with_teams(
    db: Session,
    name: str,
    team_count: int = 3,
    base_rating: int = 80,
    rating_step: int = 1,
) -> tuple[FifaLeague, list[FifaTeam]]:
    """Create a league with multiple teams for spinning."""
    league = FifaLeague(name=name, country="Test Country")
    db.add(league)
    db.commit()
    db.refresh(league)

    teams = []
    for i in range(team_count):
        r = base_rating + i * rating_step
        team = FifaTeam(
            name=f"{name} Team {i + 1}",
            league_id=league.id,
            attack_rating=r,
            midfield_rating=r,
            defense_rating=r,
            overall_rating=r * 3,
        )
        db.add(team)
        teams.append(team)

    db.commit()
    for team in teams:
        db.refresh(team)

    return league, teams


def make_token(user: User) -> str:
    """Create a JWT token for a user."""
    return create_access_token(user.id, timedelta(minutes=30))


def ws_url(room_code: str, token: str) -> str:
    """Build WebSocket connection URL."""
    return f"/api/v1/fifoteca/ws/{room_code}?token={token}"


def collect_messages(ws, count: int) -> list[dict]:
    """Collect a specific number of messages from a WebSocket."""
    return [ws.receive_json() for _ in range(count)]


def find_message(messages: list[dict], msg_type: str) -> dict | None:
    """Find first message of a given type in a list."""
    return next((m for m in messages if m["type"] == msg_type), None)


def setup_two_players_and_league(
    db: Session,
    prefix: str,
    team_count: int = 3,
    base_rating: int = 80,
    rating_step: int = 1,
) -> tuple[User, FifotecaPlayer, User, FifotecaPlayer, FifaLeague, list[FifaTeam]]:
    """Create two players and a league with teams."""
    tid = _uid()
    u1, p1 = create_test_user(db, f"{prefix}_p1_{tid}@test.com", f"{prefix}_P1")
    u2, p2 = create_test_user(db, f"{prefix}_p2_{tid}@test.com", f"{prefix}_P2")
    league, teams = create_league_with_teams(
        db,
        f"{prefix}_League_{tid}",
        team_count=team_count,
        base_rating=base_rating,
        rating_step=rating_step,
    )
    return u1, p1, u2, p2, league, teams


def setup_room_in_spinning(
    db: Session,
    p1: FifotecaPlayer,
    p2: FifotecaPlayer,
) -> FifotecaRoom:
    """Create a room in SPINNING_LEAGUES with both players and initial states."""
    room = FifotecaRoom(
        code=f"R{_uid()[:5]}",
        status=RoomStatus.SPINNING_LEAGUES,
        player1_id=p1.id,
        player2_id=p2.id,
        current_turn_player_id=p1.id,
        first_player_id=p1.id,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.commit()
    db.refresh(room)

    for player in (p1, p2):
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

    return room


def do_spin_turn(
    acting_ws, other_ws, action: str = "spin_league"
) -> tuple[list[dict], list[dict]]:
    """Execute one spin turn and collect all resulting messages from both WSes.

    After a spin action, the server sends:
    - spin_result (broadcast)
    - turn_changed (broadcast)
    - Possibly: rating_review (broadcast), phase_changed (broadcast)

    Returns (acting_msgs, other_msgs) with 2-4 messages each.
    """
    acting_ws.send_json({"type": action, "payload": {}})

    # Collect 2 messages minimum from each (spin_result + turn_changed)
    acting_msgs = collect_messages(acting_ws, 2)
    other_msgs = collect_messages(other_ws, 2)

    # If a phase transition or rating review happened, there are more messages.
    # Check if the last message indicates more to come.
    # phase_changed and rating_review are only sent if phase_transitioned is True.
    # We check by looking at the turn_changed message - not reliable.
    # Instead, we rely on the specific test to handle extra messages.
    return acting_msgs, other_msgs


# =============================================================================
# AC1: Full Game Flow Integration Test
# =============================================================================


class TestFullGameFlow:
    """Test the complete game flow through WebSocket actions.

    Covers: spin leagues -> lock -> spin teams -> lock -> rating review ->
    ready_to_play -> match creation -> score -> confirm.
    """

    def test_full_flow_spin_to_match(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC1: Complete game flow from spinning to match creation."""
        u1, p1, u2, p2, league, teams = setup_two_players_and_league(
            db, "fullflow", team_count=4, base_rating=80
        )
        room = setup_room_in_spinning(db, p1, p2)

        t1 = make_token(u1)
        t2 = make_token(u2)

        with client.websocket_connect(ws_url(room.code, t1)) as ws1:
            ws1.receive_json()  # state_sync

            with client.websocket_connect(ws_url(room.code, t2)) as ws2:
                ws2.receive_json()  # state_sync
                ws1.receive_json()  # player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # --- LEAGUE PHASE ---
                # Alternate spins: P1->P2->P1->P2->P1->P2
                # After 3 spins each, leagues auto-lock and room transitions
                for spin_num in range(6):
                    acting = ws1 if spin_num % 2 == 0 else ws2
                    acting.send_json({"type": "spin_league", "payload": {}})

                    r1 = ws1.receive_json()
                    assert r1["type"] == "spin_result", (
                        f"spin {spin_num}: expected spin_result, got {r1['type']}"
                    )
                    r2 = ws2.receive_json()
                    assert r2["type"] == "spin_result"

                    # turn_changed is always sent
                    ws1.receive_json()
                    ws2.receive_json()

                    # On 6th spin (index 5), phase_changed follows turn_changed
                    if spin_num == 5:
                        pc1 = ws1.receive_json()
                        pc2 = ws2.receive_json()
                        assert pc1["type"] == "phase_changed"
                        assert pc2["type"] == "phase_changed"

                db.refresh(room)
                assert room.status == RoomStatus.SPINNING_TEAMS

                # --- TEAM PHASE ---
                # Determine who goes first in team phase
                db.refresh(room)
                if room.current_turn_player_id == p1.id:
                    ws_first, ws_second = ws1, ws2
                else:
                    ws_first, ws_second = ws2, ws1

                for spin_num in range(6):
                    acting = ws_first if spin_num % 2 == 0 else ws_second
                    acting.send_json({"type": "spin_team", "payload": {}})

                    r1 = ws1.receive_json()
                    assert r1["type"] == "spin_result"
                    r2 = ws2.receive_json()
                    assert r2["type"] == "spin_result"

                    if spin_num < 5:
                        # Normal spin: turn_changed only
                        ws1.receive_json()  # turn_changed
                        ws2.receive_json()  # turn_changed
                    else:
                        # 6th spin: auto-lock + phase transition to RATING_REVIEW
                        # Messages: rating_review, turn_changed, phase_changed
                        last1 = collect_messages(ws1, 3)
                        types1 = {m["type"] for m in last1}
                        collect_messages(ws2, 3)  # drain ws2 too
                        assert "phase_changed" in types1
                        assert "rating_review" in types1

                db.refresh(room)
                assert room.status == RoomStatus.RATING_REVIEW

                # --- READY TO PLAY ---
                # Determine who goes first based on current turn
                db.expire_all()
                fresh = db.exec(
                    select(FifotecaRoom).where(FifotecaRoom.code == room.code)
                ).first()
                assert fresh is not None
                if fresh.current_turn_player_id == p1.id:
                    ws_first_r, ws_second_r = ws1, ws2
                elif fresh.current_turn_player_id == p2.id:
                    ws_first_r, ws_second_r = ws2, ws1
                else:
                    # No turn set (shouldn't happen in normal flow)
                    ws_first_r, ws_second_r = ws1, ws2

                # First player readies -> turn_changed broadcast (1 msg each)
                ws_first_r.send_json({"type": "ready_to_play", "payload": {}})
                ws1.receive_json()  # turn_changed
                ws2.receive_json()  # turn_changed

                # Second player readies -> turn_changed + phase_changed (2 msgs each)
                ws_second_r.send_json({"type": "ready_to_play", "payload": {}})
                msgs1 = collect_messages(ws1, 2)

                phase_msg = find_message(msgs1, "phase_changed")
                assert phase_msg is not None
                assert phase_msg["payload"]["room_status"] == RoomStatus.MATCH_IN_PROGRESS
                assert "match_id" in phase_msg["payload"]

                db.expire_all()
                db.refresh(room)
                assert room.status == RoomStatus.MATCH_IN_PROGRESS

    def test_score_submission_and_confirmation(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC1: Score submission and confirmation via REST endpoints."""
        u1, p1, u2, p2, league, teams = setup_two_players_and_league(
            db, "scoreflow", team_count=4, base_rating=80
        )

        # Pre-set room in MATCH_IN_PROGRESS
        room = FifotecaRoom(
            code=f"SC{_uid()[:4]}",
            status=RoomStatus.MATCH_IN_PROGRESS,
            player1_id=p1.id,
            player2_id=p2.id,
            current_turn_player_id=None,
            first_player_id=p1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        match = FifotecaMatch(
            room_id=room.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            player1_team_id=teams[0].id,
            player2_team_id=teams[1].id,
            rating_difference=abs(teams[0].overall_rating - teams[1].overall_rating),
        )
        db.add(match)
        db.commit()
        db.refresh(match)

        t1 = make_token(u1)
        t2 = make_token(u2)

        # P1 submits score
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/score",
            headers={"Authorization": f"Bearer {t1}"},
            json={"player1_score": 3, "player2_score": 1},
        )
        assert response.status_code == 200
        assert response.json()["player1_score"] == 3

        db.refresh(room)
        assert room.status == RoomStatus.SCORE_SUBMITTED

        # P2 confirms
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/confirm",
            headers={"Authorization": f"Bearer {t2}"},
        )
        assert response.status_code == 200
        assert response.json()["confirmed"] is True

        db.refresh(room)
        assert room.status == RoomStatus.COMPLETED

        # Verify player stats updated
        db.refresh(p1)
        db.refresh(p2)
        assert p1.total_wins == 1
        assert p2.total_losses == 1


# =============================================================================
# AC2: Room Lifecycle with Play Again Test
# =============================================================================


class TestRoomLifecycle:
    """Test room lifecycle: play_again flow and player leave."""

    def test_play_again_and_leave_flow(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC2: play_again + leave flow in a completed room."""
        tid = _uid()
        u1, p1 = create_test_user(db, f"lc1_{tid}@test.com", "LC P1")
        u2, p2 = create_test_user(db, f"lc2_{tid}@test.com", "LC P2")
        league, teams = create_league_with_teams(db, f"LC_L_{tid}", 3, 80)

        room = FifotecaRoom(
            code=f"LC{tid[:4]}",
            status=RoomStatus.COMPLETED,
            player1_id=p1.id,
            player2_id=p2.id,
            current_turn_player_id=p1.id,
            first_player_id=p1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        for player in (p1, p2):
            db.add(
                FifotecaPlayerState(
                    room_id=room.id,
                    player_id=player.id,
                    round_number=1,
                    phase=PlayerSpinPhase.READY_TO_PLAY,
                    league_spins_remaining=0,
                    team_spins_remaining=0,
                    league_locked=True,
                    team_locked=True,
                )
            )
        db.commit()

        db.add(
            FifotecaMatch(
                room_id=room.id,
                player1_id=p1.id,
                player2_id=p2.id,
                player1_team_id=teams[0].id,
                player2_team_id=teams[1].id,
                round_number=1,
                player1_score=2,
                player2_score=1,
                rating_difference=0,
                confirmed=True,
            )
        )
        db.commit()

        t1 = make_token(u1)
        t2 = make_token(u2)

        with client.websocket_connect(ws_url(room.code, t1)) as ws1:
            ws1.receive_json()  # state_sync

            with client.websocket_connect(ws_url(room.code, t2)) as ws2:
                ws2.receive_json()  # state_sync
                ws1.receive_json()  # player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # P1 initiates play_again
                ws1.send_json({"type": "play_again", "payload": {}})
                ack = ws1.receive_json()
                assert ack["type"] == "play_again_ack"
                assert ack["payload"]["waiting_for_opponent"] is True

                # P2 accepts
                ws2.send_json({"type": "play_again", "payload": {}})

                # Both receive state_sync with round 2
                sync1 = ws1.receive_json()
                sync2 = ws2.receive_json()
                assert sync1["type"] == "state_sync"
                assert sync2["type"] == "state_sync"
                assert sync1["payload"]["room"]["round_number"] == 2
                assert sync1["payload"]["room"]["status"] == RoomStatus.SPINNING_LEAGUES

                # P1 leaves
                ws1.send_json({"type": "leave_room", "payload": {}})
                left_msg = ws2.receive_json()
                assert left_msg["type"] == "player_left"
                assert left_msg["payload"]["player_id"] == str(p1.id)

                # P2 leaves
                ws2.send_json({"type": "leave_room", "payload": {}})

        db.refresh(room)
        assert room.status == RoomStatus.COMPLETED


# =============================================================================
# AC3: Turn Enforcement
# =============================================================================


class TestTurnEnforcement:
    """Test that wrong-turn actions are rejected and state is unchanged."""

    def test_wrong_turn_action_rejected(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC3: Wrong-turn action rejected, game state unchanged."""
        u1, p1, u2, p2, league, teams = setup_two_players_and_league(
            db, "turntest", team_count=3
        )
        room = setup_room_in_spinning(db, p1, p2)

        t1 = make_token(u1)
        t2 = make_token(u2)

        with client.websocket_connect(ws_url(room.code, t1)) as ws1:
            ws1.receive_json()  # state_sync

            with client.websocket_connect(ws_url(room.code, t2)) as ws2:
                ws2.receive_json()  # state_sync
                ws1.receive_json()  # player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # It's P1's turn. P2 tries to spin.
                ws2.send_json({"type": "spin_league", "payload": {}})
                error = ws2.receive_json()
                assert error["type"] == "error"
                assert error["payload"]["code"] == "NOT_YOUR_TURN"

                # Verify room state unchanged
                db.refresh(room)
                assert room.status == RoomStatus.SPINNING_LEAGUES
                assert room.current_turn_player_id == p1.id


# =============================================================================
# AC4: Reconnection State Restore
# =============================================================================


class TestReconnection:
    """Test reconnection state restore."""

    def test_reconnect_mid_game_restores_full_state_sync(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC4: Player reconnects and receives full state_sync."""
        tid = _uid()
        u1, p1 = create_test_user(db, f"rc1_{tid}@test.com", "Reconnector")
        u2, p2 = create_test_user(db, f"rc2_{tid}@test.com", "Opponent")
        league, teams = create_league_with_teams(db, f"RC_L_{tid}", 3, 80)

        room = FifotecaRoom(
            code=f"RC{tid[:4]}",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=p1.id,
            player2_id=p2.id,
            current_turn_player_id=p1.id,
            first_player_id=p1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        p1_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=p1.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=2,
            team_spins_remaining=3,
            current_league_id=league.id,
        )
        p2_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=p2.id,
            round_number=1,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=2,
            team_spins_remaining=3,
            current_league_id=league.id,
        )
        db.add(p1_state)
        db.add(p2_state)
        db.commit()

        t1 = make_token(u1)
        t2 = make_token(u2)

        # P2 connects first
        with client.websocket_connect(ws_url(room.code, t2)) as ws2:
            ws2.receive_json()  # state_sync

            # P1 reconnects
            with client.websocket_connect(ws_url(room.code, t1)) as ws1:
                sync = ws1.receive_json()
                assert sync["type"] == "state_sync"

                restored_room = sync["payload"]["room"]
                assert restored_room["code"] == room.code
                assert restored_room["status"] == RoomStatus.SPINNING_LEAGUES
                assert restored_room["current_turn_player_id"] == str(p1.id)
                assert restored_room["round_number"] == 1

                states = sync["payload"]["player_states"]
                assert len(states) == 2

                p1_restored = next(
                    (s for s in states if s["player_id"] == str(p1.id)), None
                )
                assert p1_restored is not None
                assert p1_restored["league_spins_remaining"] == 2
                assert p1_restored["current_league_id"] == str(league.id)
                assert p1_restored["phase"] == PlayerSpinPhase.LEAGUE_SPINNING

                # P2 receives player_connected
                connected = ws2.receive_json()
                assert connected["type"] == "player_connected"
                assert connected["payload"]["player_id"] == str(p1.id)

                # P1 can continue playing
                ws1.send_json({"type": "spin_league", "payload": {}})
                spin = ws1.receive_json()
                assert spin["type"] == "spin_result"


# =============================================================================
# AC5: Edge Cases
# =============================================================================


class TestSelfJoinBlocked:
    """Test self-join prevention at REST layer."""

    def test_self_join_returns_400(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC5a: Self-join blocked at REST join endpoint."""
        tid = _uid()
        u1, p1 = create_test_user(db, f"sj_{tid}@test.com", "Self Joiner")

        room = FifotecaRoom(
            code=f"SJ{tid[:4]}",
            status=RoomStatus.WAITING,
            player1_id=p1.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(room)
        db.commit()

        t1 = make_token(u1)
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms/join/{room.code}",
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert response.status_code == 400
        assert "Cannot join your own room" in response.json()["detail"]


class TestExpiredRoomRejection:
    """Test that expired rooms reject REST and WS access."""

    def test_expired_room_rest_get_returns_410(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC5b: Expired room returns 410 on REST GET."""
        tid = _uid()
        u1, p1 = create_test_user(db, f"exp_{tid}@test.com", "Expired User")

        room = FifotecaRoom(
            code=f"EX{tid[:4]}",
            status=RoomStatus.WAITING,
            player1_id=p1.id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(room)
        db.commit()

        t1 = make_token(u1)
        response = client.get(
            f"{settings.API_V1_STR}/fifoteca/rooms/{room.code}",
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert response.status_code == 410
        assert "expired" in response.json()["detail"].lower()

    def test_expired_room_rest_join_returns_410(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC5b: Expired room returns 410 on REST join."""
        tid = _uid()
        u1, p1 = create_test_user(db, f"expj1_{tid}@test.com", "Creator")
        u2, p2 = create_test_user(db, f"expj2_{tid}@test.com", "Joiner")

        room = FifotecaRoom(
            code=f"EJ{tid[:4]}",
            status=RoomStatus.WAITING,
            player1_id=p1.id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(room)
        db.commit()

        t2 = make_token(u2)
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms/join/{room.code}",
            headers={"Authorization": f"Bearer {t2}"},
        )
        assert response.status_code == 410

    def test_expired_room_ws_connect_closes(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC5b: Expired room closes WS connection."""
        tid = _uid()
        u1, p1 = create_test_user(db, f"expws_{tid}@test.com", "WS Exp User")

        room = FifotecaRoom(
            code=f"EW{tid[:4]}",
            status=RoomStatus.SPINNING_LEAGUES,
            player1_id=p1.id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(room)
        db.commit()

        t1 = make_token(u1)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(ws_url(room.code, t1)):
                pass


class TestSpecialSpinFlow:
    """Test special spin eligibility and execution."""

    def test_superspin_during_team_spinning(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC5c: Superspin executed during SPINNING_TEAMS phase."""
        tid = _uid()
        u1, p1 = create_test_user(db, f"ss1_{tid}@test.com", "SS P1")
        u2, p2 = create_test_user(db, f"ss2_{tid}@test.com", "SS P2")

        league = FifaLeague(name=f"SS_L_{tid}", country="Test")
        db.add(league)
        db.commit()
        db.refresh(league)

        # P1 has weak team, P2 has strong team
        # Extra teams near P2's rating for superspin to find
        weak_team = FifaTeam(
            name=f"Weak_{tid}",
            league_id=league.id,
            attack_rating=60,
            midfield_rating=60,
            defense_rating=60,
            overall_rating=180,
        )
        strong_team = FifaTeam(
            name=f"Strong_{tid}",
            league_id=league.id,
            attack_rating=85,
            midfield_rating=85,
            defense_rating=85,
            overall_rating=255,
        )
        near_team = FifaTeam(
            name=f"Near_{tid}",
            league_id=league.id,
            attack_rating=84,
            midfield_rating=84,
            defense_rating=84,
            overall_rating=252,
        )
        db.add_all([weak_team, strong_team, near_team])
        db.commit()
        db.refresh(weak_team)
        db.refresh(strong_team)
        db.refresh(near_team)

        # Room in SPINNING_TEAMS, P1's turn, P1 has superspin
        room = FifotecaRoom(
            code=f"SS{tid[:4]}",
            status=RoomStatus.SPINNING_TEAMS,
            player1_id=p1.id,
            player2_id=p2.id,
            current_turn_player_id=p1.id,
            first_player_id=p1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        # P1: has superspin, league locked, team spinning
        p1_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=p1.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_SPINNING,
            league_spins_remaining=0,
            team_spins_remaining=3,
            league_locked=True,
            team_locked=False,
            current_league_id=league.id,
            current_team_id=weak_team.id,
            has_superspin=True,
            superspin_used=False,
        )
        # P2: league locked, team locked already
        p2_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=p2.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_LOCKED,
            league_spins_remaining=0,
            team_spins_remaining=0,
            league_locked=True,
            team_locked=True,
            current_league_id=league.id,
            current_team_id=strong_team.id,
        )
        db.add(p1_state)
        db.add(p2_state)
        db.commit()

        t1 = make_token(u1)
        t2 = make_token(u2)

        with client.websocket_connect(ws_url(room.code, t1)) as ws1:
            ws1.receive_json()  # state_sync

            with client.websocket_connect(ws_url(room.code, t2)) as ws2:
                ws2.receive_json()  # state_sync
                ws1.receive_json()  # player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # P1 uses superspin
                ws1.send_json({"type": "use_superspin", "payload": {}})

                spin = ws1.receive_json()
                assert spin["type"] == "spin_result"
                assert spin["payload"]["type"] == "team"

                # New team should be within ±5 of opponent's 255
                new_rating = spin["payload"]["result"]["overall_rating"]
                assert abs(new_rating - strong_team.overall_rating) <= 5

                # Verify superspin marked used in DB
                db.refresh(p1_state)
                assert p1_state.superspin_used is True

    def test_parity_spin_during_rating_review(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC5c: Parity spin executed during RATING_REVIEW phase."""
        tid = _uid()
        u1, p1 = create_test_user(db, f"ps1_{tid}@test.com", "PS P1")
        u2, p2 = create_test_user(db, f"ps2_{tid}@test.com", "PS P2")

        league = FifaLeague(name=f"PS_L_{tid}", country="Test")
        db.add(league)
        db.commit()
        db.refresh(league)

        weak_team = FifaTeam(
            name=f"PSWeak_{tid}",
            league_id=league.id,
            attack_rating=60,
            midfield_rating=60,
            defense_rating=60,
            overall_rating=180,
        )
        strong_team = FifaTeam(
            name=f"PSStrong_{tid}",
            league_id=league.id,
            attack_rating=80,
            midfield_rating=80,
            defense_rating=80,
            overall_rating=240,
        )
        near_team = FifaTeam(
            name=f"PSNear_{tid}",
            league_id=league.id,
            attack_rating=76,
            midfield_rating=76,
            defense_rating=76,
            overall_rating=228,
        )
        db.add_all([weak_team, strong_team, near_team])
        db.commit()
        db.refresh(weak_team)
        db.refresh(strong_team)
        db.refresh(near_team)

        room = FifotecaRoom(
            code=f"PS{tid[:4]}",
            status=RoomStatus.RATING_REVIEW,
            player1_id=p1.id,
            player2_id=p2.id,
            current_turn_player_id=p1.id,
            first_player_id=p1.id,
            round_number=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        p1_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=p1.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_LOCKED,
            league_spins_remaining=0,
            team_spins_remaining=0,
            league_locked=True,
            team_locked=True,
            current_league_id=league.id,
            current_team_id=weak_team.id,
            has_parity_spin=True,
            parity_spin_used=False,
        )
        p2_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=p2.id,
            round_number=1,
            phase=PlayerSpinPhase.TEAM_LOCKED,
            league_spins_remaining=0,
            team_spins_remaining=0,
            league_locked=True,
            team_locked=True,
            current_league_id=league.id,
            current_team_id=strong_team.id,
        )
        db.add(p1_state)
        db.add(p2_state)
        db.commit()

        t1 = make_token(u1)
        t2 = make_token(u2)

        with client.websocket_connect(ws_url(room.code, t1)) as ws1:
            ws1.receive_json()  # state_sync

            with client.websocket_connect(ws_url(room.code, t2)) as ws2:
                ws2.receive_json()  # state_sync
                ws1.receive_json()  # player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # P1 uses parity spin
                ws1.send_json({"type": "use_parity_spin", "payload": {}})

                spin = ws1.receive_json()
                assert spin["type"] == "spin_result"
                assert spin["payload"]["type"] == "team"

                # Parity spin: team within ±30 of opponent's 240
                new_rating = spin["payload"]["result"]["overall_rating"]
                assert abs(new_rating - strong_team.overall_rating) <= 30

                db.refresh(p1_state)
                assert p1_state.parity_spin_used is True


class TestCreateAndJoinViaREST:
    """Test room creation and joining through real REST endpoints."""

    def test_create_room_join_then_ws_connect(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21: Full REST create -> join -> WS connect flow."""
        tid = _uid()
        u1, p1 = create_test_user(db, f"cj1_{tid}@test.com", "CJ P1")
        u2, p2 = create_test_user(db, f"cj2_{tid}@test.com", "CJ P2")
        create_league_with_teams(db, f"CJ_L_{tid}", 3, 80)

        t1 = make_token(u1)
        t2 = make_token(u2)

        # P1 creates room
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms",
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert response.status_code == 200
        room_data = response.json()
        room_code = room_data["code"]
        assert room_data["status"] == RoomStatus.WAITING
        assert room_data["player1_id"] == str(p1.id)

        # P2 joins
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms/join/{room_code}",
            headers={"Authorization": f"Bearer {t2}"},
        )
        assert response.status_code == 200
        join_data = response.json()
        assert join_data["status"] == RoomStatus.SPINNING_LEAGUES
        assert join_data["player2_id"] == str(p2.id)

        # Both connect via WebSocket
        with client.websocket_connect(ws_url(room_code, t1)) as ws1:
            sync1 = ws1.receive_json()
            assert sync1["type"] == "state_sync"
            assert len(sync1["payload"]["player_states"]) == 2

            with client.websocket_connect(ws_url(room_code, t2)) as ws2:
                ws2.receive_json()  # state_sync
                ws1.receive_json()  # player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                # P1 can spin
                ws1.send_json({"type": "spin_league", "payload": {}})
                r = ws1.receive_json()
                assert r["type"] == "spin_result"


class TestInvalidActionForPhase:
    """Test that actions invalid for the current phase are rejected."""

    def test_spin_team_during_league_phase_rejected(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """S21.AC5: spin_team during SPINNING_LEAGUES phase is rejected."""
        u1, p1, u2, p2, league, teams = setup_two_players_and_league(
            db, "invact", team_count=3
        )
        room = setup_room_in_spinning(db, p1, p2)

        t1 = make_token(u1)
        t2 = make_token(u2)

        with client.websocket_connect(ws_url(room.code, t1)) as ws1:
            ws1.receive_json()  # state_sync

            with client.websocket_connect(ws_url(room.code, t2)) as ws2:
                ws2.receive_json()  # state_sync
                ws1.receive_json()  # player_connected
                ws1.receive_json()  # state_sync (fresh broadcast after p2 join)

                ws1.send_json({"type": "spin_team", "payload": {}})
                error = ws1.receive_json()
                assert error["type"] == "error"
                assert error["payload"]["code"] == "INVALID_ACTION"
