from dataclasses import dataclass

from bastion.engine import Campaign

CAUGHT_BONUS = 10
SPOTTED_BONUS = 2
MAX_SPOTTED_BONUS = 10
MAX_EFFICIENCY_BONUS = 10
STEALTH_MULTIPLIER = 1.5
MAX_SPEED_BONUS = 10
DOMAIN_BONUS = 10
RANDOM_MULTIPLIER = 2


@dataclass
class Score:
    side: str
    won: bool
    base: int
    bonuses: dict[str, int]
    multiplier: float
    total: int


def red_won(campaign: Campaign) -> bool:
    return campaign.report().points > 0


def blue_score(campaign: Campaign, random_side: bool = False) -> Score:
    report = campaign.report()
    company = campaign.company
    spotted = sum(1 for result in campaign.results if result.detected)
    bonuses = {
        "caught the attacker": CAUGHT_BONUS if campaign.caught else 0,
        "spotted attempts": min(MAX_SPOTTED_BONUS, SPOTTED_BONUS * spotted),
        "budget left": round(MAX_EFFICIENCY_BONUS * (company.budget - campaign.budget_used) / company.budget),
    }
    return _total("blue", not red_won(campaign), report.defense_score, bonuses, 1.0, random_side)


def red_score(campaign: Campaign, random_side: bool = False) -> Score:
    report = campaign.report()
    company = campaign.company
    base = round(100 * min(report.points, report.max_points) / report.max_points)
    won = red_won(campaign)
    days_left = company.max_days - campaign.day
    every_server = {server.id for server in company.servers}
    bonuses = {
        "speed": round(MAX_SPEED_BONUS * days_left / company.max_days) if won else 0,
        "owned the domain": DOMAIN_BONUS if company.tier == "large" and campaign.foothold.admin_on >= every_server else 0,
    }
    stealth = STEALTH_MULTIPLIER if won and not campaign.caught else 1.0
    return _total("red", won, base, bonuses, stealth, random_side)


def _total(side: str, won: bool, base: int, bonuses: dict[str, int], multiplier: float, random_side: bool) -> Score:
    if random_side and won:
        multiplier *= RANDOM_MULTIPLIER
    total = round((base + sum(bonuses.values())) * multiplier)
    return Score(side, won, base, {k: v for k, v in bonuses.items() if v}, multiplier, total)
