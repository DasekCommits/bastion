import hashlib
import hmac
import json

from bastion.web import Session

LOGGED = (
    "start", "set_defenses", "set_arsenal", "begin", "move", "end_day", "give_up", "finish",
    "blue_act", "blue_wait", "terminal", "realism_search", "realism_act", "realism_wait",
)
FINAL = ("finish", "give_up")

UNLOCKED = json.dumps({
    "points": 0, "games": 99,
    "wins": {f"{t}/{l}": 99 for t in ("small", "medium", "large") for l in ("easy", "medium", "hard")},
    "secrets": {"sealed": 99, "script": 99},
})


def roll(secret_hex: str, game_id: int, n: int) -> int:
    digest = hmac.new(bytes.fromhex(secret_hex), f"{game_id}:{n}".encode(), hashlib.sha256).hexdigest()
    return int(digest[:13], 16)


def play(session: Session, method: str, args: list, value: int):
    if method == "start":
        return getattr(session, method)(*args[:3], value)
    session.reseed(value)
    return getattr(session, method)(*args)


def replay(moves: list) -> dict | None:
    session = Session(UNLOCKED)
    result = None
    for method, args, value in moves:
        if method not in LOGGED:
            raise ValueError(f"'{method}' is not a move")
        result = play(session, method, args, value)
    if result is None:
        return None
    return json.loads(result) if isinstance(result, str) else result
