"""Modal screens for help, finance detail, vehicle list."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from . import engine as E


class HelpScreen(ModalScreen):
    BINDINGS = [Binding("escape,q,question_mark", "app.pop_screen", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("HELP — keys", classes="title")
            yield Static(Text.from_markup(
                "[bold]Movement[/]  arrows — move cursor\n"
                "[bold]Apply[/]     enter / space — apply selected tool\n"
                "[bold]Tools[/]     1 road  2 rail  3 demolish\n"
                "               4 rail station  5 bus stop  6 truck stop\n"
                "               7 dock  8 airport  9 train  0 bus/truck\n"
                "[bold]Info[/]      f finance  v vehicles  t towns\n"
                "[bold]System[/]    p pause  ? help  q quit\n"
                "[bold]Mouse[/]     left-click = apply, drag = line-build\n\n"
                "Build a rail line, place two rail stations next to"
                " industries or towns, then hit [bold]9[/] at a station to"
                " spawn a train. It will auto-route to the nearest second"
                " rail station."
            ), id="help-body")


class FinanceScreen(ModalScreen):
    BINDINGS = [Binding("escape,q,f", "app.pop_screen", "Close")]

    def __init__(self, game: E.Game) -> None:
        super().__init__()
        self.game = game

    def compose(self) -> ComposeResult:
        g = self.game
        rows = []
        rows.append(f"[bold]FINANCE — {g.year}[/]")
        rows.append("")
        rows.append(f"Balance              £{g.funds:>12,}")
        rows.append(f"Loan                 £{g.loan:>12,}  (limit £{g.loan_limit:,})")
        rows.append(f"Income YTD           £{g.income_year:>12,}")
        rows.append(f"Expenses YTD         £{g.expense_year:>12,}")
        rows.append(f"Profit last year     £{g.profit_last_year:>12,}")
        rows.append(f"Company value        £{g.company_value:>12,}")
        rows.append("")
        rows.append("[bold]Vehicle fleet profit (this year)[/]")
        for v in g.vehicles:
            rows.append(f"  #{v.vid:<3} {v.kind:<5} £{v.profit_year:>10,}  "
                        f"cargo: {v.cargo} ×{v.cargo_amount}")
        with Vertical():
            yield Static("FINANCE", classes="title")
            yield Static(Text.from_markup("\n".join(rows)))


class VehicleScreen(ModalScreen):
    BINDINGS = [Binding("escape,q,v", "app.pop_screen", "Close")]

    def __init__(self, game: E.Game) -> None:
        super().__init__()
        self.game = game

    def compose(self) -> ComposeResult:
        g = self.game
        rows = [f"[bold]FLEET ({len(g.vehicles)} vehicles)[/]", ""]
        if not g.vehicles:
            rows.append("[dim](no vehicles yet — build stations and press 9/0)[/]")
        for v in g.vehicles:
            vt = E.VEHICLE_TYPES[v.kind]
            status = "loaded" if v.cargo_amount > 0 else "empty"
            rows.append(
                f"#{v.vid:<3} {vt.name:<13} ({v.x:5.1f},{v.y:5.1f})  "
                f"[bold]{v.cargo}[/]×{v.cargo_amount:<3} {status}  "
                f"£{v.profit_year:,}/yr"
            )
        with Vertical():
            yield Static("VEHICLES", classes="title")
            with VerticalScroll():
                yield Static(Text.from_markup("\n".join(rows)))


class TownsScreen(ModalScreen):
    BINDINGS = [Binding("escape,q,t", "app.pop_screen", "Close")]

    def __init__(self, game: E.Game) -> None:
        super().__init__()
        self.game = game

    def compose(self) -> ComposeResult:
        g = self.game
        rows = [f"[bold]TOWNS ({len(g.towns)})[/]", ""]
        for t in g.towns:
            rows.append(f"[bold]{t.name:<12}[/] ({t.x:>3},{t.y:>3})  "
                        f"pop [yellow]{t.population:>5,}[/]")
        rows.append("")
        rows.append(f"[bold]INDUSTRIES ({len(g.industries)})[/]")
        for i in g.industries:
            itype = E.INDUSTRY_BY_CODE[i.kind]
            stock = ", ".join(f"{c}:{v}" for c, v in i.stockpile.items()) or "(empty)"
            rows.append(f"[bold]{itype.name:<14}[/] ({i.x:>3},{i.y:>3})  {stock}")
        with Vertical():
            yield Static("TOWNS & INDUSTRIES", classes="title")
            with VerticalScroll():
                yield Static(Text.from_markup("\n".join(rows)))
