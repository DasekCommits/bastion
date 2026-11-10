import random

from bastion.engine import Campaign, PlanError
from bastion.realism import spl
from bastion.realism.telemetry import Telemetry
from bastion.realism.world import build_world


class RealismGame:
    def __init__(self, campaign: Campaign, rng: random.Random | None = None):
        self.campaign = campaign
        self.rng = rng or random.Random()
        self.world = build_world(campaign.company, self.rng)
        self.telemetry = Telemetry(self.world, campaign.company, campaign.defense_ids, self.rng)
        self.telemetry.noise(1)
        self.blocked_ips: set[str] = set()

    def _source(self) -> tuple[str, str]:
        foothold = self.campaign.foothold
        for employee_id in sorted(foothold.employees):
            account = self.world.accounts[employee_id]
            return account.workstation_ip, account.workstation
        for server_id in sorted(foothold.servers):
            host = self.world.hosts[server_id]
            return host.ip, host.hostname
        return self.world.attacker_ip, "internet"

    def red_move(self, attack_id: str, target_id: str):
        source_ip, source_host = self._source()
        result = self.campaign.move(attack_id, target_id)
        users = [self.world.accounts[e].username for e in sorted(self.campaign.foothold.employees)]
        self.telemetry.attack(result, source_ip, source_host, users)
        return result

    def end_day(self):
        night = self.campaign.end_day()
        if night is not None:
            self.telemetry.noise(self.campaign.day)
        return night

    def visible_events(self) -> list[dict]:
        allowed = set(self.world.visible_indexes(self.campaign.defense_ids))
        return [e for e in self.telemetry.events if e["index"] in allowed]

    def search(self, query: str) -> dict:
        result = spl.run(self.visible_events(), query)
        result["indexes"] = self.world.visible_indexes(self.campaign.defense_ids)
        return result

    def _spend(self) -> None:
        if self.campaign.blue_moves_left <= 0:
            raise PlanError("The Blue Team has no time left today")
        self.campaign.blue_moves_today += 1

    def block_ip(self, ip: str) -> str:
        self._spend()
        ip = ip.strip()
        self.blocked_ips.add(ip)
        if ip == self.world.attacker_ip:
            self.campaign.attacker_blocked = True
            return f"Blocked {ip} at the firewall. Every attempt from it now fails."
        if ip in self.world.noise_ips:
            self.campaign.disruption += 1
            return f"Blocked {ip} at the firewall. That was a customer, and now they cannot reach the shop."
        return f"Blocked {ip} at the firewall. Nothing seems to change."

    def account_id(self, username: str) -> str | None:
        return next((a.id for a in self.world.accounts.values() if a.username == username.strip().lower()), None)

    def host_id(self, name: str) -> str | None:
        name = name.strip().lower()
        return next((h.id for h in self.world.hosts.values()
                     if name in (h.hostname.lower(), h.ip, (h.public_ip or "").lower())), None)

    def disable_account(self, username: str) -> str:
        employee_id = self.account_id(username)
        if employee_id is None:
            raise PlanError(f"There is no account called '{username}'.")
        return self.campaign.blue("reset", employee_id).text

    def isolate(self, name: str) -> str:
        server_id = self.host_id(name)
        if server_id is None:
            example = next(iter(self.world.hosts.values())).hostname
            raise PlanError(f"There is no machine called '{name}'. Use a hostname like {example}.")
        return self.campaign.blue("isolate", server_id).text
