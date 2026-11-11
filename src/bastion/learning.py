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
        return {"needs": "nothing technical: it is pure social engineering",
                "gives": "a fraudulent payment, if finance does not call back to check", "intel_only": False}
    if aid == "dcsync":
        return {"needs": "administrator rights on the domain controller",
                "gives": "every account's password hash, the keys to the whole domain", "intel_only": False}
    if aid == "pass-the-hash":
        return {"needs": "admin rights somewhere already, plus an internal target",
                "gives": "access to another machine without ever knowing the password", "intel_only": False}
    if aid == "kerberoasting":
        return {"needs": "any logged-in account inside the network",
                "gives": "a service account's password to crack offline", "intel_only": False}
    table = {
        "reconnaissance": ("a server reachable from the internet", "a map of what is exposed. Intel only, not a break-in", True),
        "initial-access": ("a reachable server or a person to trick", "your first foothold inside the company", False),
        "credential-access": ("a foothold inside the network", "more credentials and wider reach", False),
        "privilege-escalation": ("a foothold on that same machine", "administrator rights on it", False),
        "lateral-movement": ("a stolen account that can log in there", "a foothold on another machine", False),
        "exfiltration": ("access to the machine holding the data", "the data out of the company, often the goal", False),
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

    # second attacker step: what this technique needs before it can work
    needs = prereq(a)
    other_needs = {}
    for x in catalog.attacks.values():
        text = prereq(x)["needs"]
        if text != needs["needs"] and text not in other_needs.values():
            other_needs[x.id] = text
    picks = rng.sample(sorted(other_needs), min(3, len(other_needs)))
    need_options = [{"id": attack_id, "label": needs["needs"]}] + [{"id": i, "label": other_needs[i]} for i in picks]
    rng.shuffle(need_options)

    return {
        "kind": "red",
        "id": attack_id,
        "name": a.name,
        "eyebrow": f"{a.mitre_id} · {TACTIC_HUMAN.get(a.tactic, a.tactic)}",
        "needs": needs["needs"],
        "gives": needs["gives"],
        "intel_only": needs["intel_only"],
        "teach": f"{a.description} In MITRE ATT&CK this is {a.name} ({a.mitre_id}), a {TACTIC_HUMAN.get(a.tactic, a.tactic)} technique.",
        "step1": {"title": "1 · Spot it", "prompt": f"An attacker wants to: {a.description.rstrip('.').lower()}. Which technique is that?",
                  "options": atk_options},
        "step2": {"title": "2 · Plan it", "prompt": f"You want to use {a.name}. What must you already have?",
                  "options": need_options},
        "done": attack_id in set(learned or []),
    }


def check(catalog, attack_id: str, attack_choice: str, need_choice: str) -> dict:
    a = catalog.attacks[attack_id]
    attack_ok = attack_choice == attack_id
    needs = prereq(a)
    need_ok = need_choice in catalog.attacks and prereq(catalog.attacks[need_choice])["needs"] == needs["needs"]
    defense, prob, mode = _best_defense(catalog, a)
    counter = (f" Defenders answer it with {defense.name}, which {mode} it about {int(round(prob * 100))}% of the time."
               if defense else "")
    return {
        "ok1": attack_ok,
        "ok2": need_ok,
        "passed": attack_ok and need_ok,
        "note1": (f"Right, that is {a.name} ({a.mitre_id})."
                  if attack_ok else f"Not quite. That was {a.name} ({a.mitre_id}): {a.description}"),
        "note2": (f"Right. {a.name} needs {needs['needs']}, and gives you {needs['gives']}." if need_ok
                  else f"Not that. {a.name} needs {needs['needs']}. It gives you {needs['gives']}.") + counter,
    }


# "Combinations" exercises: order techniques into a working attack. The order is
# validated the way the engine would, by tracking a tiny foothold/admin state and
# refusing a step whose prerequisite is not met yet.
CHAINS = [
    {"id": "smash-grab", "goal": "Break into an internet-facing web shop and steal its data, with no insider and no email.",
     "steps": ["port-scan", "exploit-web", "exfiltration"]},
    {"id": "phish-to-ransom", "goal": "Start from a person and end by ransoming the machine you land on.",
     "steps": ["phishing", "privilege-escalation", "ransomware"]},
    {"id": "deep-domain", "goal": "Phish your way in, spread across the network, and empty the domain's secrets.",
     "steps": ["phishing", "remote-desktop", "privilege-escalation", "dcsync"]},
    {"id": "password-reuse", "goal": "Log in with a password leaked from another site, hop to the file server and take the files.",
     "steps": ["credential-stuffing", "remote-desktop", "exfiltration"]},
    {"id": "vpn-wiper", "goal": "Find the VPN gateway, break through it, and wipe a server for good.",
     "steps": ["port-scan", "vpn-exploit", "privilege-escalation", "destruction"]},
    {"id": "macro-leak", "goal": "Get an employee to open a booby-trapped document and leak the data it can reach.",
     "steps": ["macro", "privilege-escalation", "exfiltration"]},
    {"id": "parking-lot", "goal": "Leave an infected USB stick in the car park and turn it into a ransom note.",
     "steps": ["usb-drop", "privilege-escalation", "ransomware"]},
    {"id": "bought-insider", "goal": "Pay someone inside to let you in, then walk out with the data.",
     "steps": ["insider", "remote-desktop", "exfiltration"]},
    {"id": "spray", "goal": "Try one common password against everyone, move sideways, and steal.",
     "steps": ["password-spray", "remote-desktop", "exfiltration"]},
    {"id": "push-bombing", "goal": "Guess a password, then spam MFA prompts until someone taps Approve, and take the data.",
     "steps": ["brute-force", "mfa-fatigue", "exfiltration"]},
    {"id": "cloud-first", "goal": "Take over a cloud account and use it to pull company data.",
     "steps": ["cloud-takeover", "exfiltration"]},
    {"id": "supply-chain", "goal": "Come in through a trusted IT vendor, become admin, reuse hashes, and steal.",
     "steps": ["vendor-breach", "privilege-escalation", "pass-the-hash", "exfiltration"]},
    {"id": "roast", "goal": "Phish any employee, roast a service account's ticket, and use it to reach the data.",
     "steps": ["phishing", "kerberoasting", "remote-desktop", "exfiltration"]},
    {"id": "invoice-fraud", "goal": "Read a finance mailbox, then send a convincing fake invoice.",
     "steps": ["phishing", "bec"]},
    {"id": "brute-door", "goal": "Scan, guess your way in, become admin, and encrypt the server.",
     "steps": ["port-scan", "brute-force", "privilege-escalation", "ransomware"]},
    {"id": "the-big-one", "goal": "Own everything: VPN in, admin, reuse hashes, steal the domain, and ransom it.",
     "steps": ["port-scan", "vpn-exploit", "privilege-escalation", "pass-the-hash", "dcsync", "ransomware"]},
]
CHAINS_BY_ID = {c["id"]: c for c in CHAINS}


def _stage_step(aid, catalog, state):
    """Apply one technique to a tiny attack state; return (ok, reason) using engine-like rules."""
    a = attack = catalog.attacks[aid]
    tactic = a.tactic
    if aid == "bec":
        return True, ""
    if tactic in ("reconnaissance",):
        return True, ""  # intel, always allowed, never required
    if tactic == "initial-access" or (tactic == "credential-access" and attack.target == "employee"):
        state["foothold"] = True
        return True, ""
    if not state["foothold"] and (tactic in ("privilege-escalation", "lateral-movement", "exfiltration", "impact")
                                  or aid in ("kerberoasting", "dcsync", "pass-the-hash")):
        return False, "The attacker has no way into the company yet. You need a foothold first."
    if tactic == "privilege-escalation":
        state["admin"] = True
        return True, ""
    if tactic == "lateral-movement":
        state["foothold"] = True
        return True, ""
    if aid == "dcsync" and not state["admin"]:
        return False, "DCSync needs administrator rights on the domain controller. Escalate first."
    if aid == "pass-the-hash" and not state["admin"]:
        return False, "Pass-the-Hash needs admin rights somewhere first, to dump hashes from memory."
    if tactic == "impact" and not state["admin"]:
        return False, "Encrypting a machine needs administrator rights on it. Escalate first."
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
            "note": ("That chain works: each step sets up the next." if passed
                     else "That order does not work yet. Follow the reason and try again.")}


# ---------------------------------------------------------------- Blue side

def _defense_order(catalog) -> list[str]:
    rank = {"prevent": 0, "detect": 1, "recover": 2}
    tiers = {"small": 0, "medium": 1, "large": 2, "huge": 3}
    return [d.id for d in sorted(catalog.defenses.values(), key=lambda d: (tiers.get(d.tier, 9), rank.get(d.category, 9), d.name))]


def _best_attack(catalog, defense):
    rows = [(catalog.attacks[a], max(defense.blocks.get(a, 0), defense.detects.get(a, 0)))
            for a in set(defense.blocks) | set(defense.detects) if a in catalog.attacks]
    return max(rows, key=lambda r: (r[1], r[0].name))[0] if rows else None


MODES = [
    {"id": "stops", "label": "It stops the attack (prevent)"},
    {"id": "spots", "label": "It spots the attack so someone can react (detect)"},
    {"id": "both", "label": "Both: it stops some and spots the rest"},
    {"id": "recovers", "label": "Neither: it helps you recover afterwards"},
]


def _mode(defense, attack_id: str) -> str:
    if defense.category == "recover":
        return "recovers"
    blocks, spots = defense.blocks.get(attack_id, 0) > 0, defense.detects.get(attack_id, 0) > 0
    return "both" if blocks and spots else "stops" if blocks else "spots"


def _handles(catalog, defense) -> str:
    parts = []
    for aid in sorted(set(defense.blocks) | set(defense.detects), key=lambda a: -max(defense.blocks.get(a, 0), defense.detects.get(a, 0))):
        if aid not in catalog.attacks:
            continue
        bits = []
        if defense.blocks.get(aid):
            bits.append(f"stops {round(defense.blocks[aid] * 100)}%")
        if defense.detects.get(aid):
            bits.append(f"spots {round(defense.detects[aid] * 100)}%")
        parts.append(f"{catalog.attacks[aid].name} ({', '.join(bits)})")
    return "; ".join(parts)


def blue_summary(catalog, learned: list[str]) -> dict:
    done = set(learned or [])
    rows = []
    for did in _defense_order(catalog):
        d = catalog.defenses[did]
        rows.append({"id": did, "name": d.name, "sub": f"{d.category} · costs {d.cost}", "done": ("blue:" + did) in done})
    return {"total": len(rows), "done": sum(r["done"] for r in rows), "lessons": rows}


def blue_lesson(catalog, defense_id: str, learned: list[str]) -> dict:
    d = catalog.defenses[defense_id]
    rng = random.Random("blue:" + defense_id)
    best = _best_attack(catalog, d)
    untouched = [a for a in catalog.attacks.values() if a.id not in d.blocks and a.id not in d.detects]
    options = [best, *rng.sample(untouched, min(3, len(untouched)))]
    attack_options = [{"id": a.id, "label": f"{a.name} ({a.mitre_id})"} for a in options]
    rng.shuffle(attack_options)
    return {
        "kind": "blue",
        "id": defense_id,
        "name": d.name,
        "eyebrow": f"{d.category} control · costs {d.cost}",
        "needs": None, "gives": None, "intel_only": False,
        "teach": f"{d.description} In the game it handles: {_handles(catalog, d)}.",
        "step1": {"title": "1 · What is it for?", "prompt": f"Which attack does {d.name} handle best?", "options": attack_options},
        "step2": {"title": "2 · How does it help?", "prompt": f"Against {best.name}, what does {d.name} do?", "options": MODES},
        "done": ("blue:" + defense_id) in set(learned or []),
    }


def blue_check(catalog, defense_id: str, attack_choice: str, mode_choice: str) -> dict:
    d = catalog.defenses[defense_id]
    best = _best_attack(catalog, d)
    ok1 = attack_choice == best.id
    mode = _mode(d, best.id)
    ok2 = mode_choice == mode
    explain = {
        "stops": f"{d.name} prevents {best.name} outright about {round(d.blocks.get(best.id, 0) * 100)}% of the time.",
        "spots": f"{d.name} does not stop {best.name}; it writes it down so an analyst can catch it ({round(d.detects.get(best.id, 0) * 100)}%). A tool nobody watches catches nobody.",
        "both": f"{d.name} stops {best.name} {round(d.blocks.get(best.id, 0) * 100)}% of the time and spots it {round(d.detects.get(best.id, 0) * 100)}% of the time.",
        "recovers": f"{d.name} does not stop or spot anything: after {best.name} you restore and the damage is undone.",
    }[mode]
    return {
        "ok1": ok1, "ok2": ok2, "passed": ok1 and ok2,
        "note1": f"Right, {d.name} is aimed at {best.name}." if ok1 else f"Not that one. {d.name} is aimed at {best.name}: {best.description}",
        "note2": ("Right. " if ok2 else "Not quite. ") + explain,
    }


# Blue combinations: stop a given attack chain with a budget. Defense in depth means
# at least one step is blocked AND at least one step is spotted, on two different steps.
def _coverage(catalog, steps, picked):
    rows = []
    for aid in steps:
        blocks = [(catalog.defenses[d].name, catalog.defenses[d].blocks[aid]) for d in picked if catalog.defenses[d].blocks.get(aid)]
        spots = [(catalog.defenses[d].name, catalog.defenses[d].detects[aid]) for d in picked if catalog.defenses[d].detects.get(aid)]
        rows.append({"id": aid, "name": catalog.attacks[aid].name,
                     "blocked": [f"{n} {round(p * 100)}%" for n, p in blocks],
                     "spotted": [f"{n} {round(p * 100)}%" for n, p in spots]})
    return rows


def _guard_ok(rows) -> bool:
    blocked = {i for i, r in enumerate(rows) if r["blocked"]}
    spotted = {i for i, r in enumerate(rows) if r["spotted"]}
    return bool(blocked) and bool(spotted) and len(blocked | spotted) >= 2


def _relevant(catalog, steps):
    return [d.id for d in catalog.defenses.values() if any(d.blocks.get(a) or d.detects.get(a) for a in steps)]


def _guard_budget(catalog, chain) -> int:
    from itertools import combinations
    pool = _relevant(catalog, chain["steps"])
    best = None
    for size in (1, 2, 3):
        for combo in combinations(pool, size):
            if _guard_ok(_coverage(catalog, chain["steps"], combo)):
                cost = sum(catalog.defenses[d].cost for d in combo)
                best = cost if best is None else min(best, cost)
    return int(-(-best * 1.3 // 5) * 5)


def guards_summary(catalog, learned: list[str]) -> dict:
    done = set(learned or [])
    rows = [{"id": c["id"], "goal": c["goal"], "steps": len(c["steps"]), "done": ("guard:" + c["id"]) in done} for c in CHAINS]
    return {"total": len(rows), "done": sum(r["done"] for r in rows), "guards": rows}


def guard(catalog, chain_id: str, learned: list[str]) -> dict:
    c = CHAINS_BY_ID[chain_id]
    rng = random.Random("guard:" + chain_id)
    relevant = _relevant(catalog, c["steps"])
    decoys = [d for d in catalog.defenses if d not in relevant]
    pool = relevant + rng.sample(decoys, min(3, len(decoys)))
    rng.shuffle(pool)
    return {
        "id": chain_id,
        "goal": c["goal"],
        "steps": [{"id": a, "name": catalog.attacks[a].name, "mitre": catalog.attacks[a].mitre_id} for a in c["steps"]],
        "budget": _guard_budget(catalog, c),
        "options": [{"id": d, "name": catalog.defenses[d].name, "cost": catalog.defenses[d].cost,
                     "category": catalog.defenses[d].category} for d in pool],
        "done": ("guard:" + chain_id) in set(learned or []),
    }


def check_guard(catalog, chain_id: str, picked: list[str]) -> dict:
    c = CHAINS_BY_ID[chain_id]
    picked = [d for d in dict.fromkeys(picked) if d in catalog.defenses]
    budget = _guard_budget(catalog, c)
    cost = sum(catalog.defenses[d].cost for d in picked)
    rows = _coverage(catalog, c["steps"], picked)
    blocked = any(r["blocked"] for r in rows)
    spotted = any(r["spotted"] for r in rows)
    if cost > budget:
        note = f"That costs {cost}, but you only have {budget}. Pick fewer, cheaper controls."
    elif not blocked:
        note = "Nothing here stops a single step. Add a control that prevents one of them."
    elif not spotted:
        note = "You can stop a step, but if it slips through nobody will notice. Add something that spots a step."
    elif not _guard_ok(rows):
        note = "Everything hangs on one step. Cover a second step too, so one miss does not lose the company."
    else:
        note = "Defense in depth: one step is stopped and another is watched, within budget."
    return {"passed": cost <= budget and _guard_ok(rows), "cost": cost, "budget": budget, "rows": rows, "note": note}
