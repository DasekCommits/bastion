import random

from bastion.catalog import Catalog
from bastion.company import Company
from bastion.engine import BLIND_PENALTY, NEEDS_FOOTHOLD, Campaign, clamp, night_hunt_chance, person_factor

INSIDE_ONLY = ("kerberoasting", "dcsync", "pass-the-hash")
GOOD_ENOUGH = 0.05
HOT = 0.45
NIGHT_RISK = 0.1
PLANS = 8
RED_AI_KNOWLEDGE = {"easy": "hard", "medium": "medium", "hard": "easy"}
BLUE_AI_KNOWLEDGE = {"easy": "hard", "medium": "medium", "hard": "easy"}


def pick_defenses(company: Company, catalog: Catalog, rng: random.Random) -> list[str]:
    pool = catalog.defenses_for(company.tier)
    chosen, spent = [], 0
    while pool:
        weights = [1 + len(set(d.blocks) | set(d.detects)) for d in pool]
        defense = rng.choices(pool, weights=weights)[0]
        pool.remove(defense)
        if spent + defense.cost <= company.budget:
            chosen.append(defense.id)
            spent += defense.cost
    return chosen


def plan_score(ids: list[str], catalog: Catalog) -> float:
    tactics = [catalog.attacks[a].tactic for a in ids]
    entries = sum(t in ("initial-access", "credential-access") for t in tactics)
    return (3 * ("exfiltration" in ids) + ("privilege-escalation" in tactics) + ("lateral-movement" in tactics)
            + 0.5 * min(3, entries) + 0.1 * len(ids))


def pick_arsenal(company: Company, catalog: Catalog, rng: random.Random, expert: bool = False) -> list[str]:
    if expert:
        plans = [pick_arsenal(company, catalog, rng) for _ in range(PLANS)]
        return max(plans, key=lambda ids: plan_score(ids, catalog))
    attacks = catalog.attacks_for(company.tier)
    entries = [a for a in attacks if a.tactic == "initial-access" or (a.tactic == "credential-access" and a.target == "employee")]
    payloads = [a for a in attacks if a.tactic in ("exfiltration", "impact")]
    while True:
        chosen = [rng.choice(entries).id, rng.choice(payloads).id]
        spent = sum(catalog.attacks[a].cost for a in chosen)
        if spent > company.red_budget:
            continue
        extras = [a for a in attacks if a.id not in chosen]
        rng.shuffle(extras)
        for attack in extras:
            if spent + attack.cost <= company.red_budget and rng.random() < 0.6:
                chosen.append(attack.id)
                spent += attack.cost
        return chosen


class RedAI:
    def __init__(self, knowledge: str):
        self.knowledge = knowledge

    def estimate(self, campaign: Campaign, attack_id: str, target_id: str) -> tuple[bool, float, float]:
        catalog = campaign.catalog
        attack = catalog.attacks[attack_id]
        preview = campaign.preview(attack_id, target_id)
        if self.knowledge == "easy":
            return preview.possible, preview.success_chance, preview.detect_chance
        if (attack_id, target_id) in campaign.burned:
            return False, 0, 0
        if self.knowledge == "medium":
            if not preview.possible:
                return False, 0, 0
        else:
            if (attack.tactic in NEEDS_FOOTHOLD or attack_id in INSIDE_ONLY) and campaign.foothold.is_empty():
                return False, 0, 0
            if attack.target == "server" and attack.tactic in ("reconnaissance", "initial-access"):
                if not campaign.company.server(target_id).internet_facing:
                    return False, 0, 0
            if attack.target == "employee" and attack.roles:
                if campaign.company.employee(target_id).department not in attack.roles:
                    return False, 0, 0
        chance = attack.base_success
        for defense_id in campaign.known_defenses:
            chance *= 1 - catalog.defenses[defense_id].blocks.get(attack_id, 0)
        if attack.target == "employee" and self.knowledge == "medium":
            chance *= person_factor(attack, campaign.company.employee(target_id))
        if attack.tactic == "initial-access" and attack.target == "server" and target_id not in campaign.foothold.scanned:
            chance *= BLIND_PENALTY
        detect = min(0.9, attack.noise * 0.3 + 0.1 * campaign.used.get(attack_id, 0) + 0.05 * campaign.moves_today)
        return True, chance, detect

    def value(self, campaign: Campaign, attack_id: str, target_id: str) -> float:
        possible, success, detect = self.estimate(campaign, attack_id, target_id)
        if not possible:
            return 0
        company, catalog = campaign.company, campaign.catalog
        attack = catalog.attacks[attack_id]
        inside = not campaign.foothold.is_empty()
        safe = success * (1 - detect) if inside else success * (1 - detect / 3)

        def data_on(server_id: str) -> int:
            if server_id in campaign.stolen:
                return 0
            return sum(d.value for d in company.data if d.location == server_id and not d.fraud)

        if attack_id == "bec":
            return sum(d.value for d in company.data if d.fraud) * safe
        if attack_id == "kerberoasting":
            gain = sum(data_on(s.id) for s in company.servers if s.role == "database" and s.id not in campaign.foothold.admin_on)
            return gain * safe * 0.6
        if attack_id == "dcsync":
            if campaign.foothold.admin_on >= {s.id for s in company.servers}:
                return 0
            return sum(data_on(s.id) for s in company.servers) * safe * 0.4
        if attack.tactic == "exfiltration":
            return data_on(target_id) * safe
        if attack.tactic == "impact":
            if target_id in campaign.encrypted or target_id in campaign.stolen:
                return 0
            return sum(d.value for d in company.data if d.location == target_id and not d.fraud) * safe
        if attack.target == "employee":
            if target_id in campaign.foothold.employees:
                return 0
            employee = company.employee(target_id)
            new = [s for s in employee.access if s not in campaign.foothold.servers]
            known_admin = employee.needs_admin or self.knowledge == "easy"
            gain = sum(data_on(s) for s in new) + (3 if employee.is_admin and known_admin else 0)
            return (gain + (0 if inside else 4)) * safe * 0.6
        if attack.tactic == "reconnaissance":
            if target_id in campaign.foothold.scanned:
                return 0
            return (1.5 if campaign.scan_helps() else 0.3) * safe
        if attack.tactic == "initial-access":
            if target_id in campaign.foothold.servers:
                return 0
            return (4 + data_on(target_id)) * safe * 0.6
        if attack.tactic == "privilege-escalation":
            if target_id in campaign.foothold.admin_on:
                return 0
            wants = any(catalog.attacks[a].tactic == "impact" for a in campaign.arsenal)
            return (data_on(target_id) if wants else 0) * safe * 0.5
        if attack.tactic == "lateral-movement":
            bonus = 10 if company.server(target_id).role == "domain-controller" and "dcsync" in campaign.arsenal else 0
            return (data_on(target_id) + bonus) * safe * 0.7
        return 0

    def too_loud(self, campaign: Campaign, attack_id: str, target_id: str) -> bool:
        heat = campaign.preview(attack_id, target_id).heat_after
        return clamp(night_hunt_chance(heat, campaign.defenses, campaign.edge)) > NIGHT_RISK

    def next_move(self, campaign: Campaign) -> tuple[str, str] | None:
        if campaign.moves_left_today <= 0:
            return None
        if self.knowledge == "easy" and campaign.heat > HOT:
            return None
        best = None
        night_watch = self.knowledge == "easy" and "soc" in campaign.defense_ids
        for attack_id in campaign.arsenal:
            for target_id in campaign.targets_for(attack_id):
                score = self.value(campaign, attack_id, target_id)
                if night_watch and score > 0 and self.too_loud(campaign, attack_id, target_id):
                    continue
                if best is None or score > best[0]:
                    best = (score, attack_id, target_id)
        if best is None or best[0] <= GOOD_ENOUGH:
            return None
        return best[1], best[2]


def play_out(campaign: Campaign, red: RedAI, on_move=None, on_night=None) -> Campaign:
    while not campaign.finished:
        move = red.next_move(campaign)
        if move is None:
            night = campaign.end_day()
            if night and on_night:
                on_night(night)
            continue
        result = campaign.move(*move)
        if on_move:
            on_move(result)
    return campaign


class BlueAI:
    def __init__(self, knowledge: str, rng: random.Random | None = None):
        self.knowledge = knowledge
        self.rng = rng or random.Random(0)
        self.handled: set[int] = set()
        self.checked_after = -1
        self.hunted: set[str] = set()

    def _contain(self, campaign: Campaign) -> tuple[str, str | int] | None:
        people = {e.id for e in campaign.company.employees}
        for entry in campaign.seen_logs():
            if not entry.real or entry.id in self.handled:
                continue
            if entry.succeeded and entry.attack_id not in (None, "port-scan"):
                self.handled.add(entry.id)
                return ("reset", entry.target_id) if entry.target_id in people else ("isolate", entry.target_id)
            if entry.from_outside and not entry.succeeded and entry.attack_id:
                self.handled.add(entry.id)
                return "block", entry.id
        return None

    def _pick(self, entries):
        if self.knowledge == "easy":
            return max(entries, key=lambda e: e.confidence)
        if self.knowledge == "medium":
            return max(entries, key=lambda e: e.confidence + self.rng.uniform(-0.25, 0.25))
        return self.rng.choice(entries)

    _FLOOR = {"easy": 0.55, "medium": 0.7, "hard": 0.85}

    def next_action(self, campaign: Campaign) -> tuple[str, str | int | None] | None:
        if campaign.blue_moves_left <= 0 or campaign.finished:
            return None
        contain = self._contain(campaign)
        if contain:
            return contain
        if campaign.unseen_logs():
            return "logs", None
        # a good analyst spends time only on alerts that look real, not on every false alarm
        floor = self._FLOOR[self.knowledge]
        suspicious = [e for e in campaign.seen_logs() if not e.investigated and e.confidence >= floor]
        if suspicious:
            return "investigate", self._pick(suspicious).id
        if self.knowledge != "hard":
            valuable = sorted(
                (s for s in campaign.company.servers if s.id not in self.hunted),
                key=lambda s: -sum(d.value for d in campaign.company.data if d.location == s.id),
            )
            if valuable:
                self.hunted.add(valuable[0].id)
                return "hunt", valuable[0].id
        return None


def play_out_active(campaign: Campaign, red: RedAI, blue: BlueAI, on_move=None, on_blue=None, on_night=None) -> Campaign:
    while not campaign.finished:
        move = red.next_move(campaign)
        if move is not None:
            result = campaign.move(*move)
            if on_move:
                on_move(result)
            step = blue.next_action(campaign)
            if step and not campaign.finished:
                action = campaign.blue(*step)
                if on_blue:
                    on_blue(action)
            continue
        while not campaign.finished:
            step = blue.next_action(campaign)
            if step is None:
                break
            action = campaign.blue(*step)
            if on_blue:
                on_blue(action)
        if campaign.finished:
            break
        night = campaign.end_day()
        if night and on_night:
            on_night(night)
    return campaign
