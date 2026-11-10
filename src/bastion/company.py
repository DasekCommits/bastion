import copy
import json
from dataclasses import dataclass
from pathlib import Path

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
TIERS = ("small", "medium", "large", "huge")


@dataclass
class Server:
    id: str
    name: str
    role: str
    internet_facing: bool
    software: list[str]


@dataclass
class Employee:
    id: str
    name: str
    role: str
    is_admin: bool
    access: list[str]
    needs_admin: bool = False
    awareness: float = 0.0
    password_hygiene: float = 0.0
    admin_chance: float = 0.0
    loyalty: float = 0.5
    department: str = ""


@dataclass
class DataAsset:
    id: str
    name: str
    location: str
    value: int
    grants: str | None = None
    fraud: bool = False


@dataclass
class Company:
    id: str
    name: str
    tier: str
    description: str
    budget: int
    red_budget: int
    max_days: int
    moves_per_day: int
    team_size: int
    servers: list[Server]
    employees: list[Employee]
    data: list[DataAsset]
    budget_range: list[int] | None = None
    red_budget_range: list[int] | None = None

    def server(self, server_id: str) -> Server:
        for server in self.servers:
            if server.id == server_id:
                return server
        raise KeyError(f"No server with id '{server_id}'")

    def employee(self, employee_id: str) -> Employee:
        for employee in self.employees:
            if employee.id == employee_id:
                return employee
        raise KeyError(f"No employee with id '{employee_id}'")

    def internet_facing_servers(self) -> list[Server]:
        return [server for server in self.servers if server.internet_facing]

    def admins(self) -> list[Employee]:
        return [employee for employee in self.employees if employee.is_admin]


def roll_mistakes(company: Company, rng) -> Company:
    rolled = copy.deepcopy(company)
    if rolled.budget_range:
        low, high = rolled.budget_range
        rolled.budget = rng.randrange(low, high + 1, 5)
    if rolled.red_budget_range:
        low, high = rolled.red_budget_range
        rolled.red_budget = rng.randrange(low, high + 1, 5)
    candidates = [e for e in rolled.employees if e.admin_chance and not e.needs_admin]
    for employee in candidates:
        employee.is_admin = False
    rng.shuffle(candidates)
    for employee in candidates:
        if rng.random() < employee.admin_chance:
            employee.is_admin = True
            break
    return rolled


class ScenarioError(ValueError):
    pass


def validate(company: Company) -> None:
    if company.tier not in TIERS:
        raise ScenarioError(f"Unknown tier '{company.tier}', expected one of {TIERS}")

    for name in ("budget_range", "red_budget_range"):
        span = getattr(company, name)
        if span is None:
            continue
        if len(span) != 2 or span[0] > span[1] or any(value % 5 for value in span):
            raise ScenarioError(f"{name} must be [low, high] in steps of 5")

    server_ids = [server.id for server in company.servers]
    if len(server_ids) != len(set(server_ids)):
        raise ScenarioError("Two servers share the same id")

    for employee in company.employees:
        for trait in ("awareness", "password_hygiene", "admin_chance", "loyalty"):
            if not 0 <= getattr(employee, trait) <= 1:
                raise ScenarioError(f"Employee '{employee.id}' needs {trait} from 0 to 1")
        for server_id in employee.access:
            if server_id not in server_ids:
                raise ScenarioError(
                    f"Employee '{employee.id}' has access to unknown server '{server_id}'"
                )

    for asset in company.data:
        if asset.location not in server_ids:
            raise ScenarioError(f"Data '{asset.id}' is stored on unknown server '{asset.location}'")
        if asset.grants is not None and asset.grants not in server_ids:
            raise ScenarioError(f"Data '{asset.id}' grants access to unknown server '{asset.grants}'")
        if not 1 <= asset.value <= 10:
            raise ScenarioError(f"Data '{asset.id}' must have a value from 1 to 10")


def load_company(path: Path) -> Company:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    company = Company(
        id=raw["id"],
        name=raw["name"],
        tier=raw["tier"],
        description=raw["description"],
        budget=raw["budget"],
        red_budget=raw["red_budget"],
        max_days=raw["max_days"],
        moves_per_day=raw["moves_per_day"],
        team_size=raw["team_size"],
        servers=[Server(**item) for item in raw["servers"]],
        employees=[Employee(**item) for item in raw["employees"]],
        data=[DataAsset(**item) for item in raw["data"]],
        budget_range=raw.get("budget_range"),
        red_budget_range=raw.get("red_budget_range"),
    )
    validate(company)
    return company


def list_scenarios() -> list[Company]:
    companies = [load_company(path) for path in SCENARIOS_DIR.glob("*.json")]
    return sorted(companies, key=lambda company: TIERS.index(company.tier))


def load_scenario(scenario_id: str) -> Company:
    return load_company(SCENARIOS_DIR / f"{scenario_id}.json")
