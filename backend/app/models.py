import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# Enums
class RoomStatus(str, Enum):
    WAITING = "WAITING"
    SPINNING_LEAGUES = "SPINNING_LEAGUES"
    SPINNING_TEAMS = "SPINNING_TEAMS"
    RATING_REVIEW = "RATING_REVIEW"
    MATCH_IN_PROGRESS = "MATCH_IN_PROGRESS"
    SCORE_SUBMITTED = "SCORE_SUBMITTED"
    COMPLETED = "COMPLETED"


class PlayerSpinPhase(str, Enum):
    LEAGUE_SPINNING = "LEAGUE_SPINNING"
    LEAGUE_LOCKED = "LEAGUE_LOCKED"
    TEAM_SPINNING = "TEAM_SPINNING"
    TEAM_LOCKED = "TEAM_LOCKED"
    READY_TO_PLAY = "READY_TO_PLAY"


class ManualMatchRequestType(str, Enum):
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"


class ManualMatchRequestStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)
    fifoteca_player: Optional["FifotecaPlayer"] = Relationship(
        back_populates="user", sa_relationship_kwargs={"uselist": False}
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# ============================================================================
# Fifoteca Models
# ============================================================================


# FIFA Reference Data
class FifaLeague(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True)
    country: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    # Relationships
    teams: list["FifaTeam"] = Relationship(back_populates="league")


class FifaTeam(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    league_id: uuid.UUID = Field(foreign_key="fifaleague.id", ondelete="CASCADE")
    attack_rating: int
    midfield_rating: int
    defense_rating: int
    overall_rating: int  # Stored column, computed at insert as att + mid + def
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    # Relationship
    league: FifaLeague | None = Relationship(back_populates="teams")


# Fifoteca Player Profile
class FifotecaPlayer(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", unique=True, ondelete="CASCADE")
    display_name: str
    total_wins: int = Field(default=0)
    total_losses: int = Field(default=0)
    total_draws: int = Field(default=0)
    has_protection: bool = Field(default=False)  # Superspin available next game
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    # Relationship
    user: Optional["User"] = Relationship(back_populates="fifoteca_player")


# Fifoteca Room
class FifotecaRoom(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    code: str = Field(unique=True, index=True, max_length=6)
    ruleset: str = Field(default="homebrew")
    status: str = Field(default=RoomStatus.WAITING)
    player1_id: uuid.UUID = Field(foreign_key="fifotecaplayer.id")
    player2_id: uuid.UUID | None = Field(default=None, foreign_key="fifotecaplayer.id")
    current_turn_player_id: uuid.UUID | None = Field(
        default=None, foreign_key="fifotecaplayer.id"
    )
    first_player_id: uuid.UUID | None = Field(
        default=None, foreign_key="fifotecaplayer.id"
    )
    round_number: int = Field(default=1)
    mutual_superspin_proposer_id: uuid.UUID | None = None
    mutual_superspin_active: bool = Field(default=False)
    superspin_request_proposer_id: uuid.UUID | None = None
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))  # type: ignore
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    # Relationships
    player1: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[FifotecaRoom.player1_id]"}
    )
    player2: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[FifotecaRoom.player2_id]"}
    )
    current_turn_player: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[FifotecaRoom.current_turn_player_id]"}
    )
    first_player: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[FifotecaRoom.first_player_id]"}
    )


# Per-Round Player State
class FifotecaPlayerState(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(foreign_key="fifotecaroom.id", ondelete="CASCADE")
    player_id: uuid.UUID = Field(foreign_key="fifotecaplayer.id")
    round_number: int
    phase: str  # PlayerSpinPhase enum
    league_spins_remaining: int = Field(default=3)
    team_spins_remaining: int = Field(default=3)
    current_league_id: uuid.UUID | None = Field(
        default=None, foreign_key="fifaleague.id"
    )
    current_team_id: uuid.UUID | None = Field(default=None, foreign_key="fifateam.id")
    league_locked: bool = Field(default=False)
    team_locked: bool = Field(default=False)
    has_superspin: bool = Field(default=False)  # Available this round
    superspin_used: bool = Field(default=False)
    has_parity_spin: bool = Field(default=False)  # Granted during rating review
    parity_spin_used: bool = Field(default=False)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    # Relationships
    room: FifotecaRoom | None = Relationship()
    player: FifotecaPlayer | None = Relationship()
    current_league: FifaLeague | None = Relationship()
    current_team: FifaTeam | None = Relationship()


# Match Record
class FifotecaMatch(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(foreign_key="fifotecaroom.id")
    round_number: int
    player1_id: uuid.UUID = Field(foreign_key="fifotecaplayer.id")
    player2_id: uuid.UUID = Field(foreign_key="fifotecaplayer.id")
    player1_team_id: uuid.UUID = Field(foreign_key="fifateam.id")
    player2_team_id: uuid.UUID = Field(foreign_key="fifateam.id")
    player1_score: int | None = None
    player2_score: int | None = None
    rating_difference: int
    protection_awarded_to_id: uuid.UUID | None = Field(
        default=None, foreign_key="fifotecaplayer.id"
    )
    submitted_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="fifotecaplayer.id"
    )
    confirmed: bool = Field(default=False)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    # Relationships
    room: FifotecaRoom | None = Relationship()
    player1: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[FifotecaMatch.player1_id]"}
    )
    player2: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[FifotecaMatch.player2_id]"}
    )
    player1_team: FifaTeam | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[FifotecaMatch.player1_team_id]"}
    )
    player2_team: FifaTeam | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[FifotecaMatch.player2_team_id]"}
    )
    protection_awarded_to: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[FifotecaMatch.protection_awarded_to_id]"
        }
    )
    submitted_by: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[FifotecaMatch.submitted_by_id]"}
    )


# Manual Match Request
class FifotecaManualMatchRequest(SQLModel, table=True):
    """Request for manual match creation, edit, or deletion (requires opponent approval)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    requester_id: uuid.UUID = Field(foreign_key="fifotecaplayer.id")
    responder_id: uuid.UUID = Field(foreign_key="fifotecaplayer.id")
    request_type: str = Field(default=ManualMatchRequestType.CREATE)
    status: str = Field(default=ManualMatchRequestStatus.PENDING)

    # For CREATE: new match data
    requester_team_id: uuid.UUID | None = Field(
        default=None, foreign_key="fifateam.id"
    )
    responder_team_id: uuid.UUID | None = Field(
        default=None, foreign_key="fifateam.id"
    )
    requester_score: int | None = None
    responder_score: int | None = None
    rating_difference: int | None = None

    # For EDIT/DELETE: reference to existing match
    original_match_id: uuid.UUID | None = Field(
        default=None, foreign_key="fifotecamatch.id"
    )

    # For EDIT: new scores
    new_requester_score: int | None = None
    new_responder_score: int | None = None

    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))  # type: ignore

    # Relationships
    requester: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[FifotecaManualMatchRequest.requester_id]"
        }
    )
    responder: FifotecaPlayer | None = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[FifotecaManualMatchRequest.responder_id]"
        }
    )
    requester_team: FifaTeam | None = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[FifotecaManualMatchRequest.requester_team_id]"
        }
    )
    responder_team: FifaTeam | None = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[FifotecaManualMatchRequest.responder_team_id]"
        }
    )
    original_match: "FifotecaMatch | None" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[FifotecaManualMatchRequest.original_match_id]"
        }
    )


# ============================================================================
# Fifoteca Public Schemas (API Response Models)
# ============================================================================


class FifaLeaguePublic(SQLModel):
    id: uuid.UUID
    name: str
    country: str


class FifaTeamPublic(SQLModel):
    id: uuid.UUID
    name: str
    league_id: uuid.UUID
    attack_rating: int
    midfield_rating: int
    defense_rating: int
    overall_rating: int


class FifotecaPlayerPublic(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    total_wins: int
    total_losses: int
    total_draws: int
    has_protection: bool


class FifotecaPlayerStatePublic(SQLModel):
    id: uuid.UUID
    room_id: uuid.UUID
    player_id: uuid.UUID
    round_number: int
    phase: str
    league_spins_remaining: int
    team_spins_remaining: int
    current_league_id: uuid.UUID | None
    current_team_id: uuid.UUID | None
    league_locked: bool
    team_locked: bool
    has_superspin: bool
    superspin_used: bool
    has_parity_spin: bool
    parity_spin_used: bool


class FifotecaRoomWithStatesPublic(SQLModel):
    id: uuid.UUID
    code: str
    ruleset: str
    status: str
    player1_id: uuid.UUID
    player2_id: uuid.UUID | None
    current_turn_player_id: uuid.UUID | None
    first_player_id: uuid.UUID | None
    round_number: int
    mutual_superspin_active: bool
    expires_at: datetime
    created_at: datetime | None
    player_states: list[FifotecaPlayerStatePublic]


class FifotecaRoomPublic(SQLModel):
    id: uuid.UUID
    code: str
    ruleset: str
    status: str
    player1_id: uuid.UUID
    player2_id: uuid.UUID | None
    current_turn_player_id: uuid.UUID | None
    first_player_id: uuid.UUID | None
    round_number: int
    mutual_superspin_active: bool
    expires_at: datetime
    created_at: datetime | None


# Match Schemas
class MatchScoreSubmit(SQLModel):
    """Request schema for submitting match scores."""

    player1_score: int = Field(ge=0)
    player2_score: int = Field(ge=0)


class FifotecaMatchPublic(SQLModel):
    """Public match schema (minimal)."""

    id: uuid.UUID
    room_id: uuid.UUID
    round_number: int
    player1_id: uuid.UUID
    player2_id: uuid.UUID
    player1_score: int | None
    player2_score: int | None
    rating_difference: int
    protection_awarded_to_id: uuid.UUID | None
    confirmed: bool
    created_at: datetime | None


class FifotecaMatchDetail(SQLModel):
    """Detailed match schema (with team and submitter info)."""

    id: uuid.UUID
    room_id: uuid.UUID
    round_number: int
    player1_id: uuid.UUID
    player2_id: uuid.UUID
    player1_team_id: uuid.UUID
    player2_team_id: uuid.UUID
    player1_league_id: uuid.UUID
    player2_league_id: uuid.UUID
    player1_score: int | None
    player2_score: int | None
    rating_difference: int
    protection_awarded_to_id: uuid.UUID | None
    submitted_by_id: uuid.UUID | None
    confirmed: bool
    created_at: datetime | None


class FifotecaMatchHistoryPublic(SQLModel):
    """Enriched match history from current player's perspective."""

    id: uuid.UUID
    created_at: datetime | None
    round_number: int
    rating_difference: int
    confirmed: bool
    # Perspective-aware fields (from current player's viewpoint)
    opponent_id: uuid.UUID
    opponent_display_name: str
    my_team_name: str
    opponent_team_name: str
    my_team_rating: int
    opponent_team_rating: int
    my_score: int | None
    opponent_score: int | None
    result: str  # "win", "loss", or "draw"


class MatchesPublic(SQLModel):
    """List of matches for current player."""

    data: list[FifotecaMatchHistoryPublic]
    count: int


# Manual Match Request Schemas
class ManualMatchCreateRequest(SQLModel):
    """Request to create a manual match."""

    opponent_id: uuid.UUID
    my_team_id: uuid.UUID
    opponent_team_id: uuid.UUID
    my_score: int = Field(ge=0)
    opponent_score: int = Field(ge=0)


class ManualMatchEditRequest(SQLModel):
    """Request to edit an existing match's scores."""

    match_id: uuid.UUID
    new_my_score: int = Field(ge=0)
    new_opponent_score: int = Field(ge=0)


class ManualMatchDeleteRequest(SQLModel):
    """Request to delete an existing match."""

    match_id: uuid.UUID


class ManualMatchRequestPublic(SQLModel):
    """Public schema for manual match request."""

    id: uuid.UUID
    request_type: str
    status: str
    requester_id: uuid.UUID
    requester_display_name: str
    responder_id: uuid.UUID
    responder_display_name: str

    # For CREATE requests
    requester_team_name: str | None = None
    responder_team_name: str | None = None
    requester_team_rating: int | None = None
    responder_team_rating: int | None = None
    requester_score: int | None = None
    responder_score: int | None = None
    rating_difference: int | None = None

    # For EDIT requests
    original_match_id: uuid.UUID | None = None
    current_requester_score: int | None = None
    current_responder_score: int | None = None
    new_requester_score: int | None = None
    new_responder_score: int | None = None

    created_at: datetime | None = None
    expires_at: datetime


class ManualMatchRequestsPublic(SQLModel):
    """List of manual match requests."""

    incoming: list[ManualMatchRequestPublic]
    outgoing: list[ManualMatchRequestPublic]


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
