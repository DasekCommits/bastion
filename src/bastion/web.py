import json
import random

from bastion import advice, ai, scoring
from bastion.catalog import load_catalog, load_edge
from bastion.company import list_scenarios, load_scenario, roll_mistakes
from bastion.engine import Campaign, PlanError
from bastion.profile import Profile
from bastion.report import format_report, percent

SUSPENSE = {
    "reconnaissance": ["Scanning {who} for open ports"],
    "initial-access": ["Sending the exploit to {who}", "Waiting for a shell"],
    "credential-access": ["Trying passwords against {who}", "Waiting for a login to work"],
    "privilege-escalation": ["Running a local exploit on {who}", "Trying to become administrator"],
    "lateral-movement": ["Logging in to {who} with a stolen account"],
    "exfiltration": ["Copying data out of {who}", "Sending it to your server"],
    "impact": ["Hitting {who}", "Waiting for the damage to spread"],
}


RED_NOTICES = {
    "reset": "{target}'s password was changed. You lost that account.",
    "isolate": "{target} was cut off from the network. You cannot reach it.",
    "block": "Your attempt was blocked. That exact trick will not work again.",
    "hunt": "Someone is digging through {target}. They know you are there.",
}


def trait_word(value: float) -> str:
    if value >= 0.6:
        return "good"
    if value >= 0.3:
        return "okay"
    return "poor"


class Session:
    def __init__(self, profile_json: str = ""):
        self.catalog = load_catalog()
        self.profile = Profile(**json.loads(profile_json)) if profile_json else Profile()
        self.campaign: Campaign | None = None
        self.events: list[dict] = []

    def menu(self) -> str:
        scenarios = list_scenarios()
        companies = [
            {"id": c.id, "name": c.name, "tier": c.tier, "people": len(c.employees), "description": c.description}
            for c in scenarios
        ]
        locks = {
            level: {c.id: self.profile.lock_reason(c.tier, level) for c in scenarios}
            for level in ("easy", "medium", "hard")
        }
        levels = {
            level: None if self.profile.level_open(level) else self.profile.lock_reason("small", level)
            for level in ("easy", "medium", "hard")
        }
        return json.dumps({"companies": companies, "locks": locks, "levels": levels, "profile": self._profile(),
                           "goal": self.profile.next_goal(), "cleared": self.profile.cleared()})

    def _profile(self) -> dict:
        return {"points": self.profile.points, "games": self.profile.games, "wins": self.profile.wins}

    def start(self, company_id: str, level: str, side: str, seed: int | None = None) -> str:
        self.rng = random.Random(seed)
        self.level = level
        self.easy = level == "easy"
        self.explain = level in ("easy", "medium")
        self.random_side = side == "random"
        self.side = self.rng.choice(("blue", "red")) if self.random_side else side
        self.company = roll_mistakes(load_scenario(company_id), self.rng)
        self.defense_ids: list[str] = []
        self.arsenal: list[str] = []
        self.campaign = None
        self.events = []
        self.gave_up = False
        return json.dumps({"side": self.side, "random_side": self.random_side, "company": self._company()})

    def _company(self) -> dict:
        company = self.company
        people = []
        for e in company.employees:
            if self.easy or e.needs_admin:
                admin = "yes" if e.is_admin else "no"
            else:
                admin = "?"
            person = {"id": e.id, "name": e.name, "role": e.role, "admin": admin, "access": e.access}
            if self.explain:
                person.update(phishing=trait_word(e.awareness), passwords=trait_word(e.password_hygiene))
                if company.tier != "small":
                    person["loyalty"] = trait_word(e.loyalty)
            people.append(person)
        return {
            "id": company.id, "name": company.name, "tier": company.tier, "description": company.description,
            "budget": company.budget, "budget_range": company.budget_range,
            "red_budget": company.red_budget, "red_budget_range": company.red_budget_range,
            "max_days": company.max_days, "moves_per_day": company.moves_per_day,
            "servers": [
                {"id": s.id, "name": s.name, "exposed": s.internet_facing, "software": s.software}
                for s in company.servers
            ],
            "people": people,
            "data": [{"name": d.name, "where": d.location, "value": d.value} for d in company.data] if self.explain else [],
            "hidden_admins": not self.easy,
        }

    def defense_options(self) -> str:
        options = []
        for d in self.catalog.defenses_for(self.company.tier):
            item = {"id": d.id, "name": d.name, "cost": d.cost}
            if self.explain:
                countered = sorted(set(d.blocks) | set(d.detects))
                names = ", ".join(self.catalog.attacks[a].name for a in countered)
                item.update(category=d.category, description=f"{d.description} Counters: {names or 'nothing directly'}.")
            options.append(item)
        return json.dumps(options)

    def attack_options(self) -> str:
        options = []
        for a in self.catalog.attacks_for(self.company.tier):
            item = {"id": a.id, "name": a.name, "cost": a.cost}
            if self.explain:
                description = f"{a.description} Targets: {a.target}s."
                if self.easy:
                    description += f" Noise: {percent(a.noise)}."
                item.update(mitre=a.mitre_id, tactic=a.tactic, description=description)
            options.append(item)
        return json.dumps(options)

    def set_defenses(self, ids_json: str) -> str:
        ids = json.loads(ids_json)
        cost = sum(self.catalog.defenses[i].cost for i in ids)
        if cost > self.company.budget:
            return json.dumps({"ok": False, "error": f"That costs {cost}, but the budget is {self.company.budget}."})
        self.defense_ids = ids
        return json.dumps({"ok": True})

    def set_arsenal(self, ids_json: str) -> str:
        ids = json.loads(ids_json)
        cost = sum(self.catalog.attacks[i].cost for i in ids)
        if not ids:
            return json.dumps({"ok": False, "error": "Buy at least one attack."})
        if cost > self.company.red_budget:
            return json.dumps({"ok": False, "error": f"That costs {cost}, but the budget is {self.company.red_budget}."})
        self.arsenal = ids
        return json.dumps({"ok": True})

    def begin(self) -> str:
        if self.side == "red":
            self.defense_ids = ai.pick_defenses(self.company, self.catalog, self.rng)
        if self.side == "blue":
            self.arsenal = ai.pick_arsenal(self.company, self.catalog, self.rng)
        edge = load_edge(self.company.tier, self.level, "blue" if self.side == "blue" else "red")
        self.campaign = Campaign(self.company, self.catalog, self.defense_ids, self.arsenal, rng=self.rng, edge=edge,
                                 active_blue=True)
        self.blue_ai = ai.BlueAI(ai.BLUE_AI_KNOWLEDGE[self.level], self.rng)
        if self.side == "blue":
            self.red_ai = ai.RedAI(ai.RED_AI_KNOWLEDGE[self.level])
            self.events: list[dict] = []
            self.verdicts: dict[int, str] = {}
            self.phase = "start"
            self._advance()
            return self.blue_state()
        return self.turn()

    def _advance(self) -> None:
        c = self.campaign
        while not c.finished:
            move = self.red_ai.next_move(c)
            if move is not None:
                result = c.move(*move)
                if self.easy:
                    self.events.append(self._move_event(result))
                else:
                    self.events.append({"type": "tick"})
                if c.blue_moves_left > 0:
                    self.phase = "after_red"
                    return
                continue
            if c.blue_moves_left > 0 and self.phase != "day_end":
                self.phase = "day_end"
                return
            self.phase = "start"
            night = c.end_day()
            if night:
                self.events.append(self._night(night))

    def _entry_view(self, entry) -> dict:
        view = {"id": entry.id, "day": entry.day, "source": entry.source, "text": entry.text,
                "target_id": entry.target_id, "investigated": entry.investigated,
                "verdict": self.verdicts.get(entry.id)}
        if self.easy:
            view["hint"] = f"looks real {round(entry.confidence * 100)}%"
        elif self.explain:
            view["hint"] = "high" if entry.confidence >= 0.66 else "medium" if entry.confidence >= 0.4 else "low"
        return view

    def blue_state(self) -> str:
        c = self.campaign
        events, self.events = self.events, []
        confirmed = sorted({e.target_id for e in c.logs if e.real and e.investigated and e.succeeded
                            and e.attack_id != "port-scan"})
        return json.dumps({
            "phase": self.phase, "finished": c.finished or self.gave_up,
            "day": c.day, "max_days": self.company.max_days,
            "time_left": c.blue_moves_left, "time_total": c.blue_moves_per_day,
            "new_logs": len(c.unseen_logs()),
            "logs": [self._entry_view(e) for e in reversed(c.seen_logs())],
            "events": events, "isolated": sorted(c.foothold.isolated), "confirmed": confirmed,
            "kicked_out": c.kicked_out,
        })

    def blue_act(self, kind: str, target: str | None = None) -> str:
        c = self.campaign
        fresh = [self._entry_view(e) for e in c.unseen_logs()] if kind == "logs" else []
        try:
            action = c.blue(kind, target or None)
        except (PlanError, KeyError, ValueError) as error:
            return json.dumps({"error": str(error)})
        if kind == "logs":
            for item in fresh:
                item["seen_now"] = True
        if kind == "investigate":
            self.verdicts[int(target)] = action.text
        outcome = {"kind": action.kind, "target": action.target, "text": action.text, "useful": action.useful}
        if not c.finished and (self.phase == "after_red" or c.blue_moves_left <= 0):
            if self.phase == "day_end" and c.blue_moves_left <= 0:
                self.phase = "start"
                night = c.end_day()
                if night:
                    self.events.append(self._night(night))
            self._advance()
        return json.dumps({"action": outcome, "fresh": fresh, "state": json.loads(self.blue_state())})

    def blue_wait(self) -> str:
        c = self.campaign
        if not c.finished:
            if self.phase == "day_end":
                self.phase = "start"
                night = c.end_day()
                if night:
                    self.events.append(self._night(night))
            self._advance()
        return self.blue_state()

    def _label(self, target_id: str) -> str:
        for s in self.company.servers:
            if s.id == target_id:
                return f"{s.name} ({s.id})"
        for e in self.company.employees:
            if e.id == target_id:
                return f"{e.name}, {e.role}"
        return target_id

    def turn(self) -> str:
        c = self.campaign
        actions = []
        for attack_id in c.arsenal:
            attack = self.catalog.attacks[attack_id]
            item = {"id": attack_id, "name": attack.name}
            if self.explain:
                used = c.used.get(attack_id, 0)
                item["tag"] = f"used {used}x, more heat" if used and self.easy else ""
                item["hint"] = attack.description
                item["disabled"] = self._why_impossible(attack_id)
            actions.append(item)
        foothold = None
        if self.explain:
            f = c.foothold
            foothold = {
                "accounts": sorted(f.employees), "machines": sorted(f.servers),
                "admin": sorted(f.admin_on), "scanned": sorted(f.scanned),
            }
        intel = sorted(self.catalog.defenses[d].name for d in c.known_defenses)
        return json.dumps({
            "day": c.day, "max_days": self.company.max_days,
            "moves_left": c.moves_left_today, "moves_per_day": self.company.moves_per_day,
            "heat": c.heat if self.easy else None,
            "foothold": foothold, "intel": intel, "actions": actions,
            "finished": c.finished or self.gave_up,
        })

    def _why_impossible(self, attack_id: str) -> str | None:
        notes = []
        for target_id in self.campaign.targets_for(attack_id):
            preview = self.campaign.preview(attack_id, target_id)
            if preview.possible:
                return None
            notes.append(preview.note)
        return notes[0] if notes else "No targets."

    def targets(self, attack_id: str) -> str:
        options = []
        for target_id in self.campaign.targets_for(attack_id):
            item = {"id": target_id, "label": self._label(target_id)}
            if self.explain:
                preview = self.campaign.preview(attack_id, target_id)
                if not preview.possible:
                    item["disabled"] = preview.note
                else:
                    item["hint"] = preview.note or None
                    if self.easy:
                        item["success"] = preview.success_chance
                        item["spotted"] = preview.detect_chance
                        item["heat_after"] = preview.heat_after
            options.append(item)
        return json.dumps(options)

    def move(self, attack_id: str, target_id: str) -> str:
        try:
            result = self.campaign.move(attack_id, target_id)
        except PlanError as error:
            return json.dumps({"error": str(error)})
        event = self._move_event(result)
        event["blue"] = self._blue_reacts(until_done=False)
        event["kicked_out"] = self.campaign.kicked_out
        return json.dumps(event)

    def _blue_reacts(self, until_done: bool) -> list[str]:
        notices = []
        c = self.campaign
        while not c.finished:
            step = self.blue_ai.next_action(c)
            if step is None:
                break
            action = c.blue(*step)
            notice = RED_NOTICES.get(action.kind) if action.useful else None
            if notice:
                notices.append(notice.format(target=action.target))
            if not until_done:
                break
        return notices

    def _move_event(self, result) -> dict:
        label = self._label(result.step.target_id)
        who = label.split(",")[0].split(" (")[0]
        lines = [line.format(who=who) for line in SUSPENSE.get(result.attack.tactic, ["Attacking {who}"])]
        if result.attack.id == "phishing":
            lines = [f"Sending a fake email to {who}", f"Waiting for {who} to click"]
        empty = result.succeeded and result.attack.tactic in ("exfiltration", "impact") and not result.points
        event = {
            "type": "move", "attack": result.attack.name, "attack_id": result.attack.id, "tactic": result.attack.tactic,
            "target": label, "target_id": result.step.target_id, "suspense": lines if result.possible else [],
            "possible": result.possible, "succeeded": result.succeeded, "empty": empty, "note": result.note,
            "detected": result.detected, "kicked": result.kicked, "points": result.points,
        }
        if self.easy:
            event["chance"] = result.success_chance
            event["heat"] = result.heat
        if self.explain and self.side != "red" and not result.succeeded:
            event["blockers"] = [self.catalog.defenses[d].name for d in result.blockers]
        return event

    def _blue_view(self, result) -> list[dict]:
        if self.easy:
            return [self._move_event(result)]
        if not result.detected:
            return []
        name = result.attack.name if self.explain else "Something suspicious"
        return [{
            "type": "alert", "attack": name, "target": self._label(result.step.target_id),
            "target_id": result.step.target_id, "kicked": result.kicked,
        }]

    def _night(self, night) -> dict:
        event = {"type": "night", "day": night.day, "found": night.found}
        if self.easy:
            event.update(heat_before=night.heat_before, heat_after=night.heat_after, hunt=night.hunt_chance)
        return event

    def end_day(self) -> str:
        notices = self._blue_reacts(until_done=True)
        night = None if self.campaign.finished else self.campaign.end_day()
        return json.dumps({"night": self._night(night) if night else None, "blue": notices,
                           "kicked_out": self.campaign.kicked_out, "turn": json.loads(self.turn())})

    def give_up(self) -> str:
        self.gave_up = True
        return self.finish()

    def finish(self) -> str:
        c = self.campaign
        report = c.report()
        result = {
            "defense_score": report.defense_score, "damage": report.points, "max_damage": report.max_points,
            "caught": report.caught,
        }
        post_mortem = None
        if self.level != "hard":
            post_mortem = format_report(report, self.catalog, lessons=self.easy)
        tips = None
        if self.easy:
            tips = {"blue": advice.blue_tips(c), "red": advice.red_tips(c)}
        score = None
        unlocked = []
        blue_actions = [
            {"day": a.day, "kind": a.kind, "target": a.target, "text": a.text, "useful": a.useful}
            for a in c.blue_actions
        ]
        if self.side != "practice":
            s = scoring.blue_score(c, self.random_side) if self.side == "blue" else scoring.red_score(c, self.random_side)
            unlocked = self.profile.record(self.company.tier, self.level, s.won, s.total)
            score = {"side": s.side, "won": s.won, "base": s.base, "bonuses": s.bonuses, "multiplier": s.multiplier, "total": s.total}
        locks = {"goal": self.profile.next_goal()}
        return json.dumps({
            "result": result, "post_mortem": post_mortem, "tips": tips, "score": score,
            "unlocked": unlocked, "locks": locks, "profile": self._profile(), "blue_actions": blue_actions,
            "profile_json": json.dumps({"points": self.profile.points, "games": self.profile.games, "wins": self.profile.wins}),
        })
