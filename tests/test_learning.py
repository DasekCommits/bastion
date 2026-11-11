import json

from bastion import learning
from bastion.catalog import load_catalog
from bastion.web import Session

CATALOG = load_catalog()


def test_every_red_chain_works_in_its_own_order_and_fails_backwards():
    assert len(learning.CHAINS) >= 15
    for chain in learning.CHAINS:
        assert learning.check_chain(CATALOG, chain["id"], chain["steps"])["passed"], chain["id"]
        backwards = list(reversed(chain["steps"]))
        if len(backwards) > 2 or chain["id"] != "invoice-fraud":
            assert not learning.check_chain(CATALOG, chain["id"], backwards)["passed"], chain["id"]


def test_red_lessons_have_the_right_prerequisite_among_the_options():
    for attack_id in CATALOG.attacks:
        lesson = learning.lesson(CATALOG, attack_id, [])
        ids = [o["id"] for o in lesson["step2"]["options"]]
        assert attack_id in ids and len(set(o["label"] for o in lesson["step2"]["options"])) == len(ids)
        assert learning.check(CATALOG, attack_id, attack_id, attack_id)["passed"]


def test_every_defense_has_a_blue_lesson_that_can_be_passed():
    assert learning.blue_summary(CATALOG, [])["total"] == len(CATALOG.defenses)
    for defense_id in CATALOG.defenses:
        lesson = learning.blue_lesson(CATALOG, defense_id, [])
        best = learning._best_attack(CATALOG, CATALOG.defenses[defense_id])
        mode = learning._mode(CATALOG.defenses[defense_id], best.id)
        assert best.id in [o["id"] for o in lesson["step1"]["options"]]
        assert learning.blue_check(CATALOG, defense_id, best.id, mode)["passed"]
        assert not learning.blue_check(CATALOG, defense_id, best.id, "nope")["passed"]


def test_every_blue_combination_is_solvable_within_its_budget():
    from itertools import combinations
    for chain in learning.CHAINS:
        guard = learning.guard(CATALOG, chain["id"], [])
        options = [o["id"] for o in guard["options"]]
        solved = any(learning.check_guard(CATALOG, chain["id"], list(c))["passed"]
                     for size in (1, 2, 3) for c in combinations(options, size))
        assert solved, chain["id"]
        assert not learning.check_guard(CATALOG, chain["id"], [])["passed"]


def test_session_records_progress_per_category():
    session = Session()
    attack = next(iter(CATALOG.attacks))
    session.learn_check("red", attack, attack, attack)
    defense = "mfa"
    best = learning._best_attack(CATALOG, CATALOG.defenses[defense])
    session.learn_check("blue", defense, best.id, learning._mode(CATALOG.defenses[defense], best.id))
    hub = json.loads(session.learn_hub())
    assert hub["red"]["techniques"]["done"] == 1
    assert hub["blue"]["defenses"]["done"] == 1
    assert attack in session.profile.learned and "blue:mfa" in session.profile.learned
