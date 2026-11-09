# Bastion

**Build a defense. Switch sides. Break it.**

Bastion is a purple-team training game. You play the Blue Team and secure a fictional company, then you switch to the Red Team and attack the defense you just built. At the end you get a post-mortem report that shows where your defense held, where it broke, and which gaps were left open, mapped to [MITRE ATT&CK](https://attack.mitre.org/).

Once you are happy with your defense, you publish it to the public leaderboard, where anyone can try to break it.

## How it works

1. **Blue phase.** You get a company (servers, employees, data) and a limited budget. You pick defenses such as MFA, patching, network segmentation, EDR, backups and detection rules, and you write your own WAF rules.
2. **Red phase.** You switch sides and run an attack chain: recon, initial access, privilege escalation, lateral movement and exfiltration. Some steps use real payloads (SQL injection, XSS) that are tested against your rules in a sandbox.
3. **Post-mortem.** You get a report on what was blocked, what got through, what was detected, and how to close each gap.
4. **Leaderboard.** You publish your fortress. Defenders are ranked by how long their fortress holds, and attackers by how many fortresses they break.

## Difficulty tiers

Each tier is a different company with its own budget, team, attack surface and attacker. Every tier has its own leaderboard, and you unlock the next tier by beating the previous one.

| | Small | Medium | Large |
|---|---|---|---|
| **Company** | Online shop, 5 people | Private clinic, 50 people | Bank, 500+ people |
| **Infrastructure** | Web server, database | + email, VPN, patient records | + Active Directory, cloud, ATM network |
| **Budget** | Low | Medium | High, but much more to cover |
| **Blue Team** | Just you | 2-3 IT staff | Full SOC with analysts |
| **Attacker** | Script kiddie | Ransomware gang | APT-style organized group |
| **Compliance** | None | GDPR (medical data) | GDPR + banking regulations |

Larger companies are harder because of more than their size. A bigger attack surface means more ways in, and every team has limited attention: too many noisy alerts and your analysts miss the real one (alert fatigue).

Every company is defined in a data file, so new scenarios can be added without touching the engine.

## Safety

Bastion never attacks real systems. The network is simulated, and payloads only run against an isolated rule engine, never against a live server.

## Tech stack

- **Engine:** Python
- **API:** FastAPI
- **Frontend:** HTML, CSS, JavaScript
- **Tests:** pytest

## Roadmap

- [x] Project setup
- [ ] Company model (assets, employees, network) and the Small tier
- [ ] Medium and Large tiers, tier unlocks
- [ ] Defense and attack catalog with MITRE ATT&CK mapping
- [ ] Simulation engine and post-mortem report
- [ ] WAF rule sandbox (real payloads vs. real rules)
- [ ] Web API and playable browser UI
- [ ] Accounts and public leaderboard
- [ ] Live deployment and CI

## Status

Early development.

## License

[MIT](LICENSE)
