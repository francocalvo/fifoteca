# Fifoteca

A real-time multiplayer FIFA companion game where two players compete in league/team selection rounds and settle scores on the pitch.

## Technology Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com) + [SQLModel](https://sqlmodel.tiangolo.com) + [PostgreSQL](https://www.postgresql.org)
- **Frontend**: [React](https://react.dev) + [TypeScript](https://www.typescriptlang.org/) + [Vite](https://vitejs.dev) + [Tailwind CSS](https://tailwindcss.com) + [shadcn/ui](https://ui.shadcn.com)
- **Real-time**: WebSocket-based game state synchronization
- **PWA**: Installable progressive web app with offline support
- **Testing**: [Pytest](https://pytest.org) (backend) + [Playwright](https://playwright.dev) (E2E)
- **Infrastructure**: [Docker Compose](https://www.docker.com) + SWAG (nginx) reverse proxy

## How It Works

1. A player creates a room and shares the code
2. The second player joins using the room code
3. Players take turns spinning for leagues and teams
4. Special mechanics: parity spins, superspins, and mutual superspins based on team rating differences
5. Players play the FIFA match and submit/confirm scores
6. Protection is awarded based on match results

## Analytics View

An opponent-centric analytics page at `/fifoteca/analytics`:

1. Select an opponent from the player list
2. View **Head-to-Head summary** — W/L/D record, favorite/underdog splits, current streak, recent form
3. Browse **Match History** — sortable table with signed rating diff and role badges
4. Explore **Spread Analytics** — stacked bar chart showing win/draw/loss rates across 5 rating-difference buckets

No analytics are shown until an opponent is selected. If the selected opponent has no matches, an empty-state message is displayed.

## Getting Started

### Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Bun](https://bun.sh/) (JavaScript runtime)

### Quick Start

```bash
# Start all services
docker compose watch
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### Configuration

Copy and adjust the `.env` file. Key variables to change for production:

- `SECRET_KEY`
- `FIRST_SUPERUSER_PASSWORD`
- `POSTGRES_PASSWORD`

Generate secure keys with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Development

- Backend docs: [backend/README.md](./backend/README.md)
- Frontend docs: [frontend/README.md](./frontend/README.md)
- Development guide: [development.md](./development.md)
- Deployment guide: [deployment.md](./deployment.md)

## Recent Updates

**2026-02-24 — Analytics View**
- Added `/fifoteca/analytics` route with opponent-scoped H2H, match history, and spread chart
- Added `GET /fifoteca/players` endpoint (authenticated, returns all registered players)
- Extended `GET /fifoteca/matches` response with `opponent_id`, `my_team_rating`, `opponent_team_rating`

## License

MIT
