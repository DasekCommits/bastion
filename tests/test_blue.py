import pytest

from bastion.catalog import load_catalog
from bastion.company import load_scenario
from bastion.engine import Campaign, PlanError


class Rolls:
    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.99

    def uniform(self, a, b):
        return (a + b) / 2

    def choice(self, items):
        return items[0]


class FirstDay:
    def random(self):
        return 0.0

    def randint(self, low, high):
        return low


@pytest.fixture
def company():
    return load_scenario("olive-byte")


@pytest.fixture
def catalog():
    return load_catalog()


def active(company, catalog, defenses, arsenal, *rolls):
    import random

    company.red_budget = 200
    campaign = Campaign(company, catalog, defenses, arsenal, rng=random.Random(1), active_blue=True)
    campaign.rng = Rolls(*rolls)
    return campaign


def test_detection_only_writes_a_log_nobody_is_kicked(company, catalog):
    campaign = active(company, catalog, ["siem"], ["phishing"], 0.0, 0.0)
    result = campaign.move("phishing", "emily")
    assert result.succeeded and result.detected
    assert not campaign.caught and "emily" in campaign.foothold.employees
    assert any(entry.real for entry in campaign.unseen_logs())


def test_blue_must_look_at_the_logs_before_investigating(company, catalog):
    campaign = active(company, catalog, ["siem"], ["phishing"], 0.0, 0.0)
    campaign.move("phishing", "emily")
    real = next(entry for entry in campaign.logs if entry.real)
    with pytest.raises(PlanError):
        campaign.blue("investigate", real.id)
    campaign.blue("logs")
    action = campaign.blue("investigate", real.id)
    assert action.useful and "Phishing" in action.text


def test_false_alarms_are_explained(company, catalog):
    campaign = active(company, catalog, [], ["phishing"])
    campaign.blue("logs")
    noise = next(entry for entry in campaign.logs if not entry.real)
    action = campaign.blue("investigate", noise.id)
    assert not action.useful and action.text.startswith("False alarm")


def test_changing_the_password_kicks_the_attacker_out(company, catalog):
    campaign = active(company, catalog, [], ["phishing"], 0.0, 0.99)
    campaign.move("phishing", "emily")
    assert campaign.foothold.servers == {"web-01", "mail"}
    action = campaign.blue("reset", "emily")
    assert action.useful
    assert campaign.foothold.is_empty() and campaign.caught and campaign.kicked_out


def test_resetting_a_clean_account_costs_disruption(company, catalog):
    campaign = active(company, catalog, [], ["phishing"])
    action = campaign.blue("reset", "maria")
    assert not action.useful and campaign.disruption == 1


def test_isolating_a_server_cuts_off_access_through_accounts(company, catalog):
    campaign = active(company, catalog, [], ["phishing", "exfiltration"], 0.0, 0.99)
    campaign.move("phishing", "jacob")
    campaign.blue("isolate", "db-01")
    assert "db-01" not in campaign.foothold.servers
    assert not campaign.preview("exfiltration", "db-01").possible
    campaign.end_day()
    campaign.end_day()
    assert campaign.preview("exfiltration", "db-01").possible


def test_password_reset_keeps_access_gained_another_way(company, catalog):
    campaign = active(company, catalog, [], ["phishing", "exfiltration"], 0.0, 0.99, 0.0, 0.99)
    campaign.move("phishing", "emily")
    campaign.move("exfiltration", "web-01")
    assert "db-01" in campaign.foothold.servers
    campaign.blue("reset", "emily")
    assert campaign.foothold.servers == {"db-01"}
    assert not campaign.caught


def test_blocking_an_outside_attempt_burns_it(company, catalog):
    campaign = active(company, catalog, ["email-filter"], ["phishing"], 0.99, 0.0)
    campaign.move("phishing", "emily")
    campaign.blue("logs")
    real = next(entry for entry in campaign.logs if entry.real)
    assert campaign.blue("block", real.id).useful
    assert not campaign.preview("phishing", "emily").possible


def test_blue_has_limited_time(company, catalog):
    campaign = active(company, catalog, [], ["phishing"])
    for _ in range(campaign.blue_moves_per_day):
        campaign.blue("logs")
    with pytest.raises(PlanError):
        campaign.blue("logs")
    campaign.end_day()
    assert campaign.blue_moves_left == campaign.blue_moves_per_day


def test_no_night_hunt_without_a_soc(company, catalog):
    campaign = active(company, catalog, ["siem", "edr"], ["phishing"], 0.0, 0.99, 0.0)
    campaign.move("phishing", "emily")
    campaign.heat = 1.0
    night = campaign.end_day()
    assert night.hunt_chance == 0 and not campaign.caught


def test_the_bank_logs_can_hide_the_clearance_message(catalog):
    import base64
    import random

    from bastion import soc

    bank = load_scenario("meridian-bank")
    old, old_rng = soc.EGG_CHANCE, soc.EGG_RNG
    soc.EGG_CHANCE, soc.EGG_RNG = 1.0, FirstDay()
    try:
        campaign = Campaign(bank, catalog, [], ["phishing"], rng=random.Random(1), active_blue=True)
    finally:
        soc.EGG_CHANCE, soc.EGG_RNG = old, old_rng
    egg = next(e for e in campaign.logs if "-enc" in e.text)
    encoded = egg.text.rsplit(" ", 1)[1]
    assert base64.b64decode(encoded).decode("utf-16-le").startswith("CLEARANCE:")
    assert not egg.real


def test_sealed_file_is_planted_only_in_bank_hard():
    import random

    from bastion.clearance import SEALED_ID, plant_sealed_file

    bank = load_scenario("meridian-bank")
    always = random.Random(0)
    always.random = lambda: 0.0
    assert any(a.id == SEALED_ID for a in plant_sealed_file(bank, "hard", always).data)
    assert not any(a.id == SEALED_ID for a in plant_sealed_file(bank, "medium", always).data)
    assert not any(a.id == SEALED_ID for a in bank.data)


def test_stealing_the_sealed_file_counts_toward_realism(catalog):
    import random

    from bastion.clearance import SEALED_ID, plant_sealed_file, record_secrets
    from bastion.profile import Profile

    always = random.Random(0)
    always.random = lambda: 0.0
    bank = plant_sealed_file(load_scenario("meridian-bank"), "hard", always)
    vault = next(a.location for a in bank.data if a.id == SEALED_ID)
    bank.red_budget = 500
    campaign = Campaign(bank, catalog, [], ["phishing", "exfiltration"], rng=random.Random(1), active_blue=True)
    campaign.rng = Rolls(0.0, 0.99, 0.0, 0.99)
    campaign.move("phishing", "sofia")
    result = campaign.move("exfiltration", vault)
    assert "not on any inventory" in result.note
    profile = Profile(secrets={"sealed": 9})
    assert not profile.realism_open()
    notes = record_secrets(campaign, profile, "hard", "red")
    assert notes and "10/10" in notes[0] and profile.realism_open()


def test_isolating_the_talking_script_counts_toward_clearance(catalog):
    import random

    from bastion import soc
    from bastion.clearance import record_secrets
    from bastion.profile import Profile

    bank = load_scenario("meridian-bank")
    old, old_rng = soc.EGG_CHANCE, soc.EGG_RNG
    soc.EGG_CHANCE, soc.EGG_RNG = 1.0, FirstDay()
    try:
        campaign = Campaign(bank, catalog, [], ["phishing"], rng=random.Random(2), active_blue=True)
    finally:
        soc.EGG_CHANCE, soc.EGG_RNG = old, old_rng
    egg = next(e for e in campaign.logs if "-enc" in e.text)
    campaign.blue("isolate", egg.target_id)
    profile = Profile(secrets={"sealed": 10, "script": 2})
    notes = record_secrets(campaign, profile, "hard", "blue")
    assert notes and "3/3" in notes[0] and profile.cleared()
    assert record_secrets(campaign, Profile(), "medium", "blue") == []
