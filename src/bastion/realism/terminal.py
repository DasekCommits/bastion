VERBS = {
    "recon": "port-scan",
    "phish": "phishing",
    "macro": "macro",
    "usb": "usb-drop",
    "bribe": "insider",
    "guess": "brute-force",
    "reuse": "credential-stuffing",
    "spray": "password-spray",
    "fatigue": "mfa-fatigue",
    "cloud": "cloud-takeover",
    "exploit": "exploit-web",
    "vpn": "vpn-exploit",
    "vendor": "vendor-breach",
    "escalate": "privilege-escalation",
    "move": "remote-desktop",
    "hash": "pass-the-hash",
    "tickets": "kerberoasting",
    "replicate": "dcsync",
    "steal": "exfiltration",
    "encrypt": "ransomware",
    "wipe": "destruction",
    "invoice": "bec",
    "hijack": "session-hijack",
    "aitm": "aitm-phishing",
    "vish": "helpdesk-vishing",
    "consent": "oauth-consent",
    "remote": "rmm-abuse",
    "dump": "lsass-dump",
    "golden": "golden-ticket",
    "upload": "cloud-exfil",
    "tunnel": "dns-tunnel",
    "nobackup": "inhibit-recovery",
}

HELP = [
    "Commands use a verb and a target: a hostname, an address or a username.",
    "  targets [search]        list machines and people; add a word to filter (e.g. targets admin)",
    "  status                  what you control right now",
    "  sleep                   end the day",
    "  giveup                  stop and see the result",
    "Moves (only the ones in your arsenal work):",
]


def help_lines(arsenal: list[str], catalog) -> list[str]:
    lines = list(HELP)
    for verb, attack_id in VERBS.items():
        if attack_id in arsenal:
            attack = catalog.attacks[attack_id]
            lines.append(f"  {verb:<10} <target>    {attack.name} ({attack.mitre_id})")
    return lines


def resolve(world, company, text: str) -> str | None:
    text = text.strip().lower()
    for host in world.hosts.values():
        if text in (host.hostname.lower(), host.ip, (host.public_ip or "").lower(), host.id.lower()):
            return host.id
    for account in world.accounts.values():
        if text in (account.username, account.email.lower(), account.id):
            return account.id
    return None
