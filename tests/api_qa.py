"""Agent-API smoke tests — spin up the aiohttp server on a free port,
hit every endpoint, assert on response shape.

Run: python -m tests.api_qa
"""

from __future__ import annotations

import asyncio
import socket
import sys

import aiohttp

from openttd_tui import engine as E
from openttd_tui.agent_api import start_server
from openttd_tui.app import OpenTTDApp


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def main() -> int:
    port = _free_port()
    app = OpenTTDApp(sound=False)
    runner = await start_server(app, port=port)
    base = f"http://127.0.0.1:{port}"
    failures = 0
    try:
        async with aiohttp.ClientSession() as s:
            # /
            async with s.get(f"{base}/") as r:
                body = await r.json()
                assert r.status == 200
                assert "endpoints" in body

            # /state
            async with s.get(f"{base}/state") as r:
                body = await r.json()
                assert r.status == 200
                for k in ("year", "funds", "cursor", "towns", "industries"):
                    assert k in body, f"missing {k}"

            # /tools
            async with s.get(f"{base}/tools") as r:
                body = await r.json()
                assert r.status == 200
                assert isinstance(body, list) and len(body) >= 5

            # /map
            async with s.get(f"{base}/map") as r:
                body = await r.json()
                assert r.status == 200
                assert body["w"] == E.MAP_W
                assert body["h"] == E.MAP_H
                assert len(body["grid"]) == E.MAP_H

            # /tile
            async with s.get(f"{base}/tile?x=5&y=5") as r:
                body = await r.json()
                assert r.status == 200
                assert body["x"] == 5 and body["y"] == 5 and "class" in body

            # /tool — try a road on (0,0).
            payload = {"code": "ROAD", "x": 0, "y": 0}
            async with s.post(f"{base}/tool", json=payload) as r:
                body = await r.json()
                assert r.status == 200
                assert "ok" in body and "funds" in body

            # /advance
            async with s.post(f"{base}/advance", json={"ticks": 50}) as r:
                body = await r.json()
                assert r.status == 200
                assert body["ticks"] == 50

            # /pause
            async with s.post(f"{base}/pause", json={"paused": True}) as r:
                body = await r.json()
                assert body["paused"] is True
            async with s.post(f"{base}/pause", json={"paused": False}) as r:
                body = await r.json()
                assert body["paused"] is False

            print("all API smoke checks passed")
    except AssertionError as e:
        print(f"FAIL: {e}")
        failures += 1
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        failures += 1
    finally:
        await runner.cleanup()
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
