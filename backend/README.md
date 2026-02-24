# Fifoteca - Backend

The backend is built with [FastAPI](https://fastapi.tiangolo.com), [SQLModel](https://sqlmodel.tiangolo.com), and [PostgreSQL](https://www.postgresql.org).

## Requirements

- [Docker](https://www.docker.com/)
- [uv](https://docs.astral.sh/uv/) for Python package and environment management

## Setup

Start the local development environment with Docker Compose following the guide in [../development.md](../development.md).

### Local Development (without Docker)

```bash
uv sync
source .venv/bin/activate
fastapi dev app/main.py
```

Make sure your editor uses the Python interpreter at `backend/.venv/bin/python`.

## Project Structure

- `app/models.py` - SQLModel models (FifaLeague, FifaTeam, FifotecaPlayer, FifotecaRoom, FifotecaMatch, FifotecaPlayerState)
- `app/api/routes/fifoteca/` - REST API endpoints (leagues, teams, players, rooms, matches, WebSocket)
- `app/services/` - Business logic (game_service, spin_service)
- `app/ws/` - WebSocket connection manager and message handlers
- `app/scripts/` - Data seeding scripts
- `data/` - FIFA teams CSV dataset

## Tests

```bash
bash ./scripts/test.sh
```

Or inside Docker:

```bash
docker compose exec backend bash scripts/tests-start.sh
```

Pass extra args to pytest:

```bash
docker compose exec backend bash scripts/tests-start.sh -x
```

Coverage report is generated at `htmlcov/index.html`.

## Migrations

```bash
# Enter the backend container
docker compose exec backend bash

# Create a new migration after model changes
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head
```

## Fifoteca API Contracts

### `GET /fifoteca/players`

Returns all registered Fifoteca players. Requires authentication (401 without valid token). Response type: `list[FifotecaPlayerPublic]`.

### `GET /fifoteca/matches` (analytics fields)

Match history responses include perspective-aware analytics fields (values are from the authenticated player's viewpoint):

| Field | Type | Description |
|-------|------|-------------|
| `opponent_id` | `uuid` | ID of the opposing player |
| `my_team_rating` | `int` | Caller's team overall rating |
| `opponent_team_rating` | `int` | Opponent's team overall rating |

These fields enable client-side favorite/underdog classification and spread analytics without additional API calls.

## Seeding FIFA Data

FIFA team data is seeded automatically on startup from `data/fifa_teams.csv`. To run manually:

```bash
python -m app.scripts.seed_fifa_data
```
