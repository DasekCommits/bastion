"""Referee: replay finished games with the dice the server rolled and confirm their scores.

The server exports the scored games that are still unchecked (server/referee.php export),
this tool replays each one against the real engine, and the verdicts go back to the server
(server/referee.php apply). A score is confirmed only if the engine, given exactly the same
moves and dice, produces exactly the claimed total.

Usage:
    python tools/verify_scores.py pending.json verdicts.json
"""
import json
import sys

from bastion import dice


def judge(game: dict) -> tuple[bool, str]:
    moves = []
    for call_json, value in game["moves"]:
        method, args = json.loads(call_json)
        moves.append([method, args, int(value)])
    if not moves or moves[0][0] != "start" or moves[-1][0] not in dice.FINAL:
        return False, "incomplete game"
    final = dice.replay(moves)
    score = (final or {}).get("score")
    if not score:
        return False, "no score in replay"
    if score["side"] != game["side"]:
        return False, f"claimed {game['side']}, engine played {score['side']}"
    if score["total"] != int(game["points"]):
        return False, f"claimed {game['points']}, engine says {score['total']}"
    return True, "ok"


def main(pending_path: str, verdicts_path: str) -> int:
    games = json.load(open(pending_path, encoding="utf-8"))
    verdicts, bad = [], 0
    for game in games:
        try:
            ok, why = judge(game)
        except Exception as error:
            ok, why = False, f"unreplayable ({error})"
        verdicts.append({"id": game["id"], "ok": ok})
        if not ok:
            bad += 1
        print(f"  game #{game['id']} user {game['user_id']} {game['side']} {game['points']}: {why}")
    json.dump(verdicts, open(verdicts_path, "w", encoding="utf-8"))
    print(f"\n{len(games)} checked, {bad} rejected.")
    return 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:3] if len(sys.argv) > 2 else ("pending.json", "verdicts.json"))))
