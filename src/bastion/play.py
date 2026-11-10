import argparse
import random
import sys
from dataclasses import dataclass

from bastion.catalog import Catalog, load_catalog
from bastion.company import Company, load_scenario
from bastion.engine import Campaign, NightResult, StepResult
from bastion.report import format_report

END_DAY = "end-day"
GIVE_UP = "give-up"
DIFFICULTIES = ("easy", "hard")


@dataclass
class Option:
    title: str
    value: str
    description: str | None = None
    disabled: str | None = None


class Terminal:
    def select(self, message: str, options: list[Option]) -> str:
        import questionary

        choices = [_to_choice(option) for option in options]
        return questionary.select(message, choices=choices).unsafe_ask()

    def checkbox(self, message: str, options: list[Option], validate) -> list[str]:
        import questionary

        choices = [_to_choice(option) for option in options]
        return questionary.checkbox(message, choices=choices, validate=validate).unsafe_ask()

    def say(self, text: str = "") -> None:
        print(text)


def _to_choice(option: Option):
    from questionary import Choice

    return Choice(option.title, value=option.value, description=option.description, disabled=option.disabled)


def percent(value: float) -> str:
    return f"{value * 100:.0f}%"


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
                options.append(Option(f"{defense.name} ({defense.cost})", defense.id))
                continue
            countered = sorted(set(defense.blocks) | set(defense.detects))
            names = ", ".join(self.catalog.attacks[attack_id].name for attack_id in countered)
            options.append(Option(
                f"{defense.name}  cost {defense.cost}  [{defense.category}]",
                defense.id,
                description=f"{defense.description} Counters: {names or 'nothing directly'}.",
            ))
        return options

    def attack_options(self) -> list[Option]:
        options = []
        for attack in self.catalog.attacks.values():
            if not self.easy:
                options.append(Option(f"{attack.name} ({attack.cost})", attack.id))
                continue
            options.append(Option(
                f"{attack.name}  cost {attack.cost}  [{attack.mitre_id} {attack.tactic}]",
                attack.id,
                description=f"{attack.description} Targets: {attack.target}s. Noise: {percent(attack.noise)}.",
            ))
        return options

    def _budget_check(self, kind: str, budget: int):
        prices = self.catalog.defenses if kind == "defense" else self.catalog.attacks

        def validate(selected: list) -> bool | str:
            total = sum(prices[item if isinstance(item, str) else item.value].cost for item in selected)
            if total > budget:
                return f"That costs {total}, but the budget is {budget}."
            return True

        return validate

    def pick_defenses(self) -> list[str]:
        self.ui.say(f"BLUE TEAM: protect {self.company.name}")
        self.ui.say(self.company.description)
        self.ui.say(f"Budget: {self.company.budget}")
        self.ui.say()
        return self.ui.checkbox(
            "Pick your defenses (space to select, enter to confirm):",
            self.defense_options(),
            self._budget_check("defense", self.company.budget),
        )

    def pick_arsenal(self) -> list[str]:
        self.ui.say()
        self.ui.say("RED TEAM: now switch sides and break in")
        self.ui.say(f"Red budget: {self.company.red_budget}. You buy each attack once and can reuse it any day.")
        self.ui.say()
        while True:
            arsenal = self.ui.checkbox(
                "Buy your arsenal:",
                self.attack_options(),
                self._budget_check("attack", self.company.red_budget),
            )
            if arsenal:
                return arsenal
            self.ui.say("You need at least one attack.")

    def status_line(self, campaign: Campaign) -> str:
        line = f"Day {campaign.day}/{self.company.max_days}, moves left today: {campaign.moves_left_today}"
        if self.easy:
            line += f", heat: {percent(campaign.heat)}"
        return line

    def foothold_line(self, campaign: Campaign) -> str:
        foothold = campaign.foothold
        parts = []
        if foothold.employees:
            parts.append("accounts: " + ", ".join(sorted(foothold.employees)))
        if foothold.servers:
            parts.append("on: " + ", ".join(sorted(foothold.servers)))
        if foothold.admin_on:
            parts.append("admin on: " + ", ".join(sorted(foothold.admin_on)))
        if foothold.scanned:
            parts.append("scanned: " + ", ".join(sorted(foothold.scanned)))
        return "Foothold: " + ("; ".join(parts) if parts else "none yet")

    def action_options(self, campaign: Campaign) -> list[Option]:
        options = []
        for attack_id in campaign.arsenal:
            attack = self.catalog.attacks[attack_id]
            used = campaign.used.get(attack_id, 0)
            title = attack.name
            if self.easy and used:
                title += f"  (used {used}x, more heat)"
            options.append(Option(title, attack_id))
        options.append(Option("End the day", END_DAY))
        options.append(Option("Give up", GIVE_UP))
        return options

    def target_options(self, campaign: Campaign, attack_id: str) -> list[Option]:
        options = []
        for target_id in campaign.targets_for(attack_id):
            label = self._target_name(target_id)
            if not self.easy:
                options.append(Option(label, target_id))
                continue
            preview = campaign.preview(attack_id, target_id)
            if not preview.possible:
                options.append(Option(label, target_id, disabled=preview.note))
                continue
            options.append(Option(
                f"{label}  success {percent(preview.success_chance)}, "
                f"spotted {percent(preview.detect_chance)}, heat -> {percent(preview.heat_after)}",
                target_id,
                description=preview.note or None,
            ))
        return options

    def _target_name(self, target_id: str) -> str:
        for server in self.company.servers:
            if server.id == target_id:
                return f"{server.name} ({server.id})"
        for employee in self.company.employees:
            if employee.id == target_id:
                return f"{employee.name}, {employee.role}"
        return target_id

    def show_result(self, result: StepResult) -> None:
        if not result.possible:
            self.ui.say(f"  WASTED  {result.note}")
            return
        outcome = "SUCCESS" if result.succeeded else "FAILED"
        if self.easy:
            outcome += f"  (chance was {percent(result.success_chance)}, heat now {percent(result.heat)})"
        self.ui.say(f"  {outcome}")
        if result.succeeded and result.note:
            self.ui.say(f"  {result.note}")
        if self.easy and not result.succeeded and result.helped:
            self.ui.say(f"  Stopped by: {', '.join(result.helped)}")
        if result.detected:
            self.ui.say("  DETECTED  The Blue Team spotted you and kicked you out.")

    def show_night(self, night: NightResult) -> None:
        self.ui.say()
        self.ui.say(f"Night {night.day} falls.")
        if self.easy:
            self.ui.say(
                f"  Heat {percent(night.heat_before)} -> {percent(night.heat_after)}, "
                f"chance the Blue Team finds you in the logs: {percent(night.hunt_chance)}"
            )
        if night.found:
            self.ui.say("  FOUND  The Blue Team found you in the logs and kicked you out.")
        else:
            self.ui.say("  The night passes quietly.")
        self.ui.say()

    def play_turns(self, campaign: Campaign) -> None:
        while not campaign.finished:
            if campaign.moves_left_today <= 0:
                self._end_day(campaign)
                continue
            self.ui.say(self.status_line(campaign))
            if self.easy:
                self.ui.say(self.foothold_line(campaign))
            action = self.ui.select("Your move:", self.action_options(campaign))
            if action == GIVE_UP:
                return
            if action == END_DAY:
                self._end_day(campaign)
                continue
            target = self.ui.select("Target:", self.target_options(campaign, action))
            self.show_result(campaign.move(action, target))
            self.ui.say()

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
        self.ui.say(format_report(campaign.report(), self.catalog))
        return campaign


def main(argv: list[str] | None = None, ui=None) -> int:
    parser = argparse.ArgumentParser(prog="bastion play", description="Play Bastion with the arrow keys.")
    parser.add_argument("--scenario", default="olive-byte")
    parser.add_argument("--difficulty", choices=DIFFICULTIES, default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)

    ui = ui or Terminal()
    try:
        difficulty = args.difficulty or ui.select("Difficulty:", [
            Option("Easy", "easy", description="See explanations, chances and heat before every move."),
            Option("Hard", "hard", description="No help. You only see what happened."),
        ])
        game = Game(load_scenario(args.scenario), load_catalog(), difficulty, ui, random.Random(args.seed))
        game.run()
    except KeyboardInterrupt:
        ui.say("\nGame stopped.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
