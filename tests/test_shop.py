import json

from bastion import shop
from bastion.catalog import load_catalog
from bastion.web import Session

CATALOG = load_catalog()


def test_starter_kit_is_free_and_everything_else_has_a_price():
    rows = shop.items(CATALOG, [])
    free = [r["id"] for r in rows if r["free"]]
    assert sorted(free) == sorted(shop.STARTER["red"] + shop.STARTER["blue"])
    assert all(r["price"] > 0 for r in rows if not r["free"])
    assert all(r["owned"] == r["free"] for r in rows)


def test_coins_are_points_over_ten_minus_spending():
    assert shop.coins({"red": 125, "blue": 9}, {"red": 5}) == {"red": 7, "blue": 0}


def test_a_web_player_cannot_pick_what_they_have_not_bought():
    session = Session(json.dumps({"owned": []}))
    session.start("olive-byte", "easy", "red", 1)
    options = {o["id"]: o for o in json.loads(session.attack_options())}
    assert not options["phishing"].get("locked") and options["ransomware"]["locked"]
    assert not json.loads(session.set_arsenal(json.dumps(["phishing", "ransomware"])))["ok"]
    assert json.loads(session.set_arsenal(json.dumps(["phishing", "exfiltration"])))["ok"]
    session.set_owned(json.dumps(["ransomware"]))
    assert json.loads(session.set_arsenal(json.dumps(["phishing", "ransomware"])))["ok"]


def test_without_a_shop_list_nothing_is_locked():
    session = Session()
    session.start("olive-byte", "easy", "red", 1)
    assert not any(o.get("locked") for o in json.loads(session.attack_options()))
