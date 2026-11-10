import json
from collections import defaultdict
from datetime import datetime, timezone

from bastion.engine import Campaign
from bastion.profile import home

EXTREME_LOW = 0.05
EXTREME_HIGH = 0.95


def log_game(campaign: Campaign, level: str, side: str, player: str = "local") -> None:
    first_way_in = next(
        (r.attack.id for r in campaign.results if r.succeeded and r.attack.tactic in ("initial-access", "credential-access")),
        None,
    )
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "player": player,
        "company": campaign.company.id,
        "tier": campaign.company.tier,
        "level": level,
        "side": side,
        "defenses": sorted(campaign.defense_ids),
        "arsenal": sorted(campaign.arsenal),
        "moves": [[r.attack.id, r.step.target_id, r.succeeded, r.detected] for r in campaign.results],
        "first_way_in": first_way_in,
        "red_won": campaign.report().points > 0,
        "damage": campaign.report().points,
    }
    folder = home()
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "games.jsonl", "a", encoding="utf-8") as file:
        file.write(json.dumps(entry) + "\n")


def read_games() -> list[dict]:
    path = home() / "games.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_extremes(games: list[dict], min_games: int = 20, versus_players_only: bool = True) -> list[str]:
    if versus_players_only:
        games = [g for g in games if g.get("side") == "pvp"]
    groups = defaultdict(list)
    for game in games:
        for defense in game["defenses"]:
            groups[(game["company"], "defense", defense)].append(game["red_won"])
        for attack in game["arsenal"]:
            groups[(game["company"], "attack", attack)].append(game["red_won"])
        groups[(game["company"], "defense set", ",".join(game["defenses"]))].append(game["red_won"])
        if game["first_way_in"]:
            groups[(game["company"], "way in", game["first_way_in"])].append(game["red_won"])
    lines = []
    for (company, kind, name), results in sorted(groups.items()):
        if len(results) < min_games:
            continue
        rate = sum(results) / len(results)
        if rate < EXTREME_LOW or rate > EXTREME_HIGH:
            lines.append(f"{company}: {kind} '{name}' -> Red wins {rate:.0%} of {len(results)} games")
    return lines
