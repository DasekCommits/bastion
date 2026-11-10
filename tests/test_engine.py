import pytest

from bastion.catalog import load_catalog
from bastion.company import load_scenario
from bastion.engine import (
    Campaign,
    PlanError,
    Step,
    detect_chance,
    heat_gain,
    run_attack,
    simulate,
    success_chance,
)


class Rolls:
    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.99


ALWAYS_WIN = 0.0
NEVER_SEEN = 0.99


@pytest.fixture
def company():
    company = load_scenario("olive-byte")
    company.employee("sophie").is_admin = True
    return company


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


def test_cannot_reach_internal_server_from_outside(company, catalog):
    report = run_attack(company, catalog, [], [Step("port-scan", "db-01")], rng=win_every_step(1))
    assert not report.results[0].possible


def test_web_exploit_only_targets_web_servers(company, catalog):
    with pytest.raises(PlanError):
        run_attack(company, catalog, [], [Step("exploit-web", "db-01")], rng=win_every_step(1))


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
    assert report.defense_score == 26


def test_admin_intern_can_be_used_for_ransomware(company, catalog):
    plan = [Step("phishing", "sophie"), Step("ransomware", "db-01")]
    report = run_attack(company, catalog, [], plan, rng=win_every_step(2))
    assert report.encrypted == ["db-01"]


def test_least_privilege_takes_admin_away_from_the_intern(company, catalog):
    plan = [Step("phishing", "sophie"), Step("ransomware", "db-01")]
    report = run_attack(company, catalog, ["least-privilege"], plan, rng=win_every_step(2))
    assert not report.results[1].possible
    assert report.encrypted == []


def test_detection_inside_ends_the_attack(company, catalog):
    plan = [Step("phishing", "emily"), Step("exfiltration", "web-01"), Step("exfiltration", "web-01")]
    report = run_attack(company, catalog, ["siem"], plan, rng=Rolls(ALWAYS_WIN, NEVER_SEEN, ALWAYS_WIN, 0.0))
    assert report.caught
    assert len(report.results) == 2


def test_detection_outside_only_blocks_that_attempt(company, catalog):
    campaign = Campaign(company, catalog, ["email-filter"], ["phishing"], rng=Rolls(ALWAYS_WIN, 0.0))
    result = campaign.move("phishing", "emily")
    assert result.detected and not result.kicked and not campaign.caught
    assert campaign.foothold.is_empty()
    assert not campaign.preview("phishing", "emily").possible
    assert campaign.preview("phishing", "george").possible


def test_night_hunt_cannot_find_someone_who_is_not_inside(company, catalog):
    campaign = Campaign(company, catalog, ["siem", "edr"], ["port-scan"], rng=Rolls(ALWAYS_WIN, NEVER_SEEN, 0.0))
    campaign.heat = 0.9
    campaign.end_day()
    assert not campaign.caught


def test_insider_depends_on_loyalty(catalog):
    clinic = load_scenario("harbor-clinic")
    campaign = Campaign(clinic, catalog, [], ["insider"], seed=1)
    assert campaign.preview("insider", "dan").success_chance > 3 * campaign.preview("insider", "helen").success_chance


def test_at_most_one_accidental_admin(company):
    import random

    from bastion.company import roll_mistakes

    rng = random.Random(4)
    for _ in range(300):
        rolled = roll_mistakes(company, rng)
        assert sum(e.is_admin and not e.needs_admin for e in rolled.employees) <= 1


def test_same_seed_same_result(company, catalog):
    plan = [Step("port-scan", "web-01"), Step("exploit-web", "web-01"), Step("exploit-web", "web-01")]
    first = run_attack(company, catalog, ["waf"], plan, seed=42)
    second = run_attack(company, catalog, ["waf"], plan, seed=42)
    assert [r.succeeded for r in first.results] == [r.succeeded for r in second.results]


def test_defenses_raise_the_average_score(company, catalog):
    plan = [Step("phishing", "sophie"), Step("ransomware", "db-01")]
    weak = simulate(company, catalog, [], plan, runs=500, seed=1)
    strong = simulate(company, catalog, ["least-privilege", "email-filter", "security-training", "mfa"], plan, runs=500, seed=1)
    assert strong.average_score > weak.average_score
    assert strong.breach_rate < weak.breach_rate


def test_red_team_budget_is_enforced(company, catalog):
    arsenal = ["ransomware", "exploit-web", "privilege-escalation", "exfiltration", "phishing", "port-scan"]
    with pytest.raises(PlanError):
        Campaign(company, catalog, [], arsenal)


def test_reusing_an_attack_costs_no_extra_budget(company, catalog):
    plan = [Step("phishing", "emily", 1), Step("phishing", "george", 2), Step("phishing", "jacob", 3)]
    report = run_attack(company, catalog, [], plan, rng=win_every_step(3))
    assert report.red_budget_used == 10


def test_campaign_plays_one_move_at_a_time(company, catalog):
    campaign = Campaign(company, catalog, ["mfa"], ["phishing", "exfiltration"], rng=win_every_step(2))
    first = campaign.move("phishing", "jacob")
    assert first.succeeded
    assert campaign.preview("exfiltration", "db-01").possible
    campaign.end_day()
    assert campaign.day == 2
    campaign.move("exfiltration", "db-01")
    assert campaign.report().points == 26


def test_campaign_rejects_attacks_outside_the_arsenal(company, catalog):
    campaign = Campaign(company, catalog, [], ["phishing"])
    with pytest.raises(PlanError):
        campaign.move("ransomware", "db-01")


def test_campaign_limits_moves_per_day(company, catalog):
    campaign = Campaign(company, catalog, [], ["port-scan"], rng=win_every_step(3))
    for _ in range(3):
        campaign.move("port-scan", "web-01")
    with pytest.raises(PlanError):
        campaign.move("port-scan", "web-01")


def test_campaign_ends_after_the_last_day(company, catalog):
    campaign = Campaign(company, catalog, [], ["port-scan"])
    for _ in range(company.max_days):
        campaign.end_day()
    assert campaign.finished
    assert campaign.day == company.max_days


def test_preview_shows_impossible_moves(company, catalog):
    campaign = Campaign(company, catalog, [], ["ransomware"])
    assert not campaign.preview("ransomware", "db-01").possible


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
    people = ("emily", "george", "jacob", "maria", "sophie")
    everyone = [Step("phishing", person, day) for person, day in zip(people, (1, 1, 1, 2, 2))]
    spam = simulate(company, catalog, [], everyone, runs=500, seed=3)
    single = simulate(company, catalog, [], everyone[:1], runs=500, seed=3)
    assert spam.caught_rate > single.caught_rate + 0.3


def test_too_many_moves_in_one_day(company, catalog):
    with pytest.raises(PlanError):
        run_attack(company, catalog, [], [Step("port-scan", "web-01")] * 4)


def test_attack_must_fit_in_the_days(company, catalog):
    with pytest.raises(PlanError):
        run_attack(company, catalog, [], [Step("port-scan", "web-01", day=6)])


def test_days_must_be_in_order(company, catalog):
    with pytest.raises(PlanError):
        run_attack(company, catalog, [], [Step("port-scan", "web-01", 2), Step("port-scan", "mail", 1)])


def test_heat_cools_down_overnight(company, catalog):
    plan = [Step("port-scan", "web-01", 1), Step("port-scan", "mail", 3)]
    report = run_attack(company, catalog, [], plan, rng=win_every_step(2))
    assert len(report.nights) == 2
    assert report.nights[1].heat_after < report.nights[0].heat_before
    assert report.days_used == 3


def test_nobody_hunts_without_detection_tools(company, catalog):
    plan = [Step("port-scan", "web-01", 1), Step("port-scan", "mail", 2)]
    report = run_attack(company, catalog, [], plan, rng=win_every_step(2))
    assert report.nights[0].hunt_chance == 0


def test_night_hunt_can_catch_the_attacker(company, catalog):
    plan = [Step("brute-force", "emily", 1), Step("exfiltration", "web-01", 2)]
    report = run_attack(company, catalog, ["siem"], plan, rng=Rolls(0.0, 0.99, 0.0))
    assert report.nights[0].found
    assert report.caught
    assert len(report.results) == 1


def test_waiting_lowers_the_heat(company, catalog):
    loud = [Step("brute-force", "emily", 1), Step("brute-force", "george", 1), Step("exfiltration", "office-pc", 1)]
    patient = [Step("brute-force", "emily", 1), Step("brute-force", "george", 3), Step("exfiltration", "office-pc", 5)]
    fast = run_attack(company, catalog, [], loud, rng=win_every_step(3))
    slow = run_attack(company, catalog, [], patient, rng=win_every_step(3))
    assert slow.results[-1].heat < fast.results[-1].heat


def test_careful_people_are_harder_to_phish(company, catalog):
    campaign = Campaign(company, catalog, [], ["phishing", "brute-force"], seed=1)
    maria = company.employee("maria")
    maria.awareness, maria.password_hygiene = 0.5, 1.0
    careless = company.employee("emily")
    careless.awareness = 0.0
    assert campaign.preview("phishing", "maria").success_chance == pytest.approx(
        campaign.preview("phishing", "emily").success_chance / 2
    )
    assert campaign.preview("brute-force", "maria").success_chance == pytest.approx(0.05)


def test_advice_points_at_missing_defense_and_unused_attack(company, catalog):
    from bastion.advice import blue_tips, red_tips

    campaign = Campaign(company, catalog, [], ["phishing", "ransomware"], rng=Rolls(ALWAYS_WIN, NEVER_SEEN))
    campaign.move("phishing", "sophie")
    blue = " ".join(blue_tips(campaign))
    red = " ".join(red_tips(campaign))
    assert "would have cut Phishing email" in blue
    assert "Least privilege" in blue
    assert "never used it" in red


def test_stealing_the_shop_config_opens_the_database(company, catalog):
    campaign = Campaign(company, catalog, [], ["phishing", "exfiltration"], rng=win_every_step(3))
    campaign.move("phishing", "emily")
    assert "db-01" not in campaign.foothold.servers
    result = campaign.move("exfiltration", "web-01")
    assert result.points == 5
    assert "db-01" in campaign.foothold.servers
    assert campaign.move("exfiltration", "db-01").points == 26


def test_segmentation_makes_the_stolen_password_useless(company, catalog):
    campaign = Campaign(company, catalog, ["segmentation"], ["phishing", "exfiltration"], rng=win_every_step(2))
    campaign.move("phishing", "emily")
    result = campaign.move("exfiltration", "web-01")
    assert "segmentation" in result.note
    assert "db-01" not in campaign.foothold.servers


def test_stealing_twice_gives_no_extra_points(company, catalog):
    campaign = Campaign(company, catalog, [], ["phishing", "exfiltration"], rng=win_every_step(3))
    campaign.move("phishing", "emily")
    campaign.move("exfiltration", "web-01")
    assert campaign.move("exfiltration", "web-01").points == 0


def test_scan_reveals_only_outside_defenses(company, catalog):
    campaign = Campaign(company, catalog, ["waf", "rate-limiting", "patching"], ["port-scan"], rng=win_every_step(1))
    result = campaign.move("port-scan", "web-01")
    assert "Web application firewall" in result.note or "WAF" in result.note
    assert campaign.known_defenses == {"waf", "patching"}


def test_scanning_the_mail_login_helps_password_attacks(company, catalog):
    campaign = Campaign(company, catalog, [], ["port-scan", "brute-force"], rng=win_every_step(1))
    before = campaign.preview("brute-force", "maria").success_chance
    campaign.move("port-scan", "mail")
    assert campaign.preview("brute-force", "maria").success_chance == pytest.approx(before * 1.5)


def test_edr_is_noticed_once_inside(company, catalog):
    campaign = Campaign(company, catalog, ["edr"], ["phishing"], rng=win_every_step(1))
    result = campaign.move("phishing", "emily")
    assert "Endpoint" in result.note or "EDR" in result.note
    assert "edr" in campaign.known_defenses


def test_accidental_admin_changes_between_games(company):
    import random

    from bastion.company import roll_mistakes

    rolls = {roll_mistakes(company, random.Random(seed)).employee("sophie").is_admin for seed in range(30)}
    assert rolls == {True, False}
    assert all(roll_mistakes(company, random.Random(s)).employee("maria").is_admin for s in range(10))


def test_clinic_loads_with_medium_attacks(catalog):
    clinic = load_scenario("harbor-clinic")
    assert clinic.tier == "medium"
    medium = {attack.id for attack in catalog.attacks_for("medium")}
    small = {attack.id for attack in catalog.attacks_for("small")}
    assert {"vpn-exploit", "macro", "usb-drop", "insider", "destruction"} <= medium - small


def test_vpn_users_open_the_file_server(catalog):
    clinic = load_scenario("harbor-clinic")
    campaign = Campaign(clinic, catalog, [], ["port-scan", "vpn-exploit", "exfiltration"], rng=win_every_step(3))
    campaign.move("port-scan", "vpn")
    campaign.move("vpn-exploit", "vpn")
    result = campaign.move("exfiltration", "vpn")
    assert "files" in campaign.foothold.servers and result.points == 2


@pytest.fixture
def bank():
    return load_scenario("meridian-bank")


def test_kerberoasting_needs_a_foothold_and_opens_the_databases(bank, catalog):
    campaign = Campaign(bank, catalog, [], ["phishing", "kerberoasting"], rng=win_every_step(2))
    assert not campaign.preview("kerberoasting", "dc").possible
    campaign.move("phishing", "jenny")
    campaign.move("kerberoasting", "dc")
    assert {"core", "hr"} <= campaign.foothold.admin_on


def test_domain_takeover_path(bank, catalog):
    arsenal = ["phishing", "kerberoasting", "pass-the-hash", "dcsync"]
    campaign = Campaign(bank, catalog, [], arsenal, rng=win_every_step(4))
    campaign.move("phishing", "jenny")
    assert not campaign.preview("pass-the-hash", "dc").possible
    campaign.move("kerberoasting", "dc")
    campaign.move("pass-the-hash", "dc")
    assert campaign.preview("dcsync", "dc").possible
    campaign.end_day()
    campaign.move("dcsync", "dc")
    assert campaign.foothold.admin_on == {server.id for server in bank.servers}


def test_bec_only_hits_finance_and_pays_once(bank, catalog):
    campaign = Campaign(bank, catalog, [], ["bec"], rng=win_every_step(2))
    assert not campaign.preview("bec", "jenny").possible
    result = campaign.move("bec", "paul")
    assert result.points == 8
    assert campaign.encrypted == []
    assert not campaign.preview("bec", "irene").possible


def test_stealing_from_payments_does_not_include_the_fraud_money(bank, catalog):
    campaign = Campaign(bank, catalog, [], ["phishing", "exfiltration"], rng=win_every_step(2))
    campaign.move("phishing", "paul")
    assert campaign.move("exfiltration", "payments").points == 5


def test_edge_makes_attacks_easier(company, catalog):
    normal = Campaign(company, catalog, [], ["phishing"], seed=1)
    easier = Campaign(company, catalog, [], ["phishing"], seed=1, edge=1.5)
    assert easier.preview("phishing", "emily").success_chance > normal.preview("phishing", "emily").success_chance


def test_no_chance_goes_below_five_or_above_ninety_five_percent(company, catalog):
    every_defense = list(catalog.defenses)
    company.budget = 10_000
    walled = Campaign(company, catalog, every_defense, ["phishing"], seed=1)
    preview = walled.preview("phishing", "emily")
    assert preview.success_chance == pytest.approx(0.05)
    assert preview.detect_chance <= 0.95
    open_door = Campaign(company, catalog, [], ["phishing"], seed=1, edge=50)
    preview = open_door.preview("phishing", "emily")
    assert preview.success_chance == pytest.approx(0.95)
    assert preview.detect_chance == pytest.approx(0.05)


def test_a_big_edge_keeps_careful_people_harder_to_phish(company, catalog):
    campaign = Campaign(company, catalog, [], ["phishing"], seed=1, edge=6)
    maria = campaign.preview("phishing", "maria").success_chance
    emily = campaign.preview("phishing", "emily").success_chance
    assert maria < emily < 0.95


def test_advice_only_suggests_defenses_the_company_can_buy(company, catalog):
    from bastion.advice import blue_tips

    campaign = Campaign(company, catalog, [], ["phishing"], rng=Rolls(ALWAYS_WIN, NEVER_SEEN))
    result = campaign.move("phishing", "emily")
    small = {d.id for d in catalog.defenses_for("small")}
    assert set(result.missing) <= small
    assert "Phishing-resistant" not in " ".join(blue_tips(campaign))


def test_stealing_then_encrypting_counts_the_data_once(company, catalog):
    company.red_budget = 100
    campaign = Campaign(company, catalog, [], ["phishing", "exfiltration", "ransomware"], rng=win_every_step(3))
    campaign.move("phishing", "sophie")
    assert campaign.move("exfiltration", "db-01").points == 26
    second = campaign.move("ransomware", "db-01")
    assert second.points == 0 and "only counts once" in second.note
    report = campaign.report()
    assert report.points <= report.max_points
