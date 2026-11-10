import io
import random

import pytest

from rich.console import Console

from bastion.catalog import load_catalog
from bastion.company import load_scenario
from bastion.engine import Campaign
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

    def checkbox(self, message, options, validate):
        self.seen.append((message, options))
        answer = self.answers.pop(0)
        assert validate(answer) is True
        return answer

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
    campaign = Campaign(company, catalog, [], ["exploit-web"], seed=1)
    options = {option.value: option for option in game.target_options(campaign, "exploit-web")}
    assert "success" in options["web-01"].tag
    assert options["db-01"].disabled


def test_hard_shows_no_numbers_and_allows_every_target(company, catalog):
    game = Game(company, catalog, "hard", Script())
    campaign = Campaign(company, catalog, [], ["exploit-web"], seed=1)
    options = game.target_options(campaign, "exploit-web")
    assert all("%" not in option.tag and not option.disabled for option in options)
    assert all(option.description is None for option in game.defense_options())


def test_budget_check_rejects_too_expensive_picks(company, catalog):
    game = Game(company, catalog, "easy", Script())
    check = game._budget_check("defense", company.budget)
    assert check(["mfa", "waf"]) is True
    assert "budget is 100" in check([defense_id for defense_id in catalog.defenses])


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
    script = Script("hard", ["firewall"], ["port-scan"], GIVE_UP)
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
    assert "did not buy" in game.move_hint(campaign, "port-scan")
