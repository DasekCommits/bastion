# Bastion

[![CI](https://github.com/DasekCommits/bastion/actions/workflows/ci.yml/badge.svg)](https://github.com/DasekCommits/bastion/actions/workflows/ci.yml)

**Build a defense. Switch sides. Break it.**

**Play it in your browser: [bastion.dasek.dev](https://bastion.dasek.dev)**

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

Pick a difficulty, a side and a company, then everything happens with the arrow keys.

| Side | What you do |
|---|---|
| **Blue** | Pick the defenses. The computer attacks, and you only see what your tools catch. |
| **Red** | Break in. The computer already picked defenses you cannot see. |
| **Random** | A coin decides Blue or Red. Double points if you win. |
| **Practice** | Play both sides. No points and no unlocks. |

Win 5 games on the small company to unlock the medium one, and 10 on the medium company to unlock the large one. Progress is saved in `~/.bastion/profile.json`.

| | During the game | At the end |
|---|---|---|
| **Easy** | Explanations, success and detection chances, heat | Post-mortem, gaps and advice for both sides |
| **Medium** | Explanations, no numbers | Post-mortem without advice |
| **Hard** | Nothing | Only the result |

Difficulty also changes the odds, so Easy is easier for you whichever side you play. Each company, difficulty and side has an attacker edge in `data/balance.json`, tuned with thousands of games between computer players so that you win about this often:

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

### Scoring

- **Blue:** the share of data that survived (0-100), plus 10 for catching the attacker, 2 per spotted attempt (up to 10) and up to 10 for unspent budget.
- **Red:** the share of data stolen or destroyed (0-100), plus up to 10 for finishing early and 10 for owning the whole domain. Never getting caught multiplies the score by 1.5.
- **Random side:** a win counts double.
- Red wins a game by stealing or destroying anything at all. Otherwise Blue wins.

### Balance tools

```bash
python -m bastion check-balance        # play thousands of computer games, fail if a win rate drifts from its target
python -m bastion balance --all        # read the game log and list choices that win or lose far too often
```

Every finished game is written to `~/.bastion/games.jsonl`. CI runs the tests and the balance check on every push.

### WAF Lab

Pick **WAF Lab** in the main menu to practise how a Web Application Firewall works. A short tutorial explains SQL injection and XSS with a login example, then you build a firewall from plain-language rules and watch live how many of 40 real attack payloads it stops and how many of 25 innocent customers it blocks by mistake. It is practice only: in the game, every player's WAF is the same, so points stay fair.

Experts can write their own regex rules in `~/.bastion/waf-rules.json` and test them with `python -m bastion waf`. Rules that hang on crafted input (ReDoS) are stopped after five seconds.

### Web version

The browser version runs the same Python engine inside the page with [Pyodide](https://pyodide.org), so nothing is installed and the rules are identical to the terminal game. `src/bastion/web.py` is the bridge between the page and the engine, and `web/` holds the page itself.

```bash
python tools/build_web.py      # writes build/web: index.html, app.js, style.css and the packaged engine
```

Progress is kept in the browser for now. Accounts, a shared leaderboard and server-side dice against cheating come next.

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
- [x] Red Team budget, heat, multi-day campaigns and night hunts
- [x] Interactive arrow-key mode with Easy, Medium and Hard
- [x] Medium tier (Harbor Clinic) and Large tier (Meridian Savings Bank, Active Directory)
- [x] Realism: per-person traits, random admin mistakes, outside-only recon, pivots
- [x] Balance tuned with simulated games, 5-95% chance floor
- [x] Full scoring system (Blue and Red points, stealth and speed bonuses)
- [x] Play one side against the computer, random side for double points
- [x] Tier unlocks
- [x] WAF Lab: build a web firewall against real payloads (practice mode)
- [x] Playable in the browser (Python in WebAssembly)
- [ ] Accounts, public leaderboard and ELO ranking
- [x] CI with tests and an automatic balance check
- [x] Game logs and a report of choices that win or lose too often
- [x] Live at bastion.dasek.dev

## Status

Playable from the command line: three companies, three difficulties, Blue, Red or random against the computer, 22 attacks and 25 defenses. Next up are accounts and a shared leaderboard.

## License

[MIT](LICENSE)
