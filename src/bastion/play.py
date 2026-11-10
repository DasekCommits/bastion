import argparse
import random
import sys
from dataclasses import dataclass

from rich.console import Console
from rich.text import Text

from bastion import look
from bastion.catalog import Catalog, load_catalog
from bastion.company import Company, load_scenario
from bastion.engine import Campaign, NightResult, StepResult
from bastion.look import percent

END_DAY = "end-day"
GIVE_UP = "give-up"
BACK = "back"
DIFFICULTIES = ("easy", "hard")
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
    def __init__(self):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        self.console = Console(highlight=False)

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

    def say(self, content="") -> None:
        self.console.print(content)


def _to_choice(option: Option):
    from questionary import Choice

    title = option.title
    if option.tag and not option.disabled:
        title = option.title.ljust(TITLE_WIDTH) + option.tag
    return Choice(title, value=option.value, description=option.description, disabled=option.disabled)


class Game:
    def __init__(self, company: Company, catalog: Catalog, difficulty: str, ui, rng: random.Random | None = None):
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"Difficulty must be one of {DIFFICULTIES}")
        self.company = company
        self.catalog = catalog
        self.easy = difficulty == "easy"
        self.ui = ui
        self.rng = rng or random.Random()

    def defense_options(self) -> list[Option]:
        options = []
        for defense in self.catalog.defenses.values():
            if not self.easy:
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
        for attack in self.catalog.attacks.values():
            if not self.easy:
                options.append(Option(attack.name, attack.id, tag=f"{attack.cost}", cost=attack.cost))
                continue
            options.append(Option(
                attack.name,
                attack.id,
                tag=f"{attack.cost:>3}  {attack.mitre_id} {attack.tactic}",
                cost=attack.cost,
                description=f"{attack.description} Targets: {attack.target}s. Noise: {percent(attack.noise)}.",
            ))
        return options

    def pick_defenses(self) -> list[str]:
        self.ui.say(look.team_rule("blue", f"protect {self.company.name}"))
        self.ui.say(look.company_panel(self.company, self.easy))
        return self.ui.pick("Pick your defenses", self.defense_options(), self.company.budget, False, "Done, switch to Red")

    def pick_arsenal(self) -> list[str]:
        self.ui.say()
        self.ui.say(look.team_rule("red", "switch sides and break in"))
        self.ui.say(Text("You buy each attack once and can reuse it on any day.", style=look.MUTED))
        return self.ui.pick("Buy your arsenal", self.attack_options(), self.company.red_budget, True, "Done, start the attack")

    def action_options(self, campaign: Campaign) -> list[Option]:
        options = []
        for attack_id in campaign.arsenal:
            attack = self.catalog.attacks[attack_id]
            used = campaign.used.get(attack_id, 0)
            if not self.easy:
                options.append(Option(attack.name, attack_id))
                continue
            tag = f"used {used}x, more heat" if used else ""
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
        if attack.tactic == "reconnaissance" and "exploit-web" not in campaign.arsenal:
            hint += " Warning: a scan only helps Exploit the web shop, which you did not buy."
        return hint

    def target_options(self, campaign: Campaign, attack_id: str) -> list[Option]:
        options = []
        for target_id in campaign.targets_for(attack_id):
            label = self.target_name(target_id)
            if not self.easy:
                options.append(Option(label, target_id))
                continue
            preview = campaign.preview(attack_id, target_id)
            if not preview.possible:
                options.append(Option(label, target_id, disabled=preview.note))
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
        self.ui.say(look.result_text(result, self.target_name(result.step.target_id), self.easy))

    def show_night(self, night: NightResult) -> None:
        self.ui.say(look.night_panel(night, self.easy))

    def play_turns(self, campaign: Campaign) -> None:
        while not campaign.finished:
            if campaign.moves_left_today <= 0:
                self._end_day(campaign)
                continue
            self.ui.say(look.status_bar(campaign, self.easy))
            if self.easy:
                self.ui.say(look.foothold_panel(campaign))
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

    def run(self) -> Campaign:
        defenses = self.pick_defenses()
        arsenal = self.pick_arsenal()
        campaign = Campaign(self.company, self.catalog, defenses, arsenal, rng=self.rng)
        self.ui.say()
        self.play_turns(campaign)
        self.ui.say()
        self.ui.say(look.final_screen(campaign.report(), self.catalog))
        return campaign


def main(argv: list[str] | None = None, ui=None) -> int:
    parser = argparse.ArgumentParser(prog="bastion play", description="Play Bastion with the arrow keys.")
    parser.add_argument("--scenario", default="olive-byte")
    parser.add_argument("--difficulty", choices=DIFFICULTIES, default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)

    ui = ui or Terminal()
    try:
        ui.say(look.title_screen(args.difficulty))
        difficulty = args.difficulty or ui.select("Difficulty", [
            Option("Easy", "easy", description="See explanations, chances and heat before every move."),
            Option("Hard", "hard", description="No help. You only see what happened."),
        ])
        game = Game(load_scenario(args.scenario), load_catalog(), difficulty, ui, random.Random(args.seed))
        game.run()
    except KeyboardInterrupt:
        ui.say(Text("\nGame stopped.", style=look.MUTED))
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
