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
        self.side = self.rng.choice(("blue", "red")) if self.random_side else side
        self.company = roll_mistakes(company, self.rng)
        self.catalog = catalog
        self.level = difficulty
        self.easy = difficulty == "easy"
        self.explain = difficulty in ("easy", "medium")
        self.ui = ui
        self.waf_score: int | None = None

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
        chosen = self.ui.pick("Pick your defenses", self.defense_options(), self.company.budget, False, done_label)
        if "waf" in chosen:
            self.waf_score = self.build_waf()
        return chosen

    def build_waf(self) -> int:
        corpus = load_corpus()
        expert_file = home() / "waf-rules.json"
        if expert_file.exists():
            how = self.ui.select("Your web application firewall", [
                Option("Pick rules from the list", "list", description="Choose ready-made rules, explained in plain words."),
                Option("Use my own rules file (expert)", "file", description=str(expert_file)),
            ])
            if how == "file":
                report = evaluate(load_rules(expert_file), corpus)
                self.ui.say(look.waf_summary(report))
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
        self.ui.say(look.outcome_text(result, self.easy, self.explain))
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

    def _end_day(self, campaign: Campaign) -> None:
        night = campaign.end_day()
        if night:
            self.show_night(night)

    def show_ai_move(self, result: StepResult) -> None:
        target = self.target_name(result.step.target_id)
        if self.easy:
            self.ui.say(look.move_header(result, target))
            self.ui.say(look.outcome_text(result, True, True))
            if result.possible:
                self.ui.say(look.detection_text(result))
            self.ui.say()
            return
        if result.detected:
            self.ui.suspense([f"Your tools raise an alert on {target}"])
            self.ui.say(look.blue_alert(result, target, named=self.explain))

    def show_blue_night(self, night: NightResult) -> None:
        self.ui.say(look.blue_night(night, self.easy))

    def watch_attack(self, campaign: Campaign) -> None:
        red = ai.RedAI(ai.RED_AI_KNOWLEDGE[self.level])
        self.ui.say(Text("The attacker is out there. You only see what your tools catch.", style=look.MUTED))
        self.ui.say()
        ai.play_out(campaign, red, on_move=self.show_ai_move, on_night=self.show_blue_night)

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
        campaign = Campaign(self.company, self.catalog, defenses, arsenal, rng=self.rng, edge=edge, waf_score=self.waf_score)
        self.ui.say()
        if self.side == "blue":
            self.watch_attack(campaign)
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
        unlocked = profile.record(self.company.tier, score.won, score.total)
        save_profile(profile)
        self.ui.say(look.score_panel(score, profile, unlocked))


def main(argv: list[str] | None = None, ui=None) -> int:
    parser = argparse.ArgumentParser(prog="bastion play", description="Play Bastion with the arrow keys.")
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--difficulty", choices=DIFFICULTIES, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--fast", action="store_true", help="no suspense pauses")
    parser.add_argument("--side", choices=SIDES, default=None)
    args = parser.parse_args(argv)

    ui = ui or Terminal(delay=0 if args.fast else 1.0)
    try:
        ui.say(look.title_screen(args.difficulty))
        difficulty = args.difficulty or ui.select("Difficulty", [
            Option("Easy", "easy", description="Attacks work more often. Explanations, chances and heat. At the end: advice."),
            Option("Medium", "medium", description="A fairer fight. Explanations but no numbers. At the end: what happened."),
            Option("Hard", "hard", description="The defenders have the edge. No help at all. At the end: only the result."),
        ])
        side = args.side or ui.select("Side", [
            Option("Blue", "blue", description="Defend the company. The computer attacks."),
            Option("Red", "red", description="Break in. The computer picked the defenses."),
            Option("Random", "random", description="Blue or Red by coin flip. Double points if you win."),
            Option("Practice", "practice", description="Play both sides. No points, no unlocks."),
        ])
        profile = load_profile()
        if args.scenario:
            company = load_scenario(args.scenario)
        else:
            choice = ui.select("Company", [
                Option(c.name, c.id, tag=f"{c.tier}, {len(c.employees)} people", description=c.description,
                       disabled=profile.lock_reason(c.tier))
                for c in list_scenarios()
            ])
            company = load_scenario(choice)
        game = Game(company, load_catalog(), difficulty, ui, random.Random(args.seed), side=side)
        game.run()
    except KeyboardInterrupt:
        ui.say(Text("\nGame stopped.", style=look.MUTED))
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
