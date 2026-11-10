import io
import random

import pytest

from rich.console import Console

from bastion.catalog import load_catalog
from bastion.company import load_scenario
from bastion.engine import Campaign
from bastion import look
from bastion.picker import Picker
from bastion.play import BACK, END_DAY, GIVE_UP, Game, Option, main


class Script:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.lines = []
        self.seen = []

    def select(self, message, options):
        self.seen.append((message, options))
        answer = self.answers.pop(0)
        assert answer in [option.value for option in options if not option.disabled]
        return answer

    def pick(self, message, options, budget, need_one, done_label):
        self.seen.append((message, options))
        answer = self.answers.pop(0)
        assert sum(option.cost for option in options if option.value in answer) <= budget
        assert answer or not need_one
        return answer

    def suspense(self, lines):
        self.lines.extend(f"... {line}" for line in lines)

    def say(self, content=""):
        buffer = io.StringIO()
        Console(file=buffer, width=120, color_system=None).print(content)
        self.lines.extend(buffer.getvalue().splitlines())

    @property
    def text(self):
        return "\n".join(self.lines)


@pytest.fixture
def company():
    return load_scenario("olive-byte")


@pytest.fixture
def catalog():
    return load_catalog()


def test_easy_shows_chances_and_hides_impossible_targets(company, catalog):
    game = Game(company, catalog, "easy", Script())
    campaign = Campaign(company, catalog, [], ["port-scan"], seed=1)
    options = {option.value: option for option in game.target_options(campaign, "port-scan")}
    assert "success" in options["web-01"].tag
    assert options["db-01"].disabled


def test_hard_shows_no_numbers_and_allows_every_target(company, catalog):
    game = Game(company, catalog, "hard", Script())
    campaign = Campaign(company, catalog, [], ["exploit-web"], seed=1)
    options = game.target_options(campaign, "exploit-web")
    assert all("%" not in option.tag and not option.disabled for option in options)
    assert all(option.description is None for option in game.defense_options())


def test_picker_shows_live_total_and_refuses_overspending(catalog):
    game = Game(load_scenario("olive-byte"), catalog, "easy", Script())
    picker = Picker("Pick", game.defense_options(), 30)
    picker.press_enter()
    assert picker.spent == catalog.defenses["mfa"].cost
    assert "Spent 15/30" in "".join(text for _, text in picker.tokens())
    picker.move(3)
    picker.press_enter()
    assert picker.spent == 15 and "Not enough budget" in picker.warning
    picker.move(-3)
    picker.press_enter()
    assert picker.spent == 0


def test_picker_only_finishes_on_done(catalog):
    game = Game(load_scenario("olive-byte"), catalog, "easy", Script())
    picker = Picker("Buy", game.attack_options(), 100, need_one=True)
    picker.move(-1)
    assert picker.on_done and not picker.press_enter()
    picker.move(1)
    assert not picker.press_enter()
    picker.move(-1)
    assert picker.press_enter() and picker.chosen == ["port-scan"]


def test_full_easy_game_ends_with_post_mortem(company, catalog):
    script = Script(
        ["siem", "mfa"],
        ["phishing", "exfiltration"],
        "phishing", "maria",
        END_DAY,
        GIVE_UP,
    )
    Game(company, catalog, "easy", script, random.Random(3)).run()
    assert "BASTION POST-MORTEM" in script.text
    assert "DEFENSE SCORE" in script.text
    assert "Night 1" in script.text or "DETECTED" in script.text


def test_day_ends_by_itself_when_moves_run_out(company, catalog):
    script = Script(*(["port-scan", "web-01"] * company.moves_per_day), GIVE_UP)
    game = Game(company, catalog, "hard", script, random.Random(0))
    campaign = Campaign(company, catalog, [], ["port-scan"], rng=random.Random(0))
    game.play_turns(campaign)
    assert campaign.day == 2 or campaign.caught


def test_main_asks_difficulty_and_plays(company):
    script = Script("hard", "practice", "olive-byte", ["firewall"], ["port-scan"], GIVE_UP)
    assert main(["--seed", "1"], ui=script) == 0
    before_red = script.text.split("RED TEAM")[0]
    assert "BLUE TEAM" in before_red and "%" not in before_red


def test_easy_greys_out_moves_with_no_possible_target(company, catalog):
    game = Game(company, catalog, "easy", Script())
    campaign = Campaign(company, catalog, [], ["phishing", "privilege-escalation"], seed=1)
    options = {option.value: option for option in game.action_options(campaign)}
    assert options["privilege-escalation"].disabled
    assert not options["phishing"].disabled


def test_back_returns_to_the_move_menu_without_using_a_move(company, catalog):
    script = Script("phishing", BACK, GIVE_UP)
    game = Game(company, catalog, "easy", script, random.Random(0))
    campaign = Campaign(company, catalog, [], ["phishing"], rng=random.Random(0))
    game.play_turns(campaign)
    assert campaign.moves_today == 0


def test_scan_warns_when_exploit_was_not_bought(company, catalog):
    game = Game(company, catalog, "easy", Script())
    campaign = Campaign(company, catalog, [], ["port-scan"], seed=1)
    assert "intel is all you get" in game.move_hint(campaign, "port-scan")


def test_suspense_comes_before_the_outcome(company, catalog):
    script = Script(["mfa"], ["phishing"], "phishing", "sophie", GIVE_UP)
    Game(company, catalog, "easy", script, random.Random(1)).run()
    text = script.text
    assert text.index("Waiting for Sophie to click") < text.index("SUCCESS" if "SUCCESS" in text else "FAILED")
    assert "Is the Blue Team watching?" in text


def play_short_game(level, company, catalog):
    script = Script(["mfa"], ["phishing", "exfiltration"], "phishing", "emily", GIVE_UP)
    Game(company, catalog, level, script, random.Random(5)).run()
    return script.text


def test_easy_ends_with_advice_for_both_sides(company, catalog):
    text = play_short_game("easy", company, catalog)
    assert "WHAT YOU COULD DO" in text and "AS BLUE" in text and "AS RED" in text
    assert "POST-MORTEM" in text


def test_medium_explains_but_gives_no_advice(company, catalog):
    text = play_short_game("medium", company, catalog)
    assert "POST-MORTEM" in text
    assert "WHAT YOU COULD DO" not in text and "Gap:" not in text and "Biggest gaps" not in text
    game = Game(company, catalog, "medium", Script())
    campaign = Campaign(company, catalog, [], ["port-scan"], seed=1)
    options = {option.value: option for option in game.target_options(campaign, "port-scan")}
    assert options["db-01"].disabled and "%" not in options["web-01"].tag
    assert all(option.description for option in game.defense_options())


def test_hard_shows_only_the_result(company, catalog):
    text = play_short_game("hard", company, catalog)
    assert "DEFENSE SCORE" in text
    assert "POST-MORTEM" not in text and "WHAT YOU COULD DO" not in text


def test_medium_and_hard_hide_accidental_admins(company, catalog):
    for level, hidden in (("easy", False), ("medium", True), ("hard", True)):
        script = Script()
        game = Game(company, catalog, level, script, random.Random(1))
        game.ui.say(look.company_panel(game.company, game.explain, reveal_admins=game.easy))
        assert ("by mistake" in script.text) == hidden


def test_blue_side_watches_the_computer_attack_and_scores(company, catalog):
    from bastion.profile import load_profile

    script = Script(["mfa", "email-filter"])
    campaign = Game(company, catalog, "medium", script, random.Random(2), side="blue").run()
    assert campaign.finished or campaign.results
    assert "SCORE" in script.text and "BLUE TEAM" in script.text
    assert load_profile().games == 1


def test_red_side_plays_against_hidden_defenses(company, catalog):
    script = Script(["phishing", "exfiltration"], GIVE_UP)
    game = Game(company, catalog, "easy", script, random.Random(3), side="red")
    campaign = game.run()
    assert campaign.defense_ids
    assert "SCORE" in script.text and "RED TEAM" in script.text


def test_random_side_doubles_points_only_on_a_win(company, catalog):
    from bastion.scoring import _total

    game = Game(company, catalog, "easy", Script(), random.Random(1), side="random")
    assert game.side in ("blue", "red") and game.random_side
    assert _total("red", True, 40, {"speed": 10}, 1.5, random_side=True).total == 150
    assert _total("red", False, 40, {}, 1.0, random_side=True).total == 40


def test_bigger_companies_unlock_after_enough_wins():
    from bastion.profile import Profile

    profile = Profile()
    assert profile.is_unlocked("small") and not profile.is_unlocked("medium")
    for _ in range(4):
        assert profile.record("small", True, 10) == []
    assert profile.record("small", True, 10) == ["medium"]
    for _ in range(9):
        profile.record("medium", True, 10)
    assert not profile.is_unlocked("large")
    assert profile.record("medium", True, 10) == ["large"]


def test_locked_companies_are_greyed_out_in_the_menu():
    script = Script("easy", "practice")
    script.answers.append("olive-byte")
    script.answers += [["mfa"], ["phishing"], GIVE_UP]
    main(["--seed", "1"], ui=script)
    company_menu = next(options for message, options in script.seen if message == "Company")
    locked = {o.value for o in company_menu if o.disabled}
    assert locked == {"harbor-clinic", "meridian-bank"}


def test_games_are_logged_and_extremes_are_found(company, catalog):
    from bastion.gamelog import find_extremes, read_games

    play_short_game("easy", company, catalog)
    games = read_games()
    assert games and games[-1]["company"] == "olive-byte"
    fake = [dict(games[-1], side="pvp", red_won=True, defenses=["mfa"]) for _ in range(25)]
    assert any("mfa" in line and "100%" in line for line in find_extremes(fake))
    assert find_extremes(fake[:5]) == []


def test_balance_command_runs(capsys):
    from bastion.__main__ import main as cli

    assert cli(["balance", "--all"]) == 0
    assert "games logged" in capsys.readouterr().out


class WafScript(Script):
    def build_waf(self, message, options, preselected, status):
        answer = self.answers.pop(0)
        status(answer)
        return answer


def test_building_a_waf_sets_its_strength_in_the_game(company, catalog):
    good = ["url-decode", "lowercase", "union", "or-true", "script", "event"]
    script = WafScript(["waf"], good)
    game = Game(company, catalog, "easy", script, random.Random(1), side="blue")
    game.pick_defenses("Done")
    assert 0 < game.waf_score < 100
    assert "Your WAF scored" in script.text
    weak = Campaign(company, catalog, ["waf"], ["exploit-web"], seed=1, waf_score=10)
    strong = Campaign(company, catalog, ["waf"], ["exploit-web"], seed=1, waf_score=95)
    assert strong.preview("exploit-web", "web-01").success_chance < weak.preview("exploit-web", "web-01").success_chance


def test_waf_builder_remembers_your_last_rules(company, catalog):
    import json

    from bastion.profile import home

    script = WafScript(["waf"], ["script"])
    Game(company, catalog, "easy", script, random.Random(1), side="blue").pick_defenses("Done")
    assert json.loads((home() / "waf-build.json").read_text()) == ["script"]


def test_real_waf_picker_with_keys(company, catalog):
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from bastion.picker import Picker
    from bastion.waf import evaluate, library_ruleset, load_corpus, load_library

    corpus = load_corpus()
    options = [Option(item.title, item.id) for item in load_library()]
    status = lambda chosen: look.waf_status_tokens(evaluate(library_ruleset(chosen), corpus))
    with create_pipe_input() as keys:
        keys.send_text("\r\x1b[B\r\x1b[A\x1b[A\r")
        with create_app_session(input=keys, output=DummyOutput()):
            chosen = Picker("WAF", options, None, status=status).run()
    assert chosen == ["url-decode", "lowercase"]
