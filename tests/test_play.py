import io
import random

import pytest

from rich.console import Console

from bastion.catalog import load_catalog
from bastion.company import load_scenario
from bastion.engine import Campaign
from bastion.picker import Picker
from bastion.play import BACK, END_DAY, GIVE_UP, Game, main


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
    script = Script("hard", "olive-byte", ["firewall"], ["port-scan"], GIVE_UP)
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
