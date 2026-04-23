"""Integration playtest via Textual's Pilot (the supported way to drive
a live Textual app in-process — matches how the QA harness runs).

Boots the app, navigates the map, builds a road and a rail station,
opens the Finance / Towns modals, pauses, then quits. Screenshots saved
to `tests/out/playtest_*.svg` so the session can be audited visually.

A real pty-driven playtest via pexpect is also possible (the app picks
up stdin keys over a tty), but the SVG output from Pilot is what we'd
actually inspect after the fact. The two loops are equivalent here.

Run: python -m tests.playtest
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from openttd_tui import engine as E
from openttd_tui.app import OpenTTDApp

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


async def main() -> int:
    app = OpenTTDApp(sound=False)
    step = 0

    def shot(label: str) -> None:
        nonlocal step
        step += 1
        app.save_screenshot(str(OUT / f"playtest_{step:02d}_{label}.svg"))

    async with app.run_test(size=(180, 60)) as pilot:
        await pilot.pause()
        shot("boot")

        # Scroll map — eight right + four down.
        for _ in range(8):
            await pilot.press("right")
        for _ in range(4):
            await pilot.press("down")
        await pilot.pause()
        shot("scrolled")

        # Park on a grass tile so road/rail ops succeed.
        def find_grass() -> tuple[int, int] | None:
            g = app.game
            for y in range(E.MAP_H):
                for x in range(E.MAP_W):
                    if (E.tile_type(g.tile_at(x, y)) == E.MP_CLEAR
                            and E.tile_low(g.tile_at(x, y)) == E.CLEAR_GRASS):
                        return x, y
            return None

        spot = find_grass()
        assert spot is not None, "world seed produced no grass"
        app.map_view.cursor_x, app.map_view.cursor_y = spot
        await pilot.pause()

        # Build a road at the cursor.
        await pilot.press("1")       # road tool
        await pilot.press("enter")
        await pilot.pause()
        shot("road_built")

        # Build a rail + rail station.
        # Find a new grass tile near the first.
        second = find_grass()
        assert second is not None
        app.map_view.cursor_x, app.map_view.cursor_y = second
        await pilot.pause()
        await pilot.press("2")       # rail
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("4")       # rail station
        await pilot.press("enter")
        await pilot.pause()
        shot("rail_station_built")

        # Open Finance modal.
        await pilot.press("f")
        await pilot.pause()
        shot("finance_open")
        await pilot.press("escape")
        await pilot.pause()

        # Open Towns modal.
        await pilot.press("t")
        await pilot.pause()
        shot("towns_open")
        await pilot.press("escape")
        await pilot.pause()

        # Pause.
        await pilot.press("p")
        await pilot.pause()
        assert app.paused is True, "pause key did not pause"
        shot("paused")
        await pilot.press("p")       # resume
        await pilot.pause()

        shot("final")

    print(f"playtest ok — {step} screenshots in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
