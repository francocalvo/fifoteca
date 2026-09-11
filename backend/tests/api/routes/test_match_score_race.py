"""Regression tests for the score-state race between submit, contest and confirm.

The endpoints in ``app.api.routes.fifoteca.matches`` read the match, validate
guards on the in-memory object and then write. Two clients acting at once (one
clicking "Confirm Score" while the other clicks "Edit Score") used to interleave
between the read and the commit, which could persist ``confirmed=True`` together
with NULL scores, report that match as a draw, and leave the room stuck in
MATCH_IN_PROGRESS with no way to reach COMPLETED.

Each race below is made deterministic by patching ``get_match_by_id`` so the
competing write lands exactly between the endpoint's read and its write. The
competing write runs in its own session (``_competing_confirm`` /
``_competing_contest``), which is what the other request would have committed.
"""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.api.routes.fifoteca import matches as matches_module
from app.core.config import settings
from app.core.db import engine
from app.models import (
    FifotecaMatch,
    FifotecaPlayer,
    FifotecaRoom,
    MatchScoreSubmit,
    RoomStatus,
)
from tests.api.routes.test_fifoteca import _cleanup_match_setup, _create_match_setup


def _competing_confirm(match_id: uuid.UUID) -> None:
    """Commit the opponent's confirmation in a separate session."""
    with Session(engine) as competing_session:
        competing_match = competing_session.get(FifotecaMatch, match_id)
        assert competing_match is not None
        competing_match.confirmed = True
        competing_room = competing_session.get(FifotecaRoom, competing_match.room_id)
        assert competing_room is not None
        competing_room.status = RoomStatus.COMPLETED
        competing_session.add(competing_match)
        competing_session.add(competing_room)
        competing_session.commit()


def _competing_contest(match_id: uuid.UUID) -> None:
    """Commit the submitter's contest in a separate session."""
    with Session(engine) as competing_session:
        competing_match = competing_session.get(FifotecaMatch, match_id)
        assert competing_match is not None
        competing_match.player1_score = None
        competing_match.player2_score = None
        competing_match.submitted_by_id = None
        competing_room = competing_session.get(FifotecaRoom, competing_match.room_id)
        assert competing_room is not None
        competing_room.status = RoomStatus.MATCH_IN_PROGRESS
        competing_session.add(competing_match)
        competing_session.add(competing_room)
        competing_session.commit()


def _player2_headers(client: TestClient) -> dict[str, str]:
    """Log in the second test user created by _create_match_setup."""
    response = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "player2@example.com", "password": "testpass123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _submit_scores(
    client: TestClient,
    headers: dict[str, str],
    match_id: Any,
    player1_score: int,
    player2_score: int,
) -> None:
    """Submit a score as the given player and assert it was accepted."""
    response = client.post(
        f"{settings.API_V1_STR}/fifoteca/matches/{match_id}/score",
        json=MatchScoreSubmit(
            player1_score=player1_score, player2_score=player2_score
        ).model_dump(),
        headers=headers,
    )
    assert response.status_code == 200


def test_contest_after_confirm_is_rejected_and_keeps_confirmed_state(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
    monkeypatch: Any,
) -> None:
    """A contest that loses the race to a confirm must not null out the result.

    Interleaving: contest reads the unconfirmed submission, the opponent's
    confirm commits (confirmed=True, room COMPLETED), then contest tries to
    clear the scores. The conditional update must match no rows.
    """
    setup = _create_match_setup(db, room_code="RACE1", league_name="Race League")
    match: FifotecaMatch = setup["match"]
    room: FifotecaRoom = setup["room"]
    original_get_match_by_id = matches_module.get_match_by_id
    state = {"raced": False}

    def get_match_by_id_racing_with_confirm(
        session: Session, match_id: Any
    ) -> FifotecaMatch:
        # Read first: this is the (stale) state the endpoint will act on.
        stale = original_get_match_by_id(session, match_id)
        if not state["raced"]:
            state["raced"] = True
            # Now the opponent's confirm request commits before we write.
            _competing_confirm(match_id)
        return stale

    try:
        _submit_scores(client, normal_user_token_headers, match.id, 3, 1)
        assert state["raced"] is False

        monkeypatch.setattr(
            matches_module, "get_match_by_id", get_match_by_id_racing_with_confirm
        )
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/contest",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 409
        assert "changed" in response.json()["detail"].lower()
        assert state["raced"] is True

        # The confirmed result survived: scores intact, still confirmed.
        db.refresh(match)
        assert match.confirmed is True
        assert match.player1_score == 3
        assert match.player2_score == 1

        # And the room is not dragged back into an in-progress state.
        db.refresh(room)
        assert room.status == RoomStatus.COMPLETED

        # A follow-up submit is still refused, so the room cannot be revived.
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/score",
            json=MatchScoreSubmit(player1_score=0, player2_score=5).model_dump(),
            headers=normal_user_token_headers,
        )
        assert response.status_code == 400
    finally:
        _cleanup_match_setup(db, setup)


def test_confirm_losing_race_to_contest_counts_no_stats(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
    monkeypatch: Any,
) -> None:
    """A confirm that loses the race to a contest must not count a result.

    Interleaving: confirm reads the submission, the submitter's contest commits
    (scores cleared), then confirm tries to confirm the vanished submission. It
    must neither confirm nor touch player totals, so confirmed=True can never
    coexist with NULL scores.
    """
    setup = _create_match_setup(db, room_code="RACE2", league_name="Race League 2")
    match: FifotecaMatch = setup["match"]
    room: FifotecaRoom = setup["room"]
    player1: FifotecaPlayer = setup["player1"]
    player2: FifotecaPlayer = setup["player2"]
    original_get_match_by_id = matches_module.get_match_by_id
    state = {"raced": False}

    def get_match_by_id_racing_with_contest(
        session: Session, match_id: Any
    ) -> FifotecaMatch:
        stale = original_get_match_by_id(session, match_id)
        if not state["raced"]:
            state["raced"] = True
            # Now the submitter's contest request commits before we write.
            _competing_contest(match_id)
        return stale

    try:
        _submit_scores(client, normal_user_token_headers, match.id, 3, 1)
        player2_headers = _player2_headers(client)

        monkeypatch.setattr(
            matches_module, "get_match_by_id", get_match_by_id_racing_with_contest
        )
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/confirm",
            headers=player2_headers,
        )
        assert response.status_code == 409
        assert "changed" in response.json()["detail"].lower()
        assert state["raced"] is True

        # No result was recorded: the match is not confirmed and has no scores.
        db.refresh(match)
        assert match.confirmed is False
        assert match.player1_score is None
        assert match.player2_score is None

        # No stats were counted for either player.
        db.refresh(player1)
        db.refresh(player2)
        assert (player1.total_wins, player1.total_losses, player1.total_draws) == (
            0,
            0,
            0,
        )
        assert (player2.total_wins, player2.total_losses, player2.total_draws) == (
            0,
            0,
            0,
        )

        # The room stays resumable instead of being closed as COMPLETED.
        db.refresh(room)
        assert room.status == RoomStatus.MATCH_IN_PROGRESS

        # The score can be entered again and confirmed normally.
        _submit_scores(client, normal_user_token_headers, match.id, 2, 0)
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/confirm",
            headers=player2_headers,
        )
        assert response.status_code == 200
        db.refresh(match)
        assert match.confirmed is True
        assert match.player1_score == 2
        assert match.player2_score == 0
        db.refresh(room)
        assert room.status == RoomStatus.COMPLETED
    finally:
        _cleanup_match_setup(db, setup)


def test_second_confirm_is_rejected_without_double_counting(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Two confirms in a row: the second returns 400 and counts no extra wins."""
    setup = _create_match_setup(db, room_code="RACE3", league_name="Race League 3")
    match: FifotecaMatch = setup["match"]
    player1: FifotecaPlayer = setup["player1"]
    player2: FifotecaPlayer = setup["player2"]

    try:
        _submit_scores(client, normal_user_token_headers, match.id, 3, 1)
        player2_headers = _player2_headers(client)

        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/confirm",
            headers=player2_headers,
        )
        assert response.status_code == 200

        second = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/confirm",
            headers=player2_headers,
        )
        assert second.status_code == 400
        assert "confirmed" in second.json()["detail"].lower()

        db.refresh(player1)
        db.refresh(player2)
        assert player1.total_wins == 1
        assert player2.total_losses == 1
        db.refresh(match)
        assert match.player1_score == 3
        assert match.player2_score == 1
    finally:
        _cleanup_match_setup(db, setup)


def test_list_matches_reports_pending_when_confirmed_without_scores(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """A confirmed match with no scores is reported as pending, never a draw."""
    setup = _create_match_setup(db, room_code="RACE4", league_name="Race League 4")
    match: FifotecaMatch = setup["match"]

    try:
        # Defensive layer: a corrupted/lost score update must not read as draw.
        match.confirmed = True
        match.submitted_by_id = setup["player2"].id
        match.player1_score = None
        match.player2_score = None
        db.add(match)
        db.commit()

        response = client.get(
            f"{settings.API_V1_STR}/fifoteca/matches/",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        match_data = next(
            (m for m in response.json()["data"] if m["id"] == str(match.id)), None
        )
        assert match_data is not None
        assert match_data["confirmed"] is True
        assert match_data["my_score"] is None
        assert match_data["opponent_score"] is None
        assert match_data["result"] == "pending"
    finally:
        _cleanup_match_setup(db, setup)


def test_no_confirmed_match_without_scores_exists_after_contest_confirm(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Invariant: contest then confirm leaves no confirmed match without scores."""
    setup = _create_match_setup(db, room_code="RACE5", league_name="Race League 5")
    match: FifotecaMatch = setup["match"]

    try:
        _submit_scores(client, normal_user_token_headers, match.id, 1, 0)

        # Contest then confirm is the supported recovery path.
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/contest",
            headers=normal_user_token_headers,
        )
        assert response.status_code == 200
        _submit_scores(client, normal_user_token_headers, match.id, 0, 1)
        player2_headers = _player2_headers(client)
        response = client.post(
            f"{settings.API_V1_STR}/fifoteca/matches/{match.id}/confirm",
            headers=player2_headers,
        )
        assert response.status_code == 200

        # The invariant that motivated the atomic transitions: no confirmed
        # match may exist without both scores, so no history row can report
        # "draw" while the persisted stats hold a real result.
        confirmed_without_scores = db.exec(
            select(FifotecaMatch).where(
                col(FifotecaMatch.confirmed).is_(True),
                col(FifotecaMatch.player1_score).is_(None),
            )
        ).all()
        assert confirmed_without_scores == []

        db.refresh(match)
        assert match.confirmed is True
        assert match.player1_score == 0
        assert match.player2_score == 1
    finally:
        _cleanup_match_setup(db, setup)
