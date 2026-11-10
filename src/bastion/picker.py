from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

from bastion import look

TITLE_WIDTH = 30
BAR_WIDTH = 20

STYLE = Style.from_dict({
    "mark": f"{look.AMBER} bold",
    "question": "bold",
    "pointer": f"{look.AMBER} bold",
    "here": f"{look.AMBER} bold",
    "on": f"{look.GREEN} bold",
    "off": look.FAINT,
    "tag": look.MUTED,
    "spent": f"{look.GREEN} bold",
    "full": f"{look.AMBER} bold",
    "empty": look.FAINT,
    "hint": f"{look.MUTED} italic",
    "warning": f"{look.RED} bold",
    "done": f"{look.GREEN} bold",
})


class Picker:
    def __init__(
        self,
        message: str,
        options: list,
        budget: int | None,
        need_one: bool = False,
        done_label: str = "Done",
        status=None,
        preselected: list[str] | None = None,
    ):
        self.message = message
        self.options = options
        self.budget = budget
        self.need_one = need_one
        self.done_label = done_label
        self.status = status
        self.cursor = 0
        valid = {option.value for option in options}
        self.chosen: list[str] = [value for value in (preselected or []) if value in valid]
        self.warning = ""

    @property
    def spent(self) -> int:
        return sum(option.cost for option in self.options if option.value in self.chosen)

    @property
    def on_done(self) -> bool:
        return self.cursor == len(self.options)

    def move(self, step: int) -> None:
        self.cursor = (self.cursor + step) % (len(self.options) + 1)
        self.warning = ""

    def toggle(self) -> None:
        option = self.options[self.cursor]
        if option.value in self.chosen:
            self.chosen.remove(option.value)
            self.warning = ""
        elif self.budget is not None and self.spent + option.cost > self.budget:
            self.warning = f"Not enough budget: {option.title} costs {option.cost}, you have {self.budget - self.spent} left."
        else:
            self.chosen.append(option.value)
            self.warning = ""

    def press_enter(self) -> bool:
        if not self.on_done:
            self.toggle()
            return False
        if self.need_one and not self.chosen:
            self.warning = "Pick at least one first."
            return False
        return True

    def tokens(self) -> list[tuple[str, str]]:
        lines = [("class:mark", "◆ "), ("class:question", self.message), ("", "\n")]
        if self.budget is not None:
            spent, left = self.spent, self.budget - self.spent
            filled = round(BAR_WIDTH * spent / self.budget) if self.budget else 0
            lines += [
                ("class:tag", "  Spent "), ("class:spent", f"{spent}/{self.budget} "),
                ("class:full", "█" * filled), ("class:empty", "░" * (BAR_WIDTH - filled)),
                ("class:tag", f"  {left} left"),
            ]
        if self.status:
            lines += self.status(list(self.chosen))
        lines.append(("", "\n\n"))
        for index, option in enumerate(self.options):
            here = index == self.cursor
            picked = option.value in self.chosen
            lines.append(("class:pointer", " › " if here else "   "))
            lines.append(("class:on", "[x] ") if picked else ("class:off", "[ ] "))
            lines.append(("class:here" if here else "", option.title.ljust(TITLE_WIDTH)))
            lines.append(("class:tag", option.tag))
            lines.append(("", "\n"))
        lines.append(("", "\n"))
        lines.append(("class:pointer", " › " if self.on_done else "   "))
        lines.append(("class:done" if self.on_done else "class:tag", f"{self.done_label} →"))
        lines.append(("", "\n\n"))
        if not self.on_done and self.options[self.cursor].description:
            lines.append(("class:hint", "  " + self.options[self.cursor].description + "\n"))
        if self.warning:
            lines.append(("class:warning", "  " + self.warning + "\n"))
        lines.append(("class:hint", "  ↑↓ move · enter picks or removes · enter on Done to continue"))
        return lines

    def run(self) -> list[str]:
        keys = KeyBindings()

        @keys.add("up")
        @keys.add("k")
        def _(event):
            self.move(-1)

        @keys.add("down")
        @keys.add("j")
        def _(event):
            self.move(1)

        @keys.add("space")
        def _(event):
            if not self.on_done:
                self.toggle()

        @keys.add("enter")
        def _(event):
            if self.press_enter():
                event.app.exit(result=list(self.chosen))

        @keys.add("c-c")
        @keys.add("c-q")
        def _(event):
            event.app.exit(exception=KeyboardInterrupt)

        window = Window(FormattedTextControl(self.tokens, show_cursor=False), wrap_lines=True)
        app = Application(layout=Layout(window), key_bindings=keys, style=STYLE, erase_when_done=True)
        return app.run()
