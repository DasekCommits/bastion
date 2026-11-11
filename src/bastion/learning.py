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


# mirrors engine._is_possible / NEEDS_FOOTHOLD: what a technique needs before it works,
# what it gives you, and whether it is only intel rather than a step forward.
def prereq(attack) -> dict:
    tactic, aid = attack.tactic, attack.id
    if aid == "bec":
        return {"needs": "nothing technical — it is pure social engineering",
                "gives": "a fraudulent payment, if finance does not call back to check", "intel_only": False}
    if aid == "dcsync":
        return {"needs": "administrator rights on the domain controller",
                "gives": "every account's password hash — the keys to the whole domain", "intel_only": False}
    if aid == "pass-the-hash":
        return {"needs": "admin rights somewhere already, plus an internal target",
                "gives": "access to another machine without ever knowing the password", "intel_only": False}
    if aid == "kerberoasting":
        return {"needs": "any logged-in account inside the network",
                "gives": "a service account's password to crack offline", "intel_only": False}
    table = {
        "reconnaissance": ("a server reachable from the internet", "a map of what is exposed — intel only, not a break-in", True),
        "initial-access": ("a reachable server or a person to trick", "your first foothold inside the company", False),
        "credential-access": ("a foothold inside the network", "more credentials and wider reach", False),
        "privilege-escalation": ("a foothold on that same machine", "administrator rights on it", False),
        "lateral-movement": ("a stolen account that can log in there", "a foothold on another machine", False),
        "exfiltration": ("access to the machine holding the data", "the data out of the company — often the goal", False),
        "impact": ("administrator rights on the target", "damage: files encrypted or wiped", False),
    }
    needs, gives, intel = table.get(tactic, ("a foothold first", "progress in the attack", False))
    return {"needs": needs, "gives": gives, "intel_only": intel}


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

    needs = prereq(a)
    return {
        "id": attack_id,
        "name": a.name,
        "mitre": a.mitre_id,
        "tactic": TACTIC_HUMAN.get(a.tactic, a.tactic),
        "needs": needs["needs"],
        "gives": needs["gives"],
        "intel_only": needs["intel_only"],
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


# "Combinations" exercises: order techniques into a working attack. The order is
# validated the way the engine would, by tracking a tiny foothold/admin state and
# refusing a step whose prerequisite is not met yet.
CHAINS = [
    {"id": "smash-grab",
     "goal": "Break into an internet-facing web shop and steal its data — no insider, no email.",
     "steps": ["port-scan", "exploit-web", "exfiltration"]},
    {"id": "phish-to-ransom",
     "goal": "Start from a person and end by ransoming the machine you land on.",
     "steps": ["phishing", "privilege-escalation", "ransomware"]},
    {"id": "deep-domain",
     "goal": "Phish your way in, spread across the network, and empty the domain's secrets.",
     "steps": ["phishing", "remote-desktop", "privilege-escalation", "dcsync"]},
]
CHAINS_BY_ID = {c["id"]: c for c in CHAINS}


def _stage_step(aid, catalog, state):
    """Apply one technique to a tiny attack state; return (ok, reason) using engine-like rules."""
    a = catalog.attacks[aid]
    tactic = a.tactic
    if aid == "bec":
        return True, ""
    if tactic in ("reconnaissance",):
        return True, ""  # intel, always allowed, never required
    if tactic == "initial-access":
        state["foothold"] = True
        return True, ""
    if not state["foothold"] and (tactic in ("privilege-escalation", "lateral-movement", "exfiltration", "impact")
                                  or aid in ("kerberoasting", "dcsync", "pass-the-hash")):
        return False, "The attacker has no way into the company yet — you need a foothold first."
    if tactic == "privilege-escalation":
        state["admin"] = True
        return True, ""
    if tactic == "lateral-movement":
        state["foothold"] = True
        return True, ""
    if aid == "dcsync" and not state["admin"]:
        return False, "DCSync needs administrator rights on the domain controller — escalate first."
    if aid == "pass-the-hash" and not state["admin"]:
        return False, "Pass-the-Hash needs admin rights somewhere first, to dump hashes from memory."
    if tactic == "impact" and not state["admin"]:
        return False, "Encrypting a machine needs administrator rights on it — escalate first."
    return True, ""


def chains_summary(learned: list[str]) -> dict:
    done = set(learned or [])
    rows = [{"id": c["id"], "goal": c["goal"], "steps": len(c["steps"]),
             "done": ("chain:" + c["id"]) in done} for c in CHAINS]
    return {"total": len(CHAINS), "done": len([r for r in rows if r["done"]]), "chains": rows}


def chain(catalog, chain_id: str, learned: list[str]) -> dict:
    c = CHAINS_BY_ID[chain_id]
    rng = random.Random("chain:" + chain_id)
    cards = [{"id": aid, "name": catalog.attacks[aid].name,
              "mitre": catalog.attacks[aid].mitre_id,
              "tactic": TACTIC_HUMAN.get(catalog.attacks[aid].tactic, catalog.attacks[aid].tactic)}
             for aid in c["steps"]]
    rng.shuffle(cards)
    return {"id": chain_id, "goal": c["goal"], "cards": cards, "length": len(c["steps"]),
            "done": ("chain:" + chain_id) in set(learned or [])}


def check_chain(catalog, chain_id: str, submitted: list[str]) -> dict:
    c = CHAINS_BY_ID[chain_id]
    state = {"foothold": False, "admin": False}
    steps = []
    passed = True
    for aid in submitted:
        if aid not in c["steps"]:
            continue
        ok, reason = _stage_step(aid, catalog, state)
        steps.append({"id": aid, "name": catalog.attacks[aid].name, "ok": ok, "reason": reason})
        if not ok:
            passed = False
            break
    if passed and len(steps) < len(c["steps"]):
        passed = False
    return {"passed": passed, "steps": steps,
            "note": ("That chain works — each step sets up the next." if passed
                     else "That order does not work yet. Follow the reason and try again.")}
