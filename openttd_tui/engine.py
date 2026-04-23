"""Pure-Python OpenTTD-inspired simulation.

See DECISIONS.md for why we don't wrap the real engine. This module
exposes a `Game` class that owns the tile grid, towns, industries, and
vehicles; it's tick-driven and deterministic from a seed.

Tile word layout (16 bits):
    bits 0..3   — low nibble: connection mask for rail/road tiles, or
                  density level for houses, or industry-type index for
                  industry tiles
    bits 4..7   — high nibble: reserved (vehicle-presence flag, signal
                  state in future)
    bits 8..13  — tile type (MP_*)

Tile type constants mirror OpenTTD's `src/tile_type.h`:
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable, Optional

# ---- Map dimensions ---------------------------------------------------

# Small map, per DECISIONS.md. Stored column-major (x * MAP_H + y) to
# match the simcity-tui buffer layout so the renderer code is familiar.
MAP_W = 64
MAP_H = 48

# ---- Tile types (mirrors OpenTTD src/tile_type.h) ---------------------

MP_CLEAR     = 0   # grass / dirt / fields
MP_RAILWAY   = 1
MP_ROAD      = 2
MP_HOUSE     = 3   # a town building
MP_TREES     = 4
MP_STATION   = 5   # rail / road / air / dock stop
MP_WATER     = 6
MP_INDUSTRY  = 7

TYPE_SHIFT = 8
TYPE_MASK = 0x3F << TYPE_SHIFT
LOW_MASK = 0x0F

def _make(tile_type: int, low: int = 0) -> int:
    return (tile_type << TYPE_SHIFT) | (low & LOW_MASK)

def tile_type(word: int) -> int:
    return (word >> TYPE_SHIFT) & 0x3F

def tile_low(word: int) -> int:
    return word & LOW_MASK


# ---- Clear subtypes ---------------------------------------------------

CLEAR_GRASS  = 0
CLEAR_DIRT   = 1
CLEAR_FIELDS = 2
CLEAR_ROCKS  = 3
CLEAR_SNOW   = 4


# ---- Rail / road connection mask (4-bit: N E S W) ---------------------
# 1 = has connection in that direction. Only the 16 combinations exist.
N, E, S, W = 1, 2, 4, 8


# ---- Cargo (subset of src/cargotype.h) --------------------------------

@dataclass(frozen=True)
class CargoType:
    code: str
    name: str
    glyph: str
    color: str  # rich style fragment

CARGOES: list[CargoType] = [
    CargoType("PASS", "Passengers", "P", "rgb(200,200,255)"),
    CargoType("MAIL", "Mail",       "M", "rgb(200,160,255)"),
    CargoType("COAL", "Coal",       "C", "rgb(120,120,120)"),
    CargoType("OIL",  "Oil",        "O", "rgb(180,130,30)"),
    CargoType("LIVE", "Livestock",  "L", "rgb(220,200,150)"),
    CargoType("GOOD", "Goods",      "G", "rgb(180,220,120)"),
    CargoType("GRAN", "Grain",      "R", "rgb(230,210,120)"),
    CargoType("WOOD", "Wood",       "W", "rgb(150,100,50)"),
    CargoType("IRON", "Iron Ore",   "I", "rgb(160,80,60)"),
    CargoType("STEL", "Steel",      "S", "rgb(200,200,220)"),
    CargoType("VALU", "Valuables",  "V", "rgb(255,220,80)"),
    CargoType("FOOD", "Food",       "F", "rgb(240,170,80)"),
]
CARGO_BY_CODE: dict[str, CargoType] = {c.code: c for c in CARGOES}


# ---- Industry types (subset of src/industry.h) ------------------------

@dataclass(frozen=True)
class IndustryType:
    code: str
    name: str
    glyph: str
    color: str
    bg: str
    footprint: tuple[int, int]  # w × h in tiles
    produces: tuple[str, ...]
    accepts: tuple[str, ...]

INDUSTRY_TYPES: list[IndustryType] = [
    IndustryType("CMINE", "Coal Mine",       "♛", "bold rgb(230,230,230)", "rgb(30,30,32)", (2, 2), ("COAL",), ()),
    IndustryType("POWRP", "Power Plant",     "☢", "bold rgb(255,240,120)", "rgb(50,45,10)", (2, 2), (), ("COAL",)),
    IndustryType("FARM",  "Farm",            "♪", "bold rgb(230,210,90)",  "rgb(40,36,10)", (2, 2), ("GRAN", "LIVE"), ()),
    IndustryType("FACT",  "Factory",         "▤", "bold rgb(230,180,80)",  "rgb(40,28,10)", (2, 2), ("GOOD",), ("GRAN", "LIVE", "STEL")),
    IndustryType("OILR",  "Oil Rig",         "⛲", "bold rgb(180,160,240)", "rgb(20,20,50)", (1, 1), ("OIL",), ()),
    IndustryType("OILF",  "Oil Refinery",    "⚗", "bold rgb(230,150,70)",  "rgb(45,25,10)", (2, 2), ("GOOD",), ("OIL",)),
    IndustryType("FORST", "Forest",          "▦", "bold rgb(60,160,70)",   "rgb(10,30,15)", (2, 2), ("WOOD",), ()),
    IndustryType("SAWM",  "Sawmill",         "▥", "bold rgb(200,150,80)",  "rgb(35,25,12)", (2, 2), ("GOOD",), ("WOOD",)),
    IndustryType("IMINE", "Iron Ore Mine",   "■", "bold rgb(200,120,90)",  "rgb(35,18,15)", (2, 2), ("IRON",), ()),
    IndustryType("STEEL", "Steel Mill",      "▩", "bold rgb(220,220,240)", "rgb(30,30,40)", (2, 2), ("STEL",), ("IRON",)),
    IndustryType("BANK",  "Bank",            "€", "bold rgb(255,220,80)",  "rgb(50,40,10)", (1, 1), ("VALU",), ("VALU",)),
    IndustryType("FOODP", "Food Plant",      "⚒", "bold rgb(240,180,100)", "rgb(45,28,12)", (2, 2), ("FOOD",), ("GRAN", "LIVE")),
]
INDUSTRY_BY_CODE: dict[str, IndustryType] = {t.code: t for t in INDUSTRY_TYPES}


# ---- Vehicle types ----------------------------------------------------

@dataclass(frozen=True)
class VehicleType:
    code: str
    name: str
    cost: int
    capacity: int
    speed: float  # tiles per tick

VEHICLE_TYPES: dict[str, VehicleType] = {
    "TRAIN": VehicleType("TRAIN", "Steam Engine",  8000, 40, 0.5),
    "BUS":   VehicleType("BUS",   "Bus",           1500, 30, 0.4),
    "TRUCK": VehicleType("TRUCK", "Lorry",         2500, 20, 0.4),
    "SHIP":  VehicleType("SHIP",  "Cargo Ship",    9000, 80, 0.2),
    "PLANE": VehicleType("PLANE", "Small Plane",  30000, 20, 1.0),
}


@dataclass
class Industry:
    kind: str          # INDUSTRY_TYPES code
    x: int             # top-left tile
    y: int
    stockpile: dict[str, int] = field(default_factory=dict)
    produced_this_month: dict[str, int] = field(default_factory=dict)


@dataclass
class Town:
    name: str
    x: int             # centre tile
    y: int
    population: int = 100
    # Houses are individual HOUSE tiles scattered near (x,y).
    # Population tracked here; actual tiles live in the grid.


@dataclass
class Station:
    name: str
    x: int
    y: int
    kind: str          # "rail" | "bus" | "truck" | "dock" | "airport"
    owner_town: Optional[str] = None  # nearest town name at build time
    cargo_waiting: dict[str, int] = field(default_factory=dict)


@dataclass
class Vehicle:
    vid: int
    kind: str          # VEHICLE_TYPES key
    x: float           # tile coords, fractional while moving
    y: float
    orders: list[tuple[int, int]]  # station coords, visited round-robin
    order_idx: int = 0
    cargo: str = "PASS"
    cargo_amount: int = 0
    age_months: int = 0
    profit_year: int = 0
    profit_last_year: int = 0
    # (x, y) of the station where the current cargo was loaded — used to
    # compute payment by Manhattan distance at drop-off.
    pickup_xy: Optional[tuple[int, int]] = None


# ---- Game -------------------------------------------------------------

class Game:
    """Top-level sim. Call `tick()` at 10 Hz.

    Public surface used by the TUI + agent API:
        tile_at(x, y) -> tile word
        set_tile(x, y, word) -> None (internal, but exposed for tools)
        tick() -> None
        build_road(x, y) / demolish(x, y) / build_rail(x, y, mask)
        build_station(x, y, kind) / place_vehicle(...)
        snapshot() -> dict
        serial — increments whenever a tile changes (for renderer skip)
    """

    def __init__(self, seed: int = 1234) -> None:
        self.seed = seed
        self._rng = random.Random(seed)
        # Column-major grid (same as simcity-tui): index = x*MAP_H + y.
        self._grid: list[int] = [_make(MP_CLEAR, CLEAR_GRASS)] * (MAP_W * MAP_H)
        # Serial so renderer can skip redraw when nothing changed.
        self.serial: int = 0

        # In-game clock. One game day = 30 ticks, one month = 30 days.
        self.tick_count: int = 0
        self.day: int = 1         # 1..30
        self.month: int = 0       # 0..11
        self.year: int = 1950

        # Finance.
        self.funds: int = 100_000
        self.loan: int = 100_000      # starting loan
        self.loan_limit: int = 500_000
        self.income_year: int = 0
        self.expense_year: int = 0
        self.profit_last_year: int = 0
        self.company_value: int = 100_000

        # Entities.
        self.towns: list[Town] = []
        self.industries: list[Industry] = []
        self.stations: list[Station] = []
        self.vehicles: list[Vehicle] = []
        self._next_vid: int = 1
        self._next_station_id: int = 1

        # Message log entries (consumed + cleared by the app each tick).
        self._events: list[tuple[str, str]] = []  # (level, text)

        self._generate_world()

    # ---- world generation --------------------------------------------

    def _generate_world(self) -> None:
        rng = self._rng
        # Seed terrain: grass + trees + some water + dirt + rocks.
        for x in range(MAP_W):
            for y in range(MAP_H):
                r = rng.random()
                if r < 0.08:
                    self._grid[x * MAP_H + y] = _make(MP_TREES, rng.randint(0, 3))
                elif r < 0.10:
                    self._grid[x * MAP_H + y] = _make(MP_CLEAR, CLEAR_DIRT)
                elif r < 0.105:
                    self._grid[x * MAP_H + y] = _make(MP_CLEAR, CLEAR_ROCKS)
                else:
                    self._grid[x * MAP_H + y] = _make(MP_CLEAR, CLEAR_GRASS)
        # Carve a river across the middle.
        river_y = MAP_H // 2 + rng.randint(-3, 3)
        for x in range(MAP_W):
            dy = rng.randint(-1, 1)
            for oy in (-1, 0, 1):
                ty = river_y + dy + oy
                if 0 <= ty < MAP_H:
                    self._grid[x * MAP_H + ty] = _make(MP_WATER, 0)
        # A lake in the NE.
        lx, ly = MAP_W * 3 // 4, MAP_H // 5
        for x in range(lx - 3, lx + 4):
            for y in range(ly - 2, ly + 3):
                if 0 <= x < MAP_W and 0 <= y < MAP_H:
                    if (x - lx) ** 2 + 2 * (y - ly) ** 2 < 10:
                        self._grid[x * MAP_H + y] = _make(MP_WATER, 0)

        # Place 4 towns on land, well-spaced.
        town_names = ["Fenwick", "Millhaven", "Oakridge", "Brightwell",
                      "Hollowford", "Ashbury"]
        rng.shuffle(town_names)
        placed_towns: list[tuple[int, int]] = []
        attempts = 0
        while len(placed_towns) < 4 and attempts < 500:
            attempts += 1
            tx = rng.randint(6, MAP_W - 7)
            ty = rng.randint(3, MAP_H - 4)
            if tile_type(self._grid[tx * MAP_H + ty]) != MP_CLEAR:
                continue
            if any(abs(tx - px) + abs(ty - py) < 14 for px, py in placed_towns):
                continue
            placed_towns.append((tx, ty))
            name = town_names[len(placed_towns) - 1]
            self.towns.append(Town(name=name, x=tx, y=ty,
                                   population=rng.randint(200, 900)))
            # Sprinkle houses around town centre.
            for _ in range(28):
                hx = tx + rng.randint(-4, 4)
                hy = ty + rng.randint(-2, 2)
                if not (0 <= hx < MAP_W and 0 <= hy < MAP_H):
                    continue
                if tile_type(self._grid[hx * MAP_H + hy]) == MP_CLEAR:
                    dens = rng.randint(0, 3)  # 0..3 house size
                    self._grid[hx * MAP_H + hy] = _make(MP_HOUSE, dens)

        # Place 6-8 industries.
        industry_pool = ["CMINE", "POWRP", "FARM", "FACT", "FORST",
                         "SAWM", "OILR", "OILF", "IMINE", "STEEL", "BANK"]
        rng.shuffle(industry_pool)
        placed_inds = 0
        for code in industry_pool:
            if placed_inds >= 8:
                break
            itype = INDUSTRY_BY_CODE[code]
            w, h = itype.footprint
            for _ in range(40):
                ix = rng.randint(1, MAP_W - w - 1)
                iy = rng.randint(1, MAP_H - h - 1)
                ok = True
                for dx in range(w):
                    for dy in range(h):
                        t = tile_type(self._grid[(ix + dx) * MAP_H + (iy + dy)])
                        if t != MP_CLEAR:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    continue
                ind = Industry(kind=code, x=ix, y=iy)
                self.industries.append(ind)
                ind_idx = len(self.industries) - 1
                for dx in range(w):
                    for dy in range(h):
                        self._grid[(ix + dx) * MAP_H + (iy + dy)] = _make(
                            MP_INDUSTRY, ind_idx & LOW_MASK
                        )
                placed_inds += 1
                break
        self.serial += 1
        self._event("info", f"{self.year} — {len(self.towns)} towns, "
                            f"{len(self.industries)} industries.")

    # ---- accessors ---------------------------------------------------

    def tile_at(self, x: int, y: int) -> int:
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return _make(MP_CLEAR, CLEAR_GRASS)
        return self._grid[x * MAP_H + y]

    def _event(self, level: str, text: str) -> None:
        self._events.append((level, text))

    def drain_events(self) -> list[tuple[str, str]]:
        e = self._events
        self._events = []
        return e

    # ---- building tools ---------------------------------------------
    # Returns (ok: bool, reason: str). Deducts cost on success.

    def _can_clear(self, x: int, y: int) -> bool:
        t = tile_type(self.tile_at(x, y))
        return t in (MP_CLEAR, MP_TREES)

    def demolish(self, x: int, y: int) -> tuple[bool, str]:
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return False, "out of bounds"
        t = tile_type(self.tile_at(x, y))
        if t == MP_WATER:
            return False, "can't demolish water"
        if t == MP_INDUSTRY:
            return False, "can't demolish industry"
        if t == MP_CLEAR and tile_low(self.tile_at(x, y)) == CLEAR_GRASS:
            return False, "nothing to demolish"
        cost = 50
        if self.funds < cost:
            return False, "not enough funds"
        # If it was a HOUSE, drop population from the nearest town.
        if t == MP_HOUSE:
            nearest = self._nearest_town(x, y)
            if nearest is not None:
                nearest.population = max(50, nearest.population - 20)
        # If it was a STATION, remove the Station record + prune any
        # vehicle orders pointing at it so orphaned trains/buses don't
        # loop forever trying to reach a tile that's no longer a stop.
        if t == MP_STATION:
            self.stations = [s for s in self.stations
                             if not (s.x == x and s.y == y)]
            survivors: list[Vehicle] = []
            for v in self.vehicles:
                v.orders = [o for o in v.orders if o != (x, y)]
                if len(v.orders) < 2:
                    # Fleet car has no useful round-trip left → retire it.
                    self._event("warn",
                                f"{VEHICLE_TYPES[v.kind].name} #{v.vid} "
                                "retired (lost a stop)")
                else:
                    v.order_idx %= len(v.orders)
                    survivors.append(v)
            self.vehicles = survivors
        self._grid[x * MAP_H + y] = _make(MP_CLEAR, CLEAR_DIRT)
        self.funds -= cost
        self.expense_year += cost
        self.serial += 1
        return True, "demolished"

    def build_road(self, x: int, y: int) -> tuple[bool, str]:
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return False, "out of bounds"
        t = tile_type(self.tile_at(x, y))
        if t == MP_ROAD:
            # Re-ping — recompute connection mask to neighbours.
            self._retopo_road(x, y)
            return True, "road (updated)"
        if not self._can_clear(x, y):
            return False, "can't build road here"
        cost = 200
        if self.funds < cost:
            return False, "not enough funds"
        self._grid[x * MAP_H + y] = _make(MP_ROAD, 0)
        self._retopo_road(x, y)
        for (nx, ny) in self._neighbours(x, y):
            if tile_type(self.tile_at(nx, ny)) == MP_ROAD:
                self._retopo_road(nx, ny)
        self.funds -= cost
        self.expense_year += cost
        self.serial += 1
        return True, "road built"

    def build_rail(self, x: int, y: int) -> tuple[bool, str]:
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return False, "out of bounds"
        t = tile_type(self.tile_at(x, y))
        if t == MP_RAILWAY:
            self._retopo_rail(x, y)
            return True, "rail (updated)"
        if not self._can_clear(x, y):
            return False, "can't build rail here"
        cost = 400
        if self.funds < cost:
            return False, "not enough funds"
        self._grid[x * MAP_H + y] = _make(MP_RAILWAY, 0)
        self._retopo_rail(x, y)
        for (nx, ny) in self._neighbours(x, y):
            if tile_type(self.tile_at(nx, ny)) == MP_RAILWAY:
                self._retopo_rail(nx, ny)
        self.funds -= cost
        self.expense_year += cost
        self.serial += 1
        return True, "rail built"

    def build_station(self, x: int, y: int, kind: str = "rail") -> tuple[bool, str]:
        """Place a station over the appropriate substrate. Rail station
        requires existing rail; bus/truck requires road; dock requires
        adjacent water; airport requires a 1×1 clear patch."""
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return False, "out of bounds"
        cur = tile_type(self.tile_at(x, y))
        cost_map = {"rail": 800, "bus": 400, "truck": 400,
                    "dock": 1200, "airport": 5000}
        cost = cost_map.get(kind, 800)
        if self.funds < cost:
            return False, "not enough funds"
        low_by_kind = {"rail": 0, "bus": 1, "truck": 2, "dock": 3, "airport": 4}
        if kind == "rail":
            if cur != MP_RAILWAY:
                return False, "rail station needs rail"
        elif kind in ("bus", "truck"):
            if cur != MP_ROAD:
                return False, f"{kind} station needs road"
        elif kind == "dock":
            if not self._can_clear(x, y):
                return False, "dock needs clear land next to water"
            if not any(tile_type(self.tile_at(nx, ny)) == MP_WATER
                       for nx, ny in self._neighbours(x, y)):
                return False, "dock must be adjacent to water"
        elif kind == "airport":
            if not self._can_clear(x, y):
                return False, "airport needs clear land"
        else:
            return False, f"unknown station kind {kind}"

        nearest = self._nearest_town(x, y)
        town_name = nearest.name if nearest else "Independent"
        self._next_station_id += 1
        name = f"{town_name} {kind.title()} #{self._next_station_id}"
        self.stations.append(Station(
            name=name, x=x, y=y, kind=kind, owner_town=(nearest.name if nearest else None),
        ))
        self._grid[x * MAP_H + y] = _make(MP_STATION, low_by_kind[kind])
        self.funds -= cost
        self.expense_year += cost
        self.serial += 1
        self._event("success", f"Built {name}")
        return True, f"built {kind} station"

    def place_vehicle(self, kind: str, x: int, y: int,
                      cargo: str = "PASS") -> tuple[bool, str]:
        """Spawn a vehicle on an existing station tile of the right kind.

        Orders are auto-set to round-trip between the two nearest
        compatible stations. Useful as a one-click placement in the TUI
        since multi-station order entry is beyond MVP scope."""
        if kind not in VEHICLE_TYPES:
            return False, f"unknown vehicle {kind}"
        vt = VEHICLE_TYPES[kind]
        if self.funds < vt.cost:
            return False, "not enough funds"
        kind_to_station = {
            "TRAIN": "rail", "BUS": "bus", "TRUCK": "truck",
            "SHIP": "dock", "PLANE": "airport",
        }
        want = kind_to_station[kind]
        compat = [s for s in self.stations if s.kind == want]
        if len(compat) < 2:
            return False, f"need 2 {want} stations for {kind}"
        # Closest + second-closest to (x,y).
        compat.sort(key=lambda s: (s.x - x) ** 2 + (s.y - y) ** 2)
        a, b = compat[0], compat[1]
        v = Vehicle(
            vid=self._next_vid, kind=kind,
            x=float(a.x), y=float(a.y),
            orders=[(a.x, a.y), (b.x, b.y)],
            cargo=cargo,
        )
        self._next_vid += 1
        self.vehicles.append(v)
        self.funds -= vt.cost
        self.expense_year += vt.cost
        self.serial += 1
        self._event("success",
                    f"{vt.name} #{v.vid} running {a.name} ↔ {b.name}")
        return True, "vehicle placed"

    # ---- topology helpers -------------------------------------------

    def _neighbours(self, x: int, y: int) -> Iterable[tuple[int, int]]:
        if y > 0: yield (x, y - 1)           # N
        if x < MAP_W - 1: yield (x + 1, y)   # E
        if y < MAP_H - 1: yield (x, y + 1)   # S
        if x > 0: yield (x - 1, y)           # W

    def _retopo_road(self, x: int, y: int) -> None:
        mask = 0
        dirs = [(0, -1, N), (1, 0, E), (0, 1, S), (-1, 0, W)]
        for dx, dy, bit in dirs:
            nx, ny = x + dx, y + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H:
                t = tile_type(self.tile_at(nx, ny))
                if t == MP_ROAD or (t == MP_STATION and
                                    tile_low(self.tile_at(nx, ny)) in (1, 2)):
                    mask |= bit
        self._grid[x * MAP_H + y] = _make(MP_ROAD, mask)

    def _retopo_rail(self, x: int, y: int) -> None:
        mask = 0
        dirs = [(0, -1, N), (1, 0, E), (0, 1, S), (-1, 0, W)]
        for dx, dy, bit in dirs:
            nx, ny = x + dx, y + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H:
                t = tile_type(self.tile_at(nx, ny))
                if t == MP_RAILWAY or (t == MP_STATION and
                                       tile_low(self.tile_at(nx, ny)) == 0):
                    mask |= bit
        self._grid[x * MAP_H + y] = _make(MP_RAILWAY, mask)

    def _nearest_town(self, x: int, y: int) -> Optional[Town]:
        if not self.towns:
            return None
        return min(self.towns,
                   key=lambda t: (t.x - x) ** 2 + (t.y - y) ** 2)

    # ---- tick --------------------------------------------------------

    def tick(self) -> None:
        """Advance sim by one 0.1 s step."""
        self.tick_count += 1

        # Move vehicles — 3-tick cadence.
        if self.tick_count % 3 == 0:
            self._advance_vehicles()

        # One game day every 30 ticks.
        if self.tick_count % 30 == 0:
            self._advance_day()

    def _advance_day(self) -> None:
        self.day += 1
        if self.day > 30:
            self.day = 1
            self._advance_month()

    def _advance_month(self) -> None:
        self.month += 1
        if self.month > 11:
            self.month = 0
            self._advance_year()
        # Monthly: industries produce.
        for ind in self.industries:
            itype = INDUSTRY_BY_CODE[ind.kind]
            for c in itype.produces:
                amount = 20 + int(self._rng.random() * 40)
                ind.stockpile[c] = ind.stockpile.get(c, 0) + amount
                ind.produced_this_month[c] = amount
            # Spoil: stockpiles drop if not collected.
            for c, amt in list(ind.stockpile.items()):
                ind.stockpile[c] = max(0, int(amt * 0.9))
        # Monthly: towns grow if served by a station.
        for town in self.towns:
            served = any(abs(s.x - town.x) + abs(s.y - town.y) <= 6
                         for s in self.stations)
            if served:
                town.population = int(town.population * 1.02) + 5
            else:
                town.population = max(50, int(town.population * 0.997))
        # Loan interest (4%/yr ≈ 0.33%/mo).
        interest = int(self.loan * 0.0033)
        self.funds -= interest
        self.expense_year += interest
        self.serial += 1

    def _advance_year(self) -> None:
        self.year += 1
        self.profit_last_year = self.income_year - self.expense_year
        for v in self.vehicles:
            v.age_months += 12
            v.profit_last_year = v.profit_year
            v.profit_year = 0
        self.income_year = 0
        self.expense_year = 0
        self.company_value = self.funds + sum(
            VEHICLE_TYPES[v.kind].cost // 2 for v in self.vehicles
        )
        self._event("news", f"New year — {self.year}. "
                            f"Profit £{self.profit_last_year:,}.")

    def _advance_vehicles(self) -> None:
        if not self.vehicles:
            return
        for v in self.vehicles:
            vt = VEHICLE_TYPES[v.kind]
            if not v.orders:
                continue
            tx, ty = v.orders[v.order_idx]
            dx = tx - v.x
            dy = ty - v.y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < 0.25:
                # Arrived. Trade cargo, flip order.
                self._vehicle_stop(v, tx, ty)
                v.order_idx = (v.order_idx + 1) % len(v.orders)
            else:
                step = vt.speed
                v.x += dx / dist * step
                v.y += dy / dist * step
        # Vehicle serial separate from tile serial — MapView uses tile
        # serial for its skip-redraw shortcut, so don't bump for pure
        # vehicle motion or 99% of frames won't repaint.

    def _vehicle_stop(self, v: Vehicle, sx: int, sy: int) -> None:
        # Find station + adjacent industries.
        station = next((s for s in self.stations if s.x == sx and s.y == sy), None)
        if station is None:
            return
        vt = VEHICLE_TYPES[v.kind]
        # Offload cargo → station pays us. Payment = £40/unit flat +
        # £5/unit/tile Manhattan distance from pickup (per DECISIONS.md).
        if v.cargo_amount > 0:
            if v.pickup_xy is not None:
                dist = abs(v.pickup_xy[0] - sx) + abs(v.pickup_xy[1] - sy)
            else:
                dist = 0
            payment = v.cargo_amount * 40 + v.cargo_amount * dist * 5
            self.funds += payment
            self.income_year += payment
            v.profit_year += payment
            station.cargo_waiting[v.cargo] = (
                station.cargo_waiting.get(v.cargo, 0) + v.cargo_amount
            )
            v.cargo_amount = 0
            v.pickup_xy = None
        # Load cargo if any industry within 2 tiles produces it.
        for ind in self.industries:
            itype = INDUSTRY_BY_CODE[ind.kind]
            if abs(ind.x - sx) > 2 or abs(ind.y - sy) > 2:
                continue
            for c in itype.produces:
                if ind.stockpile.get(c, 0) > 0:
                    load = min(ind.stockpile[c], vt.capacity)
                    ind.stockpile[c] -= load
                    v.cargo = c
                    v.cargo_amount = load
                    v.pickup_xy = (sx, sy)
                    break
            if v.cargo_amount > 0:
                break
        # Otherwise pick up PASS from attached town.
        if v.cargo_amount == 0 and station.owner_town:
            town = next((t for t in self.towns if t.name == station.owner_town), None)
            if town:
                load = min(town.population // 10, vt.capacity)
                v.cargo = "PASS"
                v.cargo_amount = load
                v.pickup_xy = (sx, sy)

    # ---- snapshot for agent API -------------------------------------

    def snapshot(self) -> dict:
        return {
            "year": self.year, "month": self.month, "day": self.day,
            "funds": self.funds, "loan": self.loan,
            "profit_last_year": self.profit_last_year,
            "serial": self.serial,
            "towns": [
                {"name": t.name, "x": t.x, "y": t.y, "pop": t.population}
                for t in self.towns
            ],
            "industries": [
                {"kind": i.kind, "x": i.x, "y": i.y,
                 "stockpile": dict(i.stockpile)}
                for i in self.industries
            ],
            "stations": [
                {"name": s.name, "x": s.x, "y": s.y, "kind": s.kind}
                for s in self.stations
            ],
            "vehicles": [
                {"vid": v.vid, "kind": v.kind,
                 "x": round(v.x, 2), "y": round(v.y, 2),
                 "cargo": v.cargo, "cargo_amount": v.cargo_amount,
                 "profit_year": v.profit_year}
                for v in self.vehicles
            ],
        }


def new_game(seed: int = 1234) -> Game:
    return Game(seed=seed)
