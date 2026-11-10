import json
import random

from bastion import ai
from bastion.catalog import DATA_DIR, load_catalog, load_edge
from bastion.company import list_scenarios, roll_mistakes
from bastion.engine import Campaign

TARGETS = {
    "small": {"easy": 0.8, "medium": 0.7, "hard": 0.5},
    "medium": {"easy": 0.7, "medium": 0.5, "hard": 0.3},
    "large": {"easy": 0.6, "medium": 0.3, "hard": 0.1},
}
LEVELS = ("easy", "medium", "hard")
SIDES = ("red", "blue")


def player_won(company, catalog, level: str, side: str, edge: float, seed: int) -> bool:
    rng = random.Random(seed)
    rolled = roll_mistakes(company, rng)
    defenses = ai.pick_defenses(rolled, catalog, rng)
    arsenal = ai.pick_arsenal(rolled, catalog, rng)
    if side == "red":
        red, blue = ai.RedAI(level), ai.BlueAI(ai.BLUE_AI_KNOWLEDGE[level], random.Random(seed))
    else:
        red, blue = ai.RedAI(ai.RED_AI_KNOWLEDGE[level]), ai.BlueAI(level, random.Random(seed))
    campaign = Campaign(rolled, catalog, defenses, arsenal, rng=rng, edge=edge, active_blue=True)
    ai.play_out_active(campaign, red, blue)
    red_won = campaign.report().points > 0
    return red_won if side == "red" else not red_won


def win_rate(company, catalog, level: str, side: str, edge: float, games: int, offset: int = 0) -> float:
    wins = sum(player_won(company, catalog, level, side, edge, seed) for seed in range(offset, offset + games))
    return wins / games


def tune(games: int = 200, steps: int = 9) -> dict:
    catalog = load_catalog()
    table = {side: {} for side in SIDES}
    for company in list_scenarios():
        for side in SIDES:
            table[side][company.tier] = {}
            for level in LEVELS:
                goal = TARGETS[company.tier][level]
                low, high = 0.02, 80.0
                for _ in range(steps):
                    mid = (low * high) ** 0.5
                    rate = win_rate(company, catalog, level, side, mid, games, offset=10_000)
                    player_needs_more = rate < goal
                    red_needs_more = player_needs_more if side == "red" else not player_needs_more
                    if red_needs_more:
                        low = mid
                    else:
                        high = mid
                table[side][company.tier][level] = round((low * high) ** 0.5, 2)
    return table


def save_table(table: dict) -> None:
    lines = ["{"]
    for s_index, side in enumerate(SIDES):
        lines.append(f'  "{side}": {{')
        tiers = list(table[side])
        for t_index, tier in enumerate(tiers):
            comma = "," if t_index < len(tiers) - 1 else ""
            lines.append(f'    "{tier}": {json.dumps(table[side][tier])}{comma}')
        lines.append("  }" + ("," if s_index < len(SIDES) - 1 else ""))
    lines.append("}")
    (DATA_DIR / "balance.json").write_text("\n".join(lines) + "\n", encoding="utf-8")


def check(games: int = 200, tolerance: float = 0.08) -> list[tuple[str, str, str, float, float, bool]]:
    catalog = load_catalog()
    rows = []
    for company in list_scenarios():
        for side in SIDES:
            for level in LEVELS:
                goal = TARGETS[company.tier][level]
                edge = load_edge(company.tier, level, side)
                rate = win_rate(company, catalog, level, side, edge, games)
                rows.append((company.id, side, level, goal, rate, abs(rate - goal) <= tolerance))
    return rows
