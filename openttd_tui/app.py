"""Textual app — 4-panel OpenTTD-inspired TUI around the pure-Python Game sim.

Mirrors the simcity-tui layout (MapView + side panels + flash bar +
message log) but drives the `Game` class from `engine.py` instead of
Micropolis. Build/demolish tools map to `game.build_road`,
`game.build_rail`, `game.build_station`, `game.place_vehicle`,
`game.demolish`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.geometry import Region, Size
from textual.message import Message
from textual.reactive import reactive
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import Footer, Header, RichLog, Static

from . import engine as E
from . import tiles
from .screens import FinanceScreen, HelpScreen, TownsScreen, VehicleScreen
from .sounds import SoundBoard


# ---- Tool catalogue --------------------------------------------------------

@dataclass(frozen=True)
class ToolDef:
    key: str
    code: str
    label: str
    cost: int
    glyph: str
    style: str


TOOLS: list[ToolDef] = [
    ToolDef("1", "ROAD",    "Build Road",        200,  "─", "bold rgb(200,190,150) on rgb(25,22,15)"),
    ToolDef("2", "RAIL",    "Build Rail",        400,  "═", "bold rgb(220,220,220) on rgb(25,25,28)"),
    ToolDef("3", "DEMO",    "Demolish",           50,  "×", "bold rgb(220,80,80) on rgb(40,15,15)"),
    ToolDef("4", "STA_RAIL","Rail Station",      800,  "▣", "bold rgb(255,220,80) on rgb(40,35,10)"),
    ToolDef("5", "STA_BUS", "Bus Stop",          400,  "◊", "bold rgb(120,220,180) on rgb(10,35,30)"),
    ToolDef("6", "STA_TRK", "Truck Stop",        400,  "◊", "bold rgb(220,180,80) on rgb(35,28,10)"),
    ToolDef("7", "STA_DOCK","Dock",             1200,  "⚓", "bold rgb(140,200,240) on rgb(10,25,45)"),
    ToolDef("8", "STA_AIR", "Airport",          5000,  "✈", "bold rgb(230,230,230) on rgb(35,35,38)"),
    ToolDef("9", "VEH_TRN", "Spawn Train",      8000,  "●", "bold rgb(255,240,120) on rgb(40,30,10)"),
    ToolDef("0", "VEH_RD",  "Spawn Bus/Truck",  1500,  "◉", "bold rgb(250,180,80) on rgb(40,25,10)"),
]


_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---- MapView ---------------------------------------------------------------

class MapView(ScrollView):
    """Renders the 64×48 tile grid via per-row Strips. Stores cursor as
    reactives so movement only repaints affected rows."""

    DEFAULT_CSS = "MapView { padding: 0; }"

    cursor_x: reactive[int] = reactive(E.MAP_W // 2)
    cursor_y: reactive[int] = reactive(E.MAP_H // 2)

    class ToolApply(Message):
        def __init__(self, x: int, y: int) -> None:
            self.x, self.y = x, y
            super().__init__()

    class DragApply(Message):
        def __init__(self, x1: int, y1: int, x2: int, y2: int) -> None:
            self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
            super().__init__()

    def __init__(self, game: E.Game) -> None:
        super().__init__()
        self.game = game
        self.virtual_size = Size(E.MAP_W, E.MAP_H)
        # Pre-parse every style once so render_line doesn't pay Style.parse().
        self._styles: dict[str, Style] = {
            klass: Style.parse(tiles.style_for(klass)) for klass in tiles.COLOR
        }
        self._cursor_style = Style.parse("bold black on rgb(255,220,80)")
        self._cursor_dim = Style.parse("bold rgb(40,40,0) on rgb(200,170,40)")
        self._unknown_style = Style.parse("bold rgb(255,0,255) on black")
        # Vehicle overlay styles.
        self._vehicle_styles: dict[str, Style] = {
            "vehicle_train": Style.parse(tiles.style_for("vehicle_train")),
            "vehicle_road":  Style.parse(tiles.style_for("vehicle_road")),
            "vehicle_ship":  Style.parse(tiles.style_for("vehicle_ship")),
            "vehicle_plane": Style.parse(tiles.style_for("vehicle_plane")),
        }
        # Animation frame counter (0/1) for water ripples + cursor blink.
        self._anim_frame: int = 0
        # Serial for skip-redraw on the 1 Hz tick.
        self._last_serial: int = -1
        # Drag tracking for mouse line-build.
        self._drag_last: Optional[tuple[int, int]] = None
        self._drag_start: Optional[tuple[int, int]] = None

    # --- rendering ----------------------------------------------------------

    def advance_animation(self) -> None:
        self._anim_frame ^= 1
        self.refresh()

    def refresh_all_tiles(self) -> None:
        self._last_serial = self.game.serial
        self.refresh()

    def refresh_if_changed(self) -> bool:
        if self.game.serial != self._last_serial:
            self._last_serial = self.game.serial
            self.refresh()
            return True
        return False

    def _vehicle_tiles(self) -> dict[tuple[int, int], str]:
        """Return {(x,y): vehicle_kind} for all current vehicles (integer tile)."""
        out: dict[tuple[int, int], str] = {}
        for v in self.game.vehicles:
            out[(int(round(v.x)), int(round(v.y)))] = v.kind
        return out

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        tile_y = y + int(scroll_y)
        width = self.size.width
        if tile_y < 0 or tile_y >= E.MAP_H:
            return Strip.blank(width)

        start_x = max(0, int(scroll_x))
        end_x = min(E.MAP_W, start_x + width)

        game = self.game
        styles = self._styles
        unknown = self._unknown_style
        cx, cy = self.cursor_x, self.cursor_y
        cursor_now = self._cursor_dim if self._anim_frame else self._cursor_style

        # Vehicle dict fetched once per row — cheap since vehicles are few.
        vehicle_at = self._vehicle_tiles()
        vehicle_styles = self._vehicle_styles
        vehicle_glyph = tiles.vehicle_glyph

        patterns = tiles._PATTERN
        frame = self._anim_frame

        segments: list[Segment] = []
        run_chars: list[str] = []
        run_style: Optional[Style] = None

        H = E.MAP_H
        for x in range(start_x, end_x):
            word = game._grid[x * H + tile_y]
            glyph, klass = tiles.glyph_and_class(word, game)

            # Pattern cycling: override glyph for terrain classes so large
            # regions don't read as letter spam.
            pat = patterns.get(klass)
            if pat is not None:
                glyph = pat[(x + tile_y) & 1]

            # Water 2-frame animation.
            if klass == "water":
                glyph = ("~", "≈")[frame]

            # Vehicle overlay trumps tile glyph (but not cursor).
            vkind = vehicle_at.get((x, tile_y))
            if vkind is not None and not (x == cx and tile_y == cy):
                vglyph, vklass = vehicle_glyph(vkind)
                glyph = vglyph
                style = vehicle_styles.get(vklass, unknown)
            elif x == cx and tile_y == cy:
                style = cursor_now
            else:
                style = styles.get(klass, unknown)

            if style is run_style:
                run_chars.append(glyph)
            else:
                if run_chars:
                    segments.append(Segment("".join(run_chars), run_style))
                run_chars = [glyph]
                run_style = style

        if run_chars:
            segments.append(Segment("".join(run_chars), run_style))

        visible = end_x - start_x
        if visible < width:
            segments.append(Segment(" " * (width - visible)))
        return Strip(segments, width)

    # --- cursor watchers ----------------------------------------------------

    def _refresh_row(self, tile_y: int) -> None:
        self.refresh(Region(0, tile_y, E.MAP_W, 1))

    def scroll_to_cursor(self) -> None:
        self.scroll_to_region(
            Region(self.cursor_x - 3, self.cursor_y - 2, 7, 5),
            animate=False, force=True,
        )

    def watch_cursor_x(self, old: int, new: int) -> None:
        if not self.is_mounted:
            return
        self._refresh_row(self.cursor_y)
        self.scroll_to_cursor()

    def watch_cursor_y(self, old: int, new: int) -> None:
        if not self.is_mounted:
            return
        self._refresh_row(old)
        self._refresh_row(new)
        self.scroll_to_cursor()

    # --- mouse --------------------------------------------------------------

    def _event_to_tile(self, event: events.MouseEvent) -> Optional[tuple[int, int]]:
        tx = event.x + int(self.scroll_offset.x)
        ty = event.y + int(self.scroll_offset.y)
        if 0 <= tx < E.MAP_W and 0 <= ty < E.MAP_H:
            return (tx, ty)
        return None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        spot = self._event_to_tile(event)
        if spot is None:
            return
        self.cursor_x, self.cursor_y = spot
        if event.button == 1:
            self.capture_mouse()
            self._drag_last = spot
            self._drag_start = spot
            self.post_message(self.ToolApply(*spot))

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._drag_last is None:
            return
        spot = self._event_to_tile(event)
        if spot is None or spot == self._drag_last:
            return
        self.cursor_x, self.cursor_y = spot
        self.post_message(self.ToolApply(*spot))
        self._drag_last = spot

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._drag_last is not None:
            self._drag_last = None
            self._drag_start = None
            self.release_mouse()


# ---- Side panels -----------------------------------------------------------

class StatusPanel(Static):
    def __init__(self, game: E.Game) -> None:
        super().__init__()
        self.game = game
        self.border_title = "STATUS"
        self._last: tuple | None = None

    def refresh_panel(self) -> None:
        g = self.game
        snap = (g.year, g.month, g.day, g.funds, len(g.towns),
                len(g.industries), len(g.stations), len(g.vehicles))
        if snap == self._last:
            return
        self._last = snap
        t = Text()
        t.append(f"{_MONTH_NAMES[g.month]} {g.day:>2}, {g.year}\n",
                 style="bold rgb(255,220,80)")
        t.append(f"Balance   £{g.funds:>11,}\n", style="bold green")
        t.append(f"Loan      £{g.loan:>11,}\n", style="dim")
        t.append(f"Last P/L  £{g.profit_last_year:>+11,}\n")
        t.append("\n")
        t.append(f"Towns         {len(g.towns):>3d}\n")
        t.append(f"Industries    {len(g.industries):>3d}\n")
        t.append(f"Stations      {len(g.stations):>3d}\n")
        t.append(f"Vehicles      {len(g.vehicles):>3d}\n")
        self.update(t)


class ToolsPanel(Static):
    class Selected(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self.border_title = "TOOLS"
        self.selected: int = 0

    def on_click(self, event: events.Click) -> None:
        if 0 <= event.y < len(TOOLS):
            self.post_message(self.Selected(event.y))

    def refresh_panel(self) -> None:
        t = Text()
        for i, tool in enumerate(TOOLS):
            prefix = "▶ " if i == self.selected else "  "
            t.append(prefix + tool.key + " ",
                     style="bold reverse" if i == self.selected else "")
            t.append(tool.glyph, style=tool.style)
            t.append(f" {tool.label:<17}",
                     style="bold" if i == self.selected else "")
            t.append(f"£{tool.cost:>5d}\n", style="dim yellow")
        t.append("\n")
        t.append_text(Text.from_markup(
            "[dim]arrows move · enter/space apply · click to place[/]\n"
            "[dim]f finance · v vehicles · t towns[/]\n"
            "[dim]p pause  · ? help  · q quit[/]"
        ))
        self.update(t)


# ---- App -------------------------------------------------------------------

class OpenTTDApp(App):
    CSS_PATH = "tui.tcss"
    TITLE = "OpenTTD — Terminal"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "toggle_pause", "Pause"),
        Binding("f", "finance", "Finance"),
        Binding("v", "vehicles", "Vehicles"),
        Binding("t", "towns", "Towns"),
        Binding("question_mark", "help", "Help"),
        Binding("enter", "apply_tool", "Apply", priority=True),
        Binding("space", "apply_tool", "Apply", show=False, priority=True),
        Binding("up",    "move_cursor(0,-1)", "↑", show=False, priority=True),
        Binding("down",  "move_cursor(0,1)",  "↓", show=False, priority=True),
        Binding("left",  "move_cursor(-1,0)", "←", show=False, priority=True),
        Binding("right", "move_cursor(1,0)",  "→", show=False, priority=True),
        *[Binding(tool.key, f"select_tool({i})", show=False)
          for i, tool in enumerate(TOOLS)],
    ]

    paused: reactive[bool] = reactive(False)

    def __init__(self, seed: int = 1234, *, agent_port: Optional[int] = None,
                 sound: bool = False) -> None:
        super().__init__()
        self._agent_port = agent_port
        self.sounds = SoundBoard(enabled=sound)
        self.game = E.new_game(seed=seed)
        self.map_view = MapView(self.game)
        self.status_panel = StatusPanel(self.game)
        self.tools_panel = ToolsPanel()
        self.message_log = RichLog(
            id="log", highlight=False, markup=True, wrap=False, max_lines=500,
        )
        self.message_log.border_title = "MESSAGE LOG"
        self.flash_bar = Static(" ", id="flash-bar")
        self._flash_timer = None
        self._last_log_text = ""
        self._last_log_count = 0
        # Optional agent API runner (set in on_mount).
        self._agent_runner = None

    # --- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="map-col"):
                yield self.map_view
                yield self.flash_bar
                yield self.message_log
            with Vertical(id="side"):
                yield self.status_panel
                yield self.tools_panel
        yield Footer()

    # --- lifecycle ----------------------------------------------------------

    async def on_mount(self) -> None:
        self.map_view.border_title = f"World  {E.MAP_W}×{E.MAP_H}"
        self.map_view.refresh_all_tiles()
        self.map_view.scroll_to_cursor()
        self.status_panel.refresh_panel()
        self.tools_panel.refresh_panel()
        self.log_msg("Welcome. Build roads/rails, place stations, then trains.",
                     level="info")
        self.log_msg("Press [bold]?[/] for keys, [bold]f[/] for finance.",
                     level="info")
        self._show_hover_info(self.map_view.cursor_x, self.map_view.cursor_y,
                              force=True)
        self.update_header()
        # 10 Hz sim tick, 1 Hz redraw, 2 Hz animation.
        self.set_interval(0.1, self.tick)
        self.set_interval(1.0, self.redraw_map)
        self.set_interval(0.5, self.map_view.advance_animation)
        # Start agent API if requested.
        if self._agent_port is not None:
            from .agent_api import start_server
            self._agent_runner = await start_server(self, port=self._agent_port)
            self.log_msg(
                f"[cyan]agent API on http://127.0.0.1:{self._agent_port}[/]",
                level="info",
            )

    def tick(self) -> None:
        if self.paused:
            return
        self.game.tick()
        # Drain engine events → message log.
        for level, text in self.game.drain_events():
            self.log_msg(text, level=level)
        self.status_panel.refresh_panel()
        self.update_header()

    def redraw_map(self) -> None:
        self.map_view.refresh_if_changed()

    def update_header(self) -> None:
        g = self.game
        paused = " · ⏸ PAUSED" if self.paused else ""
        self.sub_title = (
            f"{_MONTH_NAMES[g.month]} {g.day:>2}, {g.year}  ·  "
            f"£{g.funds:,}  ·  {len(g.vehicles)} veh{paused}"
        )

    # --- logging / flash ----------------------------------------------------

    _LOG_LEVELS = {
        "info":     ("ℹ ", "cyan"),
        "success":  ("✓ ", "green"),
        "warn":     ("⚠ ", "yellow"),
        "error":    ("✗ ", "red"),
        "news":     ("📰", "magenta"),
        "disaster": ("🔥", "bold red"),
    }

    def log_msg(self, msg: str, level: str = "info") -> None:
        g = self.game
        stamp = f"[dim][{_MONTH_NAMES[g.month]} {g.year}][/]"
        icon, color = self._LOG_LEVELS.get(level, self._LOG_LEVELS["info"])
        line = f"{stamp} [bold {color}]{icon}[/] {msg}"
        if msg == self._last_log_text and self._last_log_count >= 1:
            self._last_log_count += 1
            try:
                self.message_log.lines.pop()
            except IndexError:
                pass
            self.message_log.write(f"{line} [dim]×{self._last_log_count}[/]")
        else:
            self._last_log_text = msg
            self._last_log_count = 1
            self.message_log.write(line)

    def flash_status(self, msg: str, seconds: float = 1.5) -> None:
        self.flash_bar.update(Text.from_markup(msg))
        if self._flash_timer is not None:
            self._flash_timer.stop()

        def _clear():
            self._flash_timer = None
            self._show_hover_info(self.map_view.cursor_x,
                                  self.map_view.cursor_y, force=True)

        self._flash_timer = self.set_timer(seconds, _clear)

    def _show_hover_info(self, x: int, y: int, force: bool = False) -> None:
        if not force and self._flash_timer is not None:
            return
        word = self.game._grid[x * E.MAP_H + y]
        glyph, klass = tiles.glyph_and_class(word, self.game)
        style = tiles.style_for(klass)
        self.flash_bar.update(Text.from_markup(
            f"[{style}] {glyph} [/]  ({x},{y})  [bold]{klass}[/]"
        ))

    # --- actions ------------------------------------------------------------

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        self.flash_status("[yellow]⏸ paused[/]" if self.paused
                          else "[green]▶ resumed[/]")
        self.update_header()

    def action_move_cursor(self, dx: str, dy: str) -> None:
        cx = max(0, min(E.MAP_W - 1, self.map_view.cursor_x + int(dx)))
        cy = max(0, min(E.MAP_H - 1, self.map_view.cursor_y + int(dy)))
        self.map_view.cursor_x = cx
        self.map_view.cursor_y = cy
        self._show_hover_info(cx, cy)
        self.update_header()

    def action_select_tool(self, idx: str) -> None:
        i = int(idx)
        if 0 <= i < len(TOOLS):
            self.tools_panel.selected = i
            self.tools_panel.refresh_panel()
            self.flash_status(f"Tool: [bold]{TOOLS[i].label}[/]")
            self.sounds.play("click")

    def action_apply_tool(self) -> None:
        cx, cy = self.map_view.cursor_x, self.map_view.cursor_y
        tool = TOOLS[self.tools_panel.selected]
        ok, msg = self._apply_tool_code(tool.code, cx, cy)
        if ok:
            self.flash_status(f"[green]✓ {tool.label}[/]  {msg}")
            self.sounds.play("demolish" if tool.code == "DEMO" else "build")
        else:
            self.flash_status(f"[red]✗ {msg}[/]")
            self.sounds.play("deny")
        # Drain any engine events produced by the tool.
        for level, text in self.game.drain_events():
            self.log_msg(text, level=level)
        self.map_view.refresh_all_tiles()
        self.status_panel.refresh_panel()
        self.update_header()

    def _apply_tool_code(self, code: str, x: int, y: int) -> tuple[bool, str]:
        """Dispatch a tool code to the right game method."""
        g = self.game
        if code == "ROAD":
            return g.build_road(x, y)
        if code == "RAIL":
            return g.build_rail(x, y)
        if code == "DEMO":
            return g.demolish(x, y)
        if code == "STA_RAIL":
            return g.build_station(x, y, "rail")
        if code == "STA_BUS":
            return g.build_station(x, y, "bus")
        if code == "STA_TRK":
            return g.build_station(x, y, "truck")
        if code == "STA_DOCK":
            return g.build_station(x, y, "dock")
        if code == "STA_AIR":
            return g.build_station(x, y, "airport")
        if code == "VEH_TRN":
            return g.place_vehicle("TRAIN", x, y)
        if code == "VEH_RD":
            # Pick BUS or TRUCK based on station kind at the cursor.
            tt = E.tile_type(g.tile_at(x, y))
            if tt == E.MP_STATION:
                low = E.tile_low(g.tile_at(x, y))
                if low == 1:
                    return g.place_vehicle("BUS", x, y)
                if low == 2:
                    return g.place_vehicle("TRUCK", x, y)
            return False, "stand on a bus/truck station first"
        return False, f"unknown tool {code}"

    # --- modal actions ------------------------------------------------------

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_finance(self) -> None:
        self.push_screen(FinanceScreen(self.game))

    def action_vehicles(self) -> None:
        self.push_screen(VehicleScreen(self.game))

    def action_towns(self) -> None:
        self.push_screen(TownsScreen(self.game))

    # --- message handlers ---------------------------------------------------

    def on_tools_panel_selected(self, message: ToolsPanel.Selected) -> None:
        self.action_select_tool(str(message.index))

    def on_map_view_tool_apply(self, message: MapView.ToolApply) -> None:
        """Clicks / drags on the map post ToolApply — funnel through the
        same path as enter-key apply so costs and side effects match."""
        self.map_view.cursor_x, self.map_view.cursor_y = message.x, message.y
        self.action_apply_tool()


def run(seed: int = 1234, *, agent_port: Optional[int] = None,
        headless: bool = False, sound: bool = True) -> None:
    if headless:
        import asyncio as _asyncio
        port = agent_port if agent_port is not None else 8789
        from .agent_api import start_server
        app = OpenTTDApp(seed=seed, agent_port=port, sound=False)

        async def _main() -> None:
            runner = await start_server(app, port=port)
            print(f"[openttd-tui] headless, agent API on "
                  f"http://127.0.0.1:{port}")
            try:
                while True:
                    if not app.paused:
                        app.game.tick()
                    await _asyncio.sleep(0.1)
            finally:
                await runner.cleanup()

        try:
            _asyncio.run(_main())
        except KeyboardInterrupt:
            pass
        return

    app = OpenTTDApp(seed=seed, agent_port=agent_port, sound=sound)
    try:
        app.run()
    finally:
        import sys
        sys.stdout.write(
            "\033[?1000l\033[?1002l\033[?1003l\033[?1006l\033[?1015l\033[?25h"
        )
        sys.stdout.flush()
