from dataclasses import dataclass

from bastion import scoring
from bastion.clearance import SEALED_ID

STREAK_GOAL = 7
MAPS = ("small", "medium", "large", "huge")


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    text: str
    secret: str | None = None


ACHIEVEMENTS = (
    Achievement("ghost", "Ghost",
                "Win as Red on Meridian Bank Hard without a single move being spotted."),
    Achievement("not-one-byte", "Not One Byte",
                "Win as Blue on Meridian Bank Hard: no data lost, attacker kicked out, no clean machine or account touched."),
    Achievement("blitz", "Blitz",
                "As Red on Hard, take every piece of data a company has by the end of day 3."),
    Achievement("shoestring", "Shoestring",
                "Win as Blue on Hard using at most half of your budget."),
    Achievement("iron-streak", "Iron Streak",
                f"Win {STREAK_GOAL} Hard or Realism games in a row, either side."),
    Achievement("purple", "Purple",
                "Win Directorate-7 on Hard as Red and as Blue.", secret="cleared"),
    Achievement("full-spectrum", "Full Spectrum",
                "Win on Hard with both sides on all four maps.", secret="cleared"),
    Achievement("analyst", "Analyst",
                "Realism, Blue: kick the attacker out by the end of day 2 and win without disrupting anything clean.",
                secret="realism"),
    Achievement("silent-shell", "Silent Shell",
                "Realism, Red: win without a single move being spotted.", secret="realism"),
    Achievement("crown-jewels", "Crown Jewels",
                "Realism, Red, Meridian Bank or Directorate-7: own the whole domain and take every piece of data.",
                secret="realism"),
)
BY_ID = {a.id: a for a in ACHIEVEMENTS}


def _hard(session) -> bool:
    return session.level == "hard"


def _unseen(campaign) -> bool:
    spotted = any(r.detected for r in campaign.results)
    confirmed = any(e.real and e.investigated for e in campaign.logs)
    return not spotted and not confirmed and not campaign.caught


def _all_data(campaign) -> bool:
    every = {d.id for d in campaign.company.data if d.id != SEALED_ID}
    return bool(every) and every <= campaign.lost


def _owns_domain(campaign) -> bool:
    return campaign.foothold.admin_on >= {s.id for s in campaign.company.servers}


def summary(session) -> dict:
    """What one finished game proves, for the referee to store."""
    c = session.campaign
    side = session.side
    won = not session.gave_up and (scoring.red_won(c) if side == "red" else not scoring.red_won(c))
    tier = session.company.tier
    earned = []
    if won and _hard(session):
        if side == "red":
            if tier == "large" and _unseen(c):
                earned.append("ghost")
            loot_days = [r.step.day for r in c.results if r.points > 0]
            if _all_data(c) and loot_days and max(loot_days) <= 3:
                earned.append("blitz")
            if session.realism and _unseen(c):
                earned.append("silent-shell")
            if session.realism and tier in ("large", "huge") and _owns_domain(c) and _all_data(c):
                earned.append("crown-jewels")
        else:
            if tier == "large" and not c.lost and c.caught and c.disruption == 0:
                earned.append("not-one-byte")
            if c.budget_used * 2 <= session.company.budget:
                earned.append("shoestring")
            if session.realism and c.caught and c.day <= 2 and c.disruption == 0:
                earned.append("analyst")
    return {"tier": tier, "level": session.shown_level, "side": side, "won": won, "earned": earned}


def from_history(games: list[dict]) -> set[str]:
    """Achievements that need several verified games, in the order they were played."""
    earned = {a for g in games for a in g.get("earned", [])}
    streak = 0
    for g in games:
        if g["level"] not in ("hard", "realism"):
            continue
        streak = streak + 1 if g["won"] else 0
        if streak >= STREAK_GOAL:
            earned.add("iron-streak")
    hard_wins = {(g["tier"], g["side"]) for g in games if g["won"] and g["level"] == "hard"}
    if {("huge", "red"), ("huge", "blue")} <= hard_wins:
        earned.add("purple")
    if {(t, s) for t in MAPS for s in ("red", "blue")} <= hard_wins:
        earned.add("full-spectrum")
    return earned


def board(profile) -> list[dict]:
    """The achievements screen: classified ones stay redacted until their content is unlocked."""
    open_for = {None: True, "realism": profile.realism_open(), "cleared": profile.cleared()}
    rows = []
    for a in ACHIEVEMENTS:
        done = a.id in profile.achievements
        if open_for[a.secret] or done:
            rows.append({"id": a.id, "name": a.name, "text": a.text, "done": done, "classified": False})
        else:
            rows.append({"id": a.id, "name": "█████████", "text": "Classified. Unlock more of Bastion to read this file.",
                         "done": False, "classified": True})
    return rows
