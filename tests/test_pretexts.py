import json

from bastion import pretexts
from bastion.company import Employee
from bastion.web import Session


def person(role, department=""):
    return Employee(id="x", name="X", role=role, is_admin=False, access=[], department=department)


def test_the_story_has_to_fit_the_job():
    accountant, hr, admin = person("Accountant"), person("HR Assistant", "hr"), person("IT Administrator")
    assert pretexts.factor("phishing", accountant, "invoice") > 1.2
    assert pretexts.factor("phishing", accountant, "prize") < .5
    assert pretexts.factor("phishing", hr, "resume") > pretexts.factor("phishing", hr, "invoice")
    assert pretexts.factor("phishing", admin, "password") < 1


def test_no_story_or_another_attack_changes_nothing():
    accountant = person("Accountant")
    assert pretexts.factor("phishing", accountant, None) == 1.0
    assert pretexts.factor("brute-force", accountant, "invoice") == 1.0


def test_every_group_rates_every_story():
    for group, row in pretexts.FIT.items():
        assert set(row) == set(pretexts.PRETEXTS), group


def _red_game():
    session = Session()
    session.start("olive-byte", "easy", "red", 7)
    session.set_arsenal(json.dumps(["phishing"]))
    session.begin()
    return session


def test_the_story_moves_the_odds_and_old_moves_still_work():
    session = _red_game()
    c = session.campaign
    plain = c.preview("phishing", "george").success_chance
    good = c.preview("phishing", "george", "invoice").success_chance
    bad = c.preview("phishing", "george", "prize").success_chance
    assert bad < plain < good
    rows = json.loads(session.pretexts("phishing", "george"))
    assert {r["id"] for r in rows} == set(pretexts.PRETEXTS)
    assert all("success" in r and r["fit"] for r in rows)
    assert "error" not in json.loads(session.move("phishing", "george", "invoice"))
    assert "error" not in json.loads(session.move("phishing", "maria"))
