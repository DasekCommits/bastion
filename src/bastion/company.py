import json
from dataclasses import dataclass
from pathlib import Path

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
TIERS = ("small", "medium", "large")


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


@dataclass
class DataAsset:
    id: str
    name: str
    location: str
    value: int


@dataclass
class Company:
    id: str
    name: str
    tier: str
    description: str
    budget: int
    team_size: int
    servers: list[Server]
    employees: list[Employee]
    data: list[DataAsset]

    def server(self, server_id: str) -> Server:
        for server in self.servers:
            if server.id == server_id:
                return server
        raise KeyError(f"No server with id '{server_id}'")

    def internet_facing_servers(self) -> list[Server]:
        return [server for server in self.servers if server.internet_facing]

    def admins(self) -> list[Employee]:
        return [employee for employee in self.employees if employee.is_admin]


class ScenarioError(ValueError):
    pass


def validate(company: Company) -> None:
    if company.tier not in TIERS:
        raise ScenarioError(f"Unknown tier '{company.tier}', expected one of {TIERS}")

    server_ids = [server.id for server in company.servers]
    if len(server_ids) != len(set(server_ids)):
        raise ScenarioError("Two servers share the same id")

    for employee in company.employees:
        for server_id in employee.access:
            if server_id not in server_ids:
                raise ScenarioError(
                    f"Employee '{employee.id}' has access to unknown server '{server_id}'"
                )

    for asset in company.data:
        if asset.location not in server_ids:
            raise ScenarioError(f"Data '{asset.id}' is stored on unknown server '{asset.location}'")
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
        team_size=raw["team_size"],
        servers=[Server(**item) for item in raw["servers"]],
        employees=[Employee(**item) for item in raw["employees"]],
        data=[DataAsset(**item) for item in raw["data"]],
    )
    validate(company)
    return company


def load_scenario(scenario_id: str) -> Company:
    return load_company(SCENARIOS_DIR / f"{scenario_id}.json")
