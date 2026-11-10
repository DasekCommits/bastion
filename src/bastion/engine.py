import copy
import random
from dataclasses import dataclass, field

from bastion import soc
from bastion.catalog import Attack, Catalog, Defense
from bastion.company import Company, Employee

BLIND_PENALTY = 0.5
SCAN_BONUS = 1.5
LOGIN_ROLES = ("email", "vpn", "cloud")
DATA_ROLES = ("database",)
HEAT_PER_NOISE = 0.08
REPEAT_HEAT = 0.1
NIGHT_HUNT = 0.4
NIGHT_COOLDOWN = 0.7
BURN_HEAT = 0.15
FLOOR = 0.05
CEILING = 0.95
NEEDS_FOOTHOLD = ("privilege-escalation", "lateral-movement", "exfiltration", "impact")
BLUE_ACTIONS = ("logs", "investigate", "reset", "isolate", "hunt", "block")


class PlanError(ValueError):
    pass


@dataclass
class Step:
    attack_id: str
    target_id: str
    day: int = 1


@dataclass
class StepResult:
    step: Step
    attack: Attack
    possible: bool
    note: str
    success_chance: float
    detect_chance: float
    succeeded: bool
    detected: bool
    helped: list[str]
    missing: list[str]
    points: int = 0
    heat: float = 0.0
    blockers: list[str] = field(default_factory=list)
    kicked: bool = False


@dataclass
class NightResult:
    day: int
    heat_before: float
    hunt_chance: float
    found: bool
    heat_after: float


@dataclass
class Foothold:
    scanned: set[str] = field(default_factory=set)
    servers: set[str] = field(default_factory=set)
    admin_on: set[str] = field(default_factory=set)
    employees: set[str] = field(default_factory=set)
    fraud_done: bool = False
    direct: set[str] = field(default_factory=set)
    direct_admin: set[str] = field(default_factory=set)
    admin_accounts: set[str] = field(default_factory=set)
    isolated: dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.servers and not self.employees

    def gain(self, server_id: str, admin: bool = False) -> None:
        if server_id in self.isolated:
            return
        self.direct.add(server_id)
        self.servers.add(server_id)
        if admin:
            self.direct_admin.add(server_id)
            self.admin_on.add(server_id)

    def make_admin(self, server_id: str) -> None:
        self.direct_admin.add(server_id)
        self.admin_on.add(server_id)

    def recompute(self, company: Company) -> None:
        by_account = set()
        admin_by_account = set()
        for employee in company.employees:
            if employee.id in self.employees:
                by_account.update(employee.access)
                if employee.id in self.admin_accounts:
                    admin_by_account.update(employee.access)
        blocked = set(self.isolated)
        self.servers = (self.direct | by_account) - blocked
        self.admin_on = (self.direct_admin | admin_by_account) - blocked
        self.direct -= blocked
        self.direct_admin -= blocked


@dataclass
class Report:
    company: Company
    defenses: list[str]
    budget_used: int
    red_budget_used: int
    results: list[StepResult]
    nights: list[NightResult]
    days_used: int
    caught: bool
    points: int
    stolen: list[str]
    encrypted: list[str]
    blue_actions: list = field(default_factory=list)
    disruption: int = 0

    @property
    def max_points(self) -> int:
        return sum(asset.value for asset in self.company.data)

    @property
    def defense_score(self) -> int:
        lost = min(self.points, self.max_points)
        return round(100 * (1 - lost / self.max_points))


def check_defenses(company: Company, catalog: Catalog, defense_ids: list[str]) -> int:
    if len(defense_ids) != len(set(defense_ids)):
        raise PlanError("The same defense was picked twice")
    for defense_id in defense_ids:
        if defense_id not in catalog.defenses:
            raise PlanError(f"Unknown defense '{defense_id}'")
    cost = sum(catalog.defenses[defense_id].cost for defense_id in defense_ids)
    if cost > company.budget:
        raise PlanError(f"These defenses cost {cost}, but the budget is {company.budget}")
    return cost


def check_plan(company: Company, catalog: Catalog, plan: list[Step]) -> int:
    server_ids = {server.id for server in company.servers}
    employee_ids = {employee.id for employee in company.employees}
    for step in plan:
        attack = catalog.attacks.get(step.attack_id)
        if attack is None:
            raise PlanError(f"Unknown attack '{step.attack_id}'")
        valid_targets = server_ids if attack.target == "server" else employee_ids
        if step.target_id not in valid_targets:
            raise PlanError(f"'{step.target_id}' is not a valid {attack.target} for '{attack.id}'")
    days = [step.day for step in plan]
    if days != sorted(days):
        raise PlanError("Steps must be in day order")
    if days and (days[0] < 1 or days[-1] > company.max_days):
        raise PlanError(f"The attack must fit in {company.max_days} days")
    for day in set(days):
        if days.count(day) > company.moves_per_day:
            raise PlanError(f"Day {day} has more than {company.moves_per_day} moves")
    return check_arsenal(company, catalog, list(dict.fromkeys(step.attack_id for step in plan)))


def check_arsenal(company: Company, catalog: Catalog, attack_ids: list[str]) -> int:
    if len(attack_ids) != len(set(attack_ids)):
        raise PlanError("The same attack was bought twice")
    for attack_id in attack_ids:
        if attack_id not in catalog.attacks:
            raise PlanError(f"Unknown attack '{attack_id}'")
    cost = sum(catalog.attacks[attack_id].cost for attack_id in attack_ids)
    if cost > company.red_budget:
        raise PlanError(f"These attacks cost {cost}, but the Red Team budget is {company.red_budget}")
    return cost


def with_edge(chance: float, edge: float) -> float:
    if chance <= 0 or chance >= 1:
        return chance
    odds = chance / (1 - chance) * edge
    return odds / (1 + odds)


def clamp(chance: float) -> float:
    return min(CEILING, max(FLOOR, chance))


def success_chance(attack: Attack, defenses: list[Defense]) -> float:
    chance = attack.base_success
    for defense in defenses:
        chance *= 1 - defense.blocks.get(attack.id, 0)
    return chance


def detect_chance(attack: Attack, defenses: list[Defense]) -> float:
    missed = 1.0
    for defense in defenses:
        missed *= 1 - defense.detects.get(attack.id, 0)
    return attack.noise * (1 - missed)


def person_factor(attack: Attack, employee: Employee) -> float:
    if attack.trait is None:
        return 1.0
    return 1 - getattr(employee, attack.trait)


def heat_gain(attack: Attack, defenses: list[Defense], times_used_before: int) -> float:
    watchers = sum(1 for defense in defenses if defense.category == "detect")
    return attack.noise * HEAT_PER_NOISE * (1 + watchers) + REPEAT_HEAT * times_used_before


def night_hunt_chance(heat: float, defenses: list[Defense], edge: float = 1.0) -> float:
    watchers = sum(1 for defense in defenses if defense.category == "detect")
    return with_edge(min(1.0, heat * NIGHT_HUNT * watchers), 1 / edge)


def _night(day: int, heat: float, defenses: list[Defense], rng, edge: float = 1.0) -> NightResult:
    raw = night_hunt_chance(heat, defenses, edge)
    hunt = clamp(raw) if raw > 0 else 0.0
    found = hunt > 0 and rng.random() < hunt
    return NightResult(day, heat, hunt, found, heat * NIGHT_COOLDOWN)


def has_admin_rights(employee: Employee, defense_ids: list[str]) -> bool:
    if "least-privilege" in defense_ids:
        return employee.is_admin and employee.needs_admin
    return employee.is_admin


def _employees_with_access(company: Company, foothold: Foothold, server_id: str) -> list[Employee]:
    return [
        employee
        for employee in company.employees
        if employee.id in foothold.employees and server_id in employee.access
    ]


def _is_possible(attack: Attack, target_id: str, company: Company, foothold: Foothold) -> tuple[bool, str]:
    if attack.target == "employee" and attack.roles:
        employee = company.employee(target_id)
        if employee.department not in attack.roles:
            return False, f"{attack.name} only works on the {', '.join(attack.roles)} team."

    if attack.id == "bec":
        if foothold.fraud_done:
            return False, "The bank already sent you money once. A second request would be checked."
        return True, ""

    if attack.id in ("kerberoasting", "dcsync", "pass-the-hash") and foothold.is_empty():
        return False, "This needs a logged-in account inside the network first."

    if attack.id == "kerberoasting":
        return True, ""

    if attack.id == "dcsync":
        if target_id not in foothold.admin_on:
            return False, "DCSync needs administrator rights on the domain controller."
        return True, ""

    if attack.id == "pass-the-hash":
        if not foothold.admin_on:
            return False, "You need admin rights somewhere first, to dump password hashes from memory."
        if target_id in foothold.admin_on:
            return False, "You are already an administrator on this machine."
        if company.server(target_id).internet_facing:
            return False, "Pass-the-Hash works inside the network, not on internet-facing servers."
        return True, ""

    if attack.tactic in NEEDS_FOOTHOLD and foothold.is_empty():
        return False, "The attacker has no way into the company yet."

    if attack.target == "server":
        server = company.server(target_id)
        if attack.roles and server.role not in attack.roles:
            return False, f"{attack.name} does not work on a {server.role} server."
        if attack.tactic in ("reconnaissance", "initial-access") and not server.internet_facing:
            return False, f"{server.name} cannot be reached from the internet."

    if attack.tactic == "privilege-escalation" and target_id not in foothold.servers:
        return False, "The attacker has no access to this machine yet."

    if attack.tactic == "lateral-movement":
        if target_id in foothold.servers:
            return False, "The attacker is already on this machine."
        if not _employees_with_access(company, foothold, target_id):
            return False, "No stolen account can log in to this machine."

    if attack.tactic == "exfiltration":
        if target_id not in foothold.servers and not _employees_with_access(company, foothold, target_id):
            return False, "The attacker cannot reach this machine."

    if attack.tactic == "impact" and target_id not in foothold.admin_on:
        return False, "Encrypting a machine needs administrator rights on it."

    return True, ""


def _apply(attack: Attack, target_id: str, company: Company, foothold: Foothold, defense_ids: list[str]) -> tuple[int, str]:
    if attack.tactic == "reconnaissance":
        foothold.scanned.add(target_id)
        return 0, "The attacker now knows which software versions are running."

    if attack.id == "bec":
        money = [asset for asset in company.data if asset.fraud]
        foothold.fraud_done = True
        if not money:
            return 0, "Nobody here can move money."
        return sum(asset.value for asset in money), f"Finance paid the fake invoice: {', '.join(a.name for a in money)}."

    if attack.id == "kerberoasting":
        services = [server for server in company.servers if server.role in DATA_ROLES]
        for server in services:
            foothold.gain(server.id, admin=True)
        names = ", ".join(server.name for server in services)
        return 0, f"You cracked a service account password offline. It is admin on: {names}."

    if attack.id == "pass-the-hash":
        foothold.gain(target_id, admin=True)
        return 0, "You reused a stolen password hash and logged in as an administrator."

    if attack.id == "dcsync":
        for server in company.servers:
            foothold.gain(server.id, admin=True)
        return 0, "You copied every password in the company. You now own the whole domain."

    if attack.target == "employee":
        employee = next(employee for employee in company.employees if employee.id == target_id)
        foothold.employees.add(employee.id)
        reachable = [s for s in employee.access if s not in foothold.isolated]
        foothold.servers.update(reachable)
        if has_admin_rights(employee, defense_ids):
            foothold.admin_accounts.add(employee.id)
            foothold.admin_on.update(reachable)
            return 0, f"{employee.name}'s account is an administrator account."
        return 0, f"The attacker can now log in as {employee.name}."

    if attack.tactic == "initial-access":
        foothold.gain(target_id)
        return 0, "The attacker has a foothold on this server."

    if attack.tactic == "privilege-escalation":
        foothold.make_admin(target_id)
        return 0, "The attacker is now an administrator here."

    if attack.tactic == "lateral-movement":
        admin = any(has_admin_rights(e, defense_ids) for e in _employees_with_access(company, foothold, target_id))
        foothold.gain(target_id, admin=admin)
        return 0, "The attacker moved to a new machine."

    assets = [asset for asset in company.data if asset.location == target_id and not asset.fraud]
    if not assets:
        return 0, "There was nothing valuable on this machine."
    points = sum(asset.value for asset in assets)
    names = ", ".join(asset.name for asset in assets)
    if attack.id == "destruction":
        return points, f"Wiped: {names}."
    if attack.tactic == "exfiltration":
        note = f"Stolen: {names}."
        for asset in assets:
            if asset.grants is None or asset.grants in foothold.servers:
                continue
            reached = company.server(asset.grants).name
            if "segmentation" in defense_ids:
                note += f" The stolen password is useless: segmentation keeps the {reached} out of reach."
            else:
                foothold.gain(asset.grants)
                note += f" The stolen password opens the {reached}."
        return points, note
    return points, f"Encrypted: {names}."


@dataclass
class Preview:
    possible: bool
    note: str
    success_chance: float
    detect_chance: float
    heat_after: float


class Campaign:
    def __init__(
        self,
        company: Company,
        catalog: Catalog,
        defense_ids: list[str],
        arsenal: list[str],
        seed: int | None = None,
        rng: random.Random | None = None,
        edge: float = 1.0,
        active_blue: bool = False,
    ):
        self.edge = edge
        self.active_blue = active_blue
        self.company = company
        self.catalog = catalog
        self.defense_ids = list(defense_ids)
        self.budget_used = check_defenses(company, catalog, self.defense_ids)
        self.arsenal = list(arsenal)
        self.red_budget_used = check_arsenal(company, catalog, self.arsenal)
        self.defenses = [catalog.defenses[defense_id] for defense_id in self.defense_ids]
        self.rng = rng or random.Random(seed)
        self.foothold = Foothold()
        self.results: list[StepResult] = []
        self.nights: list[NightResult] = []
        self.stolen: list[str] = []
        self.encrypted: list[str] = []
        self.heat = 0.0
        self.used: dict[str, int] = {}
        self.known_defenses: set[str] = set()
        self.lost: set[str] = set()
        self.burned: set[tuple[str, str]] = set()
        self.day = 1
        self.moves_today = 0
        self.caught = False
        self.out_of_days = False
        self.logs: list[soc.LogEntry] = []
        self.blue_actions: list[soc.BlueAction] = []
        self.blue_moves_today = 0
        self.disruption = 0
        self.kicked_out = False
        if active_blue:
            self._add_noise()

    @property
    def finished(self) -> bool:
        return self.caught or self.out_of_days

    @property
    def moves_left_today(self) -> int:
        return self.company.moves_per_day - self.moves_today

    def targets_for(self, attack_id: str) -> list[str]:
        attack = self.catalog.attacks[attack_id]
        if attack.target == "server":
            return [s.id for s in self.company.servers if not attack.roles or s.role in attack.roles]
        return [employee.id for employee in self.company.employees]

    def scan_helps(self) -> bool:
        for attack_id in self.arsenal:
            attack = self.catalog.attacks[attack_id]
            if attack.tactic == "initial-access" and attack.target == "server":
                return True
            if attack.trait == "password_hygiene":
                return True
        return False

    def _count_once(self, attack: Attack, target_id: str, points: int, outcome: str) -> tuple[int, str]:
        if attack.id == "bec":
            hit = [asset for asset in self.company.data if asset.fraud]
        else:
            hit = [asset for asset in self.company.data if asset.location == target_id and not asset.fraud]
        new = [asset for asset in hit if asset.id not in self.lost]
        self.lost.update(asset.id for asset in hit)
        fresh = sum(asset.value for asset in new)
        if fresh < points:
            outcome += " This data was already lost earlier, so it only counts once." if not fresh else " Some of this data was already lost earlier and only counts once."
        return fresh, outcome

    def _scanned_roles(self) -> set[str]:
        return {self.company.server(server_id).role for server_id in self.foothold.scanned}

    def _reveal_outside(self, server_id: str) -> str:
        role = self.company.server(server_id).role
        seen = [d for d in self.defenses if role in d.seen_outside]
        self.known_defenses.update(d.id for d in seen)
        if not seen:
            return "No protection is visible from outside."
        return "Visible from outside: " + ", ".join(d.name for d in seen) + "."

    def _reveal_inside(self) -> str:
        if self.foothold.is_empty():
            return ""
        seen = [d for d in self.defenses if d.seen_inside and d.id not in self.known_defenses]
        self.known_defenses.update(d.id for d in seen)
        if not seen:
            return ""
        return "Inside, you notice: " + ", ".join(d.name for d in seen) + "."

    def preview(self, attack_id: str, target_id: str) -> Preview:
        attack = self.catalog.attacks[attack_id]
        if (attack_id, target_id) in self.burned:
            return Preview(False, "The Blue Team already blocked this exact attempt.", 0.0, 0.0, self.heat)
        if target_id in self.foothold.isolated:
            return Preview(False, "The Blue Team has isolated this machine. Nobody can reach it for now.", 0.0, 0.0, self.heat)
        possible, note = _is_possible(attack, target_id, self.company, self.foothold)
        if not possible:
            return Preview(False, note, 0.0, 0.0, self.heat)
        chance = success_chance(attack, self.defenses)
        if attack.target == "employee":
            chance *= person_factor(attack, self.company.employee(target_id))
        if attack.target == "employee" and attack.trait == "password_hygiene" and self._scanned_roles() & set(LOGIN_ROLES):
            chance = min(0.95, chance * SCAN_BONUS)
            note = "Your scan found the login page, so password attacks work better."
        if attack.tactic == "initial-access" and attack.target == "server" and target_id not in self.foothold.scanned:
            chance *= BLIND_PENALTY
            note = "Attacking blind: no scan first, so the attacker does not know what to exploit."
        if attack.tactic == "privilege-escalation" and target_id in self.foothold.admin_on:
            chance = 1.0
            note = "Already an administrator here, nothing to escalate."
        if chance < 1.0:
            chance = clamp(with_edge(chance, self.edge))
        heat = min(1.0, self.heat + heat_gain(attack, self.defenses, self.used.get(attack.id, 0)))
        spotted = 1 - (1 - detect_chance(attack, self.defenses)) * (1 - heat)
        spotted = clamp(with_edge(spotted, 1 / self.edge))
        return Preview(True, note, chance, spotted, heat)

    def move(self, attack_id: str, target_id: str) -> StepResult:
        if self.finished:
            raise PlanError("The campaign is over")
        if self.moves_left_today <= 0:
            raise PlanError(f"Day {self.day} has no moves left")
        if attack_id not in self.arsenal:
            raise PlanError(f"'{attack_id}' is not in your arsenal")
        if target_id not in self.targets_for(attack_id):
            attack = self.catalog.attacks[attack_id]
            raise PlanError(f"'{target_id}' is not a valid {attack.target} for '{attack_id}'")

        attack = self.catalog.attacks[attack_id]
        step = Step(attack_id, target_id, self.day)
        helped = [d.id for d in self.defenses if attack.id in d.blocks or attack.id in d.detects]
        missing = [d.id for d in self.catalog.defenses_against(attack.id, self.company.tier) if d.id not in self.defense_ids]
        self.moves_today += 1
        preview = self.preview(attack_id, target_id)

        if not preview.possible:
            result = StepResult(step, attack, False, preview.note, 0, 0, False, False, helped, missing)
            self.results.append(result)
            return result

        self.heat = preview.heat_after
        self.used[attack.id] = self.used.get(attack.id, 0) + 1
        succeeded = self.rng.random() < preview.success_chance
        detected = self.rng.random() < preview.detect_chance
        note = preview.note
        points = 0
        was_inside = not self.foothold.is_empty()
        before = copy.deepcopy(self.foothold)

        if succeeded and attack.tactic == "exfiltration" and target_id in self.stolen:
            note = "You already copied everything here."
        elif succeeded and attack.tactic == "impact" and target_id in self.encrypted:
            note = "These files are already encrypted."
        elif succeeded:
            points, outcome = _apply(attack, target_id, self.company, self.foothold, self.defense_ids)
            if points:
                points, outcome = self._count_once(attack, target_id, points, outcome)
            if attack.tactic == "reconnaissance":
                outcome = f"{outcome} {self._reveal_outside(target_id)}"
            outcome = f"{outcome} {self._reveal_inside()}".strip()
            note = f"{note} {outcome}".strip()
            if attack.tactic == "exfiltration" and points:
                self.stolen.append(target_id)
            if attack.tactic == "impact" and attack.target == "server" and points:
                self.encrypted.append(target_id)

        if self.active_blue:
            if detected:
                self._log_real(attack, target_id, succeeded, not was_inside)
            result = StepResult(
                step, attack, True, note, preview.success_chance, preview.detect_chance,
                succeeded, detected, helped, missing, points, self.heat,
                blockers=[d.id for d in self.defenses if attack.id in d.blocks],
            )
            self.results.append(result)
            return result

        if detected and not was_inside:
            self.foothold = before
            self.burned.add((attack_id, target_id))
            self.heat = min(1.0, self.heat + BURN_HEAT)
            if succeeded and attack.tactic != "reconnaissance":
                note = "It worked for a moment, but the Blue Team noticed and cut that access."

        result = StepResult(
            step, attack, True, note, preview.success_chance, preview.detect_chance,
            succeeded, detected, helped, missing, points, self.heat,
            blockers=[d.id for d in self.defenses if attack.id in d.blocks],
            kicked=detected and was_inside,
        )
        self.results.append(result)
        self.caught = result.kicked
        return result

    def end_day(self) -> NightResult | None:
        if self.finished:
            return None
        if self.day >= self.company.max_days:
            self.out_of_days = True
            return None
        night = _night(self.day, self.heat, self.defenses, self.rng, self.edge)
        if self.active_blue and "soc" not in self.defense_ids:
            night.hunt_chance = 0.0
            night.found = False
        if self.foothold.is_empty():
            night.found = False
        self.nights.append(night)
        self.heat = night.heat_after
        self.caught = night.found
        self.day += 1
        self.moves_today = 0
        if self.active_blue:
            self.blue_moves_today = 0
            self.foothold.isolated = {s: until for s, until in self.foothold.isolated.items() if until >= self.day}
            self._add_noise()
        return night

    @property
    def blue_moves_per_day(self) -> int:
        return self.company.team_size + 1

    @property
    def blue_moves_left(self) -> int:
        return self.blue_moves_per_day - self.blue_moves_today

    def _label(self, target_id: str) -> str:
        for server in self.company.servers:
            if server.id == target_id:
                return server.name
        return self.company.employee(target_id).name

    def _log_real(self, attack: Attack, target_id: str, succeeded: bool, from_outside: bool) -> None:
        entry = soc.real_entry(len(self.logs) + 1, self.day, attack, target_id, self._label(target_id),
                               self.defenses, succeeded, from_outside, self.rng)
        self.logs.append(entry)

    def _add_noise(self) -> None:
        for _ in range(soc.NOISE_PER_DAY[self.company.tier]):
            self.logs.append(soc.noise_entry(len(self.logs) + 1, self.day, self.company, self.defenses, self.rng))

    def unseen_logs(self) -> list[soc.LogEntry]:
        return [entry for entry in self.logs if not entry.seen]

    def seen_logs(self) -> list[soc.LogEntry]:
        return [entry for entry in self.logs if entry.seen]

    def _entry(self, entry_id: int) -> soc.LogEntry:
        for entry in self.logs:
            if entry.id == entry_id and entry.seen:
                return entry
        raise PlanError("You have not seen that log entry yet.")

    def blue(self, kind: str, target: str | int | None = None) -> soc.BlueAction:
        if not self.active_blue:
            raise PlanError("The Blue Team only acts in active mode")
        if self.finished:
            raise PlanError("The campaign is over")
        if kind not in BLUE_ACTIONS:
            raise PlanError(f"Unknown Blue Team action '{kind}'")
        if self.blue_moves_left <= 0:
            raise PlanError("The Blue Team has no time left today")
        was_inside = not self.foothold.is_empty()
        action = getattr(self, f"_blue_{kind}")(target)
        self.blue_moves_today += 1
        self.blue_actions.append(action)
        if was_inside and self.foothold.is_empty():
            self.kicked_out = True
            self.caught = True
        return action

    def _blue_logs(self, target) -> soc.BlueAction:
        fresh = self.unseen_logs()
        for entry in fresh:
            entry.seen = True
        text = f"{len(fresh)} new log entr{'y' if len(fresh) == 1 else 'ies'}." if fresh else "Nothing new in the logs."
        return soc.BlueAction(self.day, "logs", "", text, bool(fresh))

    def _blue_investigate(self, entry_id) -> soc.BlueAction:
        entry = self._entry(int(entry_id))
        entry.investigated = True
        if not entry.real:
            return soc.BlueAction(self.day, "investigate", entry.text, f"False alarm: {entry.innocent_reason}.", False)
        attack = self.catalog.attacks[entry.attack_id]
        label = self._label(entry.target_id)
        if entry.succeeded:
            outcome = "It worked." if entry.attack_id != "port-scan" else "The attacker mapped the server."
        else:
            outcome = "It failed, but someone is trying."
        return soc.BlueAction(self.day, "investigate", entry.text,
                              f"Real attack: {attack.name} ({attack.mitre_id}) against {label}. {outcome}", True)

    def _blue_reset(self, employee_id) -> soc.BlueAction:
        employee = self.company.employee(str(employee_id))
        if employee.id in self.foothold.employees:
            self.foothold.employees.discard(employee.id)
            self.foothold.admin_accounts.discard(employee.id)
            self.foothold.recompute(self.company)
            return soc.BlueAction(self.day, "reset", employee.name, f"The attacker had {employee.name}'s account and just lost it.", True)
        self.disruption += 1
        return soc.BlueAction(self.day, "reset", employee.name, f"{employee.name}'s account was clean. They had to pick a new password for nothing.", False)

    def _blue_isolate(self, server_id) -> soc.BlueAction:
        server = self.company.server(str(server_id))
        had = server.id in self.foothold.servers
        self.foothold.isolated[server.id] = self.day + 1
        self.foothold.recompute(self.company)
        self.disruption += 1 if had else 2
        if had:
            return soc.BlueAction(self.day, "isolate", server.name, f"The attacker was on {server.name} and is now cut off. It stays offline until the end of tomorrow.", True)
        return soc.BlueAction(self.day, "isolate", server.name, f"{server.name} was clean. It is offline until the end of tomorrow and work stops there.", False)

    def _blue_hunt(self, server_id) -> soc.BlueAction:
        server = self.company.server(str(server_id))
        if server.id in self.foothold.servers and self.rng.random() < soc.hunt_chance(self.defense_ids):
            entry = soc.LogEntry(len(self.logs) + 1, self.day, "Threat hunt", "admin",
                                 f"Hidden attacker activity found on {server.name}", server.id, True, 0.95,
                                 attack_id=None, succeeded=True, seen=True, investigated=True)
            self.logs.append(entry)
            return soc.BlueAction(self.day, "hunt", server.name, f"Found it: the attacker is on {server.name}.", True)
        return soc.BlueAction(self.day, "hunt", server.name, f"Nothing found on {server.name}.", False)

    def _blue_block(self, entry_id) -> soc.BlueAction:
        entry = self._entry(int(entry_id))
        if entry.real and entry.from_outside and entry.attack_id:
            self.burned.add((entry.attack_id, entry.target_id))
            return soc.BlueAction(self.day, "block", entry.text, "Blocked: that sender or address cannot try this again.", True)
        return soc.BlueAction(self.day, "block", entry.text, "Blocked, but there was nothing behind it to stop.", False)

    def report(self) -> Report:
        return Report(
            company=self.company,
            defenses=list(self.defense_ids),
            budget_used=self.budget_used,
            red_budget_used=self.red_budget_used,
            results=self.results,
            nights=self.nights,
            days_used=self.day if self.results or self.nights else 0,
            caught=self.caught,
            points=sum(result.points for result in self.results),
            stolen=self.stolen,
            encrypted=self.encrypted,
            blue_actions=list(self.blue_actions),
            disruption=self.disruption,
        )

    def plan(self) -> list[Step]:
        return [result.step for result in self.results]


def run_attack(
    company: Company,
    catalog: Catalog,
    defense_ids: list[str],
    plan: list[Step],
    seed: int | None = None,
    rng: random.Random | None = None,
) -> Report:
    check_defenses(company, catalog, defense_ids)
    check_plan(company, catalog, plan)
    arsenal = list(dict.fromkeys(step.attack_id for step in plan))
    campaign = Campaign(company, catalog, defense_ids, arsenal, seed=seed, rng=rng)
    for step in plan:
        while campaign.day < step.day and not campaign.finished:
            campaign.end_day()
        if campaign.finished:
            break
        campaign.move(step.attack_id, step.target_id)
        if campaign.finished:
            break
    return campaign.report()


@dataclass
class Simulation:
    runs: int
    average_score: float
    worst_score: int
    caught_rate: float
    breach_rate: float
    step_success: list[float]


def simulate(
    company: Company,
    catalog: Catalog,
    defense_ids: list[str],
    plan: list[Step],
    runs: int = 1000,
    seed: int | None = None,
) -> Simulation:
    rng = random.Random(seed)
    scores, caught, breached = [], 0, 0
    successes = [0] * len(plan)
    for _ in range(runs):
        report = run_attack(company, catalog, defense_ids, plan, rng=rng)
        scores.append(report.defense_score)
        caught += report.caught
        breached += report.points > 0
        for index, result in enumerate(report.results):
            successes[index] += result.succeeded
    return Simulation(
        runs=runs,
        average_score=sum(scores) / runs,
        worst_score=min(scores),
        caught_rate=caught / runs,
        breach_rate=breached / runs,
        step_success=[count / runs for count in successes],
    )
