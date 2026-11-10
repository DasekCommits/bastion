import json

from bastion.web import Session


def test_red_game_through_the_web_bridge():
    session = Session()
    menu = json.loads(session.menu())
    assert [cid for cid, reason in menu["locks"]["easy"].items() if not reason] == ["olive-byte"]
    assert menu["levels"]["medium"] and menu["levels"]["hard"]
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


def test_blue_plays_analyst_turns_and_hard_hides_hints():
    session = Session(json.dumps({"points": 5, "games": 1, "wins": {"small": 5}}))
    menu = json.loads(session.menu())
    assert {cid for cid, reason in menu["locks"]["easy"].items() if not reason} == {"olive-byte", "harbor-clinic"}
    start = json.loads(session.start("harbor-clinic", "hard", "blue", seed=1))
    assert all(p["admin"] in ("yes", "?") for p in start["company"]["people"])
    assert "description" not in json.loads(session.defense_options())[0]
    assert json.loads(session.set_defenses(json.dumps(["mfa", "siem"])))["ok"]
    state = json.loads(session.begin())
    assert not state["finished"] and state["time_left"] > 0
    looked = json.loads(session.blue_act("logs"))
    assert looked["action"]["kind"] == "logs"
    assert all("hint" not in entry for entry in looked["fresh"])
    state = looked["state"]
    if state["logs"] and not state["finished"]:
        investigated = json.loads(session.blue_act("investigate", str(state["logs"][0]["id"])))
        assert investigated["action"]["text"]
        state = investigated["state"]
    guard = 0
    while not state["finished"] and guard < 200:
        state = json.loads(session.blue_wait())
        guard += 1
    assert state["finished"]
    final = json.loads(session.finish())
    assert final["post_mortem"] is None and final["tips"] is None
    assert final["profile"]["games"] == 2
    assert any(a["kind"] == "logs" for a in final["blue_actions"])


def test_red_sees_only_the_consequences_of_blue_actions():
    session = Session()
    session.start("olive-byte", "hard", "red", seed=11)
    session.set_arsenal(json.dumps(["phishing", "exfiltration"]))
    session.begin()
    notices = []
    for person in ("emily", "george", "maria", "sophie", "jacob"):
        event = json.loads(session.move("phishing", person))
        notices += event.get("blue", [])
        if json.loads(session.turn())["finished"]:
            break
    assert all("password" in n or "blocked" in n or "cut off" in n or "digging" in n for n in notices)


def test_red_never_learns_which_hidden_defense_stopped_it():
    session = Session()
    session.start("olive-byte", "easy", "red", seed=3)
    session.set_arsenal(json.dumps(["phishing", "exfiltration"]))
    session.begin()
    for person in ("emily", "george", "maria"):
        event = json.loads(session.move("phishing", person))
        assert "blockers" not in event


def test_realism_blue_searches_real_logs_and_acts():
    session = Session(json.dumps({"points": 0, "games": 0, "wins": {}, "secrets": {"sealed": 10}}))
    menu = json.loads(session.menu())
    assert menu["realism"] and menu["locks"]["realism"]["meridian-bank"] is None
    session.start("olive-byte", "realism", "blue", seed=8)
    assert json.loads(session.set_defenses(json.dumps(["siem", "mfa"])))["ok"]
    state = json.loads(session.begin())
    assert "security" in state["indexes"] and state["hosts"][0]["hostname"].startswith("OLI-")
    found = json.loads(session.realism_search("index=security EventCode=4624 | stats count by user"))
    assert found["total"] >= 5 and "count" in found["columns"]
    assert "error" in json.loads(session.realism_search("index=security | nonsense"))
    acted = json.loads(session.realism_act("block", "192.0.2.1"))
    assert "Blocked" in acted["text"]
    assert "error" in json.loads(session.realism_act("isolate", "NOPE-01"))
    state = acted["state"]
    guard = 0
    while not state["finished"] and guard < 300:
        state = json.loads(session.realism_wait())
        guard += 1
    final = json.loads(session.finish())
    assert final["score"]["side"] == "blue"
    assert "small/realism" in json.loads(final["profile_json"])["wins"] or not final["score"]["won"]


def test_realism_red_terminal_drives_the_game():
    session = Session(json.dumps({"points": 0, "games": 0, "wins": {}, "secrets": {"sealed": 10}}))
    session.start("olive-byte", "realism", "red", seed=3)
    assert json.loads(session.set_arsenal(json.dumps(["port-scan", "phishing", "exfiltration"])))["ok"]
    intro = json.loads(session.begin())
    assert "help" in " ".join(intro["lines"])
    helped = json.loads(session.terminal("help"))
    assert any(line.strip().startswith("phish") for line in helped["lines"])
    assert any("guess" in line for line in helped["lines"]) is False
    targets = json.loads(session.terminal("targets"))
    assert any("OLI-WEB01" in line for line in targets["lines"])
    assert "not in the arsenal" in json.loads(session.terminal("guess maria"))["lines"][0]
    assert "not a valid target" in json.loads(session.terminal("phish nobody"))["lines"][0]
    moved = json.loads(session.terminal("recon OLI-WEB01"))
    assert moved["lines"][0].startswith("[T1595]") and moved["moves_left"] == 2
    assert json.loads(session.terminal("status"))["lines"][0].startswith("Day 1")
    reply = json.loads(session.terminal("sleep"))
    guard = 0
    while not reply["finished"] and guard < 30:
        reply = json.loads(session.terminal("sleep"))
        guard += 1
    assert reply["finished"]
    assert json.loads(session.finish())["score"]["side"] == "red"
