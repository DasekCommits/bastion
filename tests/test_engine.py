import pytest

from bastion.catalog import load_catalog
from bastion.company import load_scenario
from bastion.engine import PlanError, Step, detect_chance, heat_gain, run_attack, simulate, success_chance


class Rolls:
    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.99


ALWAYS_WIN = 0.0
NEVER_SEEN = 0.99


@pytest.fixture
def company():
    return load_scenario("olive-byte")


@pytest.fixture
def catalog():
    return load_catalog()


def win_every_step(steps):
    return Rolls(*([ALWAYS_WIN, NEVER_SEEN] * steps))


def test_no_defenses_means_base_chance(catalog):
    assert success_chance(catalog.attacks["phishing"], []) == pytest.approx(0.6)


def test_defenses_stack(catalog):
    defenses = [catalog.defenses["security-training"], catalog.defenses["email-filter"]]
    assert success_chance(catalog.attacks["phishing"], defenses) == pytest.approx(0.12)


def test_no_detection_tools_means_no_direct_detection(catalog):
    assert detect_chance(catalog.attacks["ransomware"], []) == 0


def test_over_budget_is_rejected(company, catalog):
    with pytest.raises(PlanError):
        run_attack(company, catalog, ["edr", "siem", "segmentation", "patching", "mfa", "waf"], [])


def test_unknown_defense_is_rejected(company, catalog):
    with pytest.raises(PlanError):
        run_attack(company, catalog, ["magic-shield"], [])


def test_unknown_target_is_rejected(company, catalog):
    with pytest.raises(PlanError):
        run_attack(company, catalog, [], [Step("phishing", "web-01")])


def test_cannot_escalate_without_a_foothold(company, catalog):
    report = run_attack(company, catalog, [], [Step("privilege-escalation", "db-01")], rng=win_every_step(1))
    assert not report.results[0].possible


def test_cannot_exploit_internal_server(company, catalog):
    report = run_attack(company, catalog, [], [Step("exploit-web", "db-01")], rng=win_every_step(1))
    assert not report.results[0].possible


def test_exploiting_blind_is_harder(company, catalog):
    blind = run_attack(company, catalog, [], [Step("exploit-web", "web-01")], rng=win_every_step(1))
    scanned = run_attack(
        company, catalog, [], [Step("port-scan", "web-01"), Step("exploit-web", "web-01")], rng=win_every_step(2)
    )
    assert blind.results[0].success_chance == pytest.approx(scanned.results[1].success_chance / 2)


def test_phishing_then_stealing_the_database(company, catalog):
    plan = [Step("phishing", "jacob"), Step("exfiltration", "db-01")]
    report = run_attack(company, catalog, [], plan, rng=win_every_step(2))
    assert report.stolen == ["db-01"]
    assert report.points == 26
    assert report.defense_score == 13


def test_admin_intern_can_be_used_for_ransomware(company, catalog):
    plan = [Step("phishing", "sophie"), Step("ransomware", "db-01")]
    report = run_attack(company, catalog, [], plan, rng=win_every_step(2))
    assert report.encrypted == ["db-01"]


def test_least_privilege_takes_admin_away_from_the_intern(company, catalog):
    plan = [Step("phishing", "sophie"), Step("ransomware", "db-01")]
    report = run_attack(company, catalog, ["least-privilege"], plan, rng=win_every_step(2))
    assert not report.results[1].possible
    assert report.encrypted == []


def test_detection_ends_the_attack(company, catalog):
    plan = [Step("phishing", "emily"), Step("exfiltration", "web-01")]
    report = run_attack(company, catalog, ["email-filter"], plan, rng=Rolls(0.0, 0.0))
    assert report.caught
    assert len(report.results) == 1


def test_same_seed_same_result(company, catalog):
    plan = [Step("port-scan", "web-01"), Step("exploit-web", "web-01"), Step("exfiltration", "web-01")]
    first = run_attack(company, catalog, ["waf"], plan, seed=42)
    second = run_attack(company, catalog, ["waf"], plan, seed=42)
    assert [r.succeeded for r in first.results] == [r.succeeded for r in second.results]


def test_defenses_raise_the_average_score(company, catalog):
    plan = [Step("phishing", "sophie"), Step("ransomware", "db-01")]
    weak = simulate(company, catalog, [], plan, runs=500, seed=1)
    strong = simulate(company, catalog, ["least-privilege", "email-filter", "security-training", "edr"], plan, runs=500, seed=1)
    assert strong.average_score > weak.average_score
    assert strong.breach_rate < weak.breach_rate


def test_red_team_budget_is_enforced(company, catalog):
    plan = [Step("ransomware", "db-01")] * 4
    with pytest.raises(PlanError):
        run_attack(company, catalog, [], plan)


def test_heat_builds_up(company, catalog):
    plan = [Step("port-scan", "web-01"), Step("port-scan", "mail")]
    report = run_attack(company, catalog, [], plan, rng=win_every_step(2))
    first, second = report.results
    assert 0 < first.heat < second.heat
    assert first.detect_chance > 0


def test_repeating_an_attack_raises_heat_faster(catalog):
    phishing = catalog.attacks["phishing"]
    assert heat_gain(phishing, [], 2) > heat_gain(phishing, [], 0)


def test_watchers_make_heat_rise_faster(catalog):
    phishing = catalog.attacks["phishing"]
    watchers = [catalog.defenses["siem"], catalog.defenses["edr"]]
    assert heat_gain(phishing, watchers, 0) == pytest.approx(3 * heat_gain(phishing, [], 0))


def test_spamming_phishing_gets_you_caught(company, catalog):
    everyone = [Step("phishing", e) for e in ("emily", "george", "jacob", "maria", "sophie")]
    spam = simulate(company, catalog, [], everyone, runs=500, seed=3)
    single = simulate(company, catalog, [], everyone[:1], runs=500, seed=3)
    assert spam.caught_rate > single.caught_rate + 0.3
