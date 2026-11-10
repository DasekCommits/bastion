from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from bastion.catalog import Catalog
from bastion.company import Company
from bastion.engine import Campaign, NightResult, Report, StepResult
from bastion.report import format_report

BLUE = "#5aa9ff"
RED = "#ff5f5f"
AMBER = "#f5b942"
GREEN = "#5fd38d"
MUTED = "#8a8a8a"
FAINT = "#5c5c5c"

LOGO = """\
██████╗  █████╗ ███████╗████████╗██╗ ██████╗ ███╗   ██╗
██╔══██╗██╔══██╗██╔════╝╚══██╔══╝██║██╔═══██╗████╗  ██║
██████╔╝███████║███████╗   ██║   ██║██║   ██║██╔██╗ ██║
██╔══██╗██╔══██║╚════██║   ██║   ██║██║   ██║██║╚██╗██║
██████╔╝██║  ██║███████║   ██║   ██║╚██████╔╝██║ ╚████║
╚═════╝ ╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝"""


def percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def questionary_style():
    from questionary import Style

    return Style([
        ("qmark", f"fg:{AMBER} bold"),
        ("question", "bold"),
        ("answer", f"fg:{AMBER} bold"),
        ("pointer", f"fg:{AMBER} bold"),
        ("highlighted", f"fg:{AMBER} bold"),
        ("selected", f"fg:{GREEN}"),
        ("instruction", f"fg:{MUTED} italic"),
        ("disabled", f"fg:{FAINT} italic"),
        ("separator", f"fg:{FAINT}"),
    ])


def title_screen(difficulty: str | None = None) -> Panel:
    parts = [
        Text(LOGO, style=f"bold {AMBER}"),
        Text(),
        Text.assemble(("Build a defense. ", BLUE), ("Switch sides. ", RED), ("Break it.", "bold")),
    ]
    if difficulty:
        parts.append(Text(f"\n{difficulty.upper()} MODE", style=MUTED))
    return Panel(Group(*parts), box=box.HEAVY, border_style=FAINT, padding=(1, 3), expand=False)


def team_rule(team: str, subtitle: str) -> Rule:
    color = BLUE if team == "blue" else RED
    return Rule(f"[bold {color}]{team.upper()} TEAM[/]  [{MUTED}]{subtitle}[/]", style=color)


def company_panel(company: Company, easy: bool) -> Panel:
    servers = Table(box=box.SIMPLE_HEAD, header_style=f"bold {BLUE}", pad_edge=False)
    servers.add_column("Server")
    servers.add_column("Internet")
    servers.add_column("Software", style=MUTED)
    for server in company.servers:
        online = Text("exposed", style=AMBER) if server.internet_facing else Text("inside", style=MUTED)
        servers.add_row(f"{server.name} [{MUTED}]{server.id}[/]", online, ", ".join(server.software))

    people = Table(box=box.SIMPLE_HEAD, header_style=f"bold {BLUE}", pad_edge=False)
    people.add_column("Person")
    people.add_column("Admin")
    people.add_column("Can log in to", style=MUTED)
    for employee in company.employees:
        admin = Text("yes", style=AMBER) if employee.is_admin else Text("no", style=MUTED)
        people.add_row(f"{employee.name} [{MUTED}]{employee.role}[/]", admin, ", ".join(employee.access))

    parts = [Text(company.description), Text(), servers, people]
    if easy:
        data = Table(box=box.SIMPLE_HEAD, header_style=f"bold {BLUE}", pad_edge=False)
        data.add_column("Valuable data")
        data.add_column("Where", style=MUTED)
        data.add_column("Value", justify="right")
        for asset in company.data:
            data.add_row(asset.name, asset.location, str(asset.value))
        parts.append(data)
    return Panel(
        Group(*parts),
        title=f"[bold]{company.name}[/] [{MUTED}]{company.tier} company[/]",
        title_align="left",
        border_style=BLUE,
        padding=(1, 2),
    )


def budget_line(label: str, budget: int, color: str) -> Text:
    return Text.assemble((f"{label} budget ", MUTED), (str(budget), f"bold {color}"))


def _dots(filled: int, total: int, color: str) -> Text:
    return Text.assemble(("●" * filled, color), ("○" * (total - filled), FAINT))


def heat_bar(heat: float, width: int = 12) -> Text:
    filled = round(heat * width)
    color = GREEN if heat < 0.34 else AMBER if heat < 0.67 else RED
    return Text.assemble(("█" * filled, color), ("░" * (width - filled), FAINT), (f" {percent(heat)}", color))


def status_bar(campaign: Campaign, easy: bool) -> Rule:
    company = campaign.company
    line = Text.assemble(
        ("DAY ", MUTED), (f"{campaign.day}/{company.max_days} ", "bold"),
        _dots(campaign.day, company.max_days, AMBER),
        ("   MOVES ", MUTED),
        _dots(campaign.moves_left_today, company.moves_per_day, GREEN),
    )
    if easy:
        line.append("   HEAT ", style=MUTED)
        line.append_text(heat_bar(campaign.heat))
    return Rule(line, style=FAINT)


def foothold_panel(campaign: Campaign) -> Text:
    foothold = campaign.foothold
    rows = [
        ("Accounts", foothold.employees),
        ("On machines", foothold.servers),
        ("Admin on", foothold.admin_on),
        ("Scanned", foothold.scanned),
    ]
    text = Text()
    for label, items in rows:
        if items:
            text.append(f"  {label}: ", style=MUTED)
            text.append(", ".join(sorted(items)), style=RED)
            text.append("\n")
    if not text.plain:
        text.append("  No foothold yet. Find a way in first.\n", style=MUTED)
    return text


def result_text(result: StepResult, target_name: str, easy: bool) -> Text:
    text = Text.assemble(("  ", ""), (result.attack.name, "bold"), (" → ", MUTED), (target_name, ""), "\n")
    if not result.possible:
        text.append("  WASTED ", style=f"bold black on {AMBER}")
        text.append(f" {result.note}\n", style=AMBER)
        return text
    if result.succeeded:
        text.append(" SUCCESS ", style=f"bold black on {GREEN}")
    else:
        text.append(" FAILED ", style=f"bold white on {FAINT}")
    if easy:
        text.append(f"  chance was {percent(result.success_chance)}", style=MUTED)
    text.append("\n")
    if result.succeeded and result.note:
        text.append(f"  {result.note}\n")
    if easy and not result.succeeded and result.helped:
        text.append(f"  Stopped by: {', '.join(result.helped)}\n", style=BLUE)
    if result.detected:
        text.append(" DETECTED ", style=f"bold white on {RED}")
        text.append("  The Blue Team spotted you and kicked you out.\n", style=RED)
    return text


def night_panel(night: NightResult, easy: bool) -> Panel:
    lines = Text()
    if easy:
        lines.append("Heat cools down  ", style=MUTED)
        lines.append_text(heat_bar(night.heat_before, 8))
        lines.append("  →  ", style=MUTED)
        lines.append_text(heat_bar(night.heat_after, 8))
        lines.append(f"\nChance the Blue Team finds you in the logs: {percent(night.hunt_chance)}\n", style=MUTED)
    if night.found:
        lines.append(" FOUND ", style=f"bold white on {RED}")
        lines.append("  The Blue Team found you in the logs and kicked you out.", style=RED)
    else:
        lines.append("The night passes quietly.", style=MUTED)
    return Panel(lines, title=f"[{MUTED}]☾ Night {night.day}[/]", title_align="left", border_style=FAINT, padding=(0, 2))


def _score_color(score: int) -> str:
    return GREEN if score >= 70 else AMBER if score >= 40 else RED


def final_screen(report: Report, catalog: Catalog) -> Group:
    score = report.defense_score
    board = Table.grid(expand=True, padding=(0, 4))
    board.add_column(justify="center")
    board.add_column(justify="center")
    board.add_column(justify="center")
    board.add_row(
        Text("DEFENSE SCORE", style=MUTED),
        Text("DAMAGE", style=MUTED),
        Text("ATTACKER", style=MUTED),
    )
    board.add_row(
        Text(f"{score}/100", style=f"bold {_score_color(score)}"),
        Text(f"{report.points}/{report.max_points}", style=f"bold {RED if report.points else GREEN}"),
        Text("caught" if report.caught else "got away", style=f"bold {BLUE if report.caught else RED}"),
    )

    body = Text(format_report(report, catalog))
    body.highlight_regex(r"--- DAY \d+ ---", f"bold {AMBER}")
    body.highlight_regex(r"\bSUCCESS\b", f"bold {GREEN}")
    body.highlight_regex(r"\b(BLOCKED|SKIPPED)\b", f"bold {MUTED}")
    body.highlight_regex(r"\b(DETECTED|FOUND)\b", f"bold {RED}")
    body.highlight_regex(r"Helped:.*", BLUE)
    body.highlight_regex(r"Gap:.*", AMBER)
    body.highlight_regex(r"\[T\d{4}(\.\d{3})?[^\]]*\]", MUTED)

    return Group(
        Panel(board, title="[bold]RESULT[/]", border_style=_score_color(score), padding=(1, 2)),
        Panel(body, title="[bold]POST-MORTEM[/]", title_align="left", border_style=FAINT, padding=(1, 2)),
    )
