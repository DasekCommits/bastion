import random
from dataclasses import dataclass

NOISE_PER_DAY = {"small": 2, "medium": 3, "large": 5}
EGG_RNG = random.Random()
EGG_CHANCE = 0.05
EGG_COMMAND = "QwBMAEUAQQBSAEEATgBDAEUAOgAgAGkAcwBvAGwAYQB0AGUAIAB0AGgAZQAgAG0AYQBjAGgAaQBuAGUAIABJACAAcgBhAG4AIABvAG4ALAAgAHQAaABlACAAcwBhAG0AZQAgAGQAYQB5ACAAeQBvAHUAIABzAGUAZQAgAG0AZQAuACAAVABoAHIAZQBlACAAdABpAG0AZQBzAC4A"
BASE_HUNT = 0.45
HUNT_TOOLS = {"edr": 0.3, "siem": 0.15, "soc": 0.2}

SIGNS = {
    "mail": "Suspicious attachment delivered to {who}",
    "logins": "Many failed logins on {who}'s account",
    "travel": "Login for {who} from a country they never logged in from",
    "scan": "Port scan from an unknown address against {where}",
    "web": "Strange requests to {where}",
    "admin": "Unusual administrator activity on {where}",
    "remote": "New remote login to {where}",
    "upload": "Large upload from {where} to an unknown address",
    "files": "Many files changed at once on {where}",
    "tickets": "Unusual Kerberos ticket requests on {where}",
    "replication": "Password replication request to {where} from an ordinary machine",
    "payment": "Payment request with changed bank details sent to {who}",
    "usb": "Unknown USB device plugged in by {who}",
}

INNOCENT = {
    "mail": "a supplier's newsletter with a harmless macro",
    "logins": "{who} forgot their password after the weekend",
    "travel": "{who} is on holiday and checked email from the hotel",
    "scan": "automated scanners hit every server on the internet all day",
    "web": "a search engine crawling the site",
    "admin": "IT installed scheduled updates",
    "remote": "IT logged in for routine maintenance",
    "upload": "the nightly backup job",
    "files": "a software update rewrote its own files",
    "tickets": "a new reporting tool asking for service tickets",
    "replication": "a newly added domain controller syncing",
    "payment": "a supplier really did change banks, and confirmed by phone",
    "usb": "{who} plugged in a new keyboard",
}

ATTACK_SIGN = {
    "phishing": "mail", "macro": "mail", "usb-drop": "usb", "insider": "travel",
    "brute-force": "logins", "credential-stuffing": "logins", "password-spray": "logins", "mfa-fatigue": "logins",
    "cloud-takeover": "travel", "port-scan": "scan", "exploit-web": "web", "vpn-exploit": "web",
    "vendor-breach": "remote", "privilege-escalation": "admin", "remote-desktop": "remote",
    "pass-the-hash": "remote", "kerberoasting": "tickets", "dcsync": "replication",
    "exfiltration": "upload", "ransomware": "files", "destruction": "files", "bec": "payment",
}

PERSON_SIGNS = ("mail", "logins", "travel", "payment", "usb")
SERVER_SIGNS = ("scan", "web", "admin", "remote", "upload", "files")


@dataclass
class LogEntry:
    id: int
    day: int
    source: str
    sign: str
    text: str
    target_id: str
    real: bool
    confidence: float
    attack_id: str | None = None
    succeeded: bool = False
    from_outside: bool = False
    innocent_reason: str = ""
    seen: bool = False
    investigated: bool = False


@dataclass
class BlueAction:
    day: int
    kind: str
    target: str
    text: str
    useful: bool


def source_for(attack_id: str, defenses: list) -> tuple[str, float]:
    best = None
    for defense in defenses:
        strength = defense.detects.get(attack_id, 0)
        if strength and (best is None or strength > best[1]):
            best = (defense.name, strength)
    return best or ("Server logs", 0.3)


def real_entry(entry_id: int, day: int, attack, target_id: str, label: str, defenses: list,
               succeeded: bool, from_outside: bool, rng: random.Random) -> LogEntry:
    sign = ATTACK_SIGN.get(attack.id, "admin")
    source, strength = source_for(attack.id, defenses)
    confidence = min(0.95, 0.45 + 0.5 * strength + rng.uniform(-0.1, 0.1))
    return LogEntry(entry_id, day, source, sign, SIGNS[sign].format(who=label, where=label), target_id, True,
                    round(confidence, 2), attack.id, succeeded, from_outside)


def noise_entry(entry_id: int, day: int, company, defenses: list, rng: random.Random) -> LogEntry:
    if rng.random() < 0.5:
        person = rng.choice(company.employees)
        sign = rng.choice(PERSON_SIGNS if company.tier != "small" else ("mail", "logins", "travel"))
        target_id, label = person.id, person.name
    else:
        server = rng.choice(company.servers)
        sign = rng.choice(SERVER_SIGNS)
        target_id, label = server.id, server.name
    watchers = [d.name for d in defenses if d.category == "detect"]
    source = rng.choice(watchers) if watchers and rng.random() < 0.7 else "Server logs"
    confidence = round(rng.uniform(0.15, 0.65), 2)
    return LogEntry(entry_id, day, source, sign, SIGNS[sign].format(who=label, where=label), target_id, False,
                    confidence, innocent_reason=INNOCENT[sign].format(who=label))


def egg_entry(entry_id: int, day: int, company) -> LogEntry:
    server = next((s for s in company.servers if s.role == "file"), company.servers[0])
    text = f"PowerShell started with an encoded command on {server.name}: powershell -NoProfile -enc {EGG_COMMAND}"
    return LogEntry(entry_id, day, "Endpoint detection and response", "admin", text, server.id, False, 0.5,
                    innocent_reason="an old admin script that only prints a message. Nothing harmful ran, but the message may interest you")


def hunt_chance(defense_ids: list[str]) -> float:
    return min(0.95, BASE_HUNT + sum(bonus for d, bonus in HUNT_TOOLS.items() if d in defense_ids))
