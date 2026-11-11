"""The Learning mode curriculum, generated from the real attack and defense catalog.

Each technique in the catalog becomes one lesson. A lesson has two steps that mirror
the game itself: first the attacker's view (recognise the technique from what it does),
then the defender's view (pick the control that best stops or spots it). Because the
lessons are built from the catalog, they stay true to the game's own mechanics and
never drift out of sync with it.
"""
import random

# the order a real intrusion tends to move through, so lessons flow like a kill chain
TACTIC_ORDER = [
    "reconnaissance", "initial-access", "credential-access",
    "privilege-escalation", "lateral-movement", "exfiltration", "impact",
]
TACTIC_HUMAN = {
    "reconnaissance": "reconnaissance",
    "initial-access": "initial-access",
    "credential-access": "credential-access",
    "privilege-escalation": "privilege-escalation",
    "lateral-movement": "lateral-movement",
    "exfiltration": "exfiltration",
    "impact": "impact",
}


def order(catalog) -> list[str]:
    """Technique ids in teaching order."""
    def rank(attack):
        tactic = TACTIC_ORDER.index(attack.tactic) if attack.tactic in TACTIC_ORDER else len(TACTIC_ORDER)
        return (tactic, attack.name)
    return [a.id for a in sorted(catalog.attacks.values(), key=rank)]


def _best_defense(catalog, attack):
    """The single control that best handles this attack: strongest block, else strongest detect."""
    blockers = [(d, d.blocks.get(attack.id, 0), "blocks") for d in catalog.defenses.values() if d.blocks.get(attack.id, 0) > 0]
    detectors = [(d, d.detects.get(attack.id, 0), "spots") for d in catalog.defenses.values() if d.detects.get(attack.id, 0) > 0]
    pool = blockers or detectors
    return max(pool, key=lambda row: row[1]) if pool else (None, 0, "")


def summary(catalog, learned: list[str]) -> dict:
    ids = order(catalog)
    done = set(learned or [])
    lessons = []
    for aid in ids:
        a = catalog.attacks[aid]
        lessons.append({"id": aid, "name": a.name, "mitre": a.mitre_id,
                        "tactic": TACTIC_HUMAN.get(a.tactic, a.tactic), "done": aid in done})
    return {"total": len(ids), "done": len([a for a in ids if a in done]), "lessons": lessons}


def lesson(catalog, attack_id: str, learned: list[str]) -> dict:
    a = catalog.attacks[attack_id]
    rng = random.Random("learn:" + attack_id)
    defense, prob, mode = _best_defense(catalog, a)

    # attacker step: recognise this technique from what it does, among techniques from other tactics
    others = [x for x in catalog.attacks.values() if x.tactic != a.tactic and x.id != a.id]
    atk_decoys = rng.sample(others, min(3, len(others)))
    atk_options = [{"id": x.id, "label": f"{x.name} ({x.mitre_id})"} for x in [a, *atk_decoys]]
    rng.shuffle(atk_options)

    # defender step: the best control, among controls that do nothing against this attack
    useless = [d for d in catalog.defenses.values() if d.blocks.get(attack_id, 0) == 0 and d.detects.get(attack_id, 0) == 0]
    def_decoys = rng.sample(useless, min(3, len(useless)))
    def_pool = [defense, *def_decoys] if defense else def_decoys
    def_options = [{"id": d.id, "label": d.name} for d in def_pool]
    rng.shuffle(def_options)

    return {
        "id": attack_id,
        "name": a.name,
        "mitre": a.mitre_id,
        "tactic": TACTIC_HUMAN.get(a.tactic, a.tactic),
        "teach": f"{a.description} In MITRE ATT&CK this is {a.name} ({a.mitre_id}), a {TACTIC_HUMAN.get(a.tactic, a.tactic)} technique.",
        "attack_prompt": f"An attacker wants to: {a.description.rstrip('.').lower()}. Which technique is that?",
        "attack_options": atk_options,
        "defense_prompt": f"Now you are defending. Which control best handles {a.name}?",
        "defense_options": def_options,
        "done": attack_id in set(learned or []),
    }


def check(catalog, attack_id: str, attack_choice: str, defense_choice: str) -> dict:
    a = catalog.attacks[attack_id]
    defense, prob, mode = _best_defense(catalog, a)
    attack_ok = attack_choice == attack_id
    defense_ok = defense is not None and defense_choice == defense.id
    pct = int(round(prob * 100))
    defense_note = (
        f"{defense.name} is the strongest answer: it {mode} {a.name} about {pct}% of the time. {defense.description}"
        if defense else f"{a.name} has no single control that stops it outright — depth and detection matter."
    )
    chosen = catalog.defenses.get(defense_choice)
    if not defense_ok and chosen is not None:
        defense_note = f"{chosen.name} does little against {a.name}. " + defense_note
    return {
        "attack_ok": attack_ok,
        "defense_ok": defense_ok,
        "passed": attack_ok and defense_ok,
        "attack_note": (
            f"Right — that is {a.name} ({a.mitre_id})."
            if attack_ok else f"Not quite. That was {a.name} ({a.mitre_id}): {a.description}"
        ),
        "defense_note": defense_note,
    }
