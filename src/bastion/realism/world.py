import random
from dataclasses import dataclass, field

PORTS = {
    "web": [80, 443],
    "email": [25, 443, 587],
    "vpn": [443, 500, 4500],
    "cloud": [443],
    "vendor": [22, 443],
    "database": [1433, 3306],
    "domain-controller": [53, 88, 389, 445, 636],
    "file": [139, 445],
    "workstation": [135, 445, 3389],
    "payments": [443, 8443],
    "dev": [22, 8080],
    "imaging": [104, 3389],
}
ROLE_CODES = {
    "web": "WEB", "email": "MAIL", "vpn": "VPN", "cloud": "CLOUD", "vendor": "VND", "database": "SQL",
    "domain-controller": "DC", "file": "FS", "workstation": "WS", "payments": "PAY", "dev": "DEV", "imaging": "PACS",
}
VISIBILITY = {
    "firewall": None,
    "web": None,
    "security": "siem",
    "dns": "siem",
    "sysmon": "edr",
    "mail": "email-filter",
}


@dataclass
class Host:
    id: str
    name: str
    hostname: str
    ip: str
    public_ip: str | None
    os: str
    ports: list[int]


@dataclass
class Account:
    id: str
    name: str
    username: str
    email: str
    workstation: str
    workstation_ip: str


@dataclass
class World:
    company_id: str
    domain: str
    public_domain: str
    hosts: dict[str, Host]
    accounts: dict[str, Account]
    attacker_ip: str
    noise_ips: list[str] = field(default_factory=list)

    def host_of(self, target_id: str) -> Host | None:
        return self.hosts.get(target_id)

    def account_of(self, target_id: str) -> Account | None:
        return self.accounts.get(target_id)

    def visible_indexes(self, defense_ids: list[str]) -> list[str]:
        return [index for index, needs in VISIBILITY.items() if needs is None or needs in defense_ids]


def build_world(company, rng: random.Random) -> World:
    prefix = company.id.split("-")[0][:3].upper()
    domain = f"{company.id.split('-')[0]}.local"
    public_domain = f"{company.id}.example"
    hosts, counters = {}, {}
    public = 10
    for index, server in enumerate(company.servers, start=1):
        code = ROLE_CODES.get(server.role, "SRV")
        counters[code] = counters.get(code, 0) + 1
        hostname = f"{prefix}-{code}{counters[code]:02d}"
        public_ip = None
        if server.internet_facing:
            public_ip = f"198.51.100.{public}"
            public += 1
        windows = any("windows" in s.lower() for s in server.software) or server.role in ("domain-controller", "file", "workstation")
        hosts[server.id] = Host(server.id, server.name, hostname, f"10.10.1.{9 + index}", public_ip,
                                "windows" if windows else "linux", PORTS.get(server.role, [443]))
    accounts = {}
    for index, employee in enumerate(company.employees, start=1):
        username = employee.name.lower().replace(" ", ".")
        workstation = f"{prefix}-WS{index:03d}"
        accounts[employee.id] = Account(employee.id, employee.name, username, f"{username}@{public_domain}",
                                        workstation, f"10.10.20.{10 + index}")
    attacker_ip = f"203.0.113.{rng.randint(20, 240)}"
    noise_ips = [f"192.0.2.{rng.randint(2, 250)}" for _ in range(12)]
    return World(company.id, domain, public_domain, hosts, accounts, attacker_ip, noise_ips)
