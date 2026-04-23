"""Headless QA driver for openttd-tui.

Usage:
    python -m tests.qa           # all
    python -m tests.qa cursor    # name pattern filter
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from openttd_tui import engine as E
from openttd_tui import tiles
from openttd_tui.app import OpenTTDApp, TOOLS

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    fn: Callable[[OpenTTDApp, "object"], Awaitable[None]]


# ---------- helpers ----------

def tile_class(app: OpenTTDApp, x: int, y: int) -> str:
    word = app.game.tile_at(x, y)
    return tiles.glyph_and_class(word, app.game)[1]


async def find_grass(app: OpenTTDApp) -> tuple[int, int] | None:
    g = app.game
    for y in range(E.MAP_H):
        for x in range(E.MAP_W):
            t = E.tile_type(g.tile_at(x, y))
            low = E.tile_low(g.tile_at(x, y))
            if t == E.MP_CLEAR and low == E.CLEAR_GRASS:
                return x, y
    return None


# ---------- scenarios ----------

async def s_mount_clean(app, pilot):
    assert app.map_view is not None
    assert app.status_panel is not None
    assert app.tools_panel is not None
    assert app.game is not None
    assert len(app.game.towns) >= 1, "world gen produced no towns"
    assert len(app.game.industries) >= 1, "world gen produced no industries"


async def s_cursor_starts_centered(app, pilot):
    assert app.map_view.cursor_x == E.MAP_W // 2
    assert app.map_view.cursor_y == E.MAP_H // 2


async def s_cursor_moves(app, pilot):
    sx, sy = app.map_view.cursor_x, app.map_view.cursor_y
    await pilot.press("right", "right", "right")
    await pilot.press("down", "down")
    assert app.map_view.cursor_x == sx + 3, app.map_view.cursor_x
    assert app.map_view.cursor_y == sy + 2, app.map_view.cursor_y


async def s_cursor_clamps(app, pilot):
    for _ in range(E.MAP_W + 10):
        await pilot.press("left")
    assert app.map_view.cursor_x == 0
    for _ in range(E.MAP_H + 10):
        await pilot.press("up")
    assert app.map_view.cursor_y == 0


async def s_tool_select(app, pilot):
    await pilot.press("1")  # Road
    sel = app.tools_panel.selected
    assert TOOLS[sel].code == "ROAD", TOOLS[sel].code


async def s_tool_select_rail(app, pilot):
    await pilot.press("2")
    sel = app.tools_panel.selected
    assert TOOLS[sel].code == "RAIL", TOOLS[sel].code


async def s_apply_road_deducts_funds(app, pilot):
    spot = await find_grass(app)
    assert spot is not None
    app.map_view.cursor_x, app.map_view.cursor_y = spot
    await pilot.pause()
    funds_before = app.game.funds
    await pilot.press("1")      # Road
    await pilot.press("enter")
    await pilot.pause()
    assert app.game.funds < funds_before, (funds_before, app.game.funds)


async def s_apply_road_changes_tile(app, pilot):
    spot = await find_grass(app)
    assert spot is not None
    app.map_view.cursor_x, app.map_view.cursor_y = spot
    await pilot.pause()
    before = tile_class(app, *spot)
    await pilot.press("1")
    await pilot.press("enter")
    await pilot.pause()
    after = tile_class(app, *spot)
    assert before == "grass"
    assert after == "road", f"expected road, got {after!r}"


async def s_apply_rail_changes_tile(app, pilot):
    spot = await find_grass(app)
    assert spot is not None
    app.map_view.cursor_x, app.map_view.cursor_y = spot
    await pilot.pause()
    await pilot.press("2")  # rail
    await pilot.press("enter")
    await pilot.pause()
    assert tile_class(app, *spot) == "rail"


async def s_rail_station_needs_rail(app, pilot):
    spot = await find_grass(app)
    assert spot is not None
    app.map_view.cursor_x, app.map_view.cursor_y = spot
    await pilot.pause()
    # Try rail station on grass — must fail.
    await pilot.press("4")  # rail station
    await pilot.press("enter")
    await pilot.pause()
    flash = str(app.flash_bar.content)
    assert "✗" in flash or "needs rail" in flash, flash


async def s_build_rail_then_station(app, pilot):
    spot = await find_grass(app)
    assert spot is not None
    app.map_view.cursor_x, app.map_view.cursor_y = spot
    await pilot.pause()
    await pilot.press("2")  # rail
    await pilot.press("enter")
    await pilot.pause()
    await pilot.press("4")  # rail station
    await pilot.press("enter")
    await pilot.pause()
    assert tile_class(app, *spot) == "station_rail", tile_class(app, *spot)
    assert any(s.kind == "rail" for s in app.game.stations)


async def s_pause_halts_ticks(app, pilot):
    await pilot.pause(0.2)
    tick_before = app.game.tick_count
    await pilot.press("p")
    assert app.paused is True
    await pilot.pause(0.4)
    assert app.game.tick_count == tick_before, (
        f"tick advanced while paused: {tick_before} → {app.game.tick_count}"
    )
    await pilot.press("p")
    assert app.paused is False


async def s_modal_open_close_help(app, pilot):
    await pilot.press("question_mark")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "HelpScreen"
    await pilot.press("escape")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "Screen"


async def s_modal_open_close_finance(app, pilot):
    await pilot.press("f")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "FinanceScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_modal_open_close_vehicles(app, pilot):
    await pilot.press("v")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "VehicleScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_modal_open_close_towns(app, pilot):
    await pilot.press("t")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "TownsScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_demolish_house(app, pilot):
    # Find a house tile.
    house = None
    for y in range(E.MAP_H):
        for x in range(E.MAP_W):
            if E.tile_type(app.game.tile_at(x, y)) == E.MP_HOUSE:
                house = (x, y)
                break
        if house:
            break
    assert house is not None, "no house on map"
    app.map_view.cursor_x, app.map_view.cursor_y = house
    await pilot.pause()
    await pilot.press("3")  # demolish
    await pilot.press("enter")
    await pilot.pause()
    assert E.tile_type(app.game.tile_at(*house)) != E.MP_HOUSE


async def s_sound_disabled_is_noop(app, pilot):
    assert app.sounds.enabled is False
    app.sounds.play("build")
    app.sounds.play("nonexistent")


async def s_state_snapshot_headless(app, pilot):
    """A fresh (unmounted) app must snapshot cleanly."""
    from openttd_tui.agent_api import state_snapshot
    fresh = OpenTTDApp()
    s = state_snapshot(fresh)
    for k in ("year", "funds", "cursor", "towns", "industries"):
        assert k in s, f"missing {k}"


async def s_map_renders_with_backgrounds(app, pilot):
    mv = app.map_view
    mv.scroll_to_cursor()
    await pilot.pause()
    viewport_y = mv.cursor_y - int(mv.scroll_offset.y)
    strip = mv.render_line(viewport_y)
    both = 0
    for seg in list(strip):
        if not seg.style:
            continue
        if seg.style.color is not None and seg.style.bgcolor is not None:
            both += 1
    assert both > 0, "no tiles rendered with backgrounds"


async def s_cursor_renders_with_highlight(app, pilot):
    from rich.style import Style
    expected_bright = Style.parse("bold black on rgb(255,220,80)")
    expected_dim = Style.parse("bold rgb(40,40,0) on rgb(200,170,40)")
    app.map_view.scroll_to_cursor()
    await pilot.pause()
    # Force anim frame to 0 for determinism.
    app.map_view._anim_frame = 0
    cy = app.map_view.cursor_y
    scroll_y = int(app.map_view.scroll_offset.y)
    strip = app.map_view.render_line(cy - scroll_y)
    hits = sum(
        len(seg.text) for seg in list(strip)
        if seg.style in (expected_bright, expected_dim)
    )
    assert hits == 1, f"expected 1 cursor cell, got {hits}"


async def s_unknown_class_does_not_crash(app, pilot):
    mv = app.map_view
    saved = mv._styles.pop("grass", None)
    try:
        strip = mv.render_line(0)
        assert len(list(strip)) > 0
    finally:
        if saved is not None:
            mv._styles["grass"] = saved


async def s_water_animates(app, pilot):
    mv = app.map_view
    # Find water on the map and render its row under both anim frames.
    water = None
    for y in range(E.MAP_H):
        for x in range(E.MAP_W):
            if E.tile_type(app.game.tile_at(x, y)) == E.MP_WATER:
                water = (x, y)
                break
        if water:
            break
    if water is None:
        return  # no water this seed — skip
    from textual.geometry import Region
    mv.scroll_to_region(Region(water[0], water[1], 1, 1),
                        animate=False, force=True)
    await pilot.pause()
    vy = water[1] - int(mv.scroll_offset.y)
    vx = water[0] - int(mv.scroll_offset.x)
    mv._anim_frame = 0
    g0 = "".join(seg.text for seg in list(mv.render_line(vy)))[vx]
    mv._anim_frame = 1
    g1 = "".join(seg.text for seg in list(mv.render_line(vy)))[vx]
    assert g0 != g1, f"water glyph did not cycle: {g0!r} == {g1!r}"


async def s_status_panel_throttles(app, pilot):
    p = app.status_panel
    p.refresh_panel()
    snap1 = p._last
    for _ in range(5):
        p.refresh_panel()
    assert p._last == snap1


async def s_log_collapse(app, pilot):
    before = len(app.message_log.lines)
    app.log_msg("same")
    app.log_msg("same")
    app.log_msg("same")
    grew = len(app.message_log.lines) - before
    assert grew == 1, f"expected 1 line, got {grew}"
    last = str(app.message_log.lines[-1])
    assert "×3" in last, last


async def s_tool_change_via_mouse_message(app, pilot):
    """Click-select semantics: a ToolsPanel.Selected message routes into
    select_tool."""
    app.on_tools_panel_selected(type("M", (), {"index": 1})())  # rail
    assert TOOLS[app.tools_panel.selected].code == "RAIL"


async def s_flash_bar_clears(app, pilot):
    app.flash_status("hello", seconds=0.15)
    assert "hello" in str(app.flash_bar.content)
    await pilot.pause(0.25)
    assert "hello" not in str(app.flash_bar.content)


async def s_tick_produces_events_monthly(app, pilot):
    """Running the sim for ~30 game days shouldn't crash and should
    eventually drain events (new industry stockpile, etc.)."""
    g = app.game
    start_year = g.year
    start_month = g.month
    # 30 days × 30 ticks = 900 ticks → one month.
    for _ in range(900):
        g.tick()
    assert (g.year, g.month) != (start_year, start_month), (
        "month did not advance after 900 ticks"
    )


async def s_vehicle_place_requires_stations(app, pilot):
    """Spawning a train with 0 rail stations must fail with a clear msg."""
    spot = await find_grass(app)
    assert spot is not None
    app.map_view.cursor_x, app.map_view.cursor_y = spot
    await pilot.pause()
    await pilot.press("9")  # spawn train tool
    await pilot.press("enter")
    await pilot.pause()
    flash = str(app.flash_bar.content)
    assert "✗" in flash, flash


async def s_road_connection_retopo(app, pilot):
    """Two adjacent road tiles must update their connection masks so
    the glyphs reflect joined segments."""
    g = app.game
    spot = await find_grass(app)
    assert spot is not None
    x, y = spot
    # Make sure the neighbour is also grass.
    if y + 1 >= E.MAP_H:
        return
    if E.tile_type(g.tile_at(x, y + 1)) != E.MP_CLEAR:
        return
    g.build_road(x, y)
    g.build_road(x, y + 1)
    # First tile should now have the south bit, second has north.
    low1 = E.tile_low(g.tile_at(x, y))
    low2 = E.tile_low(g.tile_at(x, y + 1))
    assert low1 & E.S, f"south bit missing on upper: mask={low1}"
    assert low2 & E.N, f"north bit missing on lower: mask={low2}"


SCENARIOS: list[Scenario] = [
    Scenario("mount_clean", s_mount_clean),
    Scenario("cursor_starts_centered", s_cursor_starts_centered),
    Scenario("cursor_moves", s_cursor_moves),
    Scenario("cursor_clamps", s_cursor_clamps),
    Scenario("tool_select_road", s_tool_select),
    Scenario("tool_select_rail", s_tool_select_rail),
    Scenario("apply_road_deducts_funds", s_apply_road_deducts_funds),
    Scenario("apply_road_changes_tile", s_apply_road_changes_tile),
    Scenario("apply_rail_changes_tile", s_apply_rail_changes_tile),
    Scenario("rail_station_needs_rail", s_rail_station_needs_rail),
    Scenario("build_rail_then_station", s_build_rail_then_station),
    Scenario("pause_halts_ticks", s_pause_halts_ticks),
    Scenario("help_opens_and_closes", s_modal_open_close_help),
    Scenario("finance_opens_and_closes", s_modal_open_close_finance),
    Scenario("vehicles_opens_and_closes", s_modal_open_close_vehicles),
    Scenario("towns_opens_and_closes", s_modal_open_close_towns),
    Scenario("demolish_removes_house", s_demolish_house),
    Scenario("sound_disabled_is_noop", s_sound_disabled_is_noop),
    Scenario("state_snapshot_headless", s_state_snapshot_headless),
    Scenario("map_renders_with_backgrounds", s_map_renders_with_backgrounds),
    Scenario("cursor_renders_with_highlight", s_cursor_renders_with_highlight),
    Scenario("unknown_class_does_not_crash", s_unknown_class_does_not_crash),
    Scenario("water_glyph_animates", s_water_animates),
    Scenario("status_panel_skips_unchanged", s_status_panel_throttles),
    Scenario("log_collapses_duplicates", s_log_collapse),
    Scenario("tool_change_via_message", s_tool_change_via_mouse_message),
    Scenario("flash_bar_clears", s_flash_bar_clears),
    Scenario("tick_advances_month", s_tick_produces_events_monthly),
    Scenario("vehicle_needs_stations", s_vehicle_place_requires_stations),
    Scenario("road_connection_retopo", s_road_connection_retopo),
]


# ---------- driver ----------

async def run_one(scn: Scenario) -> tuple[str, bool, str]:
    app = OpenTTDApp(sound=False)
    try:
        async with app.run_test(size=(180, 60)) as pilot:
            await pilot.pause()
            try:
                await scn.fn(app, pilot)
            except AssertionError as e:
                app.save_screenshot(str(OUT / f"{scn.name}.FAIL.svg"))
                return (scn.name, False, f"AssertionError: {e}")
            except Exception as e:
                app.save_screenshot(str(OUT / f"{scn.name}.ERROR.svg"))
                return (scn.name, False,
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            app.save_screenshot(str(OUT / f"{scn.name}.PASS.svg"))
            return (scn.name, True, "")
    except Exception as e:
        return (scn.name, False,
                f"harness error: {type(e).__name__}: {e}\n{traceback.format_exc()}")


async def main(pattern: str | None = None) -> int:
    scenarios = [s for s in SCENARIOS if not pattern or pattern in s.name]
    if not scenarios:
        print(f"no scenarios match {pattern!r}")
        return 2
    results = []
    for scn in scenarios:
        name, ok, msg = await run_one(scn)
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name}")
        if not ok:
            for line in msg.splitlines():
                print(f"      {line}")
        results.append((name, ok, msg))
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(main(pattern)))
