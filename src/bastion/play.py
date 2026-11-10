import argparse
import json
import random
import sys
import time
from dataclasses import dataclass

from rich.console import Console
from rich.text import Text

from bastion import advice, ai, look, scoring
from bastion.catalog import Catalog, load_catalog, load_edge
from bastion.company import Company, list_scenarios, load_scenario, roll_mistakes
from bastion.engine import Campaign, NightResult, StepResult
from bastion.gamelog import log_game
from bastion.profile import home, load_profile, save_profile
from bastion.waf import evaluate, library_ruleset, load_corpus, load_library, load_rules
from bastion.look import percent

END_DAY = "end-day"
GIVE_UP = "give-up"
BACK = "back"
PLAY_AGAIN = "again"
WAIT = "wait"
MENU = "menu"
QUIT = "quit"
DIFFICULTIES = ("easy", "medium", "hard")
SIDES = ("blue", "red", "random", "practice")
TITLE_WIDTH = 30


@dataclass
class Option:
    title: str
    value: str
    tag: str = ""
    cost: int = 0
    description: str | None = None
    disabled: str | None = None


class Terminal:
    def __init__(self, delay: float = 1.0):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        self.console = Console(highlight=False)
        self.delay = delay

    def suspense(self, lines: list[str]) -> None:
        if self.delay <= 0:
            return
        with self.console.status("", spinner="dots", spinner_style=look.AMBER) as status:
            for line in lines:
                status.update(f"[{look.MUTED}]{line}…[/]")
                time.sleep(self.delay)

    def select(self, message: str, options: list[Option]) -> str:
        import questionary

        return questionary.select(
            message,
            choices=[_to_choice(option) for option in options],
            style=look.questionary_style(),
            pointer="›",
            qmark="◆",
            instruction="(arrows to move, enter to pick)",
        ).unsafe_ask()

    def pick(self, message: str, options: list[Option], budget: int, need_one: bool, done_label: str) -> list[str]:
        from bastion.picker import Picker

        chosen = Picker(message, options, budget, need_one, done_label).run()
        names = [option.title for option in options if option.value in chosen]
        spent = sum(option.cost for option in options if option.value in chosen)
        self.console.print(
            f"[bold {look.AMBER}]◆[/] [bold]{message}[/] [{look.MUTED}]({spent}/{budget})[/] "
            f"{', '.join(names) or 'nothing'}"
        )
        return chosen

    def build_waf(self, message: str, options: list[Option], preselected: list[str], status) -> list[str]:
        from bastion.picker import Picker

        return Picker(message, options, None, False, "Done, use this WAF", status=status, preselected=preselected).run()

    def say(self, content="") -> None:
        self.console.print(content)


def _to_choice(option: Option):
    from questionary import Choice

    title = option.title
    if option.tag and not option.disabled:
        title = option.title.ljust(TITLE_WIDTH) + option.tag
    return Choice(title, value=option.value, description=option.description, disabled=option.disabled)


class Game:
    def __init__(
        self,
        company: Company,
        catalog: Catalog,
        difficulty: str,
        ui,
        rng: random.Random | None = None,
        side: str = "practice",
    ):
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"Difficulty must be one of {DIFFICULTIES}")
        if side not in SIDES:
            raise ValueError(f"Side must be one of {SIDES}")
        self.rng = rng or random.Random()
        self.random_side = side == "random"
        self.blue_ai = ai.BlueAI(ai.BLUE_AI_KNOWLEDGE[difficulty], self.rng)
        self.side = self.rng.choice(("blue", "red")) if self.random_side else side
        self.company = roll_mistakes(company, self.rng)
        self.catalog = catalog
        self.level = difficulty
        self.easy = difficulty == "easy"
        self.explain = difficulty in ("easy", "medium")
        self.ui = ui

    def defense_options(self) -> list[Option]:
        options = []
        for defense in self.catalog.defenses_for(self.company.tier):
            if not self.explain:
                options.append(Option(defense.name, defense.id, tag=f"{defense.cost}", cost=defense.cost))
                continue
            countered = sorted(set(defense.blocks) | set(defense.detects))
            names = ", ".join(self.catalog.attacks[attack_id].name for attack_id in countered)
            options.append(Option(
                defense.name,
                defense.id,
                tag=f"{defense.cost:>3}  {defense.category}",
                cost=defense.cost,
                description=f"{defense.description} Counters: {names or 'nothing directly'}.",
            ))
        return options

    def attack_options(self) -> list[Option]:
        options = []
        for attack in self.catalog.attacks_for(self.company.tier):
            if not self.explain:
                options.append(Option(attack.name, attack.id, tag=f"{attack.cost}", cost=attack.cost))
                continue
            options.append(Option(
                attack.name,
                attack.id,
                tag=f"{attack.cost:>3}  {attack.mitre_id} {attack.tactic}",
                cost=attack.cost,
                description=f"{attack.description} Targets: {attack.target}s."
                + (f" Noise: {percent(attack.noise)}." if self.easy else ""),
            ))
        return options

    def pick_defenses(self, done_label: str = "Done, switch to Red") -> list[str]:
        self.ui.say(look.team_rule("blue", f"protect {self.company.name}"))
        self.ui.say(look.company_panel(self.company, self.explain, reveal_admins=self.easy))
        self.ui.say(look.budget_note("Blue", self.company.budget, self.company.budget_range, look.BLUE))
        return self.ui.pick("Pick your defenses", self.defense_options(), self.company.budget, False, done_label)

        library = load_library()
        saved = home() / "waf-build.json"
        try:
            preselected = json.loads(saved.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            preselected = []
        options = [
            Option(item.title, item.id, tag="clean up first" if item.kind == "clean" else "", description=item.explain)
            for item in library
        ]
        self.ui.say(look.waf_intro())

        def status(chosen: list[str]) -> list[tuple[str, str]]:
            return look.waf_status_tokens(evaluate(library_ruleset(chosen, library), corpus))

        chosen = self.ui.build_waf("Build your web application firewall", options, preselected, status)
        try:
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_text(json.dumps(chosen), encoding="utf-8")
        except OSError:
            pass
        report = evaluate(library_ruleset(chosen, library), corpus)
        self.ui.say(look.waf_summary(report))
        return report.score

    def pick_arsenal(self, subtitle: str = "switch sides and break in") -> list[str]:
        self.ui.say()
        self.ui.say(look.team_rule("red", subtitle))
        if self.side == "red":
            self.ui.say(look.company_panel(self.company, self.explain, reveal_admins=self.easy))
            self.ui.say(Text("The defenders already picked their defenses. You cannot see them. A scan shows what is visible from outside.", style=look.MUTED))
        self.ui.say(Text("You buy each attack once and can reuse it on any day.", style=look.MUTED))
        self.ui.say(look.budget_note("Red", self.company.red_budget, self.company.red_budget_range, look.RED))
        return self.ui.pick("Buy your arsenal", self.attack_options(), self.company.red_budget, True, "Done, start the attack")

    def action_options(self, campaign: Campaign) -> list[Option]:
        options = []
        for attack_id in campaign.arsenal:
            attack = self.catalog.attacks[attack_id]
            used = campaign.used.get(attack_id, 0)
            if not self.explain:
                options.append(Option(attack.name, attack_id))
                continue
            tag = f"used {used}x, more heat" if used and self.easy else ""
            blocked = self.why_impossible(campaign, attack_id)
            options.append(Option(attack.name, attack_id, tag=tag, description=self.move_hint(campaign, attack_id), disabled=blocked))
        options.append(Option("End the day", END_DAY))
        options.append(Option("Give up", GIVE_UP))
        return options

    def why_impossible(self, campaign: Campaign, attack_id: str) -> str | None:
        notes = []
        for target_id in campaign.targets_for(attack_id):
            preview = campaign.preview(attack_id, target_id)
            if preview.possible:
                return None
            notes.append(preview.note)
        return notes[0] if notes else "No targets."

    def move_hint(self, campaign: Campaign, attack_id: str) -> str:
        attack = self.catalog.attacks[attack_id]
        hint = attack.description
        if attack.tactic == "reconnaissance":
            hint += " It also shows which defenses are visible from outside."
            if not campaign.scan_helps():
                hint += " You have no server exploit or password attack, so intel is all you get."
        return hint

    def target_options(self, campaign: Campaign, attack_id: str) -> list[Option]:
        options = []
        for target_id in campaign.targets_for(attack_id):
            label = self.target_name(target_id)
            if not self.explain:
                options.append(Option(label, target_id))
                continue
            preview = campaign.preview(attack_id, target_id)
            if not preview.possible:
                options.append(Option(label, target_id, disabled=preview.note))
                continue
            if not self.easy:
                options.append(Option(label, target_id, description=preview.note or None))
                continue
            options.append(Option(
                label,
                target_id,
                tag=f"success {percent(preview.success_chance):>4}   spotted {percent(preview.detect_chance):>4}   heat -> {percent(preview.heat_after)}",
                description=preview.note or None,
            ))
        options.append(Option("Back", BACK))
        return options

    def target_name(self, target_id: str) -> str:
        for server in self.company.servers:
            if server.id == target_id:
                return f"{server.name} ({server.id})"
        for employee in self.company.employees:
            if employee.id == target_id:
                return f"{employee.name}, {employee.role}"
        return target_id

    def show_result(self, result: StepResult) -> None:
        target = self.target_name(result.step.target_id)
        self.ui.say(look.move_header(result, target))
        if result.possible:
            self.ui.suspense(look.suspense_lines(result, target))
        self.ui.say(look.outcome_text(result, self.easy, self.explain and self.side != "red"))
        if result.possible:
            self.ui.suspense([look.WATCHING])
            self.ui.say(look.detection_text(result))
        self.ui.say()

    def show_night(self, night: NightResult) -> None:
        self.ui.say()
        self.ui.suspense([look.NIGHT_WATCH])
        self.ui.say(look.night_panel(night, self.easy))

    def play_turns(self, campaign: Campaign) -> None:
        while not campaign.finished:
            if campaign.moves_left_today <= 0:
                self._end_day(campaign)
                continue
            self.ui.say(look.status_bar(campaign, self.easy))
            if self.explain:
                self.ui.say(look.foothold_panel(campaign))
            if campaign.known_defenses:
                self.ui.say(look.intel_line(campaign))
            action = self.ui.select("Your move", self.action_options(campaign))
            if action == GIVE_UP:
                return
            if action == END_DAY:
                self._end_day(campaign)
                continue
            target = self.ui.select("Target", self.target_options(campaign, action))
            if target == BACK:
                continue
            self.show_result(campaign.move(action, target))
            self.blue_ai_reacts(campaign)
            if campaign.kicked_out:
                self.ui.say(Text("The Blue Team kicked you out of the network.", style=f"bold {look.RED}"))

    def _end_day(self, campaign: Campaign) -> None:
        self.blue_ai_reacts(campaign, until_done=True)
        if campaign.finished:
            return
        night = campaign.end_day()
        if night:
            self.show_night(night)

    def show_ai_move(self, result: StepResult) -> None:
        target = self.target_name(result.step.target_id)
        if self.easy:
            self.ui.say(Text("  What the attacker just did (only Easy shows this):", style=look.MUTED))
            self.ui.say(look.move_header(result, target))
            self.ui.say(look.outcome_text(result, True, True))
            self.ui.say()
            return
        self.ui.suspense(["Time passes. Somewhere, someone is trying something"])

    def show_blue_night(self, night: NightResult) -> None:
        self.ui.say(look.blue_night(night, self.easy))

    def blue_options(self, campaign: Campaign) -> list[Option]:
        fresh = len(campaign.unseen_logs())
        open_entries = [e for e in campaign.seen_logs() if not e.investigated]
        explain = self.explain
        return [
            Option("See the logs", "logs", tag=f"{fresh} new" if fresh else "",
                   description="Read what your tools recorded. Tools that nobody reads catch nobody." if explain else None),
            Option("Investigate an alert", "investigate", tag=f"{len(open_entries)} open" if open_entries else "",
                   description="Find out if an alert is a real attack or a false alarm." if explain else None,
                   disabled=None if open_entries else "read the logs first"),
            Option("Change a password", "reset",
                   description="If the attacker had this account, they lose it. If not, the employee loses some time." if explain else None),
            Option("Isolate a machine", "isolate",
                   description="Cut a machine off the network until the end of tomorrow. Stops the attacker there, but work stops too." if explain else None),
            Option("Threat hunt on a machine", "hunt",
                   description="Search a machine for an attacker that no alert has shown yet." if explain else None),
            Option("Block a sender or address", "block",
                   description="Stop an attempt from outside from ever trying again." if explain else None,
                   disabled=None if campaign.seen_logs() else "read the logs first"),
            Option("Let time pass", WAIT,
                   description="Save the rest of your time. The attacker keeps moving." if explain else None),
        ]

    def blue_target_options(self, campaign: Campaign, kind: str) -> list[Option]:
        if kind in ("investigate", "block"):
            entries = [e for e in campaign.seen_logs() if kind == "block" or not e.investigated]
            return [Option(e.text, str(e.id), tag=f"{e.source}, day {e.day}  {look.confidence_hint(e, self.level)}") for e in entries] + [Option("Back", BACK)]
        if kind == "reset":
            return [Option(f"{e.name}, {e.role}", e.id) for e in self.company.employees] + [Option("Back", BACK)]
        return [
            Option(f"{s.name} ({s.id})", s.id, disabled="already isolated" if s.id in campaign.foothold.isolated else None)
            for s in self.company.servers
        ] + [Option("Back", BACK)]

    def blue_turn(self, campaign: Campaign) -> bool:
        while True:
            self.ui.say(look.blue_status_bar(campaign, self.easy))
            kind = self.ui.select("Your move as the analyst", self.blue_options(campaign))
            if kind == WAIT:
                return False
            target = None
            if kind != "logs":
                target = self.ui.select("Which one?", self.blue_target_options(campaign, kind))
                if target == BACK:
                    continue
            fresh = campaign.unseen_logs()
            action = campaign.blue(kind, target)
            if kind == "logs" and fresh:
                self.ui.say(look.log_table(fresh, self.level))
            self.ui.say(look.blue_action_text(action))
            self.ui.say()
            return True

    def defend(self, campaign: Campaign) -> None:
        red = ai.RedAI(ai.RED_AI_KNOWLEDGE[self.level])
        self.ui.say(Text("The attacker is out there. Your tools write logs, but nobody reads them unless you do.", style=look.MUTED))
        self.ui.say()
        while not campaign.finished:
            move = red.next_move(campaign)
            if move is not None:
                self.show_ai_move(campaign.move(*move))
                if not campaign.finished and campaign.blue_moves_left > 0:
                    self.blue_turn(campaign)
                continue
            while not campaign.finished and campaign.blue_moves_left > 0:
                if not self.blue_turn(campaign):
                    break
            if campaign.finished:
                break
            night = campaign.end_day()
            if night:
                self.show_blue_night(night)
        if campaign.kicked_out:
            self.ui.say(Text("You kicked the attacker out of the network.", style=f"bold {look.BLUE}"))

    def blue_ai_reacts(self, campaign: Campaign, until_done: bool = False) -> None:
        while campaign.active_blue and not campaign.finished:
            step = self.blue_ai.next_action(campaign)
            if step is None:
                return
            notice = look.red_notice(campaign.blue(*step))
            if notice:
                self.ui.say(notice)
            if not until_done:
                return

    def run(self) -> Campaign:
        if self.random_side:
            self.ui.say(look.random_side_note(self.side))
        if self.side == "blue":
            defenses = self.pick_defenses("Done, start the game")
            arsenal = ai.pick_arsenal(self.company, self.catalog, self.rng)
        elif self.side == "red":
            defenses = ai.pick_defenses(self.company, self.catalog, self.rng)
            arsenal = self.pick_arsenal("break in")
        else:
            defenses = self.pick_defenses()
            arsenal = self.pick_arsenal()
        edge = load_edge(self.company.tier, self.level, "blue" if self.side == "blue" else "red")
        campaign = Campaign(self.company, self.catalog, defenses, arsenal, rng=self.rng, edge=edge, active_blue=True)
        self.ui.say()
        if self.side == "blue":
            self.defend(campaign)
        else:
            self.play_turns(campaign)
        self.ui.say()
        blue = advice.blue_tips(campaign) if self.easy else []
        red = advice.red_tips(campaign) if self.easy else []
        self.ui.say(look.final_screen(campaign.report(), self.catalog, self.level, blue, red))
        self.finish(campaign)
        return campaign

    def finish(self, campaign: Campaign) -> None:
        log_game(campaign, self.level, "random-" + self.side if self.random_side else self.side)
        if self.side == "practice":
            return
        if self.side == "blue":
            score = scoring.blue_score(campaign, self.random_side)
        else:
            score = scoring.red_score(campaign, self.random_side)
        profile = load_profile()
        unlocked = profile.record(self.company.tier, self.level, score.won, score.total)
        save_profile(profile)
        self.ui.say(look.score_panel(score, profile, unlocked))


def waf_lab(ui) -> int:
    corpus = load_corpus()
    ui.say(look.waf_tutorial())
    expert_file = home() / "waf-rules.json"
    if expert_file.exists():
        how = ui.select("How do you want to build it?", [
            Option("Pick rules from the list", "list", description="Ready-made rules, explained in plain words."),
            Option("Use my own rules file (expert)", "file", description=str(expert_file)),
        ])
        if how == "file":
            report = evaluate(load_rules(expert_file), corpus)
            ui.say(look.waf_summary(report))
            return report.score

    library = load_library()
    saved = home() / "waf-build.json"
    try:
        preselected = json.loads(saved.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        preselected = []
    options = [
        Option(item.title, item.id, tag="clean up first" if item.kind == "clean" else "", description=item.explain)
        for item in library
    ]

    def status(chosen: list[str]) -> list[tuple[str, str]]:
        return look.waf_status_tokens(evaluate(library_ruleset(chosen, library), corpus))

    chosen = ui.build_waf("Build your web application firewall", options, preselected, status)
    try:
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text(json.dumps(chosen), encoding="utf-8")
    except OSError:
        pass
    report = evaluate(library_ruleset(chosen, library), corpus)
    ui.say(look.waf_summary(report))
    return report.score


def main(argv: list[str] | None = None, ui=None) -> int:
    parser = argparse.ArgumentParser(prog="bastion play", description="Play Bastion with the arrow keys.")
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--difficulty", choices=DIFFICULTIES, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--fast", action="store_true", help="no suspense pauses")
    parser.add_argument("--side", choices=SIDES, default=None)
    args = parser.parse_args(argv)

    ui = ui or Terminal(delay=0 if args.fast else 1.0)
    rng = random.Random(args.seed)
    catalog = load_catalog()
    try:
        ui.say(look.title_screen(args.difficulty))
        settings = None
        given = args if (args.difficulty or args.side or args.scenario) else None
        while True:
            if settings is None:
                if given is None:
                    mode = ui.select("Menu", [
                        Option("Play", "play", description="Defend or attack a company."),
                        Option("WAF Lab", "lab", description="Practice: learn how a web firewall stops hackers. Does not change your points."),
                        Option("Quit", QUIT),
                    ])
                    if mode == QUIT:
                        break
                    if mode == "lab":
                        waf_lab(ui)
                        if ui.select("What next?", [Option("Main menu", MENU), Option("Quit", QUIT)]) == QUIT:
                            break
                        continue
                settings = choose_settings(ui, given)
                given = None
            difficulty, side, company_id = settings
            Game(load_scenario(company_id), catalog, difficulty, ui, random.Random(rng.random()), side=side).run()
            ui.say()
            choice = ui.select("What next?", [
                Option("Play again", PLAY_AGAIN, description="Same company, difficulty and side, new game."),
                Option("Main menu", MENU, description="Pick another company, difficulty or side."),
                Option("Quit", QUIT),
            ])
            if choice == QUIT:
                break
            if choice == MENU:
                settings = None
    except KeyboardInterrupt:
        ui.say(Text("\nGame stopped.", style=look.MUTED))
        return 130
    ui.say(Text("See you next time.", style=look.MUTED))
    return 0


def choose_settings(ui, given=None) -> tuple[str, str, str]:
    profile = load_profile()
    level_lock = {level: None if profile.level_open(level) else profile.lock_reason("small", level) for level in DIFFICULTIES}
    difficulty = (given and given.difficulty) or ui.select("Difficulty", [
        Option("Easy", "easy", description="Attacks work more often. Explanations, chances and heat. At the end: advice."),
        Option("Medium", "medium", description="A fairer fight. Explanations but no numbers. At the end: what happened.",
               disabled=level_lock["medium"]),
        Option("Hard", "hard", description="The defenders have the edge. No help at all. At the end: only the result.",
               disabled=level_lock["hard"]),
    ])
    side = (given and given.side) or ui.select("Side", [
        Option("Blue", "blue", description="Defend the company. The computer attacks."),
        Option("Red", "red", description="Break in. The computer picked the defenses."),
        Option("Random", "random", description="Blue or Red by coin flip. Double points if you win."),
        Option("Practice", "practice", description="Play both sides. No points, no unlocks."),
    ])
    company_id = given and given.scenario
    if not company_id:
        company_id = ui.select("Company", [
            Option(c.name, c.id, tag=f"{c.tier}, {len(c.employees)} people", description=c.description,
                   disabled=profile.lock_reason(c.tier, difficulty))
            for c in list_scenarios()
        ])
    return difficulty, side, company_id


if __name__ == "__main__":
    sys.exit(main())
