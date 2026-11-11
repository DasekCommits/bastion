import json
import random

from bastion import ai
from bastion.catalog import DATA_DIR, load_catalog, load_edge
from bastion.company import list_scenarios, roll_mistakes
from bastion.engine import Campaign

TARGETS = {
    "red": {
        "small": {"easy": 0.8, "medium": 0.7, "hard": 0.5},
        "medium": {"easy": 0.7, "medium": 0.5, "hard": 0.3},
        "large": {"easy": 0.6, "medium": 0.3, "hard": 0.1},
        "huge": {"easy": 0.5, "medium": 0.25, "hard": 0.1},
    },
    # blue targets are how often DOING NOTHING should win (low): the attacker is strong,
    # so a passive analyst loses and active response is what earns the win.
    "blue": {
        "small": {"easy": 0.3, "medium": 0.2, "hard": 0.1},
        "medium": {"easy": 0.25, "medium": 0.15, "hard": 0.08},
        "large": {"easy": 0.2, "medium": 0.1, "hard": 0.05},
        "huge": {"easy": 0.18, "medium": 0.1, "hard": 0.05},
    },
}
LEVELS = ("easy", "medium", "hard")
SIDES = ("red", "blue")


class _Passive:
    def next_action(self, campaign):
        return None


def player_won(company, catalog, level: str, side: str, edge: float, seed: int, blue="competent") -> bool:
    rng = random.Random(seed)
    rolled = roll_mistakes(company, rng)
    defenses = ai.pick_defenses(rolled, catalog, rng)
    arsenal = ai.pick_arsenal(rolled, catalog, rng, expert=side == "blue" and level == "hard")
    if side == "red":
        red, blue_ai = ai.RedAI(level), ai.BlueAI(ai.BLUE_AI_KNOWLEDGE[level], random.Random(seed))
    else:
        red = ai.RedAI(ai.RED_AI_KNOWLEDGE[level])
        blue_ai = _Passive() if blue == "passive" else ai.BlueAI(level, random.Random(seed))
    campaign = Campaign(rolled, catalog, defenses, arsenal, rng=rng, edge=edge, active_blue=True)
    ai.play_out_active(campaign, red, blue_ai)
    red_won = campaign.report().points > 0
    return red_won if side == "red" else not red_won


def win_rate(company, catalog, level: str, side: str, edge: float, games: int, offset: int = 0, blue="competent") -> float:
    wins = sum(player_won(company, catalog, level, side, edge, seed, blue) for seed in range(offset, offset + games))
    return wins / games


EDGE_MIN, EDGE_MAX = 0.02, 80.0


def at_limit(side: str, edge: float, rate: float, goal: float) -> bool:
    """The tuner already gives the attacker its maximum edge and the rate is still on the side only a stronger attacker could fix."""
    if edge < EDGE_MAX * 0.99:
        return False
    return rate > goal if side == "blue" else rate < goal


def tune(games: int = 200, steps: int = 9) -> dict:
    catalog = load_catalog()
    table = {side: {} for side in SIDES}
    for company in list_scenarios():
        for side in SIDES:
            table[side][company.tier] = {}
            for level in LEVELS:
                goal = TARGETS[side][company.tier][level]
                # red: tune so the attacking player wins the target (facing the competent defender).
                # blue: tune so a PASSIVE defender wins only the (low) target, which is monotonic in edge.
                blue_mode = "passive" if side == "blue" else "competent"
                low, high = EDGE_MIN, EDGE_MAX
                for _ in range(steps):
                    mid = (low * high) ** 0.5
                    rate = win_rate(company, catalog, level, side, mid, games, offset=10_000, blue=blue_mode)
                    # raising edge makes the attacker stronger: red wins more, passive-blue wins less
                    if side == "red":
                        if rate < goal:
                            low = mid
                        else:
                            high = mid
                    else:
                        if rate > goal:
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
                goal = TARGETS[side][company.tier][level]
                edge = load_edge(company.tier, level, side)
                mode = "passive" if side == "blue" else "competent"
                rate = win_rate(company, catalog, level, side, edge, games, blue=mode)
                ok = abs(rate - goal) <= tolerance
                rows.append((company.id, side, level, goal, rate, ok, not ok and at_limit(side, edge, rate, goal)))
    return rows


def check_feel(games: int = 300) -> list[tuple]:
    """For blue: how often doing nothing wins vs a competent analyst, at the tuned edge."""
    catalog = load_catalog()
    rows = []
    for company in list_scenarios():
        for level in LEVELS:
            edge = load_edge(company.tier, level, "blue")
            passive = win_rate(company, catalog, level, "blue", edge, games, blue="passive")
            skilled = win_rate(company, catalog, level, "blue", edge, games, blue="competent")
            rows.append((company.id, level, passive, skilled))
    return rows
