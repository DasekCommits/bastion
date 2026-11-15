import json

from bastion import dice
from bastion.engine import EVENING, minutes_for
from bastion.web import Session


def red(mode="time", company="olive-byte"):
    s = Session(dice.UNLOCKED)
    s.start(company, "easy", "red", 3, mode)
    s.set_arsenal(json.dumps(["port-scan", "phishing", "exploit-web"]))
    s.begin()
    return s


def test_moves_cost_time_not_a_move_count():
    s = red()
    c = s.campaign
    assert c.timed and c.minute == 0
    for _ in range(5):
        json.loads(s.move("port-scan", "web-01"))
    assert c.day == 1 and c.minute == 5 * minutes_for(s.catalog.attacks["port-scan"])
    t = json.loads(s.turn())
    assert t["timed"] and t["clock"] == c.minute and all("minutes" in a for a in t["actions"])


def test_the_night_changes_the_odds():
    s = red()
    c = s.campaign
    day_phish = c.preview("phishing", "george").success_chance
    day_spot = c.preview("exploit-web", "web-01").detect_chance
    json.loads(s.wait(EVENING))
    assert c.night
    assert c.preview("phishing", "george").success_chance < day_phish
    if "soc" not in c.defense_ids:
        assert c.preview("exploit-web", "web-01").detect_chance <= day_spot


def test_sleeping_starts_a_new_day_at_nine():
    s = red()
    s.wait(EVENING)
    out = json.loads(s.end_day())
    assert s.campaign.day == 2 and s.campaign.minute == 0 and out["turn"]["clock"] == 0


def test_without_the_mode_nothing_changes():
    s = red(mode="")
    assert not s.campaign.timed and json.loads(s.turn())["clock"] is None
    assert "error" in json.loads(s.wait(EVENING))


def test_the_referee_replays_a_timed_game():
    moves = [["start", ["olive-byte", "easy", "red", "time"], 11], ["set_arsenal", [json.dumps(["port-scan", "exploit-web"])], 12],
             ["begin", [], 13], ["move", ["port-scan", "web-01"], 14], ["wait", [EVENING], 15], ["move", ["exploit-web", "web-01"], 16],
             ["end_day", [], 17], ["finish", [], 18]]
    session, final = dice.replay_session(moves)
    assert session.campaign.timed and final["score"]
    again, final2 = dice.replay_session(moves)
    assert final2["score"] == final["score"]


def blue(mode="time"):
    s = Session(dice.UNLOCKED)
    s.start("olive-byte", "easy", "blue", 5, mode)
    s.set_defenses(json.dumps(["siem", "firewall"]))
    return s, json.loads(s.begin())


def test_the_analyst_works_office_hours():
    s, state = blue()
    c = s.campaign
    assert state["timed"] and state["costs"]["investigate"] == 45
    before = c.minute
    s.blue_act("hunt", "web-01")
    assert c.blue_minute >= before + 120
    c.minute = 600
    c.blue_minute = 600
    assert c.blue_moves_left == 0
    assert "error" in json.loads(s.blue_act("isolate", "web-01"))


def test_a_timed_blue_game_reaches_the_end():
    s, state = blue()
    for _ in range(200):
        if state["finished"]:
            break
        state = json.loads(s.blue_wait())
    assert state["finished"]


def test_the_tenth_coffee_ends_the_game_and_earns_heart_rate():
    from bastion import achievements
    s = red()
    for cup in range(1, 10):
        assert json.loads(s.coffee()) == {"cups": cup, "died": False}
    assert json.loads(s.coffee())["died"] and s.gave_up
    final = json.loads(s.finish())
    assert final["score"]
    summary = achievements.summary(s)
    assert "heart-rate" in summary["earned"] and summary["won"] is False


def test_time_mode_has_a_balance_for_every_map_level_and_side():
    from bastion.catalog import TIER_ORDER, load_time_scale
    for side in ("red", "blue"):
        for tier in TIER_ORDER:
            for level in ("easy", "medium", "hard"):
                assert 0.05 < load_time_scale(tier, level, side) < 80
