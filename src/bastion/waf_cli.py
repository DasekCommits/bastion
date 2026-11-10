import argparse
import shutil
import sys

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bastion import look
from bastion.catalog import DATA_DIR
from bastion.profile import home
from bastion.waf import KINDS, RuleError, evaluate_safely, load_corpus, load_rules

NAMES = {"sqli": "SQL injection", "xss": "Cross-site scripting", "traversal": "Path traversal"}


def rules_path():
    return home() / "waf-rules.json"


def ensure_rules_file():
    path = rules_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(DATA_DIR / "waf_starter.json", path)
        return path, True
    return path, False


def show(report, console: Console) -> None:
    table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {look.BLUE}")
    table.add_column("Attack type")
    table.add_column("Blocked", justify="right")
    for kind in KINDS:
        caught, total = report.caught.get(kind, 0), report.totals.get(kind, 0)
        color = look.GREEN if caught == total else look.AMBER if caught >= total / 2 else look.RED
        table.add_row(NAMES[kind], Text(f"{caught}/{total}", style=f"bold {color}"))
    fp = len(report.false_positives)
    table.add_row("Innocent requests blocked", Text(f"{fp}/{report.totals.get('benign', 0)}", style=f"bold {look.GREEN if fp == 0 else look.RED}"))
    console.print(table)

    if report.missed:
        missed = Table(box=box.SIMPLE_HEAD, header_style=f"bold {look.RED}", title="Got through", title_justify="left")
        missed.add_column("Payload")
        missed.add_column("Trick", style=look.MUTED)
        for verdict in report.missed:
            missed.add_row(Text(verdict.text, style=look.RED), verdict.hint)
        console.print(missed)

    if report.false_positives:
        wrong = Table(box=box.SIMPLE_HEAD, header_style=f"bold {look.AMBER}", title="Innocent customers you blocked", title_justify="left")
        wrong.add_column("Request")
        wrong.add_column("Blocked by")
        wrong.add_column("Why it is innocent", style=look.MUTED)
        for verdict in report.false_positives:
            wrong.add_row(Text(verdict.text, style=look.AMBER), verdict.blocked_by, verdict.hint)
        console.print(wrong)

    score = report.score
    color = look.GREEN if score >= 85 else look.AMBER if score >= 60 else look.RED
    console.print(Panel(
        Text.assemble(("WAF SCORE  ", look.MUTED), (f"{score}/100", f"bold {color}"),
                      (f"   ({round(report.catch_rate * 100)}% of attacks blocked, -{4 * fp} for innocent requests)", look.MUTED)),
        border_style=color, expand=False,
    ))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bastion waf", description="Test your own WAF rules against real attack payloads.")
    parser.add_argument("--rules", default=None, help="path to a rules JSON file (default: ~/.bastion/waf-rules.json)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    console = Console(highlight=False)

    if args.rules:
        path = args.rules
    else:
        path, created = ensure_rules_file()
        if created:
            console.print(Text(f"Created your rules file: {path}", style=look.AMBER))
    console.print(Text(f"Rules: {path}", style=look.MUTED))
    try:
        report = evaluate_safely(load_rules(path), load_corpus())
    except (RuleError, ValueError, TypeError) as error:
        console.print(Text(f"Error: {error}", style=f"bold {look.RED}"))
        return 1
    show(report, console)
    return 0
