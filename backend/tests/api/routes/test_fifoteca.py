import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session, delete, or_, select

from app.core.config import settings
from app.models import (
    FifaLeague,
    FifaTeam,
    FifotecaMatch,
    FifotecaPlayer,
    FifotecaPlayerState,
    FifotecaRoom,
    MatchScoreSubmit,
    PlayerSpinPhase,
    RoomStatus,
    User,
)


def test_read_leagues(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test retrieving all leagues."""
    # Create test leagues with unique names
    league1 = FifaLeague(name="Alpha League", country="England")
    league2 = FifaLeague(name="Beta League", country="Spain")
    db.add(league1)
    db.add(league2)
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/leagues/",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    assert len(content) >= 2

    # Check sorting by name
    league_names = [league["name"] for league in content]
    assert league_names == sorted(league_names)

    # Verify response structure
    league = next(item for item in content if item["name"] == "Alpha League")
    assert league["id"] is not None
    assert league["name"] == "Alpha League"
    assert league["country"] == "England"


def test_read_leagues_unauthorized(client: TestClient) -> None:
    """Test that authentication is required."""
    response = client.get(f"{settings.API_V1_STR}/fifoteca/leagues/")
    assert response.status_code == 401
    content = response.json()
    assert "detail" in content


def test_read_league_teams(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test retrieving teams for a specific league."""
    # Create test league and teams with unique names
    league = FifaLeague(name="English League", country="England")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Arsenal",
        league_id=league.id,
        attack_rating=85,
        midfield_rating=83,
        defense_rating=84,
        overall_rating=252,
    )
    team2 = FifaTeam(
        name="Chelsea",
        league_id=league.id,
        attack_rating=82,
        midfield_rating=84,
        defense_rating=83,
        overall_rating=249,
    )
    db.add(team1)
    db.add(team2)
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/leagues/{league.id}/teams",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    assert len(content) == 2

    # Check sorting by name
    team_names = [team["name"] for team in content]
    assert team_names == sorted(team_names)

    # Verify response structure
    arsenal = next(t for t in content if t["name"] == "Arsenal")
    assert arsenal["id"] is not None
    assert arsenal["name"] == "Arsenal"
    assert arsenal["league_id"] == str(league.id)
    assert arsenal["attack_rating"] == 85
    assert arsenal["midfield_rating"] == 83
    assert arsenal["defense_rating"] == 84
    assert arsenal["overall_rating"] == 252


def test_read_league_teams_not_found(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Test retrieving teams for a non-existent league."""
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/leagues/{uuid.uuid4()}/teams",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404
    content = response.json()
    assert content["detail"] == "League not found"


def test_read_league_teams_unauthorized(client: TestClient) -> None:
    """Test that authentication is required."""
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/leagues/{uuid.uuid4()}/teams"
    )
    assert response.status_code == 401


def test_read_teams(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test retrieving all teams."""
    # Clean up any existing test data
    statement = delete(FifaTeam).where(
        or_(FifaTeam.name == "Arsenal", FifaTeam.name == "Real Madrid")
    )
    db.exec(statement)
    statement = delete(FifaLeague).where(
        or_(FifaLeague.name == "League A", FifaLeague.name == "League B")
    )
    db.exec(statement)
    db.commit()

    # Create test leagues and teams with unique names
    league1 = FifaLeague(name="League A", country="England")
    league2 = FifaLeague(name="League B", country="Spain")
    db.add(league1)
    db.add(league2)
    db.flush()

    team1 = FifaTeam(
        name="Arsenal",
        league_id=league1.id,
        attack_rating=85,
        midfield_rating=83,
        defense_rating=84,
        overall_rating=252,
    )
    team2 = FifaTeam(
        name="Real Madrid",
        league_id=league2.id,
        attack_rating=88,
        midfield_rating=86,
        defense_rating=85,
        overall_rating=259,
    )
    db.add(team1)
    db.add(team2)
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/teams/",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    assert len(content) >= 2

    # Check sorting by name
    team_names = [team["name"] for team in content]
    assert team_names == sorted(team_names)

    # Verify response structure
    arsenal = next(t for t in content if t["name"] == "Arsenal")
    assert arsenal["id"] is not None
    assert arsenal["name"] == "Arsenal"
    assert arsenal["league_id"] == str(league1.id)
    assert arsenal["attack_rating"] == 85
    assert arsenal["midfield_rating"] == 83
    assert arsenal["defense_rating"] == 84
    assert arsenal["overall_rating"] == 252


def test_read_teams_by_league_id(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test filtering teams by league ID."""
    # Create test leagues and teams with unique names
    league1 = FifaLeague(name="League C", country="England")
    league2 = FifaLeague(name="League D", country="Spain")
    db.add(league1)
    db.add(league2)
    db.flush()

    team1 = FifaTeam(
        name="Arsenal",
        league_id=league1.id,
        attack_rating=85,
        midfield_rating=83,
        defense_rating=84,
        overall_rating=252,
    )
    team2 = FifaTeam(
        name="Chelsea",
        league_id=league1.id,
        attack_rating=82,
        midfield_rating=84,
        defense_rating=83,
        overall_rating=249,
    )
    team3 = FifaTeam(
        name="Real Madrid",
        league_id=league2.id,
        attack_rating=88,
        midfield_rating=86,
        defense_rating=85,
        overall_rating=259,
    )
    db.add(team1)
    db.add(team2)
    db.add(team3)
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/teams/?league_id={league1.id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    assert len(content) == 2

    # Verify only league1 teams are returned
    team_names = [team["name"] for team in content]
    assert set(team_names) == {"Arsenal", "Chelsea"}


def test_read_teams_by_min_rating(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test filtering teams by minimum rating."""
    league = FifaLeague(name="League E", country="England")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Arsenal",
        league_id=league.id,
        attack_rating=85,
        midfield_rating=83,
        defense_rating=84,
        overall_rating=252,
    )
    team2 = FifaTeam(
        name="Chelsea",
        league_id=league.id,
        attack_rating=82,
        midfield_rating=84,
        defense_rating=83,
        overall_rating=249,
    )
    team3 = FifaTeam(
        name="Manchester City",
        league_id=league.id,
        attack_rating=89,
        midfield_rating=87,
        defense_rating=88,
        overall_rating=264,
    )
    db.add(team1)
    db.add(team2)
    db.add(team3)
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/teams/?min_rating=250",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)

    # Verify only teams with rating >= 250 are returned
    team_names = [team["name"] for team in content]
    assert "Arsenal" in team_names  # 252
    assert "Manchester City" in team_names  # 264
    assert "Chelsea" not in team_names  # 249


def test_read_teams_by_max_rating(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test filtering teams by maximum rating."""
    league = FifaLeague(name="League F", country="England")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Arsenal",
        league_id=league.id,
        attack_rating=85,
        midfield_rating=83,
        defense_rating=84,
        overall_rating=252,
    )
    team2 = FifaTeam(
        name="Chelsea",
        league_id=league.id,
        attack_rating=82,
        midfield_rating=84,
        defense_rating=83,
        overall_rating=249,
    )
    team3 = FifaTeam(
        name="Manchester City",
        league_id=league.id,
        attack_rating=89,
        midfield_rating=87,
        defense_rating=88,
        overall_rating=264,
    )
    db.add(team1)
    db.add(team2)
    db.add(team3)
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/teams/?max_rating=250",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)

    # Verify only teams with rating <= 250 are returned
    team_names = [team["name"] for team in content]
    assert "Chelsea" in team_names  # 249
    assert "Arsenal" not in team_names  # 252
    assert "Manchester City" not in team_names  # 264


def test_read_teams_combined_filters(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test filtering teams with combined filters."""
    # Create test leagues and teams with unique names
    league1 = FifaLeague(name="League G", country="England")
    league2 = FifaLeague(name="League H", country="Spain")
    db.add(league1)
    db.add(league2)
    db.flush()

    team1 = FifaTeam(
        name="Arsenal",
        league_id=league1.id,
        attack_rating=85,
        midfield_rating=83,
        defense_rating=84,
        overall_rating=252,
    )
    team2 = FifaTeam(
        name="Chelsea",
        league_id=league1.id,
        attack_rating=82,
        midfield_rating=84,
        defense_rating=83,
        overall_rating=249,
    )
    team3 = FifaTeam(
        name="Real Madrid",
        league_id=league2.id,
        attack_rating=88,
        midfield_rating=86,
        defense_rating=85,
        overall_rating=259,
    )
    db.add(team1)
    db.add(team2)
    db.add(team3)
    db.commit()

    # Filter by league1 and min_rating 250
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/teams/?league_id={league1.id}&min_rating=250",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    assert len(content) == 1

    # Only Arsenal matches both criteria
    team_names = [team["name"] for team in content]
    assert team_names == ["Arsenal"]


def test_read_teams_unauthorized(client: TestClient) -> None:
    """Test that authentication is required."""
    response = client.get(f"{settings.API_V1_STR}/fifoteca/teams/")
    assert response.status_code == 401
    content = response.json()
    assert "detail" in content


def test_openapi_includes_fifoteca_routes(client: TestClient) -> None:
    """Test that OpenAPI spec includes fifoteca endpoints."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    # Check that fifoteca paths are present
    fifoteca_paths = [path for path in spec["paths"].keys() if "/fifoteca/" in path]
    assert len(fifoteca_paths) > 0

    # Check specific endpoints exist
    assert "/api/v1/fifoteca/leagues/" in spec["paths"]
    assert "/api/v1/fifoteca/leagues/{id}/teams" in spec["paths"]
    assert "/api/v1/fifoteca/teams/" in spec["paths"]
    assert "/api/v1/fifoteca/players/me" in spec["paths"]

    # Check leagues endpoint schema
    leagues_endpoint = spec["paths"]["/api/v1/fifoteca/leagues/"]["get"]
    assert "leagues" in leagues_endpoint["tags"]

    # Check teams endpoint schema
    teams_endpoint = spec["paths"]["/api/v1/fifoteca/teams/"]["get"]
    assert "teams" in teams_endpoint["tags"]

    # Check players endpoint schema
    players_get = spec["paths"]["/api/v1/fifoteca/players/me"]["get"]
    assert "players" in players_get["tags"]
    players_post = spec["paths"]["/api/v1/fifoteca/players/me"]["post"]
    assert "players" in players_post["tags"]


def test_create_player_profile(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test creating a new player profile."""
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, dict)
    assert "id" in content
    assert "user_id" in content
    assert "display_name" in content
    assert content["total_wins"] == 0
    assert content["total_losses"] == 0
    assert content["total_draws"] == 0
    assert content["has_protection"] is False

    # Clean up created player
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == uuid.UUID(content["id"])))  # type: ignore[arg-type]
    db.commit()


def test_create_player_profile_idempotent(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test that POST /players/me is idempotent (returns existing profile)."""
    # First call creates profile
    response1 = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response1.status_code == 200
    content1 = response1.json()

    # Second call returns same profile
    response2 = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response2.status_code == 200
    content2 = response2.json()
    assert content2["id"] == content1["id"]
    assert content2["display_name"] == content1["display_name"]
    assert content2["total_wins"] == 0
    assert content2["total_losses"] == 0
    assert content2["total_draws"] == 0

    # Clean up created player
    db.exec(
        delete(FifotecaPlayer).where(FifotecaPlayer.id == uuid.UUID(content1["id"]))  # type: ignore[arg-type]
    )
    db.commit()


def test_get_player_profile(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test retrieving the current user's player profile."""
    # First create a profile
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    player_id = uuid.UUID(content["id"])

    # Then retrieve it
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, dict)
    assert "id" in content
    assert "user_id" in content
    assert "display_name" in content
    assert "total_wins" in content
    assert "total_losses" in content
    assert "total_draws" in content
    assert "has_protection" in content

    # Display name should fall back to email if no full_name
    assert content["display_name"] == settings.EMAIL_TEST_USER

    # Clean up created player
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player_id))  # type: ignore[arg-type]
    db.commit()


def test_get_player_profile_not_found(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Test that GET returns 404 when profile doesn't exist."""
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404
    content = response.json()
    assert "detail" in content
    assert "Player profile not found" in content["detail"]


def test_create_player_profile_unauthorized(client: TestClient) -> None:
    """Test that authentication is required to create player profile."""
    response = client.post(f"{settings.API_V1_STR}/fifoteca/players/me")
    assert response.status_code == 401
    content = response.json()
    assert "detail" in content


def test_get_player_profile_unauthorized(client: TestClient) -> None:
    """Test that authentication is required to get player profile."""
    response = client.get(f"{settings.API_V1_STR}/fifoteca/players/me")
    assert response.status_code == 401
    content = response.json()
    assert "detail" in content


def test_openapi_includes_players_routes(client: TestClient) -> None:
    """Test that OpenAPI spec includes players endpoints."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    # Check that players paths are present
    assert "/api/v1/fifoteca/players/me" in spec["paths"]
    assert "get" in spec["paths"]["/api/v1/fifoteca/players/me"]
    assert "post" in spec["paths"]["/api/v1/fifoteca/players/me"]

    # Check players endpoint schema
    players_get = spec["paths"]["/api/v1/fifoteca/players/me"]["get"]
    assert "players" in players_get["tags"]

    players_post = spec["paths"]["/api/v1/fifoteca/players/me"]["post"]
    assert "players" in players_post["tags"]


def test_display_name_uses_full_name_when_available(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test that display name uses full_name when available, falling back to email."""
    from app.crud import get_user_by_email

    # Get the test user and set full_name
    user = get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    if not user:
        raise Exception("Test user not found")

    # Set full_name
    user.full_name = "Test User Full Name"
    db.add(user)
    db.commit()

    try:
        # Create profile (should use full_name)
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/players/me",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        content = response.json()
        assert content["display_name"] == "Test User Full Name"

        # Clean up created player
        db.exec(
            delete(FifotecaPlayer).where(FifotecaPlayer.id == uuid.UUID(content["id"]))  # type: ignore[arg-type]
        )
        db.commit()

        # Clear full_name and test fallback to email
        user.full_name = None
        db.add(user)
        db.commit()

        # Create new profile (should use email)
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/players/me",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        content = response.json()
        assert content["display_name"] == settings.EMAIL_TEST_USER

        # Clean up created player
        db.exec(
            delete(FifotecaPlayer).where(FifotecaPlayer.id == uuid.UUID(content["id"]))  # type: ignore[arg-type]
        )
        db.commit()

    finally:
        # Reset full_name to None for other tests
        user.full_name = None
        db.add(user)
        db.commit()


# ============================================================================
# Room Management Tests
# ============================================================================


def test_create_room_returns_valid_code(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test that room creation returns a valid 6-character code."""
    # Create player profile first
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    player_data = response.json()
    player_id = uuid.UUID(player_data["id"])

    try:
        # Create room
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        content = response.json()

        # Verify room structure
        assert "id" in content
        assert "code" in content
        assert len(content["code"]) == 6
        assert content["ruleset"] == "homebrew"
        assert content["status"] == RoomStatus.WAITING
        assert content["player1_id"] == str(player_id)
        assert content["player2_id"] is None
        assert content["current_turn_player_id"] is None
        assert content["first_player_id"] is None
        assert content["round_number"] == 1
        assert content["mutual_superspin_active"] is False

        # Verify code uses valid charset
        valid_charset = set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
        assert all(c in valid_charset for c in content["code"])

        # Verify expires_at is set
        expires_at = datetime.fromisoformat(
            content["expires_at"].replace("Z", "+00:00")
        )
        now = datetime.now(timezone.utc)
        assert expires_at > now
        assert expires_at <= now + timedelta(minutes=61)

        # Clean up room
        room_id = uuid.UUID(content["id"])
        db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room_id))
        db.commit()

    finally:
        # Clean up player
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player_id))
        db.commit()


def test_create_room_without_profile_returns_error(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Test that room creation requires a player profile."""
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/rooms",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404
    content = response.json()
    assert "Player profile not found" in content["detail"]


def test_join_room_successfully(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Test that player 2 can successfully join a waiting room."""
    # Create player profile for normal user
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    player1_data = response.json()
    player1_id = uuid.UUID(player1_data["id"])

    # Create room
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/rooms",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    room_data = response.json()
    room_code = room_data["code"]
    room_id = uuid.UUID(room_data["id"])

    try:
        # Create player profile for superuser (player 2)
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/players/me",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200
        player2_data = response.json()
        player2_id = uuid.UUID(player2_data["id"])

        try:
            # Join room
            response = client.post(
                f"{settings.API_V1_STR}/fifoteca/rooms/join/{room_code}",
                headers=superuser_token_headers,
            )
            assert response.status_code == 200
            content = response.json()

            # Verify room state updated
            assert content["player1_id"] == str(player1_id)
            assert content["player2_id"] == str(player2_id)
            assert content["status"] == RoomStatus.SPINNING_LEAGUES
            assert content["current_turn_player_id"] == str(player1_id)
            assert content["first_player_id"] == str(player1_id)

            # Verify player states were created
            player_states = db.exec(
                select(FifotecaPlayerState).where(
                    FifotecaPlayerState.room_id == room_id
                )
            ).all()
            assert len(player_states) == 2

            # Find player states
            player1_state = next(
                (ps for ps in player_states if ps.player_id == player1_id), None
            )
            player2_state = next(
                (ps for ps in player_states if ps.player_id == player2_id), None
            )

            assert player1_state is not None
            assert player2_state is not None

            # Verify player 1 state
            assert player1_state.round_number == 1
            assert player1_state.phase == PlayerSpinPhase.LEAGUE_SPINNING
            assert player1_state.league_spins_remaining == 3
            assert player1_state.team_spins_remaining == 3
            assert player1_state.has_superspin is False
            assert player1_state.league_locked is False
            assert player1_state.team_locked is False

            # Verify player 2 state
            assert player2_state.round_number == 1
            assert player2_state.phase == PlayerSpinPhase.LEAGUE_SPINNING
            assert player2_state.league_spins_remaining == 3
            assert player2_state.team_spins_remaining == 3
            assert player2_state.has_superspin is False
            assert player2_state.league_locked is False
            assert player2_state.team_locked is False

            # Clean up player states
            db.exec(
                delete(FifotecaPlayerState).where(
                    FifotecaPlayerState.room_id == room_id
                )
            )
            db.commit()

        finally:
            # Clean up room first (due to FK constraint)
            db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room_id))
            db.commit()
            # Then clean up player 2
            db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2_id))
            db.commit()

    finally:
        # Clean up player 1 (room already deleted)
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1_id))
        db.commit()


def test_join_room_full_returns_409(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Test that joining a full room returns 409 Conflict."""
    # Create players
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    player1_data = response.json()
    player1_id = uuid.UUID(player1_data["id"])

    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    player2_data = response.json()
    player2_id = uuid.UUID(player2_data["id"])

    try:
        # Create and join room
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        room_data = response.json()
        room_code = room_data["code"]
        room_id = uuid.UUID(room_data["id"])

        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms/join/{room_code}",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        try:
            # Player2 tries to join again (should fail - room not in WAITING status)
            response = client.post(
                f"{settings.API_V1_STR}/fifoteca/rooms/join/{room_code}",
                headers=superuser_token_headers,
            )
            assert response.status_code == 400
            content = response.json()
            assert "not accepting joins" in content["detail"]

        finally:
            # Clean up room
            db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room_id))
            db.commit()

    finally:
        # Clean up players
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1_id))
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2_id))
        db.commit()


def test_join_room_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Test that joining a non-existent room returns 404."""
    # Create player profile first
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200

    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/rooms/join/INVALID",
        headers=superuser_token_headers,
    )
    assert response.status_code == 404
    content = response.json()
    assert "Room not found" in content["detail"]


def test_join_room_not_waiting_status(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Test that joining a room not in WAITING status returns error."""
    # Create players
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    player1_data = response.json()
    player1_id = uuid.UUID(player1_data["id"])

    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    player2_data = response.json()
    player2_id = uuid.UUID(player2_data["id"])

    try:
        # Create room
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        room_data = response.json()
        room_code = room_data["code"]
        room_id = uuid.UUID(room_data["id"])

        # Join room (transitions to SPINNING_LEAGUES)
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms/join/{room_code}",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        try:
            # Third player tries to join (should fail - room not in WAITING)
            response = client.post(
                f"{settings.API_V1_STR}/fifoteca/rooms/join/{room_code}",
                headers=superuser_token_headers,
            )
            assert response.status_code == 400
            content = response.json()
            assert "not accepting joins" in content["detail"]

        finally:
            # Clean up room
            db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room_id))
            db.commit()

    finally:
        # Clean up players
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1_id))
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2_id))
        db.commit()


def test_join_room_self_join_blocked(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test that player cannot join their own room."""
    # Create player profile
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    player_data = response.json()
    player_id = uuid.UUID(player_data["id"])

    try:
        # Create room
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        room_data = response.json()
        room_code = room_data["code"]
        room_id = uuid.UUID(room_data["id"])

        try:
            # Try to join own room
            response = client.post(
                f"{settings.API_V1_STR}/fifoteca/rooms/join/{room_code}",
                headers=normal_user_token_headers,
            )
            assert response.status_code == 400
            content = response.json()
            assert "Cannot join your own room" in content["detail"]

        finally:
            # Clean up room
            db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room_id))
            db.commit()

    finally:
        # Clean up player
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player_id))
        db.commit()


def test_get_room_with_states(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Test that GET room returns full state including player states."""
    # Create players
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    player1_data = response.json()
    player1_id = uuid.UUID(player1_data["id"])

    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    player2_data = response.json()
    player2_id = uuid.UUID(player2_data["id"])

    try:
        # Create room
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        room_data = response.json()
        room_code = room_data["code"]
        room_id = uuid.UUID(room_data["id"])

        # Join room
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms/join/{room_code}",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        try:
            # Get room state
            response = client.get(
                f"{settings.API_V1_STR}/fifoteca/rooms/{room_code}",
                headers=normal_user_token_headers,
            )
            assert response.status_code == 200
            content = response.json()

            # Verify room fields
            assert "id" in content
            assert "code" in content
            assert "status" in content
            assert "player_states" in content

            # Verify player states
            assert len(content["player_states"]) == 2

            # Verify state structure
            for state in content["player_states"]:
                assert "id" in state
                assert "room_id" in state
                assert "player_id" in state
                assert "round_number" in state
                assert "phase" in state
                assert "league_spins_remaining" in state
                assert "team_spins_remaining" in state
                assert "has_superspin" in state

            # Verify state values
            player1_state = next(
                (
                    s
                    for s in content["player_states"]
                    if s["player_id"] == str(player1_id)
                ),
                None,
            )
            player2_state = next(
                (
                    s
                    for s in content["player_states"]
                    if s["player_id"] == str(player2_id)
                ),
                None,
            )

            assert player1_state is not None
            assert player2_state is not None
            assert player1_state["league_spins_remaining"] == 3
            assert player1_state["team_spins_remaining"] == 3
            assert player1_state["phase"] == PlayerSpinPhase.LEAGUE_SPINNING

        finally:
            # Clean up room
            db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room_id))
            db.exec(
                delete(FifotecaPlayerState).where(
                    FifotecaPlayerState.room_id == room_id
                )
            )
            db.commit()

    finally:
        # Clean up players
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1_id))
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2_id))
        db.commit()


def test_get_room_not_found(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Test that GET returns 404 for non-existent room."""
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/rooms/INVALID",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404
    content = response.json()
    assert "Room not found" in content["detail"]


def test_get_room_expired(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test that GET returns 410 Gone for expired room."""
    # Create player profile
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    player_data = response.json()
    player_id = uuid.UUID(player_data["id"])

    try:
        # Create expired room directly
        room = FifotecaRoom(
            code="EXPIR1",
            ruleset="homebrew",
            status=RoomStatus.WAITING,
            player1_id=player_id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(room)
        db.commit()
        room_id = room.id

        try:
            # Try to get expired room - should return 410 Gone
            response = client.get(
                f"{settings.API_V1_STR}/fifoteca/rooms/EXPIR1",
                headers=normal_user_token_headers,
            )
            assert response.status_code == 410
            content = response.json()
            assert "expired" in content["detail"].lower()

            # Verify room was marked as COMPLETED
            db.refresh(room)
            assert room.status == RoomStatus.COMPLETED

        finally:
            # Clean up room
            db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room_id))
            db.commit()

    finally:
        # Clean up player
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player_id))
        db.commit()


def test_join_room_expired_returns_410(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """Test that joining an expired room returns 410 Gone."""
    # Create player profiles for two users
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    player_data = response.json()
    player1_id = uuid.UUID(player_data["id"])

    # Create second user
    user2 = User(
        email="joinexpired2@example.com",
        display_name="Join Expired 2",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user2)
    db.commit()
    db.refresh(user2)

    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Join Expired 2",
    )
    db.add(player2)
    db.commit()
    player2_id = player2.id

    try:
        # Create expired room directly
        room = FifotecaRoom(
            code="EXPJON",  # 6 chars max
            ruleset="homebrew",
            status=RoomStatus.WAITING,
            player1_id=player1_id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(room)
        db.commit()
        room_id = room.id

        try:
            # Try to join expired room - should return 410 Gone
            response = client.post(
                f"{settings.API_V1_STR}/fifoteca/rooms/join/EXPJON",
                headers=normal_user_token_headers,
            )
            assert response.status_code == 410
            content = response.json()
            assert "expired" in content["detail"].lower()

            # Verify room was marked as COMPLETED
            db.refresh(room)
            assert room.status == RoomStatus.COMPLETED

        finally:
            # Clean up room
            db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room_id))
            db.commit()

    finally:
        # Clean up players
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1_id))
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2_id))
        db.exec(delete(User).where(User.id == user2.id))
        db.commit()


def test_superspin_carried_from_protection(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Test that has_protection on FifotecaPlayer sets has_superspin on FifotecaPlayerState."""
    # Create players
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    player1_data = response.json()
    player1_id = uuid.UUID(player1_data["id"])

    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    player2_data = response.json()
    player2_id = uuid.UUID(player2_data["id"])

    try:
        # Set has_protection on player 2
        player2 = db.get(FifotecaPlayer, player2_id)
        if player2:
            player2.has_protection = True
            db.add(player2)
            db.commit()

        # Create room
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        room_data = response.json()
        room_code = room_data["code"]
        room_id = uuid.UUID(room_data["id"])

        # Join room
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/rooms/join/{room_code}",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        try:
            # Get player states
            player_states = db.exec(
                select(FifotecaPlayerState).where(
                    FifotecaPlayerState.room_id == room_id
                )
            ).all()

            player1_state = next(
                (ps for ps in player_states if ps.player_id == player1_id), None
            )
            player2_state = next(
                (ps for ps in player_states if ps.player_id == player2_id), None
            )

            assert player1_state is not None
            assert player2_state is not None

            # Player 1 should not have superspin
            assert player1_state.has_superspin is False

            # Player 2 should have superspin from protection
            assert player2_state.has_superspin is True

        finally:
            # Clean up room
            db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room_id))
            db.exec(
                delete(FifotecaPlayerState).where(
                    FifotecaPlayerState.room_id == room_id
                )
            )
            db.commit()

    finally:
        # Clean up players
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1_id))
        db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2_id))
        db.commit()


def test_openapi_includes_rooms_routes(client: TestClient) -> None:
    """Test that OpenAPI spec includes rooms endpoints."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    # Check that rooms paths are present
    assert "/api/v1/fifoteca/rooms" in spec["paths"]
    assert "/api/v1/fifoteca/rooms/join/{code}" in spec["paths"]
    assert "/api/v1/fifoteca/rooms/{code}" in spec["paths"]

    # Check rooms endpoint schema
    rooms_post = spec["paths"]["/api/v1/fifoteca/rooms"]["post"]
    assert "rooms" in rooms_post["tags"]

    rooms_join = spec["paths"]["/api/v1/fifoteca/rooms/join/{code}"]["post"]
    assert "rooms" in rooms_join["tags"]

    rooms_get = spec["paths"]["/api/v1/fifoteca/rooms/{code}"]["get"]
    assert "rooms" in rooms_get["tags"]


# ============================================================================
# Step 10: Match Endpoints
# ============================================================================


def test_submit_match_score_success(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S10.AC5: Submit score by participant succeeds."""
    # Setup: create players, room, teams, and match
    # Get the test user (created by the fixture if needed)
    from app import crud
    from app.models import UserCreate

    user1 = crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)

    # Create a second user for player2
    user2_email = "player2@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    # Commit user creation before creating players
    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    league = FifaLeague(name="Test League", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Team1",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="Team2",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    room = FifotecaRoom(
        code="TEST1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.MATCH_IN_PROGRESS,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.flush()

    match = FifotecaMatch(
        room_id=room.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
    )
    db.add(match)
    db.commit()

    # Submit scores
    score_data = MatchScoreSubmit(player1_score=3, player2_score=1)
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/score",
        json=score_data.model_dump(),
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    content = response.json()
    assert content["player1_score"] == 3
    assert content["player2_score"] == 1
    assert content["room_id"] == str(room.id)

    # Verify room status changed
    db.refresh(room)
    assert room.status == RoomStatus.SCORE_SUBMITTED

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_submit_match_score_non_participant_forbidden(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S10.AC6: Non-participant cannot submit scores."""
    # Setup: create players and match, but normal_user is not a participant
    # Import User creation utilities
    from app import crud
    from app.models import UserCreate

    # Create users for player1 and player2
    user1_email = "player1_non_participant@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_non_participant@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    # Commit user creation before creating players
    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    # Ensure normal_user (authenticated user) has a FifotecaPlayer record
    # so the endpoint doesn't 404 on player lookup
    normal_user = crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    if normal_user:
        normal_player = db.exec(
            select(FifotecaPlayer).where(FifotecaPlayer.user_id == normal_user.id)
        ).first()
        if not normal_player:
            normal_player = FifotecaPlayer(
                user_id=normal_user.id,
                display_name="Normal User",
                total_wins=0,
                total_losses=0,
                total_draws=0,
                has_protection=False,
            )
            db.add(normal_player)
            db.flush()

    league = FifaLeague(name="Test League", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Team1",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="Team2",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    room = FifotecaRoom(
        code="TEST1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.MATCH_IN_PROGRESS,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.flush()

    match = FifotecaMatch(
        room_id=room.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
    )
    db.add(match)
    db.commit()

    # Try to submit scores as non-participant
    score_data = MatchScoreSubmit(player1_score=3, player2_score=1)
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/score",
        json=score_data.model_dump(),
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
    content = response.json()
    assert "not a participant" in content["detail"].lower()

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_submit_match_score_already_submitted(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S10.AC7: Cannot submit scores if already submitted."""
    # Setup: create match with already submitted scores
    # Setup: create match with already submitted scores
    # Import User creation utilities
    from app import crud
    from app.models import UserCreate

    # Create users for player1 and player2
    user1_email = "player1_already_submitted@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_already_submitted@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    # Commit user creation before creating players
    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    league = FifaLeague(name="Test League", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Team1",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="Team2",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    room = FifotecaRoom(
        code="TEST1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.MATCH_IN_PROGRESS,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.flush()

    match = FifotecaMatch(
        room_id=room.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        player1_score=3,
        player2_score=1,
        submitted_by_id=player1.id,
    )
    db.add(match)
    db.commit()

    # Link player1 to normal_user
    from app.models import User

    user = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).first()
    if user:
        player1.user_id = user.id
        db.add(player1)
        db.commit()

    # Try to submit scores again
    score_data = MatchScoreSubmit(player1_score=2, player2_score=2)
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/score",
        json=score_data.model_dump(),
        headers=normal_user_token_headers,
    )

    assert response.status_code == 400
    content = response.json()
    assert "already submitted" in content["detail"].lower()

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_confirm_match_submitting_player_forbidden(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S10.AC8: Submitting player cannot confirm their own scores."""
    # Setup: create match with scores submitted by player1
    # Setup: create match with submitted scores
    # Import User creation utilities
    from app import crud
    from app.models import UserCreate

    # Create users for player1 and player2
    user1_email = "player1_submitting_forbidden@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_submitting_forbidden@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    # Commit user creation before creating players
    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    league = FifaLeague(name="Test League", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Team1",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="Team2",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    room = FifotecaRoom(
        code="TEST1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.SCORE_SUBMITTED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.flush()

    match = FifotecaMatch(
        room_id=room.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        player1_score=3,
        player2_score=1,
        submitted_by_id=player1.id,
    )
    db.add(match)
    db.commit()

    # Link player1 to normal_user
    from app.models import User

    user = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).first()
    if user:
        player1.user_id = user.id
        db.add(player1)
        db.commit()

    # Try to confirm as submitting player
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/confirm",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
    content = response.json()
    assert "cannot confirm" in content["detail"].lower()

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_confirm_match_success(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S10.AC9: Non-submitting player can confirm and updates stats."""
    # Setup: create match with scores submitted by player1
    # Setup: create match with submitted scores
    # Import User creation utilities
    from app import crud
    from app.models import UserCreate

    # Create users for player1 and player2
    user1_email = "player1_confirm_success@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_confirm_success@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    # Commit user creation before creating players
    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    league = FifaLeague(name="Test League", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Team1",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="Team2",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    room = FifotecaRoom(
        code="TEST1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.SCORE_SUBMITTED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.flush()

    match = FifotecaMatch(
        room_id=room.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        player1_score=3,
        player2_score=1,
        submitted_by_id=player1.id,
    )
    db.add(match)
    db.commit()

    # Link player2 to normal_user (non-submitting player)
    from app.models import User

    user = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).first()
    if user:
        player2.user_id = user.id
        db.add(player2)
        db.commit()

    # Confirm as non-submitting player
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/confirm",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    content = response.json()
    assert content["confirmed"] is True

    # Verify match confirmed
    db.refresh(match)
    assert match.confirmed is True

    # Verify room status
    db.refresh(room)
    assert room.status == RoomStatus.COMPLETED

    # Verify player stats updated (player1 won, player2 lost)
    db.refresh(player1)
    db.refresh(player2)
    assert player1.total_wins == 1
    assert player1.total_losses == 0
    assert player1.total_draws == 0
    assert player2.total_wins == 0
    assert player2.total_losses == 1
    assert player2.total_draws == 0

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_confirm_match_draw_updates_stats(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S10.AC10: Confirming a draw updates stats correctly."""
    # Setup: create match with draw score
    # Setup: create match with draw scores
    # Import User creation utilities
    from app import crud
    from app.models import UserCreate

    # Create users for player1 and player2
    user1_email = "player1_draw_stats@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_draw_stats@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    # Commit user creation before creating players
    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    league = FifaLeague(name="Test League", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Team1",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="Team2",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    room = FifotecaRoom(
        code="TEST1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.SCORE_SUBMITTED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.flush()

    match = FifotecaMatch(
        room_id=room.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        player1_score=2,
        player2_score=2,
        submitted_by_id=player1.id,
    )
    db.add(match)
    db.commit()

    # Link player2 to normal_user
    from app.models import User

    user = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).first()
    if user:
        player2.user_id = user.id
        db.add(player2)
        db.commit()

    # Confirm draw
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/confirm",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200

    # Verify both players got a draw
    db.refresh(player1)
    db.refresh(player2)
    assert player1.total_wins == 0
    assert player1.total_losses == 0
    assert player1.total_draws == 1
    assert player2.total_wins == 0
    assert player2.total_losses == 0
    assert player2.total_draws == 1

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_list_matches_returns_player_matches(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S10.AC11: GET /matches returns only caller matches, newest first."""
    # Setup: create players and multiple matches
    # Setup: create players and match for user1
    # Import User creation utilities
    from app import crud
    from app.models import UserCreate

    # Create users for player1 and player2
    user1_email = "player1_list_matches@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_list_matches@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    # Commit user creation before creating players
    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    # Create user for player3
    user3_email = "player3_list_matches@example.com"
    user3 = crud.get_user_by_email(session=db, email=user3_email)
    if not user3:
        user3_in = UserCreate(email=user3_email, password="testpass123")
        user3 = crud.create_user(session=db, user_create=user3_in)

    # Commit user creation before creating player3
    db.commit()

    player3 = FifotecaPlayer(
        user_id=user3.id,
        display_name="Player3",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.add(player3)
    db.flush()

    league = FifaLeague(name="Test League", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Team1",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="Team2",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    # Create room and match for player1 vs player2
    room1 = FifotecaRoom(
        code="TEST1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room1)
    db.flush()

    match1 = FifotecaMatch(
        room_id=room1.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match1)
    db.flush()

    # Create room and match for player2 vs player3 (player1 not involved)
    room2 = FifotecaRoom(
        code="TEST45",
        ruleset="standard",
        player1_id=player2.id,
        player2_id=player3.id,
        current_turn_player_id=player2.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room2)
    db.flush()

    match2 = FifotecaMatch(
        room_id=room2.id,
        round_number=1,
        player1_id=player2.id,
        player2_id=player3.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match2)
    db.flush()

    # Link player1 to normal_user
    from app.models import User

    user = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).first()
    if user:
        player1.user_id = user.id
        db.add(player1)
        db.commit()

    # List matches
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/matches",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert len(content["data"]) == 1

    # Verify enriched history fields (S18)
    match_data = content["data"][0]
    assert match_data["id"] == str(match1.id)
    assert "opponent_display_name" in match_data
    assert match_data["opponent_display_name"] == "Player2"
    assert "my_team_name" in match_data
    assert match_data["my_team_name"] == "Team1"
    assert "opponent_team_name" in match_data
    assert match_data["opponent_team_name"] == "Team2"
    assert "my_score" in match_data
    assert "opponent_score" in match_data
    assert "result" in match_data
    assert "confirmed" in match_data
    assert "rating_difference" in match_data
    assert "round_number" in match_data
    assert "created_at" in match_data

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match1.id))
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match2.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room1.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room2.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player3.id))
    db.commit()


def test_list_matches_enriched_result_calculation(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S18: Verify win/loss/draw result calculation in match history."""
    from app import crud
    from app.models import User, UserCreate

    # Create users
    user1_email = "player1_result_calc@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_result_calc@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    league = FifaLeague(name="Test League Result", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="TeamA",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="TeamB",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    # Create a WIN match for player1 (3-1)
    room1 = FifotecaRoom(
        code="WIN1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room1)
    db.flush()

    match_win = FifotecaMatch(
        room_id=room1.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        player1_score=3,
        player2_score=1,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match_win)
    db.flush()

    # Create a LOSS match for player1 (0-2)
    room2 = FifotecaRoom(
        code="LOSS1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room2)
    db.flush()

    match_loss = FifotecaMatch(
        room_id=room2.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        player1_score=0,
        player2_score=2,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match_loss)
    db.flush()

    # Create a DRAW match for player1 (2-2)
    room3 = FifotecaRoom(
        code="DRAW1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room3)
    db.flush()

    match_draw = FifotecaMatch(
        room_id=room3.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        player1_score=2,
        player2_score=2,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match_draw)
    db.flush()

    # Link player1 to normal_user
    user = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).first()
    if user:
        player1.user_id = user.id
        db.add(player1)
        db.commit()

    # List matches
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/matches",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 3
    assert len(content["data"]) == 3

    # Build a map of match id to result
    results = {m["id"]: m for m in content["data"]}

    # Verify win result
    win_match = results[str(match_win.id)]
    assert win_match["my_score"] == 3
    assert win_match["opponent_score"] == 1
    assert win_match["result"] == "win"

    # Verify loss result
    loss_match = results[str(match_loss.id)]
    assert loss_match["my_score"] == 0
    assert loss_match["opponent_score"] == 2
    assert loss_match["result"] == "loss"

    # Verify draw result
    draw_match = results[str(match_draw.id)]
    assert draw_match["my_score"] == 2
    assert draw_match["opponent_score"] == 2
    assert draw_match["result"] == "draw"

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match_win.id))
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match_loss.id))
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match_draw.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room1.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room2.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room3.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_list_matches_sorted_newest_first(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S18.AC2: Verify matches are sorted by created_at descending."""
    from app import crud
    from app.models import User, UserCreate

    # Create users
    user1_email = "player1_sorted@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_sorted@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    league = FifaLeague(name="Test League Sorted", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="TeamX",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="TeamY",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    # Create 3 matches with slight time difference to ensure order
    import time

    room1 = FifotecaRoom(
        code="ORDR1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room1)
    db.flush()

    match1 = FifotecaMatch(
        room_id=room1.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match1)
    db.commit()
    time.sleep(0.01)  # Small delay to ensure different created_at

    room2 = FifotecaRoom(
        code="ORDR2",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room2)
    db.flush()

    match2 = FifotecaMatch(
        room_id=room2.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match2)
    db.commit()
    time.sleep(0.01)

    room3 = FifotecaRoom(
        code="ORDR3",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room3)
    db.flush()

    match3 = FifotecaMatch(
        room_id=room3.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match3)
    db.commit()

    # Link player1 to normal_user
    user = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).first()
    if user:
        player1.user_id = user.id
        db.add(player1)
        db.commit()

    # List matches
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/matches",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 3

    # Verify newest first ordering (match3 should be first)
    ids = [m["id"] for m in content["data"]]
    assert ids[0] == str(match3.id)
    assert ids[1] == str(match2.id)
    assert ids[2] == str(match1.id)

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match1.id))
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match2.id))
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match3.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room1.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room2.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room3.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_get_match_participant_allowed(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S10.AC12: GET /matches/{id} allowed for participant."""
    # Setup: create player, room, team, and match
    # Setup: create match
    # Import User creation utilities
    from app import crud
    from app.models import UserCreate

    # Create users for player1 and player2
    user1_email = "player1_get_allowed@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_get_allowed@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    # Commit user creation before creating players
    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    league = FifaLeague(name="Test League", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Team1",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="Team2",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    room = FifotecaRoom(
        code="TEST1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.flush()

    match = FifotecaMatch(
        room_id=room.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match)
    db.commit()

    # Link player1 to normal_user
    from app.models import User

    user = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).first()
    if user:
        player1.user_id = user.id
        db.add(player1)
        db.commit()

    # Get match detail
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/matches/{match.id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    content = response.json()
    assert content["id"] == str(match.id)
    assert content["player1_team_id"] == str(team1.id)
    assert content["player2_team_id"] == str(team2.id)

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_get_match_outsider_forbidden(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """S10.AC13: GET /matches/{id} forbidden for non-participant."""
    # Setup: create match where normal_user is not a participant
    # Setup: create match, but normal_user is not a participant
    # Import User creation utilities
    from app import crud
    from app.models import UserCreate

    # Create users for player1 and player2
    user1_email = "player1_outsider_forbidden@example.com"
    user1 = crud.get_user_by_email(session=db, email=user1_email)
    if not user1:
        user1_in = UserCreate(email=user1_email, password="testpass123")
        user1 = crud.create_user(session=db, user_create=user1_in)

    user2_email = "player2_outsider_forbidden@example.com"
    user2 = crud.get_user_by_email(session=db, email=user2_email)
    if not user2:
        user2_in = UserCreate(email=user2_email, password="testpass123")
        user2 = crud.create_user(session=db, user_create=user2_in)

    # Commit user creation before creating players
    # Ensure normal_user has a FifotecaPlayer record
    normal_user = crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    if normal_user:
        normal_player = db.exec(
            select(FifotecaPlayer).where(FifotecaPlayer.user_id == normal_user.id)
        ).first()
        if not normal_player:
            normal_player = FifotecaPlayer(
                user_id=normal_user.id,
                display_name="Normal User",
                total_wins=0,
                total_losses=0,
                total_draws=0,
                has_protection=False,
            )
            db.add(normal_player)
            db.flush()

    db.commit()

    player1 = FifotecaPlayer(
        user_id=user1.id,
        display_name="Player1",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    player2 = FifotecaPlayer(
        user_id=user2.id,
        display_name="Player2",
        total_wins=0,
        total_losses=0,
        total_draws=0,
        has_protection=False,
    )
    db.add(player1)
    db.add(player2)
    db.flush()

    league = FifaLeague(name="Test League", country="Test")
    db.add(league)
    db.flush()

    team1 = FifaTeam(
        name="Team1",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    team2 = FifaTeam(
        name="Team2",
        league_id=league.id,
        attack_rating=80,
        midfield_rating=80,
        defense_rating=80,
        overall_rating=240,
    )
    db.add(team1)
    db.add(team2)
    db.flush()

    room = FifotecaRoom(
        code="TEST1",
        ruleset="standard",
        player1_id=player1.id,
        player2_id=player2.id,
        current_turn_player_id=player1.id,
        status=RoomStatus.COMPLETED,
        round_number=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(room)
    db.flush()

    match = FifotecaMatch(
        room_id=room.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        player1_team_id=team1.id,
        player2_team_id=team2.id,
        rating_difference=0,
        confirmed=True,
    )
    db.add(match)
    db.commit()

    # Try to get match detail as outsider
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/matches/{match.id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
    content = response.json()
    assert "not a participant" in content["detail"].lower()

    # Clean up
    db.exec(delete(FifotecaMatch).where(FifotecaMatch.id == match.id))
    db.exec(delete(FifotecaRoom).where(FifotecaRoom.id == room.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team1.id))
    db.exec(delete(FifaTeam).where(FifaTeam.id == team2.id))
    db.exec(delete(FifaLeague).where(FifaLeague.id == league.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player1.id))
    db.exec(delete(FifotecaPlayer).where(FifotecaPlayer.id == player2.id))
    db.commit()


def test_openapi_includes_matches_routes(client: TestClient) -> None:
    """Test that OpenAPI spec includes matches endpoints."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    # Check that matches paths are present
    assert "/api/v1/fifoteca/matches" in spec["paths"]
    assert "/api/v1/fifoteca/matches/{id}" in spec["paths"]
    assert "/api/v1/fifoteca/matches/{id}/score" in spec["paths"]
    assert "/api/v1/fifoteca/matches/{id}/confirm" in spec["paths"]

    # Check matches endpoint tags
    matches_get = spec["paths"]["/api/v1/fifoteca/matches"]["get"]
    assert "matches" in matches_get["tags"]

    matches_score = spec["paths"]["/api/v1/fifoteca/matches/{id}/score"]["post"]
    assert "matches" in matches_score["tags"]

    matches_confirm = spec["paths"]["/api/v1/fifoteca/matches/{id}/confirm"]["post"]
    assert "matches" in matches_confirm["tags"]
