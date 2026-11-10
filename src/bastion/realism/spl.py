import fnmatch
import re
import shlex
from dataclasses import dataclass

MAX_RESULTS = 500
COMPARE = re.compile(r"^([A-Za-z_][\w.]*)\s*(!=|>=|<=|=|>|<)\s*(.*)$")
AGGREGATES = ("count", "dc", "values", "sum", "min", "max", "avg")


class QueryError(ValueError):
    pass


@dataclass
class Term:
    field: str | None
    op: str
    value: str
    negate: bool = False


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _matches_value(actual, pattern: str) -> bool:
    if actual is None:
        return False
    if isinstance(actual, list):
        return any(_matches_value(item, pattern) for item in actual)
    return fnmatch.fnmatchcase(str(actual).lower(), pattern.lower())


def _compare(actual, op: str, expected: str) -> bool:
    if op in ("=", "!="):
        hit = _matches_value(actual, expected)
        return hit if op == "=" else (actual is not None and not hit)
    left, right = _number(actual), _number(expected)
    if left is None or right is None:
        return False
    return {">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right}[op]


def _term_matches(event: dict, term: Term) -> bool:
    if term.field is None:
        hit = fnmatch.fnmatchcase(event.get("_raw", "").lower(), f"*{term.value.lower()}*")
    else:
        hit = _compare(event.get(term.field), term.op, term.value)
    return not hit if term.negate else hit


def _split(text: str) -> list[str]:
    try:
        lexer = shlex.shlex(text, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError as error:
        raise QueryError(f"Check your quotes: {error}") from error


def _split_pipes(query: str) -> list[str]:
    parts, current, quote = [], [], None
    for char in query:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current.append(char)
        elif char == "|":
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return parts


def _parse_search(text: str) -> list[list[Term]]:
    groups, current, negate = [], [], False
    for token in _split(text):
        if token.upper() == "OR":
            groups.append(current)
            current = []
            continue
        if token.upper() == "NOT":
            negate = True
            continue
        match = COMPARE.match(token)
        if match:
            current.append(Term(match.group(1), match.group(2), match.group(3), negate))
        else:
            current.append(Term(None, "=", token, negate))
        negate = False
    groups.append(current)
    return [group for group in groups if group] or [[]]


def search(events: list[dict], text: str) -> list[dict]:
    groups = _parse_search(text)
    return [e for e in events if any(all(_term_matches(e, t) for t in group) for group in groups)]


def _parse_aggregates(tokens: list[str]) -> list[tuple[str, str | None, str]]:
    specs, i = [], 0
    while i < len(tokens):
        token = tokens[i].rstrip(",")
        match = re.match(r"^(\w+)(?:\((\w[\w.]*)\))?$", token)
        if not match or match.group(1) not in AGGREGATES:
            raise QueryError(f"stats does not know '{token}'. Use count, dc(field), values(field), sum, min, max or avg.")
        func, field = match.group(1), match.group(2)
        if func != "count" and not field:
            raise QueryError(f"{func} needs a field, like {func}(src_ip).")
        name = f"{func}({field})" if field else "count"
        if i + 1 < len(tokens) and tokens[i + 1].lower() == "as":
            if i + 2 >= len(tokens):
                raise QueryError("'as' needs a new name after it.")
            name = tokens[i + 2].rstrip(",")
            i += 2
        specs.append((func, field, name))
        i += 1
    return specs


def _aggregate(func: str, field: str | None, rows: list[dict]):
    if func == "count":
        return len(rows) if field is None else sum(1 for r in rows if r.get(field) is not None)
    values = [r.get(field) for r in rows if r.get(field) is not None]
    if func == "dc":
        return len({str(v) for v in values})
    if func == "values":
        return sorted({str(v) for v in values})
    numbers = [n for n in (_number(v) for v in values) if n is not None]
    if not numbers:
        return None
    if func == "sum":
        return sum(numbers)
    if func == "min":
        return min(numbers)
    if func == "max":
        return max(numbers)
    return round(sum(numbers) / len(numbers), 2)


def _stats(rows: list[dict], args: list[str]) -> list[dict]:
    lowered = [a.lower() for a in args]
    if "by" in lowered:
        cut = lowered.index("by")
        agg_tokens, by = args[:cut], [f.strip(",") for f in " ".join(args[cut + 1:]).replace(",", " ").split()]
    else:
        agg_tokens, by = args, []
    if not agg_tokens:
        raise QueryError("stats needs something to count, like: stats count by src_ip")
    specs = _parse_aggregates(agg_tokens)
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = tuple(row.get(f) for f in by)
        if by and any(k is None for k in key):
            continue
        groups.setdefault(key, []).append(row)
    out = []
    for key, members in groups.items():
        result = dict(zip(by, key))
        for func, field, name in specs:
            result[name] = _aggregate(func, field, members)
        out.append(result)
    return out


def _sort_key(value):
    number = _number(value)
    return (0, number, "") if number is not None else (1, 0, str(value).lower())


def _sort(rows: list[dict], args: list[str]) -> list[dict]:
    fields = [a for a in " ".join(args).replace(",", " ").split() if not a.isdigit()]
    if not fields:
        raise QueryError("sort needs a field, like: sort -count")
    for spec in reversed(fields):
        reverse = spec.startswith("-")
        name = spec.lstrip("+-")
        present = [r for r in rows if r.get(name) is not None]
        missing = [r for r in rows if r.get(name) is None]
        rows = sorted(present, key=lambda r: _sort_key(r.get(name)), reverse=reverse) + missing
    return rows


def _where(rows: list[dict], args: list[str]) -> list[dict]:
    text = re.sub(r"\s*(!=|>=|<=|=|>|<)\s*", r"\1", " ".join(args), count=1)
    match = COMPARE.match(text)
    if not match:
        raise QueryError("where needs a comparison, like: where count > 20")
    field, op, value = match.group(1), match.group(2), match.group(3).strip().strip("\"'")
    return [r for r in rows if _compare(r.get(field), op, value)]


def _top(rows: list[dict], args: list[str], rare: bool) -> list[dict]:
    if not args:
        raise QueryError("top and rare need a field, like: top src_ip")
    field = args[0]
    counted = _stats(rows, ["count", "by", field])
    total = sum(r["count"] for r in counted) or 1
    for r in counted:
        r["percent"] = round(100 * r["count"] / total, 1)
    counted.sort(key=lambda r: r["count"], reverse=not rare)
    return counted[:10]


def run(events: list[dict], query: str) -> dict:
    query = query.strip()
    if not query:
        raise QueryError("Type a search, for example: index=security EventCode=4625")
    stages = _split_pipes(query)
    first = stages[0]
    if first.lower().startswith("search "):
        first = first[7:]
    rows = search(events, first) if first else list(events)
    rows = sorted(rows, key=lambda e: e.get("_time", ""), reverse=True)
    columns = None
    for stage in stages[1:]:
        if not stage:
            raise QueryError("There is an empty step between two | signs.")
        tokens = _split(stage)
        command, args = tokens[0].lower(), tokens[1:]
        if command == "stats":
            rows = _stats(rows, args)
            columns = None
        elif command == "sort":
            rows = _sort(rows, args)
        elif command in ("head", "tail"):
            n = int(args[0]) if args and args[0].isdigit() else 10
            rows = rows[:n] if command == "head" else rows[-n:]
        elif command in ("table", "fields"):
            columns = [f for f in " ".join(args).replace(",", " ").split()]
            if not columns:
                raise QueryError(f"{command} needs field names, like: {command} _time user src_ip")
            rows = [{c: r.get(c) for c in columns} for r in rows]
        elif command == "dedup":
            if not args:
                raise QueryError("dedup needs a field, like: dedup user")
            seen, kept = set(), []
            for r in rows:
                key = tuple(r.get(f.strip(",")) for f in args)
                if key not in seen:
                    seen.add(key)
                    kept.append(r)
            rows = kept
        elif command == "where":
            rows = _where(rows, args)
        elif command == "rename":
            if len(args) < 3 or args[1].lower() != "as":
                raise QueryError("rename works like: rename src_ip as attacker")
            old, new = args[0], args[2]
            rows = [{(new if k == old else k): v for k, v in r.items()} for r in rows]
            if columns:
                columns = [new if c == old else c for c in columns]
        elif command in ("top", "rare"):
            rows = _top(rows, args, rare=command == "rare")
            columns = None
        elif command == "search":
            rows = search(rows, " ".join(args))
        else:
            raise QueryError(f"Unknown command '{command}'. Try stats, sort, head, table, dedup, where, rename, top or rare.")
    if columns is None and rows and "_raw" not in rows[0]:
        columns = list(dict.fromkeys(k for r in rows for k in r))
    return {"rows": rows[:MAX_RESULTS], "total": len(rows), "columns": columns}
