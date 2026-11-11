import json
import sys
from pathlib import Path

from bastion import achievements
from bastion.profile import Profile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_scores import referee  # noqa: E402
from tests.test_dice import play_red  # noqa: E402


def game(tier="small", level="hard", side="red", won=True, earned=()):
    return {"tier": tier, "level": level, "side": side, "won": won, "earned": list(earned)}


def test_there_are_ten_and_five_are_classified():
    assert len(achievements.ACHIEVEMENTS) == 10
    assert sum(1 for a in achievements.ACHIEVEMENTS if a.secret) == 5


def test_classified_ones_are_redacted_until_unlocked():
    rows = achievements.board(Profile())
    hidden = [r for r in rows if r["classified"]]
    assert len(hidden) == 5
    assert all("█" in r["name"] and r["id"] not in r["text"] for r in hidden)
    assert not any("Directorate" in r["text"] or "Realism" in r["text"] for r in hidden)
    realism = Profile(secrets={"sealed": 10})
    assert sum(r["classified"] for r in achievements.board(realism)) == 2
    cleared = Profile(secrets={"sealed": 10, "script": 3})
    assert not any(r["classified"] for r in achievements.board(cleared))


def test_an_earned_classified_one_is_always_shown():
    rows = achievements.board(Profile(achievements=["purple"]))
    purple = next(r for r in rows if r["id"] == "purple")
    assert purple["done"] and not purple["classified"]


def test_streak_needs_seven_hard_wins_in_a_row_and_a_loss_resets_it():
    six = [game() for _ in range(6)]
    assert "iron-streak" not in achievements.from_history(six)
    assert "iron-streak" in achievements.from_history(six + [game(level="realism")])
    assert "iron-streak" not in achievements.from_history(six + [game(won=False)] + [game()])
    easy_between = six[:3] + [game(level="easy", won=False)] + six[3:] + [game()]
    assert "iron-streak" in achievements.from_history(easy_between)


def test_purple_and_full_spectrum():
    both = [game("huge", side="red"), game("huge", side="blue")]
    assert "purple" in achievements.from_history(both)
    assert "full-spectrum" not in achievements.from_history(both)
    every = [game(t, side=s) for t in achievements.MAPS for s in ("red", "blue")]
    assert "full-spectrum" in achievements.from_history(every)
    assert "purple" not in achievements.from_history([game("huge", level="easy", side="red"), game("huge", level="easy", side="blue")])


def test_referee_confirms_counts_abandoned_as_loss_and_rejects_forgery():
    final, moves = play_red("olive-byte", "hard")
    calls = [[json.dumps([m, a]), v] for m, a, v in moves]
    total = final["score"]["total"]
    data = {"games": [
        {"id": 1, "user_id": 5, "status": "done", "side": "red", "points": total, "moves": calls},
        {"id": 2, "user_id": 5, "status": "done", "side": "red", "points": total + 9, "moves": calls},
        {"id": 3, "user_id": 5, "status": "abandoned", "side": None, "points": None, "moves": calls[:3]},
    ], "history": {}}
    out = referee(data)
    verdicts = {v["id"]: v for v in out["verdicts"]}
    assert verdicts[1]["ok"] and verdicts[1]["summary"]["level"] == "hard"
    assert not verdicts[2]["ok"]
    assert verdicts[3]["ok"] and verdicts[3]["summary"]["won"] is False
    assert "5" in out["achievements"]


def test_referee_rejects_a_game_that_used_items_not_bought():
    final, moves = play_red("olive-byte", "easy")
    calls = [[json.dumps([m, a]), v] for m, a, v in moves]
    base = {"user_id": 9, "status": "done", "side": "red", "points": final["score"]["total"], "moves": calls}
    picked = json.loads(next(a for m, a, v in moves if m == "set_arsenal")[0])
    out = referee({"games": [dict(base, id=1, owned=picked), dict(base, id=2, owned=[]), dict(base, id=3, owned=None)], "history": {}})
    ok = {v["id"]: v["ok"] for v in out["verdicts"]}
    from bastion import shop
    assert ok[1] and ok[3]
    assert ok[2] == all(shop.is_free(i) for i in picked)
