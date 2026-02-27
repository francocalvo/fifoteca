# Fifoteca Architecture

## Purpose

Fifoteca is a real-time multiplayer FIFA companion app where two authenticated users:

1. Create/join a room
2. Spin leagues/teams with game rules (superspin/parity/mutual superspin)
3. Play the FIFA match outside the app
4. Submit and confirm score in-app
5. Track historical analytics by opponent

The system is split into a FastAPI backend, a React frontend, PostgreSQL persistence, and WebSocket-based room synchronization.

## High-Level Components

- `backend/`: FastAPI app (REST + WebSocket), SQLModel domain models, business services
- `frontend/`: React + TanStack Router + TanStack Query + generated OpenAPI client
- `postgres`: primary state store (users, players, rooms, rounds, matches, FIFA reference data)
- `SWAG nginx` (external host): TLS termination and reverse proxy for frontend + `/api/*`

## Backend Architecture

### Entry and API Layout

- Framework: FastAPI
- Domain API prefix: `/api/v1/fifoteca`
- Main route groups under `backend/app/api/routes/fifoteca/`:
  - `rooms.py`: room create/join/get state
  - `leagues.py`, `teams.py`: reference data
  - `players.py`: player profile endpoints
  - `matches.py`: submit/confirm/list match history
  - `ws.py`: room WebSocket endpoint

### Core Domain Model

Defined in `backend/app/models.py`.

- `User`: auth identity
- `FifotecaPlayer`: game profile (wins/losses/draws/protection)
- `FifotecaRoom`: room lifecycle + turn state + expiry
- `FifotecaPlayerState`: per-player, per-round spin state
- `FifotecaMatch`: persisted match result and protection outcome
- `FifaLeague` / `FifaTeam`: seeded reference catalog

Key enums:

- `RoomStatus`: `WAITING -> SPINNING_LEAGUES -> SPINNING_TEAMS -> RATING_REVIEW -> MATCH_IN_PROGRESS -> SCORE_SUBMITTED -> COMPLETED`
- `PlayerSpinPhase`: player-level progression during a round

### Business Logic and Real-Time

- Services in `backend/app/services/`:
  - `game_service.py`: room/game state transitions and snapshots
  - `spin_service.py`: spin mechanics and constraints
- WebSocket stack in `backend/app/ws/`:
  - connection manager per room
  - message handlers for in-room actions
  - broadcast events (`state_sync`, `score_submitted`, `match_result`, etc.)

WebSocket endpoint:

- `/api/v1/fifoteca/ws/{room_code}?token=...`
- Validates JWT before accept
- Ensures room membership and non-expired room
- Sends immediate `state_sync`

### Persistence and Seed Data

- PostgreSQL 18
- Alembic migrations under `backend/app/alembic/`
- Startup initialization (`backend/app/core/db.py`) ensures:
  - superuser exists from env vars
  - some dev players if missing
  - FIFA teams/leagues seeded from `backend/data/fifa_teams.csv`

## Frontend Architecture

- React + TypeScript + Vite
- UI stack: Tailwind + shadcn/ui
- Routing: TanStack Router (`frontend/src/routes/`)
- Data fetching/cache: TanStack Query
- API client: generated from OpenAPI under `frontend/src/client/`

Key feature surfaces:

- Game flow routes: lobby/game/match/history
- Analytics route: `/fifoteca/analytics`
  - opponent selector
  - H2H summary
  - match history table
  - spread analytics chart

WebSocket URL construction (`frontend/src/hooks/useGameRoom.ts`):

- derives `ws://`/`wss://` from `VITE_API_URL`
- appends `/api/v1/fifoteca/ws/{roomCode}?token=...`

## Request and Event Flow

### Room lifecycle

1. Player A creates room (`POST /rooms`)
2. Player B joins (`POST /rooms/join/{code}`)
3. Backend creates both `FifotecaPlayerState` rows for round 1
4. Both clients connect via WebSocket
5. Actions mutate state through handlers/services and broadcast updates

### Match lifecycle

1. Participant submits score (`POST /matches/{id}/score`)
2. Non-submitter confirms (`POST /matches/{id}/confirm`)
3. Backend updates:
   - match confirmation
   - player W/L/D counters
   - protection awards (rating-diff based)
4. Backend broadcasts `match_result`

## Deployment Architecture (current known setup)

### App Host

- Host: `192.168.1.4`
- Path: `/home/muad/fifoteca`
- Runtime: Docker Compose CLI backed by Podman (`podman-compose` provider)
- Compose command in use:
  - `docker compose -f compose.yml -f compose.deploy.yml up -d --build`

Ports exposed on host:

- Frontend: `53172 -> 80`
- Backend: `18437 -> 8000`

### Proxy Host

- Host: `192.168.1.100`
- SWAG config path:
  - `/mnt/arrakis/swag/nginx/proxy-confs/subdomains/fifoteca.subdomain.conf`

Path-based routing target:

- `fif.calvo.dev/` -> frontend (`192.168.1.4:53172`)
- `fif.calvo.dev/api/` -> backend (`192.168.1.4:18437`)
- websocket path proxied via `/api/v1/fifoteca/ws/`

### Data Storage (Postgres)

The DB now supports bind mount in deploy override (`compose.deploy.yml`):

- `HOST_DB_DATA_PATH` (default: `/home/muad/fifoteca/data/postgres`)
- Mounted to `/var/lib/postgresql/data/pgdata`

This replaces named-volume-only behavior for deployment mode and allows host-visible backups/migrations.

## Operational Notes and Caveats

- In this environment, Podman dual-network attachment (`default` + `traefik-public`) has caused connectivity issues for exposed ports; operational workaround has been disconnecting `fifoteca_traefik-public` from app containers after deploy.
- SWAG `proxy.conf` already sets `proxy_http_version` and several `proxy_set_header` directives; custom vhost files should avoid duplicating those directives.
- `.env` is the source of runtime behavior (`VITE_API_URL`, CORS, auth, DB credentials, etc.).

## Testing Strategy

- Backend: Pytest (`backend/tests/`), including route/service coverage
- Frontend unit: Vitest (`frontend/src/**/*.test.ts(x)`)
- E2E: Playwright (`frontend/tests/fifoteca/`)

## Key Configuration Knobs

- `VITE_API_URL`: frontend API base used for HTTP and WS URL derivation
- `BACKEND_CORS_ORIGINS`: must include browser origin(s)
- `SECRET_KEY`: JWT signing
- `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD`: bootstrap admin
- `HOST_BACKEND_PORT`, `HOST_FRONTEND_PORT`: host port mapping in deploy override
- `HOST_DB_DATA_PATH`: host bind path for DB data (deploy override)
