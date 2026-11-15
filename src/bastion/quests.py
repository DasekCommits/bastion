"""Shop quests: one-time goals that pay Red or Blue coins.

Each verified game can move a quest forward by one. The referee records which quests a
game moved (in the game summary), and the server adds up those marks across verified
games, so progress cannot be typed in from the browser.
"""
from dataclasses import dataclass

from bastion import scoring


@dataclass(frozen=True)
class Quest:
    id: str
    side: str
    name: str
    text: str
    goal: int
    reward: int


QUESTS = (
    Quest("red-scout", "red", "Scout First",
          "Scan a server, then break into that same server in the same game.", 1, 3),
    Quest("red-inside", "red", "Foot in the Door",
          "Get inside the company.", 3, 4),
    Quest("red-climb", "red", "Climb the Ladder",
          "Become an administrator with privilege escalation.", 3, 5),
    Quest("red-loot", "red", "Smash and Grab",
          "Steal data from the company.", 5, 6),
    Quest("red-quiet", "red", "Quiet Hands",
          "Win without a single move being spotted.", 1, 6),
    Quest("red-veteran", "red", "Red Veteran",
          "Win on Medium or Hard.", 3, 8),
    Quest("blue-confirm", "blue", "Eyes on the Logs",
          "Investigate an alert and confirm a real attack.", 3, 3),
    Quest("blue-shut", "blue", "Shut the Door",
          "Block an attack that came from outside.", 3, 4),
    Quest("blue-cut", "blue", "Cut Them Off",
          "Kick the attacker out of the company.", 3, 5),
    Quest("blue-vault", "blue", "Nothing Leaves",
          "Win without losing any data.", 5, 6),
    Quest("blue-surgical", "blue", "Surgical",
          "Kick the attacker out and win without disrupting a clean machine or account.", 1, 6),
    Quest("blue-veteran", "blue", "Blue Veteran",
          "Win on Medium or Hard.", 3, 8),
)
BY_ID = {q.id: q for q in QUESTS}


def _won(session) -> bool:
    c = session.campaign
    if session.gave_up:
        return False
    return scoring.red_won(c) if session.side == "red" else not scoring.red_won(c)


def marks(session) -> list[str]:
    """The quests this finished game moves forward, at most once each."""
    c = session.campaign
    won = _won(session)
    hard = session.shown_level in ("medium", "hard", "realism")
    done = []
    if session.side == "red":
        if any(r.succeeded and r.attack.tactic == "initial-access" and r.attack.target == "server"
               and r.step.target_id in c.foothold.scanned for r in c.results):
            done.append("red-scout")
        if c.reached_on:
            done.append("red-inside")
        if any(r.succeeded and r.attack.id == "privilege-escalation" and r.success_chance < 1.0 for r in c.results):
            done.append("red-climb")
        if any(r.attack.tactic == "exfiltration" and r.points > 0 for r in c.results):
            done.append("red-loot")
        if won and not any(r.detected for r in c.results) and not c.caught:
            done.append("red-quiet")
        if won and hard:
            done.append("red-veteran")
    elif session.side == "blue":
        if any(e.real and e.investigated for e in c.logs):
            done.append("blue-confirm")
        if any(a.kind == "block" and a.useful for a in c.blue_actions):
            done.append("blue-shut")
        if c.caught:
            done.append("blue-cut")
        if won and not c.lost:
            done.append("blue-vault")
        if won and c.caught and c.disruption == 0:
            done.append("blue-surgical")
        if won and hard:
            done.append("blue-veteran")
    return done


def progress(summaries: list[dict]) -> dict[str, int]:
    counts = {q.id: 0 for q in QUESTS}
    for summary in summaries:
        for quest_id in set(summary.get("quests", [])):
            if quest_id in counts:
                counts[quest_id] += 1
    return counts


def rewards(counts: dict[str, int]) -> dict[str, int]:
    coins = {"red": 0, "blue": 0}
    for q in QUESTS:
        if counts.get(q.id, 0) >= q.goal:
            coins[q.side] += q.reward
    return coins


def board(counts: dict[str, int] | None = None) -> list[dict]:
    counts = counts or {}
    return [{"id": q.id, "side": q.side, "name": q.name, "text": q.text, "goal": q.goal, "reward": q.reward,
             "count": min(counts.get(q.id, 0), q.goal), "done": counts.get(q.id, 0) >= q.goal} for q in QUESTS]
