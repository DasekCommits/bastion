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


def company_panel(company: Company, easy: bool, reveal_admins: bool = True) -> Panel:
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
    loyalty = company.tier != "small"
    if easy:
        people.add_column("Spots phishing")
        people.add_column("Passwords")
        if loyalty:
            people.add_column("Loyalty")
    for employee in company.employees:
        if reveal_admins or employee.needs_admin:
            admin = Text("yes", style=AMBER) if employee.is_admin else Text("no", style=MUTED)
        else:
            admin = Text("?", style=MUTED)
        row = [f"{employee.name} [{MUTED}]{employee.role}[/]", admin, ", ".join(employee.access)]
        if easy:
            row += [_trait(employee.awareness), _trait(employee.password_hygiene)]
            if loyalty:
                row.append(_trait(employee.loyalty))
        people.add_row(*row)

    parts = [Text(company.description), Text(), servers, people]
    if not reveal_admins:
        parts.append(Text("Someone may have admin rights by mistake, or nobody. You will find out once you are in.", style=f"italic {MUTED}"))
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


def _trait(value: float) -> Text:
    if value >= 0.6:
        return Text("good", style=GREEN)
    if value >= 0.3:
        return Text("okay", style=AMBER)
    return Text("poor", style=RED)


def budget_note(team: str, budget: int, span: list[int] | None, color: str) -> Text:
    text = Text.assemble((f"{team} budget this game: ", MUTED), (str(budget), f"bold {color}"))
    if span:
        text.append(f"  (can be {span[0]} to {span[1]})", style=MUTED)
    return text


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


def intel_line(campaign: Campaign) -> Text:
    names = sorted(campaign.catalog.defenses[d].name for d in campaign.known_defenses)
    return Text.assemble(("  Intel: ", MUTED), (", ".join(names), BLUE))


def move_header(result: StepResult, target_name: str) -> Text:
    return Text.assemble(("  ", ""), (result.attack.name, "bold"), (" → ", MUTED), (target_name, ""))


def outcome_text(result: StepResult, easy: bool, explain: bool = True) -> Text:
    text = Text()
    if not result.possible:
        text.append("  WASTED ", style=f"bold black on {AMBER}")
        text.append(f" {result.note}", style=AMBER)
        return text
    empty = result.succeeded and result.attack.tactic in ("exfiltration", "impact") and not result.points
    if empty:
        text.append("  NOTHING HERE ", style=f"bold black on {AMBER}")
    elif result.succeeded:
        text.append("  SUCCESS ", style=f"bold black on {GREEN}")
    else:
        text.append("  FAILED ", style=f"bold white on {FAINT}")
    if easy:
        text.append(f"  chance was {percent(result.success_chance)}", style=MUTED)
    if result.succeeded and result.note:
        text.append(f"\n  {result.note}")
    if explain and not result.succeeded:
        if result.blockers:
            text.append(f"\n  Stopped by: {', '.join(result.blockers)}", style=BLUE)
        else:
            text.append("\n  Nothing blocked it. It just did not work this time.", style=MUTED)
    return text


def detection_text(result: StepResult) -> Text:
    if result.detected and not result.kicked:
        return Text.assemble(
            ("  SPOTTED ", f"bold black on {AMBER}"),
            ("  The Blue Team blocked this attempt. You are still outside, but they are more alert.", AMBER),
        )
    if result.detected:
        return Text.assemble(
            ("  DETECTED ", f"bold white on {RED}"),
            ("  The Blue Team spotted you and kicked you out.", RED),
        )
    return Text("  Nobody noticed.", style=MUTED)


def suspense_lines(result: StepResult, target_name: str) -> list[str]:
    tactic = result.attack.tactic
    who = target_name.split(",")[0]
    if result.attack.id == "phishing":
        return [f"Sending a fake email to {who}", f"Waiting for {who} to click"]
    if tactic == "reconnaissance":
        return [f"Scanning {who} for open ports"]
    if tactic == "initial-access":
        return [f"Sending the exploit to {who}", "Waiting for a shell"]
    if tactic == "credential-access":
        return [f"Trying passwords against {who}'s account", "Waiting for a login to work"]
    if tactic == "privilege-escalation":
        return [f"Running a local exploit on {who}", "Trying to become administrator"]
    if tactic == "lateral-movement":
        return [f"Logging in to {who} with a stolen account"]
    if tactic == "exfiltration":
        return [f"Copying data out of {who}", "Sending it to your server"]
    if tactic == "impact":
        return [f"Encrypting files on {who}", "Dropping the ransom note"]
    return [f"Attacking {who}"]


WATCHING = "Is the Blue Team watching?"
NIGHT_WATCH = "The office is empty. The Blue Team is reviewing the logs"


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


def final_screen(report: Report, catalog: Catalog, level: str = "easy", blue: list[str] = (), red: list[str] = ()) -> Group:
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

    result = Panel(board, title="[bold]RESULT[/]", border_style=_score_color(score), padding=(1, 2))
    if level == "hard":
        return Group(result)

    body = Text(format_report(report, catalog, lessons=level == "easy"))
    body.highlight_regex(r"--- DAY \d+ ---", f"bold {AMBER}")
    body.highlight_regex(r"\bSUCCESS\b", f"bold {GREEN}")
    body.highlight_regex(r"\b(BLOCKED|SKIPPED)\b", f"bold {MUTED}")
    body.highlight_regex(r"\b(DETECTED|FOUND)\b", f"bold {RED}")
    body.highlight_regex(r"\bSPOTTED\b", f"bold {AMBER}")
    body.highlight_regex(r"Helped:.*", BLUE)
    body.highlight_regex(r"Gap:.*", AMBER)
    body.highlight_regex(r"\[T\d{4}(\.\d{3})?[^\]]*\]", MUTED)

    parts = [result, Panel(body, title="[bold]POST-MORTEM[/]", title_align="left", border_style=FAINT, padding=(1, 2))]
    if level == "easy":
        parts.append(tips_panel(blue, red))
    return Group(*parts)


def tips_panel(blue: list[str], red: list[str]) -> Panel:
    grid = Table.grid(expand=True, padding=(0, 3))
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(Text("AS BLUE", style=f"bold {BLUE}"), Text("AS RED", style=f"bold {RED}"))
    blue_text = Text("\n".join(f"• {tip}" for tip in blue))
    red_text = Text("\n".join(f"• {tip}" for tip in red))
    grid.add_row(blue_text, red_text)
    return Panel(grid, title="[bold]WHAT YOU COULD DO[/]", title_align="left", border_style=AMBER, padding=(1, 2))


def random_side_note(side: str) -> Text:
    color = BLUE if side == "blue" else RED
    return Text.assemble(("The coin says: ", MUTED), (f"you play {side.upper()}", f"bold {color}"), ("  (double points if you win)", MUTED))


def blue_alert(result: StepResult, target_name: str, named: bool) -> Text:
    what = result.attack.name if named else "Something suspicious"
    if result.kicked:
        return Text.assemble(("  CAUGHT ", f"bold white on {BLUE}"), (f"  {what} on {target_name}. You kicked the attacker out.", BLUE))
    return Text.assemble(("  ALERT ", f"bold black on {AMBER}"), (f"  {what} against {target_name} was blocked.", AMBER))


def blue_night(night: NightResult, easy: bool) -> Text:
    text = Text(f"  ☾ Night {night.day}: your team reviews the logs", style=MUTED)
    if easy:
        text.append(f" ({percent(night.hunt_chance)} chance to find the attacker)", style=MUTED)
    if night.found:
        text.append("\n  FOUND ", style=f"bold white on {BLUE}")
        text.append("  The attacker was hiding in the network. You threw them out.", style=BLUE)
    return text


def score_panel(score, profile, unlocked: list[str]) -> Panel:
    color = BLUE if score.side == "blue" else RED
    verdict = Text("YOU WIN" if score.won else "YOU LOSE", style=f"bold {GREEN if score.won else RED}")
    lines = Text()
    lines.append(f"{score.side.upper()} TEAM  ", style=f"bold {color}")
    lines.append_text(verdict)
    lines.append(f"\n\nBase  {score.base}", style=MUTED)
    for name, value in score.bonuses.items():
        lines.append(f"\n+{value}  {name}", style=MUTED)
    if score.multiplier != 1:
        lines.append(f"\n×{score.multiplier:g}  multiplier", style=MUTED)
    lines.append("\n\nPoints this game  ", style=MUTED)
    lines.append(str(score.total), style=f"bold {AMBER}")
    lines.append(f"\nTotal points  {profile.points}   Games  {profile.games}   ", style=MUTED)
    lines.append("Wins  " + ", ".join(f"{tier} {count}" for tier, count in profile.wins.items()) if profile.wins else "Wins  none yet", style=MUTED)
    for tier in unlocked:
        lines.append(f"\n\nUNLOCKED  the {tier} company is now open!", style=f"bold {GREEN}")
    for tier in ("medium", "large"):
        reason = profile.lock_reason(tier)
        if reason and tier not in unlocked:
            lines.append(f"\nLocked: {tier}, {reason}", style=FAINT)
            break
    return Panel(lines, title="[bold]SCORE[/]", title_align="left", border_style=color, padding=(1, 2))


def waf_tutorial() -> Panel:
    text = Text()
    text.append("WAF LAB", style=f"bold {AMBER}")
    text.append("  practice only, it does not change your points\n\n", style=MUTED)
    text.append("1. A normal login\n", style="bold")
    text.append("You type a name and a password. The site asks its database:\n", style=MUTED)
    text.append("   find the user maria AND password 1234\n\n")
    text.append("2. SQL injection\n", style="bold")
    text.append("A hacker types ", style=MUTED)
    text.append("' OR 1=1", style=f"bold {RED}")
    text.append(" as the password. The question becomes:\n", style=MUTED)
    text.append("   find the user maria AND password '' OR 1=1\n")
    text.append("1=1 is always true, so the database lets them in without a password.\n\n", style=MUTED)
    text.append("3. XSS\n", style="bold")
    text.append("A hacker writes a product review containing ", style=MUTED)
    text.append("<script>...</script>", style=f"bold {RED}")
    text.append(". Every visitor's browser runs that code.\n\n", style=MUTED)
    text.append("4. The WAF\n", style="bold")
    text.append("A doorman in front of the site. He reads every message and blocks the suspicious ones, "
                "without blocking real customers like Mr O'Brien. Pick what he cleans up and what he blocks. "
                "40 real attacks and 25 innocent customers will try to get in.", style=MUTED)
    return Panel(text, border_style=AMBER, padding=(1, 2))


def waf_status_tokens(report) -> list[tuple[str, str]]:
    attacks = sum(report.totals.get(kind, 0) for kind in ("sqli", "xss", "traversal"))
    caught = sum(report.caught.get(kind, 0) for kind in ("sqli", "xss", "traversal"))
    tokens = [
        ("class:tag", "  Hackers blocked "), ("class:spent", f"{caught}/{attacks}"),
        ("class:tag", "   Innocent customers blocked "),
        ("class:warning" if report.false_positives else "class:spent", f"{len(report.false_positives)}/{report.totals.get('benign', 0)}"),
        ("class:tag", "   WAF score "), ("class:spent", f"{report.score}/100"),
    ]
    if report.missed:
        tricks = [v.hint for v in report.missed[:3]]
        more = f" (+{len(report.missed) - 3} more)" if len(report.missed) > 3 else ""
        tokens += [("", "\n"), ("class:tag", "  Still getting in: " + "; ".join(tricks) + more)]
    if report.false_positives:
        names = ", ".join(f"'{v.text}'" for v in report.false_positives[:3])
        tokens += [("", "\n"), ("class:warning", f"  Wrongly blocked: {names}")]
    return tokens


def waf_summary(report) -> Text:
    color = GREEN if report.score >= 85 else AMBER if report.score >= 60 else RED
    return Text.assemble(
        ("Your WAF scored ", MUTED), (f"{report.score}/100", f"bold {color}"),
        (f". It blocked {round(report.catch_rate * 100)}% of the hackers and {len(report.false_positives)} innocent customers.", MUTED),
    )
