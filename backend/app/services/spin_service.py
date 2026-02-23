"""SpinService for Fifoteca core game logic.

This service handles league and team spins, locking, turn management,
and phase transitions for the turn-based spin game.
"""

import random
import uuid

from sqlmodel import Session, select

from app.models import (
    FifaLeague,
    FifaTeam,
    FifotecaPlayer,
    FifotecaPlayerState,
    FifotecaRoom,
    PlayerSpinPhase,
    RoomStatus,
)


# Special spin exceptions
class SpecialSpinError(Exception):
    """Base exception for special spin validation errors."""

    pass


class SpinService:
    """Service for Fifoteca spin and lock logic."""

    @staticmethod
    def spin_league(session: Session, player_state: FifotecaPlayerState) -> dict:
        """Pick random league and decrement spins remaining.

        Args:
            session: Database session.
            player_state: The player state to spin for.

        Returns:
            Dictionary with spin result:
                {"league": FifaLeague, "spins_remaining": int}

        Raises:
            ValueError: If no leagues available or player has no spins remaining.
        """
        if player_state.league_spins_remaining <= 0:
            raise ValueError("No league spins remaining")

        # Get all leagues
        statement = select(FifaLeague)
        leagues = session.exec(statement).all()

        if not leagues:
            raise ValueError("No leagues available")

        # Pick random league
        league = random.choice(leagues)

        # Update player state
        player_state.current_league_id = league.id
        player_state.league_spins_remaining -= 1

        # Auto-lock if this was the last spin
        auto_locked = False
        if player_state.league_spins_remaining == 0:
            SpinService.lock_league(session, player_state)
            auto_locked = True

        session.add(player_state)
        session.commit()
        session.refresh(player_state)

        return {
            "league": league,
            "spins_remaining": player_state.league_spins_remaining,
            "auto_locked": auto_locked,
        }

    @staticmethod
    def lock_league(session: Session, player_state: FifotecaPlayerState) -> None:
        """Lock current league and transition to team spinning phase.

        Args:
            session: Database session.
            player_state: The player state to lock.
        """
        player_state.league_locked = True
        player_state.phase = PlayerSpinPhase.TEAM_SPINNING

        session.add(player_state)
        session.commit()

    @staticmethod
    def spin_team(session: Session, player_state: FifotecaPlayerState) -> dict:
        """Pick random team from locked league.

        Args:
            session: Database session.
            player_state: The player state to spin for.

        Returns:
            Dictionary with spin result:
                {"team": FifaTeam, "spins_remaining": int}

        Raises:
            ValueError: If league not locked, no teams in league,
                       or no spins remaining.
        """
        if not player_state.league_locked:
            raise ValueError("League must be locked before spinning teams")

        if player_state.team_spins_remaining <= 0:
            raise ValueError("No team spins remaining")

        if not player_state.current_league_id:
            raise ValueError("No league selected")

        # Get teams from current league
        statement = select(FifaTeam).where(
            FifaTeam.league_id == player_state.current_league_id
        )
        teams = session.exec(statement).all()

        if not teams:
            raise ValueError("No teams available in selected league")

        # Pick random team
        team = random.choice(teams)

        # Update player state
        player_state.current_team_id = team.id
        player_state.team_spins_remaining -= 1

        # Auto-lock if this was the last spin
        auto_locked = False
        if player_state.team_spins_remaining == 0:
            SpinService.lock_team(session, player_state)
            auto_locked = True

        session.add(player_state)
        session.commit()
        session.refresh(player_state)

        return {
            "team": team,
            "spins_remaining": player_state.team_spins_remaining,
            "auto_locked": auto_locked,
        }

    @staticmethod
    def lock_team(session: Session, player_state: FifotecaPlayerState) -> None:
        """Lock current team.

        Args:
            session: Database session.
            player_state: The player state to lock.
        """
        player_state.team_locked = True
        player_state.phase = PlayerSpinPhase.TEAM_LOCKED

        session.add(player_state)
        session.commit()

    @staticmethod
    def determine_next_turn(
        session: Session, room: FifotecaRoom, acting_player_id: uuid.UUID
    ) -> FifotecaPlayer | None:
        """Determine who goes next based on turn interleaving rules.

        Args:
            session: Database session.
            room: The room object.
            acting_player_id: The UUID of the player who just acted.

        Returns:
            The FifotecaPlayer who should act next, or None if both done.
        """
        # Get other player
        if room.player1_id == acting_player_id:
            other_player_id = room.player2_id
        else:
            other_player_id = room.player1_id

        if not other_player_id:
            return None

        # Get player states for current round
        acting_state = session.exec(
            select(FifotecaPlayerState).where(
                FifotecaPlayerState.player_id == acting_player_id,
                FifotecaPlayerState.room_id == room.id,
                FifotecaPlayerState.round_number == room.round_number,
            )
        ).first()

        other_state = session.exec(
            select(FifotecaPlayerState).where(
                FifotecaPlayerState.player_id == other_player_id,
                FifotecaPlayerState.room_id == room.id,
                FifotecaPlayerState.round_number == room.round_number,
            )
        ).first()

        if not acting_state or not other_state:
            return None

        # Determine based on room status and interleaving rules
        if room.status == RoomStatus.SPINNING_LEAGUES:
            # If other player has locked league, acting player keeps turn
            if other_state.league_locked:
                # Return acting player as they continue spinning
                return session.get(FifotecaPlayer, acting_player_id)
            else:
                # Alternate to other player
                return session.get(FifotecaPlayer, other_player_id)

        elif room.status == RoomStatus.SPINNING_TEAMS:
            # If other player has locked team, acting player keeps turn
            if other_state.team_locked:
                # Return acting player as they continue spinning
                return session.get(FifotecaPlayer, acting_player_id)
            else:
                # Alternate to other player
                return session.get(FifotecaPlayer, other_player_id)

        elif room.status == RoomStatus.RATING_REVIEW:
            # During rating review, both players can act (ready_to_play, special spins).
            # If other player hasn't readied yet, pass turn to them.
            if other_state.phase != PlayerSpinPhase.READY_TO_PLAY:
                return session.get(FifotecaPlayer, other_player_id)
            # If both have readied (or only acting player left), no turn needed
            return None

        return None

    @staticmethod
    def check_phase_transition(session: Session, room: FifotecaRoom) -> bool:
        """Check if room status should transition and update if needed.

        Args:
            session: Database session.
            room: The room object to check.

        Returns:
            True if phase transition occurred, False otherwise.
        """
        # Get all player states for current round
        statement = select(FifotecaPlayerState).where(
            FifotecaPlayerState.room_id == room.id,
            FifotecaPlayerState.round_number == room.round_number,
        )
        player_states = session.exec(statement).all()

        if len(player_states) < 2:
            return False

        # Check league phase transition
        if room.status == RoomStatus.SPINNING_LEAGUES:
            all_locked = all(state.league_locked for state in player_states)
            if all_locked:
                room.status = RoomStatus.SPINNING_TEAMS
                session.add(room)
                session.commit()
                session.refresh(room)
                return True

        # Check team phase transition
        elif room.status == RoomStatus.SPINNING_TEAMS:
            all_locked = all(state.team_locked for state in player_states)
            if all_locked:
                room.status = RoomStatus.RATING_REVIEW
                session.add(room)
                session.commit()
                session.refresh(room)
                return True

        return False

    @staticmethod
    def execute_superspin(
        session: Session, player_state: FifotecaPlayerState, opponent_rating: int | None
    ) -> dict:
        """Execute superspin: find team within ±5 rating of opponent.

        Args:
            session: Database session.
            player_state: The player state executing superspin.
            opponent_rating: The opponent's team overall rating.

        Returns:
            Dictionary with:
                - team: FifaTeam (selected team)
                - was_fallback: bool (always False for superspin)

        Raises:
            SpecialSpinError: If no qualifying teams or opponent rating unavailable.
        """
        if opponent_rating is None:
            raise SpecialSpinError(
                "Cannot execute superspin: opponent rating unavailable"
            )

        # Find teams where overall_rating is within ±5 of opponent_rating
        statement = select(FifaTeam).where(
            (FifaTeam.overall_rating >= opponent_rating - 5)
            & (FifaTeam.overall_rating <= opponent_rating + 5)
        )
        candidates = session.exec(statement).all()

        if not candidates:
            raise SpecialSpinError(
                f"No teams found within ±5 rating of opponent ({opponent_rating})"
            )

        # Randomly select one candidate
        selected_team = random.choice(candidates)

        # Update player state
        player_state.current_team_id = selected_team.id
        player_state.team_locked = True
        player_state.phase = PlayerSpinPhase.TEAM_LOCKED
        player_state.superspin_used = True

        # Update current_league_id if different league
        if player_state.current_league_id != selected_team.league_id:
            player_state.current_league_id = selected_team.league_id

        session.add(player_state)
        session.commit()
        session.refresh(player_state)

        return {
            "team": selected_team,
            "was_fallback": False,  # Superspin doesn't have fallback logic
        }

    @staticmethod
    def execute_parity_spin(
        session: Session, player_state: FifotecaPlayerState, opponent_rating: int | None
    ) -> dict:
        """Execute parity spin: find team within ±30 rating (same league first).

        Args:
            session: Database session.
            player_state: The player state executing parity spin.
            opponent_rating: The opponent's team overall rating.

        Returns:
            Dictionary with:
                - team: FifaTeam (selected team)
                - was_fallback: bool (True if used fallback across all leagues)

        Raises:
            SpecialSpinError: If no qualifying teams or opponent rating unavailable.
        """
        if opponent_rating is None:
            raise SpecialSpinError(
                "Cannot execute parity spin: opponent rating unavailable"
            )

        was_fallback = False
        selected_team = None

        # First, try same league
        if player_state.current_league_id:
            statement = select(FifaTeam).where(
                (FifaTeam.league_id == player_state.current_league_id)
                & (FifaTeam.overall_rating >= opponent_rating - 30)
                & (FifaTeam.overall_rating <= opponent_rating + 30)
            )
            same_league_candidates = session.exec(statement).all()

            if same_league_candidates:
                selected_team = random.choice(same_league_candidates)
                was_fallback = False

        # Fallback to all leagues if no same-league candidate
        if selected_team is None:
            statement = select(FifaTeam).where(
                (FifaTeam.overall_rating >= opponent_rating - 30)
                & (FifaTeam.overall_rating <= opponent_rating + 30)
            )
            all_candidates = session.exec(statement).all()

            if not all_candidates:
                raise SpecialSpinError(
                    f"No teams found within ±30 rating of opponent ({opponent_rating})"
                )

            selected_team = random.choice(all_candidates)
            was_fallback = True

        # Update player state
        player_state.current_team_id = selected_team.id
        player_state.parity_spin_used = True

        # Update current_league_id if different league (fallback scenario)
        if player_state.current_league_id != selected_team.league_id:
            player_state.current_league_id = selected_team.league_id

        session.add(player_state)
        session.commit()
        session.refresh(player_state)

        return {
            "team": selected_team,
            "was_fallback": was_fallback,
        }
