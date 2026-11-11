import json

from bastion import dice
from bastion.web import Session

SECRET = "ab" * 32


class Server:
    def __init__(self):
        self.moves = []

    def __call__(self, method, args):
        value = dice.roll(SECRET, 7, len(self.moves))
        self.moves.append([method, args, value])
        return value


def client(session, server, method, *args):
    if method in dice.LOGGED:
        out = dice.play(session, method, list(args), server(method, list(args)))
    else:
        out = getattr(session, method)(*args)
    return json.loads(out) if isinstance(out, str) else out


def play_red(company="olive-byte", level="easy"):
    session, server = Session(dice.UNLOCKED), Server()
    client(session, server, "start", company, level, "red")
    options = client(session, server, "attack_options")
    budget = session.company.red_budget
    picked, spent = [], 0
    for option in sorted(options, key=lambda o: o["cost"]):
        if spent + option["cost"] <= budget:
            picked.append(option["id"])
            spent += option["cost"]
    assert client(session, server, "set_arsenal", json.dumps(picked))["ok"]
    turn = client(session, server, "begin")
    for _ in range(300):
        if turn["finished"]:
            break
        moved = False
        if turn["moves_left"]:
            for action in turn["actions"]:
                targets = [t for t in client(session, server, "targets", action["id"]) if not t.get("disabled")]
                if not action.get("disabled") and targets:
                    client(session, server, "move", action["id"], targets[0]["id"])
                    moved = True
                    break
        if not moved:
            client(session, server, "end_day")
        turn = client(session, server, "turn")
    final = client(session, server, "finish")
    return final, server.moves


def play_blue(company="olive-byte", level="medium"):
    session, server = Session(dice.UNLOCKED), Server()
    client(session, server, "start", company, level, "blue")
    options = client(session, server, "defense_options")
    picked, spent = [], 0
    for option in options:
        if spent + option["cost"] <= session.company.budget:
            picked.append(option["id"])
            spent += option["cost"]
    client(session, server, "set_defenses", json.dumps(picked))
    state = client(session, server, "begin")
    for _ in range(300):
        if state["finished"]:
            break
        if state["time_left"] and state["phase"] != "day_end":
            state = client(session, server, "blue_act", "logs")["state"]
        else:
            state = client(session, server, "blue_wait")
    return client(session, server, "finish"), server.moves


def test_rolls_are_deterministic_and_secret_dependent():
    assert dice.roll(SECRET, 1, 0) == dice.roll(SECRET, 1, 0)
    assert dice.roll(SECRET, 1, 0) != dice.roll(SECRET, 1, 1)
    assert dice.roll(SECRET, 1, 0) != dice.roll("cd" * 32, 1, 0)
    assert 0 <= dice.roll(SECRET, 1, 0) < 2 ** 52


def test_replay_of_server_log_gives_the_same_red_score():
    final, moves = play_red()
    assert all(m[0] in dice.LOGGED for m in moves)
    assert sum(m[0] == "move" for m in moves) >= 3
    assert dice.replay(moves)["score"]["total"] == final["score"]["total"]


def test_replay_of_server_log_gives_the_same_blue_score():
    final, moves = play_blue()
    assert dice.replay(moves)["score"]["total"] == final["score"]["total"]


def test_reads_do_not_change_the_outcome():
    final, moves = play_red("harbor-clinic", "medium")
    session = Session(dice.UNLOCKED)
    for method, args, value in moves:
        dice.play(session, method, args, value)
        session.turn() if session.campaign else None
        if session.campaign:
            for attack_id in session.campaign.arsenal:
                session.targets(attack_id)
    replayed = dice.replay(moves)
    assert replayed["score"]["total"] == final["score"]["total"]

