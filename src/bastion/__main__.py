import argparse
import sys

from bastion.catalog import load_catalog
from bastion.company import load_scenario
from bastion.engine import PlanError, Step, run_attack, simulate
from bastion.report import format_report, format_simulation


def parse_plan(text: str) -> list[Step]:
    plan = []
    for day, moves in enumerate(text.split("|"), start=1):
        for item in moves.split(","):
            if not item.strip():
                continue
            attack_id, _, target_id = item.strip().partition(":")
            if not target_id:
                raise PlanError(f"Write each step as attack:target, got '{item.strip()}'")
            plan.append(Step(attack_id, target_id, day))
    return plan


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "play":
        from bastion.play import main as play

        return play(argv[1:])

    parser = argparse.ArgumentParser(prog="bastion", description="Build a defense. Switch sides. Break it.")
    parser.add_argument("--scenario", default="olive-byte")
    parser.add_argument("--defenses", default="", help="comma-separated defense ids")
    parser.add_argument("--attack", required=True, help="attack:target steps, commas between moves, | between days")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--runs", type=int, default=1000, help="how many times to replay the attack")
    args = parser.parse_args(argv)

    company = load_scenario(args.scenario)
    catalog = load_catalog()
    defense_ids = [item.strip() for item in args.defenses.split(",") if item.strip()]

    try:
        plan = parse_plan(args.attack)
        report = run_attack(company, catalog, defense_ids, plan, seed=args.seed)
        simulation = simulate(company, catalog, defense_ids, plan, runs=args.runs, seed=args.seed)
    except PlanError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(format_report(report, catalog))
    print(format_simulation(simulation, plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
