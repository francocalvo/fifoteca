"""Fifoteca API routes for leagues and teams."""

from fastapi import APIRouter

from app.api.routes.fifoteca import leagues, matches, players, rooms, teams, ws

router = APIRouter(prefix="/fifoteca", tags=["fifoteca"])
router.include_router(leagues.router)
router.include_router(matches.router)
router.include_router(players.router)
router.include_router(rooms.router)
router.include_router(teams.router)
router.include_router(ws.router)
