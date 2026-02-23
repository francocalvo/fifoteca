"""Tests for SpinService core game logic."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from app.core.security import get_password_hash
from app.models import (
    FifaLeague,
    FifaTeam,
    FifotecaPlayer,
    FifotecaPlayerState,
    FifotecaRoom,
    PlayerSpinPhase,
    RoomStatus,
    User,
)
from app.services.spin_service import SpecialSpinError, SpinService


@pytest.fixture
def league(db: Session) -> FifaLeague:
    """Create a test league."""
    league = FifaLeague(name="Premier League", country="England")
    db.add(league)
    db.commit()
    db.refresh(league)
    return league


@pytest.fixture
def league2(db: Session) -> FifaLeague:
    """Create a second test league."""
    league = FifaLeague(name="La Liga", country="Spain")
    db.add(league)
    db.commit()
    db.refresh(league)
    return league


@pytest.fixture
def team1(db: Session, league: FifaLeague) -> FifaTeam:
    """Create a test team."""
    team = FifaTeam(
        name="Arsenal",
        league_id=league.id,
        attack_rating=85,
        midfield_rating=83,
        defense_rating=82,
        overall_rating=250,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@pytest.fixture
def team2(db: Session, league: FifaLeague) -> FifaTeam:
    """Create a second test team."""
    team = FifaTeam(
        name="Chelsea",
        league_id=league.id,
        attack_rating=84,
        midfield_rating=84,
        defense_rating=83,
        overall_rating=251,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@pytest.fixture
def player(db: Session) -> FifotecaPlayer:
    """Create a test player."""
    # Create a user first
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpassword"),
    )
    db.add(user)
    db.flush()

    player = FifotecaPlayer(
        user_id=user.id,
        display_name="Test Player",
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


@pytest.fixture
def player2(db: Session) -> FifotecaPlayer:
    """Create a second test player."""
    # Create a user first
    user = User(
        email="test2@example.com",
        hashed_password=get_password_hash("testpassword"),
    )
    db.add(user)
    db.flush()

    player = FifotecaPlayer(
        user_id=user.id,
        display_name="Test Player 2",
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


@pytest.fixture
def room(db: Session, player: FifotecaPlayer) -> FifotecaRoom:
    """Create a test room in spinning leagues phase."""
    room = FifotecaRoom(
        code="ABC123",
        status=RoomStatus.SPINNING_LEAGUES,
        player1_id=player.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@pytest.fixture
def player_state(
    db: Session, room: FifotecaRoom, player: FifotecaPlayer
) -> FifotecaPlayerState:
    """Create a test player state."""
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
    db.refresh(state)
    return state


def test_spin_league_returns_valid_league_and_decrements_counter(
    db: Session,
    player_state: FifotecaPlayerState,
    league: FifaLeague,  # noqa: ARG001
):
    """AC1: League spin returns valid league and decrements counter."""
    initial_spins = player_state.league_spins_remaining

    result = SpinService.spin_league(db, player_state)

    # Check that a league was returned
    assert "league" in result
    assert result["league"] is not None
    assert result["league"].name in ["Premier League", "La Liga"]

    # Check that spins were decremented
    assert result["spins_remaining"] == initial_spins - 1
    assert player_state.league_spins_remaining == initial_spins - 1

    # Check that current_league_id was set
    assert player_state.current_league_id is not None


def test_spin_league_auto_locks_at_zero_spins(
    db: Session,
    player_state: FifotecaPlayerState,
    league: FifaLeague,  # noqa: ARG001
):
    """AC2: Auto-lock triggers at 0 spins."""
    # Set to 1 spin remaining
    player_state.league_spins_remaining = 1
    db.add(player_state)
    db.commit()

    result = SpinService.spin_league(db, player_state)

    # Check auto-lock occurred
    assert result["auto_locked"] is True

    # Check phase transitioned
    assert player_state.league_locked is True
    assert player_state.phase == PlayerSpinPhase.TEAM_SPINNING

    # Check no spins remaining
    assert result["spins_remaining"] == 0


def test_lock_league_transitions_phase(db: Session, player_state: FifotecaPlayerState):
    """AC3: Lock league transitions phase."""
    SpinService.lock_league(db, player_state)

    # Check league locked
    assert player_state.league_locked is True

    # Check phase transitioned
    assert player_state.phase == PlayerSpinPhase.TEAM_SPINNING


def test_spin_team_only_from_locked_leagues_teams(
    db: Session,
    player_state: FifotecaPlayerState,
    league: FifaLeague,
    team1: FifaTeam,  # noqa: ARG001
    team2: FifaTeam,  # noqa: ARG001
):
    """AC4: Team spin only from locked league's teams."""
    # Lock league first
    player_state.league_locked = True
    player_state.current_league_id = league.id
    player_state.phase = PlayerSpinPhase.TEAM_SPINNING
    db.add(player_state)
    db.commit()

    result = SpinService.spin_team(db, player_state)

    # Check that a team was returned
    assert "team" in result
    assert result["team"] is not None
    assert result["team"].name in ["Arsenal", "Chelsea"]

    # Check that spins were decremented
    assert result["spins_remaining"] == 2
    assert player_state.team_spins_remaining == 2

    # Check that current_team_id was set
    assert player_state.current_team_id is not None


def test_spin_team_auto_locks_at_zero_spins(
    db: Session,
    player_state: FifotecaPlayerState,
    league: FifaLeague,
    team1: FifaTeam,  # noqa: ARG001
):
    """Auto-lock triggers at 0 team spins."""
    # Lock league and set to 1 team spin remaining
    player_state.league_locked = True
    player_state.current_league_id = league.id
    player_state.phase = PlayerSpinPhase.TEAM_SPINNING
    player_state.team_spins_remaining = 1
    db.add(player_state)
    db.commit()

    result = SpinService.spin_team(db, player_state)

    # Check auto-lock occurred
    assert result["auto_locked"] is True

    # Check phase transitioned
    assert player_state.team_locked is True
    assert player_state.phase == PlayerSpinPhase.TEAM_LOCKED

    # Check no spins remaining
    assert result["spins_remaining"] == 0


def test_spin_team_fails_if_league_not_locked(
    db: Session, player_state: FifotecaPlayerState
):
    """Team spin fails if league is not locked."""
    player_state.league_locked = False
    db.add(player_state)
    db.commit()

    with pytest.raises(ValueError, match="League must be locked"):
        SpinService.spin_team(db, player_state)


def test_spin_team_fails_if_no_spins_remaining(
    db: Session, player_state: FifotecaPlayerState, league: FifaLeague
):
    """Team spin fails if no spins remaining."""
    player_state.league_locked = True
    player_state.current_league_id = league.id
    player_state.phase = PlayerSpinPhase.TEAM_SPINNING
    player_state.team_spins_remaining = 0
    db.add(player_state)
    db.commit()

    with pytest.raises(ValueError, match="No team spins remaining"):
        SpinService.spin_team(db, player_state)


def test_lock_team(db: Session, player_state: FifotecaPlayerState):
    """Lock team sets team_locked and phase."""
    SpinService.lock_team(db, player_state)

    assert player_state.team_locked is True
    assert player_state.phase == PlayerSpinPhase.TEAM_LOCKED


def test_turn_alternation_in_league_phase(
    db: Session,
    room: FifotecaRoom,
    player: FifotecaPlayer,
    player2: FifotecaPlayer,
    player_state: FifotecaPlayerState,  # noqa: ARG001
):
    """AC5: Turn alternation works correctly in league phase."""
    # Add player2 to room
    room.player2_id = player2.id
    room.current_turn_player_id = player.id
    db.add(room)
    db.commit()

    # Create player2 state (not locked)
    player2_state = FifotecaPlayerState(
        room_id=room.id,
        player_id=player2.id,
        round_number=1,
        phase=PlayerSpinPhase.LEAGUE_SPINNING,
        league_spins_remaining=3,
        team_spins_remaining=3,
    )
    db.add(player2_state)
    db.commit()

    # Player1 acts, next turn should be player2
    next_player = SpinService.determine_next_turn(db, room, player.id)

    assert next_player is not None
    assert next_player.id == player2.id


def test_turn_stays_with_acting_player_when_other_locked(
    db: Session,
    room: FifotecaRoom,
    player: FifotecaPlayer,
    player2: FifotecaPlayer,
    player_state: FifotecaPlayerState,  # noqa: ARG001
):
    """AC6: Turn stays with acting player when other is done."""
    # Add player2 to room and lock their league
    room.player2_id = player2.id
    room.current_turn_player_id = player.id
    db.add(room)
    db.commit()

    # Create player2 state (locked league)
    player2_state = FifotecaPlayerState(
        room_id=room.id,
        player_id=player2.id,
        round_number=1,
        phase=PlayerSpinPhase.TEAM_SPINNING,
        league_spins_remaining=3,
        team_spins_remaining=3,
        league_locked=True,
    )
    db.add(player2_state)
    db.commit()

    # Player1 acts, next turn should still be player1 (they continue)
    next_player = SpinService.determine_next_turn(db, room, player.id)

    assert next_player is not None
    assert next_player.id == player.id


def test_phase_transition_to_spinning_teams(
    db: Session,
    room: FifotecaRoom,
    player: FifotecaPlayer,  # noqa: ARG001
    player2: FifotecaPlayer,
    player_state: FifotecaPlayerState,
):
    """AC7: Phase transition to SPINNING_TEAMS when both leagues locked."""
    # Add player2 to room
    room.player2_id = player2.id
    db.add(room)
    db.commit()

    # Lock both players' leagues
    player_state.league_locked = True
    player_state.phase = PlayerSpinPhase.TEAM_SPINNING
    db.add(player_state)

    player2_state = FifotecaPlayerState(
        room_id=room.id,
        player_id=player2.id,
        round_number=1,
        phase=PlayerSpinPhase.TEAM_SPINNING,
        league_spins_remaining=3,
        team_spins_remaining=3,
        league_locked=True,
    )
    db.add(player2_state)
    db.commit()

    # Check phase transition
    transitioned = SpinService.check_phase_transition(db, room)

    assert transitioned is True
    assert room.status == RoomStatus.SPINNING_TEAMS


def test_phase_transition_to_rating_review(
    db: Session,
    room: FifotecaRoom,
    player: FifotecaPlayer,
    player2: FifotecaPlayer,
):
    """AC7: Phase transition to RATING_REVIEW when both teams locked."""
    # Add player2 to room and set to team spinning phase
    room.player2_id = player2.id
    room.status = RoomStatus.SPINNING_TEAMS
    db.add(room)
    db.commit()

    # Lock both players' teams
    player_state = FifotecaPlayerState(
        room_id=room.id,
        player_id=player.id,
        round_number=1,
        phase=PlayerSpinPhase.TEAM_LOCKED,
        league_spins_remaining=3,
        team_spins_remaining=3,
        league_locked=True,
        team_locked=True,
    )
    db.add(player_state)

    player2_state = FifotecaPlayerState(
        room_id=room.id,
        player_id=player2.id,
        round_number=1,
        phase=PlayerSpinPhase.TEAM_LOCKED,
        league_spins_remaining=3,
        team_spins_remaining=3,
        league_locked=True,
        team_locked=True,
    )
    db.add(player2_state)
    db.commit()

    # Check phase transition
    transitioned = SpinService.check_phase_transition(db, room)

    assert transitioned is True
    assert room.status == RoomStatus.RATING_REVIEW


def test_no_phase_transition_when_not_all_locked(
    db: Session,
    room: FifotecaRoom,
    player: FifotecaPlayer,  # noqa: ARG001
    player2: FifotecaPlayer,
    player_state: FifotecaPlayerState,
):
    """No phase transition when not all players locked."""
    # Add player2 to room
    room.player2_id = player2.id
    db.add(room)
    db.commit()

    # Only lock player1's league, player2 not locked
    player_state.league_locked = True
    player_state.phase = PlayerSpinPhase.TEAM_SPINNING
    db.add(player_state)

    player2_state = FifotecaPlayerState(
        room_id=room.id,
        player_id=player2.id,
        round_number=1,
        phase=PlayerSpinPhase.LEAGUE_SPINNING,
        league_spins_remaining=3,
        team_spins_remaining=3,
        league_locked=False,
    )
    db.add(player2_state)
    db.commit()

    # Check no phase transition
    transitioned = SpinService.check_phase_transition(db, room)

    assert transitioned is False
    assert room.status == RoomStatus.SPINNING_LEAGUES


def test_full_spin_flow(
    db: Session,
    room: FifotecaRoom,
    player: FifotecaPlayer,
    league: FifaLeague,  # noqa: ARG001
    team1: FifaTeam,  # noqa: ARG001
):
    """AC8: Unit tests cover full spin flow."""
    # Create player state
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

    # Spin league 3 times
    SpinService.spin_league(db, player_state)
    assert player_state.league_spins_remaining == 2
    assert player_state.current_league_id is not None

    SpinService.spin_league(db, player_state)
    assert player_state.league_spins_remaining == 1

    # Third spin should auto-lock
    result = SpinService.spin_league(db, player_state)
    assert result["auto_locked"] is True
    assert player_state.league_locked is True
    assert player_state.phase == PlayerSpinPhase.TEAM_SPINNING
    assert player_state.league_spins_remaining == 0

    # Spin team 3 times
    SpinService.spin_team(db, player_state)
    assert player_state.team_spins_remaining == 2
    assert player_state.current_team_id is not None

    SpinService.spin_team(db, player_state)
    assert player_state.team_spins_remaining == 1

    # Third spin should auto-lock
    result = SpinService.spin_team(db, player_state)
    assert result["auto_locked"] is True
    assert player_state.team_locked is True
    assert player_state.phase == PlayerSpinPhase.TEAM_LOCKED
    assert player_state.team_spins_remaining == 0


# ============================================================================
# S09.T01: Special Spin Tests
# ============================================================================


def test_superspin_selects_team_within_rating_range(
    db: Session,
    player_state: FifotecaPlayerState,
    league: FifaLeague,
):
    """S09.AC4: Superspin finds team within ±5 rating."""

    # Create teams with ratings 85, 90, 95, 100
    teams = []
    for rating in [85, 90, 95, 100]:
        team = FifaTeam(
            name=f"Team {rating}",
            league_id=league.id,
            attack_rating=rating,
            midfield_rating=rating,
            defense_rating=rating,
            overall_rating=rating * 3,  # sum-based rating
        )
        teams.append(team)
        db.add(team)
    db.commit()

    # Execute superspin with opponent rating of 90*3 = 270
    opponent_rating = 270  # 90 * 3
    result = SpinService.execute_superspin(db, player_state, opponent_rating)

    # Should select team within ±5 (i.e., 265-275)
    selected_rating = result["team"].overall_rating
    assert 265 <= selected_rating <= 275
    assert result["was_fallback"] is False
    assert player_state.team_locked is True
    assert player_state.superspin_used is True


def test_superspin_rejects_when_no_teams_in_range(
    db: Session,
    player_state: FifotecaPlayerState,
    league: FifaLeague,
):
    """S09.AC4: Superspin rejects when no qualifying teams."""

    # Create teams with ratings 50, 55 (outside ±5 of 100)
    teams = []
    for rating in [50, 55]:
        team = FifaTeam(
            name=f"Team {rating}",
            league_id=league.id,
            attack_rating=rating,
            midfield_rating=rating,
            defense_rating=rating,
            overall_rating=rating * 3,  # sum-based rating
        )
        teams.append(team)
        db.add(team)
    db.commit()

    # Execute superspin with opponent rating of 100*3 = 300
    opponent_rating = 300

    # Should raise SpecialSpinError
    with pytest.raises(SpecialSpinError, match="No teams found within ±5"):
        SpinService.execute_superspin(db, player_state, opponent_rating)


def test_superspin_rejects_when_opponent_rating_unavailable(
    db: Session,
    player_state: FifotecaPlayerState,
):
    """S09.AC4: Superspin rejects when opponent rating unavailable."""

    # Should raise SpecialSpinError
    with pytest.raises(
        SpecialSpinError, match="Cannot execute superspin: opponent rating unavailable"
    ):
        SpinService.execute_superspin(db, player_state, None)


def test_parity_spin_uses_same_league_first(
    db: Session,
    player_state: FifotecaPlayerState,
    league: FifaLeague,
    league2: FifaLeague,
):
    """S09.AC5: Parity spin uses same-league candidates when available."""

    # Set player's current league
    player_state.current_league_id = league.id
    db.add(player_state)
    db.commit()

    # Create teams in same league within range
    for rating in [70, 75, 80]:
        team = FifaTeam(
            name=f"Same League Team {rating}",
            league_id=league.id,
            attack_rating=rating,
            midfield_rating=rating,
            defense_rating=rating,
            overall_rating=rating * 3,
        )
        db.add(team)

    # Create teams in other league within range
    for rating in [70, 75, 80]:
        team = FifaTeam(
            name=f"Other League Team {rating}",
            league_id=league2.id,
            attack_rating=rating,
            midfield_rating=rating,
            defense_rating=rating,
            overall_rating=rating * 3,
        )
        db.add(team)
    db.commit()

    # Execute parity spin with opponent rating of 75*3 = 225
    opponent_rating = 225
    result = SpinService.execute_parity_spin(db, player_state, opponent_rating)

    # Should select from same league (no fallback)
    assert result["was_fallback"] is False
    assert result["team"].league_id == league.id


def test_parity_spin_falls_back_to_all_leagues(
    db: Session,
    player_state: FifotecaPlayerState,
    league: FifaLeague,
    league2: FifaLeague,
):
    """S09.AC6: Parity spin falls back to all leagues when same-league has none."""

    # Set player's current league
    player_state.current_league_id = league.id
    db.add(player_state)
    db.commit()

    # Create teams in same league OUTSIDE range
    team_outside = FifaTeam(
        name="Same League Team Outside Range",
        league_id=league.id,
        attack_rating=10,
        midfield_rating=10,
        defense_rating=10,
        overall_rating=30,  # way outside range
    )
    db.add(team_outside)

    # Create teams in other league WITHIN range
    for rating in [70, 75, 80]:
        team = FifaTeam(
            name=f"Other League Team {rating}",
            league_id=league2.id,
            attack_rating=rating,
            midfield_rating=rating,
            defense_rating=rating,
            overall_rating=rating * 3,
        )
        db.add(team)
    db.commit()

    # Execute parity spin with opponent rating of 75*3 = 225
    opponent_rating = 225
    result = SpinService.execute_parity_spin(db, player_state, opponent_rating)

    # Should fallback to other league
    assert result["was_fallback"] is True
    assert result["team"].league_id == league2.id
    assert player_state.parity_spin_used is True


def test_parity_spin_rejects_when_no_teams_in_range(
    db: Session,
    player_state: FifotecaPlayerState,
    league: FifaLeague,
):
    """S09.AC4: Parity spin rejects when no qualifying teams."""

    # Set player's current league
    player_state.current_league_id = league.id
    db.add(player_state)
    db.commit()

    # Create teams with ratings way outside ±30 of 100
    team = FifaTeam(
        name="Team Outside Range",
        league_id=league.id,
        attack_rating=10,
        midfield_rating=10,
        defense_rating=10,
        overall_rating=30,  # way outside range of 300 (100*3)
    )
    db.add(team)
    db.commit()

    # Execute parity spin with opponent rating of 100*3 = 300
    opponent_rating = 300

    # Should raise SpecialSpinError
    with pytest.raises(SpecialSpinError, match="No teams found within ±30 rating"):
        SpinService.execute_parity_spin(db, player_state, opponent_rating)


def test_parity_spin_rejects_when_opponent_rating_unavailable(
    db: Session,
    player_state: FifotecaPlayerState,
):
    """S09.AC4: Parity spin rejects when opponent rating unavailable."""

    # Should raise SpecialSpinError
    with pytest.raises(
        SpecialSpinError,
        match="Cannot execute parity spin: opponent rating unavailable",
    ):
        SpinService.execute_parity_spin(db, player_state, None)
