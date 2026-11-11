from bastion.catalog import load_catalog
from bastion.company import load_scenario
from bastion.engine import Campaign

CATALOG = load_catalog()
BANK = load_scenario("meridian-bank")


def campaign(defenses=(), arsenal=("lsass-dump", "golden-ticket", "inhibit-recovery", "ransomware")):
    return Campaign(BANK, CATALOG, list(defenses), list(arsenal), seed=1, active_blue=True)


def dc():
    return next(s.id for s in BANK.servers if s.role == "domain-controller")


def test_lsass_dump_needs_admin_and_hands_over_the_accounts_that_log_in_there():
    c = campaign()
    server = next(s.id for s in BANK.servers if sum(server_id == s.id for e in BANK.employees for server_id in e.access) > 1)
    c.foothold.gain(server)
    assert not c.preview("lsass-dump", server).possible
    c.foothold.make_admin(server)
    assert c.preview("lsass-dump", server).possible
    from bastion.engine import _apply
    _apply(CATALOG.attacks["lsass-dump"], server, BANK, c.foothold, [])
    assert {e.id for e in BANK.employees if server in e.access} <= c.foothold.employees


def test_golden_ticket_only_on_the_domain_controller_with_admin():
    c = campaign()
    other = next(s.id for s in BANK.servers if s.role != "domain-controller")
    c.foothold.gain(other, admin=True)
    assert not c.preview("golden-ticket", other).possible
    assert not c.preview("golden-ticket", dc()).possible
    c.foothold.gain(dc(), admin=True)
    assert c.preview("golden-ticket", dc()).possible


def test_deleting_backups_beats_normal_backups_but_not_immutable_ones():
    target = next(s.id for s in BANK.servers if s.role == "database")
    plain, plain_gone = campaign(["backups"]), campaign(["backups"])
    hard_gone = campaign(["immutable-backups"])
    for c in (plain, plain_gone, hard_gone):
        c.foothold.gain(target, admin=True)
    plain_gone.foothold.no_recovery.add(target)
    hard_gone.foothold.no_recovery.add(target)
    assert plain_gone.preview("ransomware", target).success_chance > plain.preview("ransomware", target).success_chance
    assert hard_gone.preview("ransomware", target).success_chance < plain_gone.preview("ransomware", target).success_chance


def test_every_new_attack_has_a_counter_and_every_new_defense_counters_something():
    new_attacks = ["session-hijack", "aitm-phishing", "helpdesk-vishing", "oauth-consent", "rmm-abuse",
                   "lsass-dump", "golden-ticket", "cloud-exfil", "dns-tunnel", "inhibit-recovery"]
    for a in new_attacks:
        assert any(d.blocks.get(a) or d.detects.get(a) for d in CATALOG.defenses.values()), a
    for d in CATALOG.defenses.values():
        assert all(a in CATALOG.attacks for a in list(d.blocks) + list(d.detects)), d.id


def test_every_attack_has_a_realism_terminal_verb():
    from bastion.realism.terminal import VERBS
    assert set(CATALOG.attacks) <= set(VERBS.values())
    assert len(VERBS) == len(set(VERBS.values()))


def test_new_verbs_work_in_the_terminal():
    import json
    from bastion.web import Session
    session = Session()
    session.start("meridian-bank", "realism", "red", 3)
    session.set_arsenal(json.dumps(["session-hijack", "cloud-exfil"]))
    session.begin()
    help_text = "\n".join(json.loads(session.terminal("help"))["lines"])
    assert "hijack" in help_text and "upload" in help_text
    user = next(iter(session.real.world.accounts.values())).username
    reply = json.loads(session.terminal(f"hijack {user}"))
    assert reply["lines"] and not any("Unknown command" in line for line in reply["lines"])
