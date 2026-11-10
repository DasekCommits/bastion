import json

from bastion.web import Session


def test_red_game_through_the_web_bridge():
    session = Session()
    menu = json.loads(session.menu())
    assert [c["id"] for c in menu["companies"] if not c["locked"]] == ["olive-byte"]
    start = json.loads(session.start("olive-byte", "easy", "red", seed=3))
    assert start["side"] == "red" and start["company"]["people"]
    options = json.loads(session.attack_options())
    assert all("description" in o for o in options)
    assert not json.loads(session.set_arsenal(json.dumps([o["id"] for o in options])))["ok"]
    assert json.loads(session.set_arsenal(json.dumps(["phishing", "exfiltration"])))["ok"]
    turn = json.loads(session.begin())
    assert turn["day"] == 1 and turn["heat"] == 0
    targets = json.loads(session.targets("phishing"))
    assert all("success" in t for t in targets)
    event = json.loads(session.move("phishing", "emily"))
    assert event["type"] == "move" and event["suspense"]
    after = json.loads(session.end_day())
    assert after["turn"]["day"] in (1, 2)
    final = json.loads(session.give_up())
    assert final["score"]["side"] == "red" and final["tips"] and final["post_mortem"]
    assert json.loads(final["profile_json"])["games"] == 1


def test_blue_game_plays_itself_and_hard_hides_everything():
    session = Session(json.dumps({"points": 5, "games": 1, "wins": {"small": 5}}))
    menu = json.loads(session.menu())
    assert {c["id"] for c in menu["companies"] if not c["locked"]} == {"olive-byte", "harbor-clinic"}
    start = json.loads(session.start("harbor-clinic", "hard", "blue", seed=1))
    assert all(p["admin"] in ("yes", "?") for p in start["company"]["people"])
    assert "description" not in json.loads(session.defense_options())[0]
    assert json.loads(session.set_defenses(json.dumps(["mfa", "siem"])))["ok"]
    played = json.loads(session.begin())
    assert played["finished"]
    assert all(e["type"] in ("alert", "night") for e in played["events"])
    final = json.loads(session.finish())
    assert final["post_mortem"] is None and final["tips"] is None
    assert final["profile"]["games"] == 2


def test_red_never_learns_which_hidden_defense_stopped_it():
    session = Session()
    session.start("olive-byte", "easy", "red", seed=3)
    session.set_arsenal(json.dumps(["phishing", "exfiltration"]))
    session.begin()
    for person in ("emily", "george", "maria"):
        event = json.loads(session.move("phishing", person))
        assert "blockers" not in event
