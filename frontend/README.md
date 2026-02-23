# Fifoteca - Frontend

The frontend is built with [Vite](https://vitejs.dev/), [React](https://reactjs.org/), [TypeScript](https://www.typescriptlang.org/), [TanStack Query](https://tanstack.com/query), [TanStack Router](https://tanstack.com/router), and [Tailwind CSS](https://tailwindcss.com/). It is a PWA (Progressive Web App) installable on mobile devices.

## Requirements

- [Bun](https://bun.sh/) (recommended) or [Node.js](https://nodejs.org/)

## Quick Start

```bash
bun install
bun run dev
```

Then open http://localhost:5173/.

For production-like testing, build the Docker image instead. But for development, the local dev server with live reload is recommended.

## Project Structure

- `src/client/` - Auto-generated OpenAPI client
- `src/components/fifoteca/` - Game UI components (LeagueCard, TeamCard, SpinDisplay, ScoreInput, RatingComparison, MutualSuperspinDialog)
- `src/hooks/useGameRoom.ts` - WebSocket-based game state management via React Query cache
- `src/hooks/useFifotecaPlayer.ts` - Player profile hook
- `src/routes/_layout/fifoteca/` - Route pages (lobby, game, match, history)

## Generate API Client

After backend API changes, regenerate the client:

```bash
# Automatic (with backend running)
bash ./scripts/generate-client.sh

# Manual
bun run generate-client
```

## E2E Tests

Requires the Docker Compose stack running:

```bash
docker compose up -d --wait backend
bunx playwright test
```

UI mode:

```bash
bunx playwright test --ui
```

## Remote API

Set `VITE_API_URL` in `frontend/.env` to use a remote backend:

```env
VITE_API_URL=https://api.your-domain.com
```
