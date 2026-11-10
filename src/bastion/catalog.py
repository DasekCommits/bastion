import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

TACTICS = (
    "reconnaissance",
    "initial-access",
    "credential-access",
    "privilege-escalation",
    "lateral-movement",
    "exfiltration",
    "impact",
)
TARGETS = ("server", "employee")
TRAITS = ("awareness", "password_hygiene", "loyalty")
TIER_ORDER = ("small", "medium", "large")
CATEGORIES = ("prevent", "detect", "recover")
MITRE_ID = re.compile(r"^T\d{4}(\.\d{3})?$")


@dataclass
class Attack:
    id: str
    name: str
    mitre_id: str
    tactic: str
    target: str
    base_success: float
    noise: float
    cost: int
    description: str
    trait: str | None = None
    roles: list[str] = field(default_factory=list)
    tier: str = "small"

    @property
    def mitre_url(self) -> str:
        return "https://attack.mitre.org/techniques/" + self.mitre_id.replace(".", "/") + "/"


@dataclass
class Defense:
    id: str
    name: str
    category: str
    cost: int
    blocks: dict[str, float]
    detects: dict[str, float]
    description: str
    seen_outside: list[str] = field(default_factory=list)
    seen_inside: bool = False
    tier: str = "small"


@dataclass
class Catalog:
    attacks: dict[str, Attack]
    defenses: dict[str, Defense]

    def attacks_for(self, tier: str) -> list[Attack]:
        limit = TIER_ORDER.index(tier)
        return [a for a in self.attacks.values() if TIER_ORDER.index(a.tier) <= limit]

    def defenses_for(self, tier: str) -> list[Defense]:
        limit = TIER_ORDER.index(tier)
        return [d for d in self.defenses.values() if TIER_ORDER.index(d.tier) <= limit]

    def attacks_in_tactic(self, tactic: str) -> list[Attack]:
        return [attack for attack in self.attacks.values() if attack.tactic == tactic]

    def defenses_against(self, attack_id: str) -> list[Defense]:
        return [
            defense
            for defense in self.defenses.values()
            if attack_id in defense.blocks or attack_id in defense.detects
        ]


class CatalogError(ValueError):
    pass


def _is_chance(value: float) -> bool:
    return isinstance(value, (int, float)) and 0 <= value <= 1


def validate(catalog: Catalog) -> None:
    for attack in catalog.attacks.values():
        if not MITRE_ID.match(attack.mitre_id):
            raise CatalogError(f"Attack '{attack.id}' has an invalid MITRE ID '{attack.mitre_id}'")
        if attack.tactic not in TACTICS:
            raise CatalogError(f"Attack '{attack.id}' has an unknown tactic '{attack.tactic}'")
        if attack.target not in TARGETS:
            raise CatalogError(f"Attack '{attack.id}' has an unknown target '{attack.target}'")
        if not _is_chance(attack.base_success) or not _is_chance(attack.noise):
            raise CatalogError(f"Attack '{attack.id}' needs base_success and noise from 0 to 1")
        if attack.cost <= 0:
            raise CatalogError(f"Attack '{attack.id}' must cost more than 0")
        if attack.trait is not None and attack.trait not in TRAITS:
            raise CatalogError(f"Attack '{attack.id}' has an unknown trait '{attack.trait}'")
        if attack.tier not in TIER_ORDER:
            raise CatalogError(f"Attack '{attack.id}' has an unknown tier '{attack.tier}'")

    for defense in catalog.defenses.values():
        if defense.category not in CATEGORIES:
            raise CatalogError(f"Defense '{defense.id}' has an unknown category '{defense.category}'")
        if defense.cost <= 0:
            raise CatalogError(f"Defense '{defense.id}' must cost more than 0")
        if defense.tier not in TIER_ORDER:
            raise CatalogError(f"Defense '{defense.id}' has an unknown tier '{defense.tier}'")
        for effect in (defense.blocks, defense.detects):
            for attack_id, chance in effect.items():
                if attack_id not in catalog.attacks:
                    raise CatalogError(f"Defense '{defense.id}' refers to unknown attack '{attack_id}'")
                if not _is_chance(chance):
                    raise CatalogError(f"Defense '{defense.id}' has a chance outside 0 to 1")


def _load_unique(path: Path, cls):
    items = {}
    for raw in json.loads(path.read_text(encoding="utf-8")):
        item = cls(**raw)
        if item.id in items:
            raise CatalogError(f"Duplicate id '{item.id}' in {path.name}")
        items[item.id] = item
    return items


def load_catalog(data_dir: Path = DATA_DIR) -> Catalog:
    catalog = Catalog(
        attacks=_load_unique(Path(data_dir) / "attacks.json", Attack),
        defenses=_load_unique(Path(data_dir) / "defenses.json", Defense),
    )
    validate(catalog)
    return catalog
