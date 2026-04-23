# openttd-tui — design decisions

Mirrors the simcity-tui skeleton (`~/AI/projects/simcity-tui`) wherever it
makes sense. Divergences justified inline.

## Engine strategy — pure-Python sim, not FFI into OpenTTD

**Option A rejected: compile OpenTTD and drive via the admin port.**
OpenTTD ships a TCP admin protocol (default port 3977) with a simple
authenticated command set — RCON, CHAT, POLL, UPDATE subscriptions for
chat, console, vehicle events, etc. Pros: faithful engine, real vehicle
physics, real economy. Cons for a TUI-in-a-single-session build:

- OpenTTD is ~300k LOC of C++17, needs SDL2 + lzma + libpng + freetype +
  fontconfig + ICU + fluidsynth for a full build. A CMake build on taro
  takes 10–20 minutes fresh.
- The admin protocol is observation-heavy: it gets events and can call
  `rcon`, but it **cannot build tiles, lay track, or issue vehicle
  orders**. RCON is limited to the in-game console, which itself is
  mostly server-admin commands (pause, kick, save, reset_company). No
  construction primitives are exposed.
- Construction + vehicle orders live in the AI/GameScript Squirrel VM,
  which is in-process only. Driving it from outside requires either (a)
  shipping a NoAI GS script that reads commands from disk, or (b)
  patching an out-of-tree IPC bridge into the engine. Both are multi-
  session sub-projects.

**Option B rejected: vendor OpenTTD, drive via a custom Squirrel
bridge script.** Would work, but the script has to be loaded as an AI
or GameScript *before* a game starts, and the round-trip for each tile
build is still one disk poll per frame. The UX would be "terminal
overlay on a hidden OpenTTD window," not a self-contained TUI.

**Option C chosen: pure-Python sim inspired by OpenTTD.** Matches the
pattern used by `julius-tui` and `freeorion-tui` in this batch: take
the engine's data model (tile types, industries, vehicle classes,
cargo enum) and reimplement the simulation in Python. The vendored
OpenTTD source (fetched by `make bootstrap`, gitignored) is a
reference for constants and formulas, not linked into the process.

**Specifically borrowed from OpenTTD:**
- Tile type enum (`MP_CLEAR`, `MP_RAILWAY`, `MP_ROAD`, `MP_HOUSE`,
  `MP_TREES`, `MP_STATION`, `MP_WATER`, `MP_INDUSTRY`) — see
  `src/tile_type.h`.
- Core cargo enum (`PASSENGERS`, `COAL`, `MAIL`, `OIL`, `LIVESTOCK`,
  `GOODS`, `GRAIN`, `WOOD`, `IRON_ORE`, `STEEL`, `VALUABLES`,
  `FOOD`) — see `src/cargotype.h`.
- Industry types (coal mine, power plant, farm, factory, oil rig,
  oil refinery, forest, sawmill, steel mill, iron ore mine, bank)
  and their accept/produce chains — see `src/industry.h` +
  `src/table/industry_land.h`.
- Vehicle type enum (train, road, ship, aircraft) and engine age
  decay — see `src/vehicle_type.h`.
- Town growth model: houses upgrade tiers based on adjacency to
  stations + road network.
- £ currency + monthly/yearly finance — see `src/economy.cpp`.

**Future upgrade path:** the `openttd_tui/engine.py` shim wraps a
`Game` class. A later session can swap the implementation for an
admin-port client without changing the TUI layer — the public
methods (`tick`, `build_road`, `build_rail`, `build_station`,
`place_vehicle`, `serial`, `tile_at`, `snapshot`) are the contract.

## Map size: 64×48 (not OpenTTD's 256×256..4096×4096)

OpenTTD supports maps 64×64 up to 4096×4096. At 1 char/tile even 256×256
is tractable in a terminal, but pure-Python town growth + vehicle
pathing on a 64k-tile grid is too slow for the 10 Hz tick target.

We render **64×48** (3072 tiles). Small enough for instant sim
response, big enough for 4 towns + 6 industries + a useful rail
network. Matches the "Small" map preset in OpenTTD.

## Rendering conventions (from simcity-tui)

- `ScrollView` + per-row `render_line(y)`
- Pre-parsed `rich.style.Style` cached at init
- Run-length same-style segments
- 2-glyph pattern per terrain class keyed on `(x + y) & 1`
- 2 Hz animation frame counter for water ripples, train motion,
  station activity

## Tile glyphs (divergent from simcity-tui)

OpenTTD's visual grammar is transport-first, zone-second. So rails and
roads dominate the glyph set:

- Rails: `═ ║ ╔ ╗ ╚ ╝ ╬` etc. (same 16-entry connection table trick
  as simcity roads).
- Roads: `─ │ ┐ ┘ └ ┌ ┼` (tan/brown).
- Stations: `▣` (rail), `◊` (bus/truck), `⚓` (dock), `✈` (airport).
- Industries: `♛` coal mine, `▤` factory, `♪` farm, `▦` forest, `▥`
  sawmill, `☢` power plant, `■` steel mill, `⛲` oil rig, `▩` bank.
- Towns/houses: `⌂ ░ ▒ ▓` scaled by size.
- Vehicles: `●` train (on rail), `◉` road, `⛵` ship, `✦` plane.

## Finance / tick cadence

- 1 sim tick = 1 Textual tick = 0.1 s. 30 sim ticks = 1 in-game day.
  So ~3 s / game day, ~90 s / game month (10× OpenTTD's default
  speed — terminal play is more deliberate than a click-frenzy RTS).
- Vehicle positions advance every 3 ticks (sub-tile motion).
- Finance settles monthly; yearly report at month 0.

## Scope gates (per skill Stage 6)

- **Phase A (MVP):** terrain rendering, tile info, build/demolish
  toolbar, town + industry placement at world-gen, static vehicle
  placement.
- **Phase B:** finance panel, vehicle list, cargo accept/produce
  simulation, graphs (passengers, £, cargo).
- **Phase C:** agent REST API — same action schema shape as
  simcity-tui.
- **Phase D:** sound (synth only; OpenTTD's real SFX are in
  proprietary `.grf` files we don't vendor).
- **Phase E:** save/load JSON, scenario picker (2–3 built-in maps).
- **Phase F:** animated trains (train moves one cell per 0.5 s).
- **Phase G:** LLM advisor (skipped unless time permits; the skill
  calls this optional).

## What's stubbed / out of scope for this session

- Signalling (block vs path signals). Trains move regardless of
  collision.
- Multi-car trains. Each train is one cell.
- Cargo payment rates by distance × time (OpenTTD's famous curve).
  We use flat £/unit × distance.
- Aircraft physics (altitude, runway length).
- Ships have no water-routing — they teleport between docks.
- GameScript/AI companies. Single-company only.
- NewGRF modding.
- Multiplayer, pausing on network.

## Directory layout

```
openttd-tui/
├── openttd.py                 # entry
├── pyproject.toml
├── Makefile                   # bootstrap (fetch vendor), venv, run, test
├── DECISIONS.md
├── README.md
├── engine/                    # vendored OpenTTD, reference only (gitignored)
├── openttd_tui/
│   ├── engine.py              # Game class (pure-Python sim)
│   ├── tiles.py               # tile table + patterns + colour/bg dicts
│   ├── vehicles.py            # vehicle + cargo models
│   ├── towns.py               # town growth logic
│   ├── industries.py          # industry accept/produce chains
│   ├── app.py                 # TextualApp, MapView, panels
│   ├── screens.py             # modal screens
│   ├── agent_api.py           # aiohttp routes (Phase C)
│   ├── sounds.py              # synth SFX (Phase D)
│   └── tui.tcss
└── tests/
    ├── qa.py                  # Pilot scenarios
    └── perf.py
```
