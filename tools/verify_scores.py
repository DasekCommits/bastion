"""Replay stored score transcripts against the engine to catch forged scores.

The game runs in the player's browser, so a submitted score cannot be trusted on
its own. Every submission stores its transcript (the ordered list of engine calls,
starting from the seed). This tool re-runs each transcript here, where the engine is
authoritative, and flags any score that does not match what the real game produces.

Usage:
    # pull the audit rows from the server, then verify them:
    ssh -i ~/.ssh/dasek_deploy dasek@server33.cretaforce.gr \
        'cd ~/dasek.dev/bastion && php -r "require \"api/lib.php\";
         echo json_encode(db()->query(\"SELECT id,user_id,side,points,transcript FROM score_audit WHERE accepted=1 AND transcript IS NOT NULL\")->fetchAll(PDO::FETCH_ASSOC));"' \
        > audit.json
    .venv/Scripts/python.exe tools/verify_scores.py audit.json
"""
import json
import sys

from bastion.web import Session

# a profile with everything unlocked, so replaying any game's start() is allowed
UNLOCKED = json.dumps({
    "points": 0, "games": 99,
    "wins": {f"{t}/{l}": 99 for t in ("small", "medium", "large") for l in ("easy", "medium", "hard")},
    "secrets": {"sealed": 99, "script": 99},
})


def replay(moves: list) -> int | None:
    """Re-run a transcript and return the score the engine actually produces."""
    session = Session(UNLOCKED)
    result = None
    for method, args in moves:
        result = getattr(session, method)(*args)
    if result is None:
        return None
    final = json.loads(result) if isinstance(result, str) else result
    score = final.get("score")
    return score["total"] if score else None


def main(path: str) -> int:
    rows = json.load(open(path, encoding="utf-8"))
    bad = 0
    for row in rows:
        claimed = int(row["points"])
        try:
            transcript = json.loads(row["transcript"])
            actual = replay(transcript["moves"])
        except Exception as error:  # a transcript that will not replay is itself suspect
            print(f"  audit #{row['id']} user {row['user_id']} {row['side']}: UNREPLAYABLE ({error})")
            bad += 1
            continue
        if actual is None:
            print(f"  audit #{row['id']} user {row['user_id']} {row['side']}: no final score in replay")
            bad += 1
        elif actual != claimed:
            print(f"  audit #{row['id']} user {row['user_id']} {row['side']}: claimed {claimed}, engine says {actual}  <-- MISMATCH")
            bad += 1
    print(f"\n{len(rows)} checked, {bad} suspicious.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "audit.json"))
