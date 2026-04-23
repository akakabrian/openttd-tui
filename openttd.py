"""Entry point — `python openttd.py [--agent] [--headless]`."""

from __future__ import annotations

import argparse

from openttd_tui.app import run


def main() -> None:
    p = argparse.ArgumentParser(prog="openttd-tui")
    p.add_argument("--seed", type=int, default=1234,
                   help="world generation seed (default 1234)")
    p.add_argument("--agent", action="store_true",
                   help="start the agent HTTP API alongside the TUI")
    p.add_argument("--agent-port", type=int, default=8789,
                   help="port for the agent API (default: 8789)")
    p.add_argument("--headless", action="store_true",
                   help="no TUI, run sim + agent API only")
    p.add_argument("--no-sound", action="store_true",
                   help="disable sound effects")
    args = p.parse_args()

    agent_port = args.agent_port if (args.agent or args.headless) else None
    run(seed=args.seed, agent_port=agent_port, headless=args.headless,
        sound=not args.no_sound)


if __name__ == "__main__":
    main()
