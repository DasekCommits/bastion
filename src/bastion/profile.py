import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

UNLOCKS = {
    "medium": ("small", 5),
    "large": ("medium", 10),
}


def home() -> Path:
    return Path(os.environ.get("BASTION_HOME", Path.home() / ".bastion"))


@dataclass
class Profile:
    points: int = 0
    games: int = 0
    wins: dict[str, int] = field(default_factory=dict)

    def wins_on(self, tier: str) -> int:
        return self.wins.get(tier, 0)

    def is_unlocked(self, tier: str) -> bool:
        if tier not in UNLOCKS:
            return True
        needed_tier, needed = UNLOCKS[tier]
        return self.wins_on(needed_tier) >= needed

    def lock_reason(self, tier: str) -> str | None:
        if self.is_unlocked(tier):
            return None
        needed_tier, needed = UNLOCKS[tier]
        return f"win {needed} games on a {needed_tier} company first ({self.wins_on(needed_tier)}/{needed})"

    def record(self, tier: str, won: bool, points: int) -> list[str]:
        before = {t for t in UNLOCKS if self.is_unlocked(t)}
        self.games += 1
        self.points += points
        if won:
            self.wins[tier] = self.wins_on(tier) + 1
        return [t for t in UNLOCKS if self.is_unlocked(t) and t not in before]


def load_profile() -> Profile:
    path = home() / "profile.json"
    if not path.exists():
        return Profile()
    return Profile(**json.loads(path.read_text(encoding="utf-8")))


def save_profile(profile: Profile) -> None:
    folder = home()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "profile.json").write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")
