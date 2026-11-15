import json
import sys
from pathlib import Path

from bastion import quests
from bastion.web import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_scores import referee  # noqa: E402
from tests.test_dice import play_red  # noqa: E402


def test_six_quests_per_side_with_goals_and_rewards():
    for side in ("red", "blue"):
        mine = [q for q in quests.QUESTS if q.side == side]
        assert len(mine) == 6
        assert all(q.goal >= 1 and q.reward > 0 for q in mine)
    assert len(quests.BY_ID) == len(quests.QUESTS)


def test_progress_counts_each_game_once_and_ignores_unknown_ids():
    games = [{"quests": ["red-inside", "red-inside", "nope"]}, {"quests": ["red-inside"]}, {}]
    counts = quests.progress(games)
    assert counts["red-inside"] == 2
    assert "nope" not in counts


def test_rewards_only_for_finished_quests_and_on_the_right_side():
    counts = {"red-scout": 1, "red-inside": 2, "blue-surgical": 1}
    assert quests.rewards(counts) == {"red": 3, "blue": 6}


def test_board_caps_progress_at_the_goal():
    rows = {r["id"]: r for r in quests.board({"red-scout": 4})}
    assert rows["red-scout"]["count"] == 1 and rows["red-scout"]["done"]
    assert rows["red-loot"]["count"] == 0 and not rows["red-loot"]["done"]


def test_session_exposes_the_board():
    rows = json.loads(Session().quest_board(json.dumps({"blue-cut": 3})))
    assert next(r for r in rows if r["id"] == "blue-cut")["done"]


def test_the_referee_records_quest_marks_in_the_summary():
    final, moves = play_red()
    calls = [[json.dumps([m, a]), v] for m, a, v in moves]
    game = {"id": 1, "user_id": 5, "status": "done", "side": "red", "points": final["score"]["total"], "moves": calls}
    out = referee({"games": [game], "history": {}})
    summary = out["verdicts"][0]["summary"]
    assert out["verdicts"][0]["ok"]
    assert isinstance(summary["quests"], list)
    assert all(q in quests.BY_ID and quests.BY_ID[q].side == "red" for q in summary["quests"])
