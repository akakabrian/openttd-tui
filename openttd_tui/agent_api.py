"""REST API over aiohttp so AI agents can observe and control the game.

Endpoints:
    GET  /                  — server info
    GET  /state             — top-level snapshot
    GET  /tools             — tool catalogue
    GET  /map               — full tile grid (class names, row-major)
    GET  /tile?x=&y=        — single tile info
    POST /tool              — {code, x, y} — apply a tool
    POST /advance           — {ticks: int} — step the sim N times
    POST /pause             — {paused: bool}
    GET  /events            — server-sent events (state every second)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web

from . import engine as E
from . import tiles


def state_snapshot(app) -> dict[str, Any]:
    g = app.game
    mv = app.map_view
    snap = g.snapshot()
    snap.update({
        "paused": app.paused,
        "cursor": {"x": mv.cursor_x, "y": mv.cursor_y},
        "world": {"w": E.MAP_W, "h": E.MAP_H},
    })
    return snap


def _tile_info(game: E.Game, x: int, y: int) -> dict[str, Any]:
    word = game.tile_at(x, y)
    glyph, klass = tiles.glyph_and_class(word, game)
    return {
        "x": x, "y": y, "word": word,
        "type": E.tile_type(word), "low": E.tile_low(word),
        "glyph": glyph, "class": klass,
    }


def build_app(game_app) -> web.Application:
    routes = web.RouteTableDef()

    @routes.get("/")
    async def root(request):
        return web.json_response({
            "name": "openttd-tui agent API",
            "endpoints": [
                "GET /state", "GET /tools", "GET /map", "GET /tile",
                "GET /events", "POST /tool", "POST /advance", "POST /pause",
            ],
            "world": {"w": E.MAP_W, "h": E.MAP_H},
        })

    @routes.get("/state")
    async def state(request):
        return web.json_response(state_snapshot(game_app))

    @routes.get("/tools")
    async def tools_endpoint(request):
        from .app import TOOLS
        return web.json_response([
            {"key": t.key, "code": t.code, "label": t.label, "cost": t.cost}
            for t in TOOLS
        ])

    @routes.get("/map")
    async def full_map(request):
        g = game_app.game
        grid = [
            [tiles.glyph_and_class(g._grid[x * E.MAP_H + y], g)[1]
             for x in range(E.MAP_W)]
            for y in range(E.MAP_H)
        ]
        return web.json_response({"w": E.MAP_W, "h": E.MAP_H, "grid": grid})

    @routes.get("/tile")
    async def tile(request):
        try:
            x = int(request.query["x"])
            y = int(request.query["y"])
        except (KeyError, ValueError):
            return web.json_response({"error": "missing/invalid x,y"}, status=400)
        if not (0 <= x < E.MAP_W and 0 <= y < E.MAP_H):
            return web.json_response({"error": "out of bounds"}, status=400)
        return web.json_response(_tile_info(game_app.game, x, y))

    @routes.post("/tool")
    async def apply_tool(request):
        try:
            body = await request.json()
            code = str(body["code"])
            x = int(body["x"])
            y = int(body["y"])
        except (KeyError, ValueError, json.JSONDecodeError):
            return web.json_response({"error": "body must be {code, x, y}"},
                                     status=400)
        if not (0 <= x < E.MAP_W and 0 <= y < E.MAP_H):
            return web.json_response({"error": "out of bounds"}, status=400)
        ok, msg = game_app._apply_tool_code(code, x, y)
        # Pick up engine events (e.g. station built) without dropping them.
        events = game_app.game.drain_events()
        # Only refresh UI if the app is actually mounted — in headless/API
        # mode there's no active App, and refresh() would crash on the
        # widget lookup.
        if game_app.map_view.is_mounted:
            game_app.map_view.refresh_all_tiles()
        if game_app.status_panel.is_mounted:
            game_app.status_panel.refresh_panel()
        return web.json_response({
            "ok": ok, "message": msg,
            "funds": game_app.game.funds,
            "events": [{"level": l, "text": t} for l, t in events],
        })

    @routes.post("/advance")
    async def advance(request):
        try:
            body = await request.json()
            n = int(body.get("ticks", 1))
        except (ValueError, json.JSONDecodeError):
            return web.json_response({"error": "body must be {ticks: int}"},
                                     status=400)
        n = max(1, min(n, 100_000))
        g = game_app.game
        y_before = g.year
        m_before = g.month
        for _ in range(n):
            g.tick()
        return web.json_response({
            "ticks": n,
            "year_before": y_before, "month_before": m_before,
            "year_after": g.year, "month_after": g.month,
        })

    @routes.post("/pause")
    async def pause(request):
        try:
            body = await request.json()
            game_app.paused = bool(body["paused"])
        except (KeyError, json.JSONDecodeError):
            return web.json_response({"error": "body must be {paused: bool}"},
                                     status=400)
        return web.json_response({"paused": game_app.paused})

    @routes.get("/events")
    async def events_stream(request):
        resp = web.StreamResponse(status=200, reason="OK", headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        })
        await resp.prepare(request)
        try:
            while True:
                payload = json.dumps(state_snapshot(game_app))
                await resp.write(f"data: {payload}\n\n".encode())
                await asyncio.sleep(1.0)
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        return resp

    aio_app = web.Application()
    aio_app.add_routes(routes)
    return aio_app


async def start_server(game_app, host: str = "127.0.0.1",
                       port: int = 8789) -> web.AppRunner:
    aio_app = build_app(game_app)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
