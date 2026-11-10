import html
import json
import multiprocessing
import re
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty
from urllib.parse import unquote_plus

from bastion.catalog import DATA_DIR

NORMALIZERS = ("url-decode", "html-decode", "lowercase", "strip-sql-comments", "collapse-spaces", "remove-tabs")
KINDS = ("sqli", "xss", "traversal")
FALSE_POSITIVE_PENALTY = 4
TIMEOUT_SECONDS = 5


class RuleError(ValueError):
    pass


@dataclass
class Rule:
    id: str
    pattern: str
    note: str = ""


@dataclass
class RuleSet:
    normalize: list[str]
    rules: list[Rule]


@dataclass
class Verdict:
    text: str
    kind: str
    blocked_by: str | None
    hint: str


@dataclass
class WafReport:
    verdicts: list[Verdict]
    caught: dict[str, int] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)

    @property
    def missed(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.kind != "benign" and not v.blocked_by]

    @property
    def false_positives(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.kind == "benign" and v.blocked_by]

    @property
    def catch_rate(self) -> float:
        attacks = sum(self.totals.get(kind, 0) for kind in KINDS)
        return sum(self.caught.get(kind, 0) for kind in KINDS) / attacks if attacks else 0.0

    @property
    def score(self) -> int:
        return max(0, round(100 * self.catch_rate) - FALSE_POSITIVE_PENALTY * len(self.false_positives))


def normalize(text: str, steps: list[str]) -> str:
    for step in steps:
        if step == "url-decode":
            for _ in range(3):
                decoded = unquote_plus(text)
                if decoded == text:
                    break
                text = decoded
        elif step == "html-decode":
            text = html.unescape(text)
        elif step == "lowercase":
            text = text.lower()
        elif step == "strip-sql-comments":
            text = re.sub(r"/\*.*?\*/", " ", text)
        elif step == "collapse-spaces":
            text = re.sub(r"\s+", " ", text)
        elif step == "remove-tabs":
            text = text.replace("\t", "")
    return text


def parse_rules(raw: dict) -> RuleSet:
    steps = raw.get("normalize", [])
    for step in steps:
        if step not in NORMALIZERS:
            raise RuleError(f"Unknown normalize step '{step}'. Use any of: {', '.join(NORMALIZERS)}")
    rules = []
    for item in raw.get("rules", []):
        rule = Rule(**item)
        try:
            re.compile(rule.pattern)
        except re.error as error:
            raise RuleError(f"Rule '{rule.id}' is not a valid regex: {error}") from error
        rules.append(rule)
    return RuleSet(steps, rules)


def load_rules(path: Path) -> RuleSet:
    return parse_rules(json.loads(Path(path).read_text(encoding="utf-8")))


def load_corpus() -> dict:
    return json.loads((DATA_DIR / "waf_corpus.json").read_text(encoding="utf-8"))


def evaluate(ruleset: RuleSet, corpus: dict) -> WafReport:
    compiled = [(rule.id, re.compile(rule.pattern)) for rule in ruleset.rules]
    report = WafReport(verdicts=[])
    requests = [(a["text"], a["kind"], a["trick"]) for a in corpus["attacks"]]
    requests += [(b["text"], "benign", b["why"]) for b in corpus["benign"]]
    for text, kind, hint in requests:
        seen = normalize(text, ruleset.normalize)
        blocked_by = next((rule_id for rule_id, regex in compiled if regex.search(seen)), None)
        report.verdicts.append(Verdict(text, kind, blocked_by, hint))
        report.totals[kind] = report.totals.get(kind, 0) + 1
        if blocked_by and kind != "benign":
            report.caught[kind] = report.caught.get(kind, 0) + 1
    return report


def _worker(ruleset: RuleSet, corpus: dict, queue) -> None:
    queue.put(evaluate(ruleset, corpus))


def evaluate_safely(ruleset: RuleSet, corpus: dict, timeout: float = TIMEOUT_SECONDS) -> WafReport:
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=_worker, args=(ruleset, corpus, queue))
    process.start()
    try:
        report = queue.get(timeout=timeout)
    except Empty:
        process.terminate()
        process.join()
        raise RuleError(
            f"Your rules took more than {timeout:g} seconds. One of them probably backtracks forever "
            "(ReDoS), for example a pattern like (a+)+. Attackers use this to freeze real WAFs."
        ) from None
    process.join()
    return report


CLEAN_ORDER = ("url-decode", "html-decode", "remove-tabs", "strip-sql-comments", "collapse-spaces", "lowercase")


@dataclass
class LibraryItem:
    id: str
    kind: str
    title: str
    explain: str
    pattern: str = ""


def load_library() -> list[LibraryItem]:
    raw = json.loads((DATA_DIR / "waf_library.json").read_text(encoding="utf-8"))
    return [LibraryItem(**item) for item in raw]


def library_ruleset(selected: list[str], library: list[LibraryItem] | None = None) -> RuleSet:
    library = library or load_library()
    chosen = {item.id: item for item in library if item.id in selected}
    steps = [step for step in CLEAN_ORDER if step in chosen]
    rules = [Rule(item.id, item.pattern, item.title) for item in library if item.kind == "rule" and item.id in chosen]
    return RuleSet(steps, rules)
