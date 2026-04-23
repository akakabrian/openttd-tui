"""Tile → (glyph, class) lookup for the OpenTTD TUI renderer.

Takes an engine tile word (16 bits, laid out per engine.py) and returns
a glyph + tile class name. COLOR / BG dicts + style_for() give Rich
styles; _PATTERN applies 2-glyph checkerboarding so large terrain
regions don't read as letter spam.
"""

from __future__ import annotations

from . import engine as E

# 16-entry road / rail connection table.
# Key = 4-bit connection mask (N=1, E=2, S=4, W=8).
# 0 = isolated / no neighbours
_ROAD_GLYPH: dict[int, str] = {
    0:  "•",
    1:  "│",   # N only
    2:  "─",   # E only
    3:  "└",   # N + E
    4:  "│",   # S only
    5:  "│",   # N + S
    6:  "┌",   # E + S
    7:  "├",   # N + E + S
    8:  "─",   # W only
    9:  "┘",   # N + W
    10: "─",   # E + W
    11: "┴",   # N + E + W
    12: "┐",   # S + W
    13: "┤",   # N + S + W
    14: "┬",   # E + S + W
    15: "┼",   # 4-way
}

# Rails use heavy box glyphs so they're visibly distinct from roads.
_RAIL_GLYPH: dict[int, str] = {
    0:  "•",
    1:  "║",
    2:  "═",
    3:  "╚",
    4:  "║",
    5:  "║",
    6:  "╔",
    7:  "╠",
    8:  "═",
    9:  "╝",
    10: "═",
    11: "╩",
    12: "╗",
    13: "╣",
    14: "╦",
    15: "╬",
}

# Station glyph per station kind (low nibble 0..4).
_STATION_GLYPH: dict[int, tuple[str, str]] = {
    0: ("▣", "station_rail"),
    1: ("◊", "station_bus"),
    2: ("◊", "station_truck"),
    3: ("⚓", "station_dock"),
    4: ("✈", "station_airport"),
}

# Clear (terrain) glyph + class per low nibble.
_CLEAR_GLYPH: dict[int, tuple[str, str]] = {
    E.CLEAR_GRASS:  (",", "grass"),
    E.CLEAR_DIRT:   (".", "dirt"),
    E.CLEAR_FIELDS: ("⋯", "fields"),
    E.CLEAR_ROCKS:  ("▲", "rocks"),
    E.CLEAR_SNOW:   (" ", "snow"),
}

# House density → glyph. Low nibble 0..3.
_HOUSE_GLYPH = {
    0: ("⌂", "house_sm"),
    1: ("░", "house_md"),
    2: ("▒", "house_lg"),
    3: ("▓", "house_xl"),
}

# Industry-tile glyph resolved by the engine's INDUSTRY_TYPES list. The
# low nibble of an MP_INDUSTRY tile is the industry index (capped at 15
# since LOW_MASK = 0x0F). With 8 industries max we stay well inside.
def _industry_glyph(idx: int, game) -> tuple[str, str]:
    if game is None or idx >= len(game.industries):
        return ("?", "misc")
    ind = game.industries[idx]
    itype = E.INDUSTRY_BY_CODE.get(ind.kind)
    if itype is None:
        return ("?", "misc")
    return (itype.glyph, f"ind_{ind.kind}")


# 2-glyph pattern for checkerboard texture (not letter spam).
_PATTERN: dict[str, tuple[str, str]] = {
    "grass":     (",", "."),
    "dirt":      (".", ","),
    "fields":    ("⋯", "⋮"),
    "rocks":     ("▲", "△"),
    "snow":      (" ", "·"),
    "water":     ("~", "≈"),
    "trees_0":   ("♣", "^"),
    "trees_1":   ("^", "♣"),
    "trees_2":   ("♣", "♠"),
    "trees_3":   ("♠", "♣"),
    "house_md":  ("░", "▒"),
    "house_lg":  ("▒", "▓"),
    "house_xl":  ("▓", "█"),
}

# Foreground colours per class.
COLOR: dict[str, str] = {
    "grass":          "rgb(60,120,50)",
    "dirt":           "rgb(110,85,50)",
    "fields":         "rgb(190,180,90)",
    "rocks":          "rgb(140,140,140)",
    "snow":           "rgb(230,230,230)",
    "water":          "rgb(80,130,200)",
    "trees_0":        "rgb(40,110,50)",
    "trees_1":        "rgb(30,100,40)",
    "trees_2":        "rgb(50,130,60)",
    "trees_3":        "rgb(30,90,40)",
    "house_sm":       "rgb(190,170,120)",
    "house_md":       "rgb(200,180,140)",
    "house_lg":       "bold rgb(220,200,160)",
    "house_xl":       "bold rgb(240,220,180)",
    "road":           "rgb(190,180,140)",
    "rail":           "bold rgb(210,210,210)",
    "station_rail":   "bold rgb(255,220,80)",
    "station_bus":    "bold rgb(120,220,180)",
    "station_truck":  "bold rgb(220,180,80)",
    "station_dock":   "bold rgb(140,200,240)",
    "station_airport":"bold rgb(230,230,230)",
    "vehicle_train":  "bold rgb(255,240,120)",
    "vehicle_road":   "bold rgb(250,180,80)",
    "vehicle_ship":   "bold rgb(140,200,240)",
    "vehicle_plane":  "bold rgb(240,240,240)",
    "cursor":         "bold black on rgb(255,220,80)",
    "misc":           "rgb(200,200,200)",
    # Industries — one class per code (ind_*).
    "ind_CMINE":      "bold rgb(230,230,230)",
    "ind_POWRP":      "bold rgb(255,240,120)",
    "ind_FARM":       "bold rgb(230,210,90)",
    "ind_FACT":       "bold rgb(230,180,80)",
    "ind_OILR":       "bold rgb(180,160,240)",
    "ind_OILF":       "bold rgb(230,150,70)",
    "ind_FORST":      "bold rgb(60,170,70)",
    "ind_SAWM":       "bold rgb(200,150,80)",
    "ind_IMINE":      "bold rgb(200,120,90)",
    "ind_STEEL":      "bold rgb(220,220,240)",
    "ind_BANK":       "bold rgb(255,220,80)",
    "ind_FOODP":      "bold rgb(240,180,100)",
}

# Subtle backgrounds per class — nearly black so fg carries the info.
BG: dict[str, str] = {
    "grass":          "rgb(8,20,10)",
    "dirt":           "rgb(25,18,10)",
    "fields":         "rgb(35,30,10)",
    "rocks":          "rgb(25,25,25)",
    "snow":           "rgb(45,45,50)",
    "water":          "rgb(10,25,50)",
    "trees_0":        "rgb(5,18,8)",
    "trees_1":        "rgb(5,15,8)",
    "trees_2":        "rgb(8,22,10)",
    "trees_3":        "rgb(5,15,8)",
    "house_sm":       "rgb(25,20,12)",
    "house_md":       "rgb(30,25,15)",
    "house_lg":       "rgb(35,30,20)",
    "house_xl":       "rgb(40,35,25)",
    "road":           "rgb(22,20,14)",
    "rail":           "rgb(25,25,28)",
    "station_rail":   "rgb(40,35,10)",
    "station_bus":    "rgb(10,35,30)",
    "station_truck":  "rgb(35,28,10)",
    "station_dock":   "rgb(10,25,45)",
    "station_airport":"rgb(35,35,38)",
    "vehicle_train":  "rgb(40,30,10)",
    "vehicle_road":   "rgb(40,25,10)",
    "vehicle_ship":   "rgb(10,25,45)",
    "vehicle_plane":  "rgb(35,35,40)",
    "misc":           "rgb(25,25,25)",
    "ind_CMINE":      "rgb(20,20,22)",
    "ind_POWRP":      "rgb(45,40,10)",
    "ind_FARM":       "rgb(35,30,10)",
    "ind_FACT":       "rgb(35,25,10)",
    "ind_OILR":       "rgb(18,18,40)",
    "ind_OILF":       "rgb(40,22,10)",
    "ind_FORST":      "rgb(8,22,12)",
    "ind_SAWM":       "rgb(30,22,12)",
    "ind_IMINE":      "rgb(30,15,12)",
    "ind_STEEL":      "rgb(25,25,35)",
    "ind_BANK":       "rgb(45,38,10)",
    "ind_FOODP":      "rgb(40,28,12)",
}


def style_for(klass: str) -> str:
    fg = COLOR.get(klass, "rgb(255,0,255)")
    bg = BG.get(klass, "rgb(0,0,0)")
    return f"{fg} on {bg}"


def glyph_and_class(word: int, game=None) -> tuple[str, str]:
    """Dispatch to the right per-type lookup. Game param is optional —
    needed only for industry dereference."""
    tt = E.tile_type(word)
    low = E.tile_low(word)
    if tt == E.MP_CLEAR:
        return _CLEAR_GLYPH.get(low, (".", "dirt"))
    if tt == E.MP_WATER:
        return ("~", "water")
    if tt == E.MP_TREES:
        return ("♣", f"trees_{low & 3}")
    if tt == E.MP_HOUSE:
        return _HOUSE_GLYPH.get(low & 3, ("⌂", "house_sm"))
    if tt == E.MP_ROAD:
        return (_ROAD_GLYPH.get(low, "•"), "road")
    if tt == E.MP_RAILWAY:
        return (_RAIL_GLYPH.get(low, "•"), "rail")
    if tt == E.MP_STATION:
        return _STATION_GLYPH.get(low, ("▣", "station_rail"))
    if tt == E.MP_INDUSTRY:
        return _industry_glyph(low, game)
    return ("?", "misc")


def vehicle_glyph(kind: str) -> tuple[str, str]:
    """Render glyph for a vehicle on top of its current tile."""
    return {
        "TRAIN": ("●", "vehicle_train"),
        "BUS":   ("◉", "vehicle_road"),
        "TRUCK": ("◉", "vehicle_road"),
        "SHIP":  ("⛵", "vehicle_ship"),
        "PLANE": ("✦", "vehicle_plane"),
    }.get(kind, ("?", "misc"))
