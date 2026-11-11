"""Referee: replay finished games with the dice the server rolled, confirm scores, award achievements.

Input (from GET api/referee.php):
    {"games": [{"id", "user_id", "status", "side", "points", "moves": [[call_json, roll], ...]}],
     "history": {"<user_id>": [summary, ...]}}       # that user's already verified games, oldest first
Output (for POST api/referee.php):
    {"verdicts": [{"id", "ok", "summary"}], "achievements": {"<user_id>": [ids]}}

A claimed score is confirmed only if the engine, given exactly the same moves and dice,
produces exactly that total. An abandoned game counts as a loss, so quitting cannot
protect a streak. Achievements are worked out here, never in the browser.

Usage:
    python tools/verify_scores.py pending.json verdicts.json
"""
import json
import sys

from bastion import achievements, dice


def judge(game: dict) -> tuple[bool, str, dict | None]:
    moves = []
    for call_json, value in game["moves"]:
        method, args = json.loads(call_json)
        moves.append([method, args, int(value)])
    if not moves or moves[0][0] != "start":
        return False, "no start", None
    finished = moves[-1][0] in dice.FINAL
    if not finished:
        session, _ = dice.replay_session(moves[:1])
        return True, "abandoned, counted as a loss", {
            "tier": session.company.tier, "level": session.shown_level, "side": session.side,
            "won": False, "earned": []}
    session, final = dice.replay_session(moves)
    score = (final or {}).get("score")
    if not score:
        return False, "no score in replay", None
    if game.get("points") is not None:
        if score["side"] != game["side"]:
            return False, f"claimed {game['side']}, engine played {score['side']}", None
        if score["total"] != int(game["points"]):
            return False, f"claimed {game['points']}, engine says {score['total']}", None
    summary = achievements.summary(session)
    return True, f"{'won' if summary['won'] else 'lost'} {score['total']}", summary


def referee(data: dict) -> dict:
    history = {str(k): list(v) for k, v in data.get("history", {}).items()}
    verdicts = []
    for game in sorted(data["games"], key=lambda g: int(g["id"])):
        try:
            ok, why, summary = judge(game)
        except Exception as error:
            ok, why, summary = False, f"unreplayable ({error})", None
        verdicts.append({"id": int(game["id"]), "ok": ok, "summary": summary})
        if ok and summary:
            history.setdefault(str(game["user_id"]), []).append(summary)
        print(f"  game #{game['id']} user {game['user_id']}: {'OK' if ok else 'REJECTED'} - {why}")
    earned = {user: sorted(achievements.from_history(games)) for user, games in history.items()}
    return {"verdicts": verdicts, "achievements": earned}


def main(pending_path: str, verdicts_path: str) -> int:
    data = json.load(open(pending_path, encoding="utf-8"))
    out = referee(data)
    json.dump(out, open(verdicts_path, "w", encoding="utf-8"))
    bad = sum(not v["ok"] for v in out["verdicts"])
    print(f"\n{len(out['verdicts'])} checked, {bad} rejected.")
    return 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:3] if len(sys.argv) > 2 else ("pending.json", "verdicts.json"))))
