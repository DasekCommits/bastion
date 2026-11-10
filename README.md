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

## Scoring

Both sides are limited and both sides score points.

**Blue Team**
- **Defense score (0-100):** how much of the company's data survived, averaged over every attack other players throw at your fortress
- **Detection bonus:** catching the attacker counts, not only stopping them
- **Efficiency bonus:** the same protection for less budget ranks higher

**Red Team**
- **Damage:** the value of the data you stole or encrypted
- **Stealth bonus:** x1.5 if you were never detected
- **Speed bonus:** fewer steps, more points
- **Attack budget:** every technique has a cost. A phishing email is cheap, a zero-day exploit is expensive, so attackers have to choose as carefully as defenders.
- **Heat:** every step makes noise, and noise adds up. Repeating the same attack raises suspicion even faster, and detection tools such as SIEM and EDR make heat rise quicker. The longer and louder you are, the more likely you get caught.

**Days.** An attack is a campaign of up to 5 days with up to 3 moves per day. Spend day one on recon, lie low on day two, strike on day three. Heat cools down overnight, but if the Blue Team has detection tools, they review the logs every night and may find you. Fast and loud or slow and patient: both are valid strategies.

**Ranking** uses an ELO rating, as in chess: breaking a strong fortress is worth more than breaking a weak one.

Every attack is replayed 1,000 times (Monte Carlo simulation), so scores reflect the quality of a defense, not a lucky roll.

## Try it

```bash
python -m venv .venv
.venv/Scripts/activate        # on Linux or macOS: source .venv/bin/activate
pip install -e . pytest

python -m bastion --defenses "mfa,patching,email-filter" --attack "phishing:sophie | | exfiltration:db-01,ransomware:db-01"
pytest
```

Commas separate moves and `|` separates days (an empty day means waiting). You get a day-by-day post-mortem of the attack and a summary of 1,000 replays.

### Interactive play

```bash
python -m bastion play
python -m bastion play --scenario harbor-clinic --difficulty medium --seed 7 --fast
```

Pick a company and a difficulty, then everything happens with the arrow keys: your defenses as Blue, your arsenal as Red, then one move at a time.

| | During the game | At the end |
|---|---|---|
| **Easy** | Explanations, success and detection chances, heat | Post-mortem, gaps and advice for both sides |
| **Medium** | Explanations, no numbers | Post-mortem without advice |
| **Hard** | Nothing | Only the result |

Difficulty also changes the odds. Each company and difficulty has an attacker edge in `data/balance.json`, tuned with thousands of simulated games so the attacker gets away with something about this often:

| | Small | Medium | Large |
|---|---|---|---|
| Easy | 80% | 70% | 60% |
| Medium | 70% | 50% | 30% |
| Hard | 50% | 30% | 10% |

No single move ever has less than a 5% or more than a 95% chance to succeed or to be spotted, so even a perfect setup on either side can still lose.

### Companies

| Company | Tier | People | Blue / Red budget (rolled each game, steps of 5) | Days |
|---|---|---|---|---|
| Olive Byte, an online olive oil shop | small | 5 | 40-60 / 40-60 | 5 |
| Harbor Clinic, a private medical clinic | medium | 10 | 70-90 / 60-80 | 7 |
| Meridian Savings Bank, a regional bank on Active Directory | large | 20 | 130-170 / 100-140 | 10 |

The large tier adds Active Directory attacks (Kerberoasting, Pass-the-Hash, DCSync), password spraying, MFA fatigue, cloud account takeover, a breached IT vendor and business email compromise, answered by phishing-resistant MFA, LAPS, a tiered admin model, honeytokens, conditional access, vendor access control, payment call-back checks and a 24/7 SOC.

The medium tier adds a VPN gateway, macro documents, infected USB sticks, bribed insiders and data wiping, plus macro blocking, USB control and data loss prevention on the Blue side.

### Realism

- **People differ.** Each employee has their own awareness of phishing and password habits, so the best target depends on the attack.
- **Mistakes are random.** At most one non-IT employee may have been given admin rights by mistake, rolled every game. Only Easy shows who; in Medium and Hard you find out once you are in.
- **Getting spotted outside is not the end.** If the Blue Team spots an attempt before you are inside, they block that exact attempt and become more alert. Getting spotted once you are inside gets you kicked out. Nobody can find you in the logs at night if you never got in.
- **Insiders.** Bribing an employee depends on their loyalty: a long-time director rarely sells out, an underpaid contractor might.
- **Recon shows only the outside.** A port scan reveals defenses visible from the internet (firewall, WAF, patch level, email filtering, MFA on login pages). Internal defenses such as SIEM or segmentation stay hidden, and EDR is only noticed once you are inside a machine. Scanning a login page makes password attacks more effective.
- **Pivots.** Config files on a web server or VPN can hold passwords that open internal systems, unless the network is segmented.

## Safety

Bastion never attacks real systems. The network is simulated, and payloads only run against an isolated rule engine, never against a live server.

## Tech stack

- **Engine:** Python
- **API:** FastAPI
- **Frontend:** HTML, CSS, JavaScript
- **Tests:** pytest

## Roadmap

- [x] Project setup
- [x] Company model (assets, employees, network) and the Small tier
- [x] Defense and attack catalog with MITRE ATT&CK mapping
- [x] Simulation engine and post-mortem report
- [ ] Red Team budget and the full scoring system
- [ ] Medium and Large tiers, tier unlocks
- [ ] WAF rule sandbox (real payloads vs. real rules)
- [ ] Web API and playable browser UI
- [ ] Accounts, public leaderboard and ELO ranking
- [ ] Live deployment and CI

## Status

Early development. The Small tier is playable from the command line, including an interactive arrow-key mode. The Medium and Large tiers are playable too.

## License

[MIT](LICENSE)
