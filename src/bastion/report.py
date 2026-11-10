from bastion.catalog import Catalog
from bastion.engine import Report


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def format_report(report: Report, catalog: Catalog) -> str:
    company = report.company
    lines = [
        f"BASTION POST-MORTEM: {company.name} ({company.tier})",
        "=" * 60,
        f"Defenses: {', '.join(report.defenses) or 'none'}",
        f"Blue budget used: {report.budget_used}/{company.budget}",
        f"Red budget used:  {report.red_budget_used}/{company.red_budget}",
        "",
    ]

    for number, result in enumerate(report.results, start=1):
        attack = result.attack
        lines.append(
            f"{number}. {attack.name} -> {result.step.target_id}   "
            f"[{attack.mitre_id} {attack.tactic}, cost {attack.cost}]"
        )
        if not result.possible:
            lines.append(f"   SKIPPED  {result.note}")
        else:
            outcome = "SUCCESS" if result.succeeded else "BLOCKED"
            lines.append(
                f"   {outcome}  chance {_percent(result.success_chance)}, "
                f"detection {_percent(result.detect_chance)}, heat {_percent(result.heat)}"
            )
            if result.note:
                lines.append(f"   {result.note}")
            if result.detected:
                lines.append("   DETECTED  The Blue Team spotted this and kicked the attacker out.")
        if result.possible and result.helped:
            lines.append(f"   Helped: {', '.join(result.helped)}")
        if result.possible and result.succeeded and result.missing:
            lines.append(f"   Gap: {', '.join(result.missing)} would have made this harder")
        lines.append("")

    lines.append("-" * 60)
    if report.caught:
        lines.append("The attacker was caught.")
    else:
        lines.append("The attacker was never caught.")
    lines.append(f"Damage: {report.points}/{report.max_points} points")
    lines.append(f"Defense score: {report.defense_score}/100")

    gaps = {}
    for result in report.results:
        if result.possible and result.succeeded:
            for defense_id in result.missing:
                gaps.setdefault(defense_id, []).append(result.attack.mitre_id)
    if gaps:
        lines.append("")
        lines.append("Biggest gaps:")
        ranked = sorted(gaps.items(), key=lambda item: len(item[1]), reverse=True)
        for defense_id, mitre_ids in ranked[:3]:
            defense = catalog.defenses[defense_id]
            lines.append(f"  - {defense.name} (cost {defense.cost}) counters {', '.join(sorted(set(mitre_ids)))}")

    return "\n".join(lines)


def format_simulation(simulation, plan) -> str:
    lines = [
        "",
        f"SIMULATION: the same attack played {simulation.runs} times",
        "=" * 60,
        f"Average defense score: {simulation.average_score:.0f}/100",
        f"Worst run:             {simulation.worst_score}/100",
        f"Data lost in:          {_percent(simulation.breach_rate)} of runs",
        f"Attacker caught in:    {_percent(simulation.caught_rate)} of runs",
        "",
        "How often each step worked:",
    ]
    for step, rate in zip(plan, simulation.step_success):
        lines.append(f"  {_percent(rate):>4}  {step.attack_id} -> {step.target_id}")
    return "\n".join(lines)
