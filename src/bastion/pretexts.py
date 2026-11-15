"""Phishing stories: the email you send has to fit the person who reads it.

An unpaid invoice works on someone who pays invoices, a CV works on HR, and a prize
draw fools almost nobody at work. Each story multiplies the phishing chance by how
well it fits the target's job. No story chosen means no change.
"""
PHISHING = ("phishing", "aitm-phishing")

PRETEXTS = {
    "invoice": "Unpaid invoice, pay today",
    "resume": "Job application, CV attached",
    "password": "IT: your password expires today",
    "delivery": "Missed parcel delivery",
    "update": "Security update for your tools",
    "prize": "You won a prize",
}

FIT = {
    "finance": {"invoice": 1.35, "resume": .8, "password": 1.0, "delivery": 1.0, "update": .9, "prize": .4},
    "hr": {"invoice": .9, "resume": 1.4, "password": 1.0, "delivery": 1.0, "update": .9, "prize": .45},
    "executive": {"invoice": 1.2, "resume": .9, "password": .9, "delivery": 1.15, "update": .9, "prize": .5},
    "it": {"invoice": .7, "resume": .8, "password": .5, "delivery": .9, "update": .8, "prize": .35},
    "dev": {"invoice": .7, "resume": .8, "password": .7, "delivery": .95, "update": 1.2, "prize": .4},
    "support": {"invoice": .9, "resume": .9, "password": 1.25, "delivery": 1.1, "update": 1.0, "prize": .55},
    "front": {"invoice": 1.0, "resume": .9, "password": 1.1, "delivery": 1.3, "update": 1.0, "prize": .6},
    "health": {"invoice": .8, "resume": .9, "password": 1.2, "delivery": 1.15, "update": 1.0, "prize": .55},
    "junior": {"invoice": .8, "resume": .8, "password": 1.15, "delivery": 1.1, "update": 1.0, "prize": .9},
    "security": {"invoice": .5, "resume": .5, "password": .4, "delivery": .5, "update": .5, "prize": .3},
    "other": {"invoice": 1.0, "resume": .9, "password": 1.05, "delivery": 1.05, "update": 1.0, "prize": .5},
}

DEPARTMENTS = {
    "finance": "finance", "hr": "hr", "executive": "executive", "it": "it", "dev": "dev", "support": "support",
    "reception": "front", "retail": "front", "security": "security", "legal": "executive", "marketing": "other",
    "vendor": "it", "casework": "other", "comms": "other", "field": "other", "records": "other",
}

ROLE_WORDS = (
    ("security", "security"), ("accountant", "finance"), ("billing", "finance"), ("finance", "finance"), ("payable", "finance"),
    ("treasury", "finance"), ("hr ", "hr"), ("owner", "executive"), ("director", "executive"), ("chief", "executive"),
    ("manager", "executive"), ("developer", "dev"), ("administrator", "it"), ("it ", "it"), ("contractor", "it"),
    ("helpdesk", "it"), ("support", "support"), ("receptionist", "front"), ("front desk", "front"), ("nurse", "health"),
    ("physician", "health"), ("radiologist", "health"), ("intern", "junior"), ("student", "junior"),
)


def group_of(employee) -> str:
    department = (getattr(employee, "department", "") or "").lower()
    if department in DEPARTMENTS:
        return DEPARTMENTS[department]
    role = f"{employee.role.lower()} "
    for word, group in ROLE_WORDS:
        if word in role:
            return group
    return "other"


def factor(attack_id: str, employee, pretext: str | None) -> float:
    if not pretext or attack_id not in PHISHING:
        return 1.0
    if pretext not in PRETEXTS:
        raise ValueError(f"Unknown phishing story '{pretext}'")
    return FIT[group_of(employee)][pretext]


def fit_word(value: float) -> str:
    if value >= 1.2:
        return "fits their job"
    if value >= .95:
        return "could work"
    if value >= .7:
        return "a stretch"
    return "they will see through it"
