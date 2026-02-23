# Fifoteca

A real-time multiplayer FIFA companion game where two players compete in league/team selection rounds and settle scores on the pitch.

## Technology Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com) + [SQLModel](https://sqlmodel.tiangolo.com) + [PostgreSQL](https://www.postgresql.org)
- **Frontend**: [React](https://react.dev) + [TypeScript](https://www.typescriptlang.org/) + [Vite](https://vitejs.dev) + [Tailwind CSS](https://tailwindcss.com) + [shadcn/ui](https://ui.shadcn.com)
- **Real-time**: WebSocket-based game state synchronization
- **PWA**: Installable progressive web app with offline support
- **Testing**: [Pytest](https://pytest.org) (backend) + [Playwright](https://playwright.dev) (E2E)
- **Infrastructure**: [Docker Compose](https://www.docker.com) + [Traefik](https://traefik.io) reverse proxy

## How It Works

1. A player creates a room and shares the code
2. The second player joins using the room code
3. Players take turns spinning for leagues and teams
4. Special mechanics: parity spins, superspins, and mutual superspins based on team rating differences
5. Players play the FIFA match and submit/confirm scores
6. Protection is awarded based on match results

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

## License

MIT
