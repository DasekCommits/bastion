from bastion.engine import Campaign, has_admin_rights, person_factor, success_chance
from bastion.look import percent

MAX_TIPS = 4


def blue_tips(campaign: Campaign) -> list[str]:
    company, catalog = campaign.company, campaign.catalog
    owned = set(campaign.defense_ids)
    tips = []

    suggested = set()
    for result in campaign.results:
        if not (result.possible and result.succeeded):
            continue
        best = None
        for defense in catalog.defenses_against(result.attack.id):
            if defense.id in owned or defense.id in suggested:
                continue
            block = defense.blocks.get(result.attack.id, 0)
            if best is None or block > best[1]:
                best = (defense, block)
        if best is None:
            continue
        defense, block = best
        suggested.add(defense.id)
        if block:
            after = result.success_chance * (1 - block)
            tips.append(
                f"{defense.name} ({defense.cost}) would have cut {result.attack.name} "
                f"from {percent(result.success_chance)} to {percent(after)}."
            )
        else:
            spot = defense.detects.get(result.attack.id, 0)
            tips.append(f"{defense.name} ({defense.cost}) could have spotted {result.attack.name} ({percent(spot)} more often).")

    if "least-privilege" not in owned:
        for employee in company.employees:
            if employee.id in campaign.foothold.employees and employee.is_admin and not employee.needs_admin:
                tips.append(
                    f"{employee.name} ({employee.role}) had admin rights they do not need. "
                    f"Least privilege ({catalog.defenses['least-privilege'].cost}) would have taken them away."
                )
                break

    if not any(defense.category == "detect" for defense in campaign.defenses):
        tips.append("You had no detection (SIEM or EDR), so nobody searched the logs at night.")

    left = company.budget - campaign.budget_used
    tried = {result.attack.id for result in campaign.results}
    useful = [d for d in catalog.defenses.values() if d.id not in owned and d.cost <= left and (set(d.blocks) | set(d.detects)) & tried]
    cheapest = min(useful, key=lambda d: d.cost, default=None)
    if cheapest:
        tips.append(f"You left {left} of {company.budget} unspent. {cheapest.name} ({cheapest.cost}) still fit and counters what Red tried.")

    if not tips:
        tips.append("Your defense held. Try the same setup in Hard, or spend less and see if it still holds.")
    return tips[:MAX_TIPS]


def _best_way_in(campaign: Campaign) -> str | None:
    best = None
    for attack_id in campaign.arsenal:
        attack = campaign.catalog.attacks[attack_id]
        if attack.target != "employee":
            continue
        for employee in campaign.company.employees:
            chance = success_chance(attack, campaign.defenses) * person_factor(attack, employee)
            if best is None or chance > best[0]:
                best = (chance, attack, employee)
    if best is None:
        return None
    chance, attack, employee = best
    return f"Your best way in was {attack.name} on {employee.name} ({percent(chance)})."


def red_tips(campaign: Campaign) -> list[str]:
    catalog = campaign.catalog
    tips = []

    spotted = next((r for r in campaign.results if r.detected), None)
    if spotted:
        tips.append(
            f"You were spotted during {spotted.attack.name} with heat at {percent(spotted.heat)}. "
            "Spread noisy moves over several days: every night heat drops by 30%."
        )
    found = next((n for n in campaign.nights if n.found), None)
    if found:
        tips.append(f"The Blue Team found you on night {found.day} with heat at {percent(found.heat_before)}. Fewer moves per day keep you hidden.")

    if campaign.foothold.is_empty():
        way_in = _best_way_in(campaign)
        if way_in:
            tips.append("You never got inside. " + way_in)
    else:
        reachable = {asset.location for asset in campaign.company.data if asset.location in campaign.foothold.servers}
        untouched = reachable - set(campaign.stolen) - set(campaign.encrypted)
        if untouched:
            tips.append(f"You could reach {', '.join(sorted(untouched))}, which holds valuable data, but never stole or encrypted it.")
        admin_employees = [
            e for e in campaign.company.employees
            if e.id in campaign.foothold.employees and has_admin_rights(e, campaign.defense_ids)
        ]
        if not admin_employees and not campaign.foothold.admin_on and "ransomware" in campaign.arsenal:
            tips.append("Ransomware needs admin rights. Phish an admin, or bring Privilege escalation.")

    if "port-scan" in campaign.arsenal and "exploit-web" not in campaign.arsenal:
        tips.append("Port scan only helps Exploit the web shop. Without it, that budget was wasted.")

    tried = {result.attack.id for result in campaign.results}
    unused = [catalog.attacks[a] for a in campaign.arsenal if a not in tried]
    if unused:
        names = ", ".join(f"{a.name} ({a.cost})" for a in unused)
        tips.append(f"You paid for {names} but never used it.")

    wasted = sum(1 for r in campaign.results if not r.possible)
    if wasted:
        moves = "1 move" if wasted == 1 else f"{wasted} moves"
        verb = "was" if wasted == 1 else "were"
        tips.append(f"{moves} could not work and {verb} wasted. Get a foothold first.")

    if not tips:
        tips.append("Clean run. Try it in Hard, where you cannot see the odds.")
    return tips[:MAX_TIPS]
