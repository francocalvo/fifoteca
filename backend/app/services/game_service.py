"""GameService for Fifoteca game state and snapshots.

This service handles game state serialization for WebSocket synchronization
and game action orchestration.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlmodel import Session, and_, select

from app.models import (
    FifaLeague,
    FifaTeam,
    FifotecaMatch,
    FifotecaPlayer,
    FifotecaPlayerState,
    FifotecaRoom,
    PlayerSpinPhase,
    RoomStatus,
)


def check_room_expiry(room: FifotecaRoom, session: Session) -> None:
    """Check if room is expired and handle accordingly.

    If room is expired:
    - Mark room status as COMPLETED if not already
    - Raise HTTPException with 410 Gone

    Args:
        room: The room to check.
        session: Database session.

    Raises:
        HTTPException: 410 Gone if room has expired.
    """
    now = datetime.now(timezone.utc)
    if room.expires_at < now:
        # Mark as completed if not already
        if room.status != RoomStatus.COMPLETED:
            room.status = RoomStatus.COMPLETED
            session.add(room)
            session.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Room has expired",
        )


# Game action exceptions - these are caught by WebSocket handlers
# and converted to error messages with deterministic codes
class GameActionError(HTTPException):
    """Base exception for game action validation errors."""

    def __init__(self, code: str, message: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
        self.code = code


class NotYourTurnError(GameActionError):
    """Raised when a player attempts to act outside their turn."""

    def __init__(self):
        super().__init__("NOT_YOUR_TURN", "It's not your turn")


class InvalidActionError(GameActionError):
    """Raised when an action is not valid for the current game phase."""

    def __init__(self, action_type: str, current_phase: str):
        message = f"Action '{action_type}' not valid in phase '{current_phase}'"
        super().__init__("INVALID_ACTION", message)


class GameService:
    """Service for Fifoteca game state management."""

    @staticmethod
    def _get_opponent_state(
        session: Session, room: FifotecaRoom, player_id: uuid.UUID, round_number: int
    ) -> FifotecaPlayerState:
        """Get opponent's player state for the current round.

        Args:
            session: Database session.
            room: The room object.
            player_id: The current player's ID.
            round_number: The current round number.

        Returns:
            The opponent's FifotecaPlayerState.

        Raises:
            HTTPException: If opponent state not found.
        """
        # Get opponent player ID
        if room.player1_id == player_id:
            opponent_id = room.player2_id
        else:
            opponent_id = room.player1_id

        if not opponent_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Opponent not found"
            )

        # Get opponent state
        statement = select(FifotecaPlayerState).where(
            and_(
                FifotecaPlayerState.room_id == room.id,
                FifotecaPlayerState.player_id == opponent_id,
                FifotecaPlayerState.round_number == round_number,
            )
        )
        opponent_state = session.exec(statement).first()

        if not opponent_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Opponent state not found"
            )

        return opponent_state

    @staticmethod
    def _compute_rating_review(
        session: Session, room: FifotecaRoom, *, award_parity_spin: bool = True
    ) -> dict | None:
        """Compute rating comparison and protection/parity awards.

        Args:
            session: Database session.
            room: The room object.
            award_parity_spin: Whether to award parity spin. Should be True
                only on the initial phase transition, and False on
                recomputations after special spins to prevent both players
                from receiving parity spins in the same round.

        Returns:
            Dictionary with rating review data, or None if teams not locked.
        """
        # Get both player states for current round
        statement = select(FifotecaPlayerState).where(
            and_(
                FifotecaPlayerState.room_id == room.id,
                FifotecaPlayerState.round_number == room.round_number,
            )
        )
        player_states = session.exec(statement).all()

        if len(player_states) < 2:
            return None

        # Check both teams locked
        if not all(state.team_locked for state in player_states):
            return None

        # Match states to room player order (DB query order is not guaranteed)
        p1_state = next(
            (s for s in player_states if s.player_id == room.player1_id), None
        )
        p2_state = next(
            (s for s in player_states if s.player_id == room.player2_id), None
        )

        if not p1_state or not p2_state:
            return None

        p1_team = session.get(FifaTeam, p1_state.current_team_id)
        p2_team = session.get(FifaTeam, p2_state.current_team_id)

        if not p1_team or not p2_team:
            return None

        # Calculate rating difference
        rating_difference = abs(p1_team.overall_rating - p2_team.overall_rating)

        # Determine weaker player
        if p1_team.overall_rating < p2_team.overall_rating:
            weaker_state = p1_state
            weaker_player_id = room.player1_id
        else:
            weaker_state = p2_state
            weaker_player_id = room.player2_id

        # Protection preview (diff >= 5) — actual has_protection is set
        # when the match is created, not here, since special spins can change teams.
        protection_awarded_to_id = None
        if rating_difference >= 5:
            protection_awarded_to_id = weaker_player_id

        # Award parity spin at diff >= 30 (only on initial computation)
        parity_available_to_id = None
        if rating_difference >= 30 and not weaker_state.parity_spin_used:
            if award_parity_spin:
                weaker_state.has_parity_spin = True
                session.add(weaker_state)
            # Report parity availability if the weaker player already has it
            # (from initial award) or we just awarded it
            if weaker_state.has_parity_spin:
                parity_available_to_id = weaker_player_id

        # Superspin availability (check who has it)
        superspin_available_to_id = None
        if p1_state.has_superspin and not p1_state.superspin_used:
            superspin_available_to_id = room.player1_id
        elif p2_state.has_superspin and not p2_state.superspin_used:
            superspin_available_to_id = room.player2_id

        session.commit()

        # Build rating review payload
        return {
            "p1_team": {
                "id": str(p1_team.id),
                "name": p1_team.name,
                "overall_rating": p1_team.overall_rating,
            },
            "p2_team": {
                "id": str(p2_team.id),
                "name": p2_team.name,
                "overall_rating": p2_team.overall_rating,
            },
            "difference": rating_difference,
            "protection_awarded_to_id": (
                str(protection_awarded_to_id) if protection_awarded_to_id else None
            ),
            "parity_available_to_id": (
                str(parity_available_to_id) if parity_available_to_id else None
            ),
            "superspin_available_to_id": (
                str(superspin_available_to_id) if superspin_available_to_id else None
            ),
        }

    @staticmethod
    def _create_match_for_current_round(
        session: Session, room: FifotecaRoom
    ) -> FifotecaMatch:
        """Create a match record for the current room round.

        Args:
            session: Database session.
            room: The room object.

        Returns:
            The created or existing FifotecaMatch.

        Raises:
            HTTPException: If player states or teams not found.
        """
        # Check if match already exists (idempotency)
        statement = select(FifotecaMatch).where(
            and_(
                FifotecaMatch.room_id == room.id,
                FifotecaMatch.round_number == room.round_number,
            )
        )
        existing_match = session.exec(statement).first()
        if existing_match:
            return existing_match

        # Load both player states for current round
        statement = select(FifotecaPlayerState).where(
            and_(
                FifotecaPlayerState.room_id == room.id,
                FifotecaPlayerState.round_number == room.round_number,
            )
        )
        player_states = session.exec(statement).all()

        if len(player_states) < 2:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Both player states required",
            )

        # Validate both have current_team_id
        for state in player_states:
            if not state.current_team_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Both players must have selected a team",
                )

        # Get player states by room player IDs
        p1_state = next(
            (s for s in player_states if s.player_id == room.player1_id), None
        )
        p2_state = next(
            (s for s in player_states if s.player_id == room.player2_id), None
        )

        if not p1_state or not p2_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player states not found",
            )

        # Load teams
        p1_team = session.get(FifaTeam, p1_state.current_team_id)
        p2_team = session.get(FifaTeam, p2_state.current_team_id)

        if not p1_team or not p2_team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teams not found",
            )

        # Compute rating difference (preliminary; protection is awarded at confirmation time)
        rating_difference = abs(p1_team.overall_rating - p2_team.overall_rating)

        # Create match (protection_awarded_to_id is set at confirmation time)
        match = FifotecaMatch(
            room_id=room.id,
            round_number=room.round_number,
            player1_id=room.player1_id,
            player2_id=room.player2_id,  # type: ignore[arg-type]
            player1_team_id=p1_team.id,
            player2_team_id=p2_team.id,
            rating_difference=rating_difference,
        )
        session.add(match)
        session.commit()
        session.refresh(match)

        return match

    @staticmethod
    def handle_action(
        session,
        room_code: str,
        player_id: uuid.UUID,
        action_type: str,
        payload: dict | None = None,  # noqa: ARG001
    ) -> dict:
        """Handle a game action with validation and orchestration.

        Args:
            session: Database session.
            room_code: The room code for the game.
            player_id: The UUID of the player performing the action.
            action_type: The type of action (spin_league, lock_league, spin_team, lock_team).
            payload: Optional payload for the action (currently unused in Step 7).

        Returns:
            Dictionary containing:
                - action_type: The action type performed
                - player_id: The player who performed the action
                - result: The action result (spin or lock data)
                - auto_locked: Whether auto-lock occurred (for spin actions)
                - current_turn_player_id: The player whose turn it is now (or None)
                - phase_transitioned: Whether a phase transition occurred
                - room_status: The new room status (if changed)

        Raises:
            NotYourTurnError: If it's not the player's turn.
            InvalidActionError: If the action is invalid for the current phase.
            HTTPException: If room not found or expired.
        """
        # Import SpinService here to avoid circular imports
        from app.services.spin_service import SpinService

        # Load room
        statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
        room = session.exec(statement).first()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
            )

        # Check if room has expired (returns 410 if expired)
        check_room_expiry(room, session)

        # Load acting player's state for current round
        statement = select(FifotecaPlayerState).where(
            and_(
                FifotecaPlayerState.room_id == room.id,
                FifotecaPlayerState.player_id == player_id,
                FifotecaPlayerState.round_number == room.round_number,
            )
        )
        player_state = session.exec(statement).first()

        if not player_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Player state not found"
            )

        # Validate action allowed for room phase
        if room.status == RoomStatus.SPINNING_LEAGUES:
            valid_actions = ["spin_league", "lock_league"]
        elif room.status == RoomStatus.SPINNING_TEAMS:
            valid_actions = ["spin_team", "lock_team"]
        elif room.status == RoomStatus.RATING_REVIEW:
            valid_actions = ["use_parity_spin", "use_superspin", "ready_to_play"]
        else:
            valid_actions = []

        if action_type not in valid_actions:
            raise InvalidActionError(action_type, room.status)

        # Validate turn (skip for RATING_REVIEW actions which are not turn-gated)
        if room.status != RoomStatus.RATING_REVIEW:
            if room.current_turn_player_id != player_id:
                raise NotYourTurnError()

        # Delegate action to SpinService
        action_result = None
        auto_locked = False

        if action_type == "spin_league":
            result = SpinService.spin_league(session, player_state)
            action_result = {
                "league": {
                    "id": str(result["league"].id),
                    "name": result["league"].name,
                    "country": result["league"].country,
                },
                "spins_remaining": result["spins_remaining"],
            }
            auto_locked = result["auto_locked"]
            if auto_locked:
                # Add lock information to result
                action_result["lock"] = {
                    "league_locked": True,
                    "new_phase": player_state.phase,
                }

        elif action_type == "lock_league":
            SpinService.lock_league(session, player_state)
            action_result = {
                "lock": {
                    "league_locked": True,
                    "new_phase": player_state.phase,
                }
            }

        elif action_type == "spin_team":
            result = SpinService.spin_team(session, player_state)
            # Refresh to get league data for team
            session.refresh(player_state)
            team_league = session.get(FifaLeague, player_state.current_league_id)

            action_result = {
                "team": {
                    "id": str(result["team"].id),
                    "name": result["team"].name,
                    "league_id": str(player_state.current_league_id),
                    "league_name": team_league.name if team_league else None,
                    "attack_rating": result["team"].attack_rating,
                    "midfield_rating": result["team"].midfield_rating,
                    "defense_rating": result["team"].defense_rating,
                    "overall_rating": result["team"].overall_rating,
                },
                "spins_remaining": result["spins_remaining"],
            }
            auto_locked = result["auto_locked"]
            if auto_locked:
                # Add lock information to result
                action_result["lock"] = {
                    "team_locked": True,
                    "new_phase": player_state.phase,
                }

        elif action_type == "lock_team":
            SpinService.lock_team(session, player_state)
            action_result = {
                "lock": {
                    "team_locked": True,
                    "new_phase": player_state.phase,
                }
            }

        elif action_type == "use_superspin":
            if not player_state.has_superspin or player_state.superspin_used:
                raise InvalidActionError(action_type, "superspin not available")
            # Get opponent's team rating
            opponent_state = GameService._get_opponent_state(
                session, room, player_id, room.round_number
            )
            opponent_team = session.get(FifaTeam, opponent_state.current_team_id)
            opponent_rating = opponent_team.overall_rating if opponent_team else None

            result = SpinService.execute_superspin(
                session, player_state, opponent_rating
            )

            # Refresh to get league data for team
            session.refresh(player_state)
            team_league = session.get(FifaLeague, player_state.current_league_id)

            action_result = {
                "team": {
                    "id": str(result["team"].id),
                    "name": result["team"].name,
                    "league_id": str(player_state.current_league_id),
                    "league_name": team_league.name if team_league else None,
                    "attack_rating": result["team"].attack_rating,
                    "midfield_rating": result["team"].midfield_rating,
                    "defense_rating": result["team"].defense_rating,
                    "overall_rating": result["team"].overall_rating,
                },
                "was_fallback": result["was_fallback"],
            }

        elif action_type == "use_parity_spin":
            if not player_state.has_parity_spin or player_state.parity_spin_used:
                raise InvalidActionError(action_type, "parity spin not available")
            # Get opponent's team rating
            opponent_state = GameService._get_opponent_state(
                session, room, player_id, room.round_number
            )
            opponent_team = session.get(FifaTeam, opponent_state.current_team_id)
            opponent_rating = opponent_team.overall_rating if opponent_team else None

            result = SpinService.execute_parity_spin(
                session, player_state, opponent_rating
            )

            # Refresh to get league data for team
            session.refresh(player_state)
            team_league = session.get(FifaLeague, player_state.current_league_id)

            action_result = {
                "team": {
                    "id": str(result["team"].id),
                    "name": result["team"].name,
                    "league_id": str(player_state.current_league_id),
                    "league_name": team_league.name if team_league else None,
                    "attack_rating": result["team"].attack_rating,
                    "midfield_rating": result["team"].midfield_rating,
                    "defense_rating": result["team"].defense_rating,
                    "overall_rating": result["team"].overall_rating,
                },
                "was_fallback": result["was_fallback"],
            }

        elif action_type == "ready_to_play":
            # Mark player as ready
            player_state.phase = PlayerSpinPhase.READY_TO_PLAY
            session.add(player_state)
            session.commit()
            action_result = {"ready": True}

        # Refresh room and player state after action
        session.refresh(room)
        session.refresh(player_state)

        # Update turn
        next_player = SpinService.determine_next_turn(session, room, player_id)
        room.current_turn_player_id = next_player.id if next_player else None
        session.add(room)
        session.commit()

        # Check phase transition
        phase_transitioned = SpinService.check_phase_transition(session, room)
        session.refresh(room)

        # Build response
        response = {
            "action_type": action_type,
            "player_id": str(player_id),
            "result": action_result,
            "auto_locked": auto_locked,
            "current_turn_player_id": (
                str(room.current_turn_player_id)
                if room.current_turn_player_id
                else None
            ),
            "phase_transitioned": phase_transitioned,
            "room_status": room.status,
        }

        # Compute rating review if transitioned to RATING_REVIEW
        if phase_transitioned and room.status == RoomStatus.RATING_REVIEW:
            rating_review = GameService._compute_rating_review(session, room)
            if rating_review:
                response["rating_review"] = rating_review

        # For ready_to_play, check both players ready
        if action_type == "ready_to_play":
            # Get both player states
            statement = select(FifotecaPlayerState).where(
                and_(
                    FifotecaPlayerState.room_id == room.id,
                    FifotecaPlayerState.round_number == room.round_number,
                )
            )
            player_states = session.exec(statement).all()

            both_ready = all(
                state.phase == PlayerSpinPhase.READY_TO_PLAY for state in player_states
            )

            if both_ready:
                # Create match record (idempotent)
                match = GameService._create_match_for_current_round(session, room)

                room.status = RoomStatus.MATCH_IN_PROGRESS
                session.add(room)
                session.commit()
                session.refresh(room)
                response["phase_transitioned"] = True
                response["room_status"] = room.status
                response["match_id"] = str(match.id)

        # Recompute rating review after special spins (don't re-award parity)
        if action_type in ("use_superspin", "use_parity_spin"):
            rating_review = GameService._compute_rating_review(
                session, room, award_parity_spin=False
            )
            if rating_review:
                response["rating_review"] = rating_review

        return response

    @staticmethod
    def get_game_snapshot(session, room_code: str) -> dict:
        """Get full game snapshot for WebSocket state_sync.

        Args:
            session: Database session.
            room_code: The room code to get snapshot for.

        Returns:
            Dictionary containing room data and current round player states.

        Raises:
            HTTPException: If room not found (404).
            HTTPException: If room has expired (410).
        """
        # Get room
        statement = select(FifotecaRoom).where(FifotecaRoom.code == room_code)
        room = session.exec(statement).first()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
            )

        # Check if room has expired (returns 410 if expired)
        check_room_expiry(room, session)

        # Get player states for current round
        statement = select(FifotecaPlayerState).where(
            and_(
                FifotecaPlayerState.room_id == room.id,
                FifotecaPlayerState.round_number == room.round_number,
            )
        )
        player_states = session.exec(statement).all()

        # Resolve league/team objects for each player state
        def _resolve_league(league_id):
            if not league_id:
                return None
            league = session.get(FifaLeague, league_id)
            if not league:
                return None
            return {
                "id": str(league.id),
                "name": league.name,
                "country": league.country,
            }

        def _resolve_team(team_id):
            if not team_id:
                return None
            team = session.get(FifaTeam, team_id)
            if not team:
                return None
            return {
                "id": str(team.id),
                "name": team.name,
                "league_id": str(team.league_id),
                "attack_rating": team.attack_rating,
                "midfield_rating": team.midfield_rating,
                "defense_rating": team.defense_rating,
                "overall_rating": team.overall_rating,
            }

        # Resolve display names for players
        def _resolve_display_name(player_id):
            if not player_id:
                return None
            player = session.get(FifotecaPlayer, player_id)
            return player.display_name if player else None

        # Build snapshot
        snapshot = {
            "room": {
                "id": str(room.id),
                "code": room.code,
                "ruleset": room.ruleset,
                "status": room.status,
                "player1_id": str(room.player1_id),
                "player2_id": str(room.player2_id) if room.player2_id else None,
                "current_turn_player_id": (
                    str(room.current_turn_player_id)
                    if room.current_turn_player_id
                    else None
                ),
                "first_player_id": (
                    str(room.first_player_id) if room.first_player_id else None
                ),
                "round_number": room.round_number,
                "mutual_superspin_active": room.mutual_superspin_active,
                "expires_at": room.expires_at.isoformat(),
                "created_at": room.created_at.isoformat() if room.created_at else None,
            },
            "player_states": [
                {
                    "id": str(state.id),
                    "room_id": str(state.room_id),
                    "player_id": str(state.player_id),
                    "display_name": _resolve_display_name(state.player_id),
                    "round_number": state.round_number,
                    "phase": state.phase,
                    "league_spins_remaining": state.league_spins_remaining,
                    "team_spins_remaining": state.team_spins_remaining,
                    "current_league_id": (
                        str(state.current_league_id)
                        if state.current_league_id
                        else None
                    ),
                    "current_team_id": (
                        str(state.current_team_id) if state.current_team_id else None
                    ),
                    "current_league": _resolve_league(state.current_league_id),
                    "current_team": _resolve_team(state.current_team_id),
                    "league_locked": state.league_locked,
                    "team_locked": state.team_locked,
                    "has_superspin": state.has_superspin,
                    "superspin_used": state.superspin_used,
                    "has_parity_spin": state.has_parity_spin,
                    "parity_spin_used": state.parity_spin_used,
                    "created_at": (
                        state.created_at.isoformat() if state.created_at else None
                    ),
                }
                for state in player_states
            ],
        }

        return snapshot

    @staticmethod
    def reset_room_for_new_round(session: Session, room: FifotecaRoom) -> dict:
        """Reset room for a new round after match completion.

        Args:
            session: Database session.
            room: The room object to reset.

        Returns:
            Dictionary with reset context (room_code, round_number, first_player_id).

        Raises:
            HTTPException: If room doesn't have both players or match not found.
        """
        # Validate room has both players
        if not room.player1_id or not room.player2_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room must have both players to start new round",
            )

        # Get match for current round
        statement = select(FifotecaMatch).where(
            and_(
                FifotecaMatch.room_id == room.id,
                FifotecaMatch.round_number == room.round_number,
            )
        )
        match = session.exec(statement).first()

        if not match:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Match not found for current round",
            )

        # Determine first player from match result
        # player1 win → player1, player2 win → player2, draw → player1
        # Scores must be non-None for comparison
        p1_score = match.player1_score or 0
        p2_score = match.player2_score or 0

        if p1_score > p2_score:
            first_player_id = room.player1_id
        elif p2_score > p1_score:
            first_player_id = room.player2_id
        else:
            # Draw - player1 goes first
            first_player_id = room.player1_id

        # Increment round number
        room.round_number += 1

        # Set room status to SPINNING_LEAGUES
        room.status = RoomStatus.SPINNING_LEAGUES

        # Set first_player_id and current_turn_player_id to winner (or player1 on draw)
        room.first_player_id = first_player_id
        room.current_turn_player_id = first_player_id

        # Get both players
        p1_player = session.get(FifotecaPlayer, room.player1_id)
        p2_player = session.get(FifotecaPlayer, room.player2_id)

        if not p1_player or not p2_player:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Players not found",
            )

        # Create new FifotecaPlayerState rows for new round
        p1_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=room.player1_id,
            round_number=room.round_number,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
            has_superspin=p1_player.has_protection,  # Transfer protection to superspin
        )

        p2_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=room.player2_id,
            round_number=room.round_number,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
            has_superspin=p2_player.has_protection,  # Transfer protection to superspin
        )

        session.add(p1_state)
        session.add(p2_state)

        # Clear has_protection from players after transferring
        p1_player.has_protection = False
        p2_player.has_protection = False

        session.add(p1_player)
        session.add(p2_player)
        session.add(room)
        session.commit()
        session.refresh(room)

        return {
            "room_code": room.code,
            "round_number": room.round_number,
            "first_player_id": str(first_player_id),
        }

    @staticmethod
    def reset_room_for_mutual_superspin(session: Session, room: FifotecaRoom) -> dict:
        """Reset room for mutual superspin (both players get superspin).

        This is different from reset_room_for_new_round:
        - Round number stays the same
        - Both players get has_superspin=True
        - Status goes back to SPINNING_LEAGUES

        Args:
            session: Database session.
            room: The room object to reset.

        Returns:
            Dictionary with reset context.

        Raises:
            HTTPException: If room doesn't have both players.
        """
        # Validate room has both players
        if not room.player1_id or not room.player2_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room must have both players for mutual superspin",
            )

        # Determine first player - preserve existing first_player_id if set
        first_player_id = room.first_player_id or room.player1_id

        # Set room status to SPINNING_LEAGUES
        room.status = RoomStatus.SPINNING_LEAGUES

        # Set mutual_superspin_active
        room.mutual_superspin_active = True

        # Clear proposal field
        room.mutual_superspin_proposer_id = None

        # Set first_player_id and current_turn_player_id
        room.first_player_id = first_player_id
        room.current_turn_player_id = first_player_id

        # Delete existing player states for current round
        statement = select(FifotecaPlayerState).where(
            and_(
                FifotecaPlayerState.room_id == room.id,
                FifotecaPlayerState.round_number == room.round_number,
            )
        )
        existing_states = session.exec(statement).all()
        for state in existing_states:
            session.delete(state)

        session.commit()

        # Create new FifotecaPlayerState rows for current round with superspin
        p1_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=room.player1_id,
            round_number=room.round_number,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
            has_superspin=True,  # Both players get superspin
            superspin_used=False,
            has_parity_spin=False,
            parity_spin_used=False,
        )

        p2_state = FifotecaPlayerState(
            room_id=room.id,
            player_id=room.player2_id,
            round_number=room.round_number,
            phase=PlayerSpinPhase.LEAGUE_SPINNING,
            league_spins_remaining=3,
            team_spins_remaining=3,
            has_superspin=True,  # Both players get superspin
            superspin_used=False,
            has_parity_spin=False,
            parity_spin_used=False,
        )

        session.add(p1_state)
        session.add(p2_state)
        session.add(room)
        session.commit()
        session.refresh(room)

        return {
            "room_code": room.code,
            "round_number": room.round_number,
            "first_player_id": str(first_player_id),
            "mutual_superspin_active": True,
        }
