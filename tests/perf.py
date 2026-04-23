"""Hot-path benchmarks for openttd-tui.

Tests the three things most likely to dominate frame time:
  - engine.tick() at 10 Hz with a few vehicles
  - render_line() for a single map row
  - a full world snapshot (what the agent API returns per /state hit)

Run: python -m tests.perf
"""

from __future__ import annotations

import time

from openttd_tui import engine as E
from openttd_tui.app import OpenTTDApp


def bench(name: str, fn, iters: int) -> None:
    # Warmup.
    for _ in range(max(1, iters // 20)):
        fn()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    dt = (time.perf_counter() - t0) / iters
    us = dt * 1_000_000
    print(f"  {name:<32}  {us:>9.2f} μs / call   ({iters} iters)")


def main() -> None:
    print("openttd-tui perf bench\n")

    # 1) engine tick, empty world + vehicles.
    g = E.new_game(seed=1234)
    bench("engine.tick (no vehicles)", g.tick, 10_000)

    # Seed a couple stations + trains to make the tick do real work.
    # Find two grass tiles, lay rail, make two stations, spawn a train.
    grass_spots = []
    for y in range(E.MAP_H):
        for x in range(E.MAP_W):
            if (E.tile_type(g.tile_at(x, y)) == E.MP_CLEAR
                    and E.tile_low(g.tile_at(x, y)) == E.CLEAR_GRASS):
                grass_spots.append((x, y))
                if len(grass_spots) >= 2:
                    break
        if len(grass_spots) >= 2:
            break
    if len(grass_spots) >= 2:
        ax, ay = grass_spots[0]
        bx, by = grass_spots[1]
        g.build_rail(ax, ay); g.build_rail(bx, by)
        g.build_station(ax, ay, "rail"); g.build_station(bx, by, "rail")
        g.place_vehicle("TRAIN", ax, ay)
        bench("engine.tick (1 train)", g.tick, 10_000)

    # 2) render_line on the map view — needs a live app context so the
    # ScrollView has a real size. Use App.run_test().
    import asyncio

    async def _render_bench() -> None:
        app = OpenTTDApp(sound=False)
        async with app.run_test(size=(180, 60)) as pilot:
            await pilot.pause()
            bench("render_line (row 10)",
                  lambda: app.map_view.render_line(10), 2_000)
            bench("game.snapshot()", app.game.snapshot, 5_000)

    asyncio.run(_render_bench())


if __name__ == "__main__":
    main()
