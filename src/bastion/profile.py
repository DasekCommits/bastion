import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

TIERS = ("small", "medium", "large")
LEVELS = ("easy", "medium", "hard")
TIER_NAMES = {"small": "Olive Byte", "medium": "Harbor Clinic", "large": "Meridian Bank"}

UNLOCKS = {
    ("medium", "easy"): (("small", "easy"), 5),
    ("small", "medium"): (("medium", "easy"), 10),
    ("medium", "medium"): (("small", "medium"), 5),
    ("small", "hard"): (("medium", "medium"), 10),
    ("medium", "hard"): (("small", "hard"), 5),
    ("large", "easy"): (("medium", "hard"), 10),
    ("large", "medium"): (("medium", "hard"), 10),
    ("large", "hard"): (("medium", "hard"), 10),
}


SEALED_GOAL = 10
SCRIPT_GOAL = 3


def home() -> Path:
    return Path(os.environ.get("BASTION_HOME", Path.home() / ".bastion"))


def key(tier: str, level: str) -> str:
    return f"{tier}/{level}"


def describe(tier: str, level: str) -> str:
    return f"{TIER_NAMES[tier]} {level.capitalize()}"


@dataclass
class Profile:
    points: int = 0
    games: int = 0
    wins: dict[str, int] = field(default_factory=dict)
    secrets: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        migrated = {}
        for name, count in self.wins.items():
            target = name if "/" in name else key(name, "easy")
            migrated[target] = migrated.get(target, 0) + count
        self.wins = migrated

    def wins_on(self, tier: str, level: str) -> int:
        return self.wins.get(key(tier, level), 0)

    def is_unlocked(self, tier: str, level: str) -> bool:
        rule = UNLOCKS.get((tier, level))
        if rule is None:
            return True
        (need_tier, need_level), count = rule
        return self.wins_on(need_tier, need_level) >= count

    def lock_reason(self, tier: str, level: str) -> str | None:
        if self.is_unlocked(tier, level):
            return None
        (need_tier, need_level), count = UNLOCKS[(tier, level)]
        return f"win {count} games on {describe(need_tier, need_level)} first ({self.wins_on(need_tier, need_level)}/{count})"

    def add_secret(self, name: str, amount: int) -> int:
        self.secrets[name] = self.secrets.get(name, 0) + amount
        return self.secrets[name]

    def realism_open(self) -> bool:
        return self.secrets.get("sealed", 0) >= SEALED_GOAL

    def cleared(self) -> bool:
        return self.realism_open() and self.secrets.get("script", 0) >= SCRIPT_GOAL

    def level_open(self, level: str) -> bool:
        return any(self.is_unlocked(tier, level) for tier in TIERS)

    def next_goal(self) -> str | None:
        for (tier, level), ((need_tier, need_level), count) in UNLOCKS.items():
            if not self.is_unlocked(tier, level) and self.is_unlocked(need_tier, need_level):
                return f"Next: win {count} games on {describe(need_tier, need_level)} to unlock {describe(tier, level)} ({self.wins_on(need_tier, need_level)}/{count})"
        return None

    def record(self, tier: str, level: str, won: bool, points: int) -> list[str]:
        before = {pair for pair in UNLOCKS if self.is_unlocked(*pair)}
        self.games += 1
        self.points += points
        if won:
            self.wins[key(tier, level)] = self.wins_on(tier, level) + 1
        return [describe(*pair) for pair in UNLOCKS if self.is_unlocked(*pair) and pair not in before]


def load_profile() -> Profile:
    path = home() / "profile.json"
    if not path.exists():
        return Profile()
    return Profile(**json.loads(path.read_text(encoding="utf-8")))


def save_profile(profile: Profile) -> None:
    folder = home()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "profile.json").write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")
