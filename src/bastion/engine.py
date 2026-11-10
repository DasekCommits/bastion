import random
from dataclasses import dataclass, field

from bastion.catalog import Attack, Catalog, Defense
from bastion.company import Company, Employee

BLIND_PENALTY = 0.5
HEAT_PER_NOISE = 0.08
REPEAT_HEAT = 0.1
NIGHT_HUNT = 0.4
NIGHT_COOLDOWN = 0.7
NEEDS_FOOTHOLD = ("privilege-escalation", "lateral-movement", "exfiltration", "impact")


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

    def is_empty(self) -> bool:
        return not self.servers and not self.employees


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
    cost = sum(catalog.attacks[step.attack_id].cost for step in plan)
    if cost > company.red_budget:
        raise PlanError(f"This attack costs {cost}, but the Red Team budget is {company.red_budget}")
    return cost


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


def heat_gain(attack: Attack, defenses: list[Defense], times_used_before: int) -> float:
    watchers = sum(1 for defense in defenses if defense.category == "detect")
    return attack.noise * HEAT_PER_NOISE * (1 + watchers) + REPEAT_HEAT * times_used_before


def night_hunt_chance(heat: float, defenses: list[Defense]) -> float:
    watchers = sum(1 for defense in defenses if defense.category == "detect")
    return min(1.0, heat * NIGHT_HUNT * watchers)


def _night(day: int, heat: float, defenses: list[Defense], rng) -> NightResult:
    hunt = night_hunt_chance(heat, defenses)
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
    if attack.tactic in NEEDS_FOOTHOLD and foothold.is_empty():
        return False, "The attacker has no way into the company yet."

    if attack.target == "server":
        server = company.server(target_id)
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

    if attack.target == "employee":
        employee = next(employee for employee in company.employees if employee.id == target_id)
        foothold.employees.add(employee.id)
        foothold.servers.update(employee.access)
        if has_admin_rights(employee, defense_ids):
            foothold.admin_on.update(employee.access)
            return 0, f"{employee.name}'s account is an administrator account."
        return 0, f"The attacker can now log in as {employee.name}."

    if attack.tactic == "initial-access":
        foothold.servers.add(target_id)
        return 0, "The attacker has a foothold on this server."

    if attack.tactic == "privilege-escalation":
        foothold.admin_on.add(target_id)
        return 0, "The attacker is now an administrator here."

    if attack.tactic == "lateral-movement":
        foothold.servers.add(target_id)
        if any(has_admin_rights(e, defense_ids) for e in _employees_with_access(company, foothold, target_id)):
            foothold.admin_on.add(target_id)
        return 0, "The attacker moved to a new machine."

    assets = [asset for asset in company.data if asset.location == target_id]
    if not assets:
        return 0, "There was nothing valuable on this machine."
    points = sum(asset.value for asset in assets)
    names = ", ".join(asset.name for asset in assets)
    if attack.tactic == "exfiltration":
        return points, f"Stolen: {names}."
    return points, f"Encrypted: {names}."


def run_attack(
    company: Company,
    catalog: Catalog,
    defense_ids: list[str],
    plan: list[Step],
    seed: int | None = None,
    rng: random.Random | None = None,
) -> Report:
    budget_used = check_defenses(company, catalog, defense_ids)
    red_budget_used = check_plan(company, catalog, plan)
    rng = rng or random.Random(seed)
    defenses = [catalog.defenses[defense_id] for defense_id in defense_ids]
    foothold = Foothold()
    results = []
    stolen, encrypted = [], []
    caught = False
    heat = 0.0
    used = {}
    nights = []
    day = 1

    for step in plan:
        while day < step.day and not caught:
            night = _night(day, heat, defenses, rng)
            nights.append(night)
            heat = night.heat_after
            caught = night.found
            day += 1
        if caught:
            break

        attack = catalog.attacks[step.attack_id]
        helped = [d.id for d in defenses if attack.id in d.blocks or attack.id in d.detects]
        missing = [d.id for d in catalog.defenses_against(attack.id) if d.id not in defense_ids]
        possible, note = _is_possible(attack, step.target_id, company, foothold)

        if not possible:
            results.append(StepResult(step, attack, False, note, 0, 0, False, False, helped, missing))
            continue

        chance = success_chance(attack, defenses)
        if attack.id == "exploit-web" and step.target_id not in foothold.scanned:
            chance *= BLIND_PENALTY
            note = "Attacking blind: no scan first, so the attacker does not know what to exploit."
        if attack.tactic == "privilege-escalation" and step.target_id in foothold.admin_on:
            chance = 1.0
            note = "Already an administrator here, nothing to escalate."

        heat = min(1.0, heat + heat_gain(attack, defenses, used.get(attack.id, 0)))
        used[attack.id] = used.get(attack.id, 0) + 1
        spotted = 1 - (1 - detect_chance(attack, defenses)) * (1 - heat)
        succeeded = rng.random() < chance
        detected = rng.random() < spotted
        points = 0

        if succeeded:
            points, outcome = _apply(attack, step.target_id, company, foothold, defense_ids)
            note = f"{note} {outcome}".strip()
            if attack.tactic == "exfiltration" and points:
                stolen.append(step.target_id)
            if attack.tactic == "impact" and points:
                encrypted.append(step.target_id)

        results.append(
            StepResult(step, attack, True, note, chance, spotted, succeeded, detected, helped, missing, points, heat)
        )
        if detected:
            caught = True
            break

    return Report(
        company=company,
        defenses=list(defense_ids),
        budget_used=budget_used,
        red_budget_used=red_budget_used,
        results=results,
        nights=nights,
        days_used=day if plan else 0,
        caught=caught,
        points=sum(result.points for result in results),
        stolen=stolen,
        encrypted=encrypted,
    )


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
