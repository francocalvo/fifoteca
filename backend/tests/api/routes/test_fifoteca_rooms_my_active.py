"""Tests for GET /fifoteca/rooms/my-active.

The endpoint powers the frontend "Resume Game" card: it returns the
current player's non-expired, non-COMPLETED rooms.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.models import FifotecaRoom, RoomStatus


def _create_profile(client: TestClient, headers: dict[str, str]) -> uuid.UUID:
    """Create the player profile for the authenticated user."""
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/players/me",
        headers=headers,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["id"])


def _create_room(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    """Create a room owned by the authenticated user and return its payload."""
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/rooms",
        headers=headers,
    )
    assert response.status_code == 200
    return cast(dict[str, Any], response.json())


def _get_my_active(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch the current player's active rooms."""
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/rooms/my-active",
        headers=headers,
    )
    assert response.status_code == 200
    content = cast(list[dict[str, Any]], response.json())
    assert isinstance(content, list)
    return content


def test_my_active_returns_active_room(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A participant sees their own active room."""
    _create_profile(client, normal_user_token_headers)
    room = _create_room(client, normal_user_token_headers)

    content = _get_my_active(client, normal_user_token_headers)

    assert len(content) == 1
    assert content[0]["code"] == room["code"]
    assert content[0]["status"] == RoomStatus.WAITING


def test_my_active_includes_joined_room(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """A player who joined as player2 also sees the room."""
    _create_profile(client, normal_user_token_headers)
    room = _create_room(client, normal_user_token_headers)

    _create_profile(client, superuser_token_headers)
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/rooms/join/{room['code']}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200

    content = _get_my_active(client, superuser_token_headers)

    assert len(content) == 1
    assert content[0]["code"] == room["code"]


def test_my_active_excludes_expired_room(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """An expired room is not offered as resumable."""
    _create_profile(client, normal_user_token_headers)
    room = _create_room(client, normal_user_token_headers)

    db_room = db.get(FifotecaRoom, uuid.UUID(room["id"]))
    assert db_room is not None
    db_room.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.add(db_room)
    db.commit()

    content = _get_my_active(client, normal_user_token_headers)

    assert content == []


def test_my_active_excludes_completed_room(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """A COMPLETED room is not offered as resumable."""
    _create_profile(client, normal_user_token_headers)
    room = _create_room(client, normal_user_token_headers)

    db_room = db.get(FifotecaRoom, uuid.UUID(room["id"]))
    assert db_room is not None
    db_room.status = RoomStatus.COMPLETED
    db.add(db_room)
    db.commit()

    content = _get_my_active(client, normal_user_token_headers)

    assert content == []


def test_my_active_excludes_other_players_rooms(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """A player never sees rooms they do not participate in."""
    _create_profile(client, normal_user_token_headers)
    room = _create_room(client, normal_user_token_headers)

    _create_profile(client, superuser_token_headers)

    content = _get_my_active(client, superuser_token_headers)

    assert content == []
    assert room["code"] not in [item["code"] for item in content]


def test_my_active_without_profile_returns_404(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A user without a player profile cannot list active rooms."""
    response = client.get(
        f"{settings.API_V1_STR}/fifoteca/rooms/my-active",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 404
    assert "Player profile not found" in response.json()["detail"]


def test_my_active_orders_newest_room_first(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    """With several active rooms, the most recently created one comes first."""
    _create_profile(client, normal_user_token_headers)
    older_room = _create_room(client, normal_user_token_headers)
    newer_room = _create_room(client, normal_user_token_headers)

    # Backdate the first room so the ordering assertion is deterministic.
    db_room = db.get(FifotecaRoom, uuid.UUID(older_room["id"]))
    assert db_room is not None
    db_room.created_at = datetime.now(UTC) - timedelta(hours=1)
    db.add(db_room)
    db.commit()

    content = _get_my_active(client, normal_user_token_headers)

    assert [item["code"] for item in content] == [
        newer_room["code"],
        older_room["code"],
    ]


def test_my_active_requires_authentication(client: TestClient) -> None:
    """The endpoint rejects unauthenticated requests."""
    response = client.get(f"{settings.API_V1_STR}/fifoteca/rooms/my-active")

    assert response.status_code == 401
