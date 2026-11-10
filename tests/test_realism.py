import random

import pytest

from bastion.catalog import load_catalog
from bastion.company import load_scenario
from bastion.engine import Campaign
from bastion.realism.game import RealismGame


class Rolls:
    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.99

    def uniform(self, a, b):
        return (a + b) / 2

    def choice(self, items):
        return items[0]


@pytest.fixture
def game():
    company = load_scenario("olive-byte")
    company.red_budget = 300
    company.budget = 300
    catalog = load_catalog()
    campaign = Campaign(company, catalog, ["siem", "edr", "email-filter"],
                        ["port-scan", "brute-force", "phishing", "exfiltration"],
                        rng=random.Random(1), active_blue=True)
    return RealismGame(campaign, random.Random(2))


def test_world_has_real_looking_addresses(game):
    world = game.world
    assert world.attacker_ip.startswith("203.0.113.")
    assert all(h.ip.startswith("10.10.1.") for h in world.hosts.values())
    assert any(h.public_ip and h.public_ip.startswith("198.51.100.") for h in world.hosts.values())
    assert world.accounts["maria"].email.endswith(".example")


def test_normal_day_has_plenty_of_noise(game):
    result = game.search("index=security EventCode=4624 | stats count")
    assert result["rows"][0]["count"] >= len(game.world.accounts)
    assert game.search("index=web | stats count")["rows"][0]["count"] > 5


def test_brute_force_shows_up_as_many_failures_from_one_address(game):
    game.campaign.rng = Rolls(0.0, 0.99)
    game.red_move("brute-force", "maria")
    rows = game.search("index=security EventCode=4625 | stats count by src_ip | sort -count | head 1")["rows"]
    assert rows[0]["src_ip"] == game.world.attacker_ip and rows[0]["count"] >= 40
    success = game.search(f"EventCode=4624 src_ip={game.world.attacker_ip}")
    assert success["total"] == 1


def test_phishing_leaves_a_mail_and_an_encoded_powershell(game):
    game.campaign.rng = Rolls(0.0, 0.99)
    game.red_move("phishing", "emily")
    assert game.search("index=mail attachment=*.html")["total"] == 1
    assert game.search('index=sysmon ParentImage=*WINWORD.EXE "-enc"')["total"] == 1


def test_visibility_depends_on_defenses():
    company = load_scenario("olive-byte")
    campaign = Campaign(company, load_catalog(), [], ["port-scan"], rng=random.Random(1), active_blue=True)
    blind = RealismGame(campaign, random.Random(3))
    assert set(blind.search("*")["indexes"]) == {"firewall", "web"}
    assert blind.search("index=security")["total"] == 0


def test_blocking_the_attacker_ip_stops_outside_attempts(game):
    text = game.block_ip(game.world.attacker_ip)
    assert "Every attempt" in text
    assert not game.campaign.preview("phishing", "emily").possible


def test_blocking_a_customer_costs_disruption(game):
    game.block_ip(game.world.noise_ips[0])
    assert game.campaign.disruption == 1


def test_disable_and_isolate_by_real_names(game):
    game.campaign.rng = Rolls(0.0, 0.99)
    game.red_move("phishing", "emily")
    db = game.world.hosts["db-01"].hostname
    assert "offline" in game.isolate(db)
    assert "lost" in game.disable_account("emily")
    assert game.campaign.kicked_out


def test_footprint_shows_the_logs_a_move_just_created(game):
    game.campaign.rng = Rolls(0.0, 0.99)
    game.red_move("brute-force", "maria")
    lines = game.footprint_lines()
    assert lines and any("security/" in line and "4625" in line for line in lines)
    assert all(line.startswith("  ") for line in lines)


def test_footprint_marks_what_defenders_cannot_see():
    import random

    from bastion.catalog import load_catalog
    from bastion.company import load_scenario
    from bastion.engine import Campaign

    company = load_scenario("olive-byte")
    company.red_budget = 300
    campaign = Campaign(company, load_catalog(), [], ["phishing"], rng=random.Random(1), active_blue=True)
    blind = RealismGame(campaign, random.Random(1))
    blind.campaign.rng = Rolls(0.0, 0.99)
    blind.red_move("phishing", "emily")
    assert any("not watching" in line for line in blind.footprint_lines())
