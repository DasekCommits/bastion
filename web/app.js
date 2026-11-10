(() => {
  "use strict";

  const PROFILE_KEY = "bastion-profile";
  const SETTINGS_KEY = "bastion-settings";
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const STEP_MS = reduced ? 120 : 650;

  const app = document.getElementById("app");
  const gauges = document.getElementById("gauges");
  const accountBox = document.getElementById("account");
  const GITHUB_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>';

  const S = {
    session: null,
    settings: { level: null, side: null, company: null },
    start: null,
    turn: null,
    attack: null,
    busy: false,
    map: null,
    user: null,
    accounts: false,
    notice: "",
  };

  const LEVELS = [
    { id: "easy", name: "Easy", text: "Attacks work more often. You see the odds, the heat and advice at the end." },
    { id: "medium", name: "Medium", text: "A fairer fight. Moves are explained, but no numbers." },
    { id: "hard", name: "Hard", text: "The defenders have the edge. No help at all, only the result." },
  ];
  const SIDES = [
    { id: "blue", name: "Blue", text: "Defend the company. The computer attacks.", cls: "blue-side" },
    { id: "red", name: "Red", text: "Break in. The computer picked defenses you cannot see.", cls: "red-side" },
    { id: "random", name: "Random", text: "A coin decides your side. Double points if you win." },
    { id: "practice", name: "Practice", text: "Play both sides. No points, no unlocks." },
  ];

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (value) => `${Math.round(value * 100)}%`;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const store = {
    get(key, fallback) { try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} },
  };

  function api(method, ...args) {
    const out = S.session[method](...args);
    return typeof out === "string" ? JSON.parse(out) : out;
  }

  async function fetchMe() {
    try {
      const response = await fetch("api/me.php", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) return null;
      return await response.json();
    } catch {
      return null;
    }
  }

  async function saveProgress(profile) {
    if (!S.user) return;
    try {
      await fetch("api/progress.php", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Bastion": "1" },
        body: JSON.stringify(profile),
      });
    } catch {}
  }

  function renderAccount() {
    if (!S.accounts) { accountBox.innerHTML = ""; return; }
    if (S.user) {
      accountBox.innerHTML = `${S.user.avatar ? `<img src="${esc(S.user.avatar)}" alt="">` : ""}<span class="who">${esc(S.user.login)}</span><button class="linkish" id="signout">Sign out</button>`;
      document.getElementById("signout").addEventListener("click", signOut);
    } else {
      accountBox.innerHTML = `<a class="signin" href="api/login.php">${GITHUB_ICON}Sign in with GitHub</a>`;
    }
  }

  async function signOut() {
    try {
      await fetch("api/logout.php", { method: "POST", credentials: "same-origin", headers: { "X-Bastion": "1" } });
    } catch {}
    S.user = null;
    S.notice = "Signed out. Your progress stays saved in your account.";
    renderAccount();
    if (!S.start || app.querySelector("#go")) renderMenu();
  }

  function readSigninResult() {
    const params = new URLSearchParams(location.search);
    const result = params.get("signin");
    if (!result) return;
    history.replaceState(null, "", location.pathname);
    if (result === "failed") S.notice = "Signing in with GitHub did not work. Try again in a minute.";
    if (result === "cancelled") S.notice = "Sign-in was cancelled. You can still play, progress stays in this browser.";
  }

  function show(html) {
    app.innerHTML = html;
    app.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }

  async function boot() {
    const status = document.getElementById("boot-status");
    const fill = document.getElementById("boot-fill");
    const progress = (text, amount) => { status.textContent = text; fill.style.width = amount; };
    try {
      progress("Loading Python in your browser…", "15%");
      const pyodide = await loadPyodide();
      progress("Loading the game…", "70%");
      const response = await fetch("bastion.zip?v=__VERSION__");
      if (!response.ok) throw new Error(`could not download the game (${response.status})`);
      pyodide.unpackArchive(await response.arrayBuffer(), "zip", { extractDir: "/home/pyodide/game" });
      pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide/game')");
      const web = pyodide.pyimport("bastion.web");
      readSigninResult();
      const me = await fetchMe();
      S.accounts = me !== null && !me.error;
      let profile = store.get(PROFILE_KEY, null);
      if (me && me.signed_in) {
        S.user = me.user;
        const server = me.profile;
        if (server.games === 0 && profile && profile.games > 0) {
          await saveProgress(profile);
          S.notice = `Signed in as ${me.user.login}. The progress from this browser is now saved to your account.`;
        } else {
          profile = server;
          store.set(PROFILE_KEY, profile);
        }
      }
      renderAccount();
      S.session = web.Session(profile ? JSON.stringify(profile) : "");
      progress("Ready.", "100%");
      S.settings = Object.assign(S.settings, store.get(SETTINGS_KEY, {}));
      renderMenu();
    } catch (error) {
      progress(`The game could not start: ${error.message}. Reload the page to try again.`, "100%");
    }
  }

  function setGauges(turn) {
    if (!turn) { gauges.hidden = true; gauges.innerHTML = ""; return; }
    const pips = (on, total, cls = "") => `<span class="pips ${cls}">${Array.from({ length: total }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</span>`;
    let html = `<span class="gauge">Day <b>${turn.day}/${turn.max_days}</b> ${pips(turn.day, turn.max_days)}</span>`;
    if (turn.moves_left !== undefined) html += `<span class="gauge">Moves ${pips(turn.moves_left, turn.moves_per_day, "moves")}</span>`;
    if (turn.heat !== null && turn.heat !== undefined) html += `<span class="gauge">Heat <span class="heat"><span style="width:${pct(turn.heat)}"></span></span> <b>${pct(turn.heat)}</b></span>`;
    gauges.innerHTML = html;
    gauges.hidden = false;
  }

  function renderMenu() {
    setGauges(null);
    const menu = api("menu");
    const p = menu.profile;
    const NAMES = { small: "Olive Byte", medium: "Harbor Clinic", large: "Meridian Bank" };
    const wins = Object.entries(p.wins).map(([k, n]) => { const [t, l] = k.split("/"); return `${NAMES[t] || t} ${l ? l[0].toUpperCase() + l.slice(1) : ""} ${n}`; }).join(", ") || "none yet";
    if (S.settings.level && menu.levels[S.settings.level]) S.settings.level = null;
    const level = S.settings.level || "easy";
    const card = (group, item, extra = "") => {
      const lockedLevel = group === "level" && menu.levels[item.id];
      if (lockedLevel) {
        return `<button class="choice" disabled><strong>${esc(item.name)}</strong><small>Locked: ${esc(lockedLevel)}</small></button>`;
      }
      const on = S.settings[group] === item.id;
      return `<button class="choice ${item.cls || ""}" data-group="${group}" data-id="${item.id}" aria-pressed="${on}" ${extra}${on ? ' style="border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)"' : ""}>
        <strong>${esc(item.name)}</strong><small>${esc(item.text)}</small></button>`;
    };
    const companies = menu.companies.map((c) => {
      c.locked = menu.locks[level][c.id];
      const on = S.settings.company === c.id;
      return `<button class="choice" data-group="company" data-id="${c.id}" aria-pressed="${on}" ${c.locked ? "disabled" : ""}${on ? ' style="border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)"' : ""}>
        <span class="tag">${esc(c.tier)} · ${c.people} people</span>
        <strong>${esc(c.name)}</strong>
        <small>${esc(c.locked ? `Locked: ${c.locked}` : c.description)}</small></button>`;
    }).join("");
    if (S.settings.company && menu.locks[level][S.settings.company]) S.settings.company = null;
    const ready = S.settings.level && S.settings.side && S.settings.company;
    const notice = S.notice ? `<p class="notice" role="status">${esc(S.notice)}</p>` : "";
    S.notice = "";
    const saveNote = S.user ? "Progress is saved to your GitHub account." : S.accounts ? "Progress is saved in this browser. Sign in with GitHub to keep it on every device." : "";
    show(`<section class="step">
      ${notice}
      <div class="step-head">
        <div><p class="eyebrow">New game</p><h1>Pick your fight.</h1>${saveNote ? `<p class="muted" style="margin:8px 0 0;font-size:14px">${esc(saveNote)}</p>` : ""}</div>
        <p class="profile-line">${p.points} points · ${p.games} games · wins: ${esc(wins)}${menu.goal ? `<br>${esc(menu.goal)}` : ""}</p>
      </div>
      <div class="settings">
        <div class="setting"><h3>Difficulty</h3><div class="choices">${LEVELS.map((l) => card("level", l)).join("")}
          <button class="choice classified" disabled><span class="tag">classified</span><strong>████████</strong>
          <small>${menu.realism ? "Clearance granted. Opening soon." : "Unlock conditions: unknown. Some files are not on any inventory."}</small></button></div></div>
        <div class="setting"><h3>Side</h3><div class="choices">${SIDES.map((s) => card("side", s)).join("")}</div></div>
        <div class="setting"><h3>Company</h3><div class="choices">${companies}
          <button class="choice classified" disabled><span class="tag">classified · ??? people</span><strong>█████████ ███</strong>
          <small>${menu.cleared ? "Clearance granted. The doors open soon." : "Unlock conditions: unknown. Some scripts talk."}</small></button></div></div>
      </div>
      <div class="btn-row"><button class="btn" id="go" ${ready ? "" : "disabled"}>Start the game</button></div>
    </section>`);
    app.querySelectorAll(".choice[data-group]").forEach((el) => el.addEventListener("click", () => {
      S.settings[el.dataset.group] = el.dataset.id;
      store.set(SETTINGS_KEY, S.settings);
      renderMenu();
    }));
    document.getElementById("go").addEventListener("click", startGame);
  }

  function startGame() {
    const { company, level, side } = S.settings;
    S.start = api("start", company, level, side, Math.floor(Math.random() * 1e9));
    S.turn = null;
    S.attack = null;
    S.map = { owned: new Set(), admin: new Set(), scanned: new Set(), taken: new Set(), targets: new Set(), ping: null };
    if (S.start.side === "red") renderArsenal();
    else renderDefenses();
  }

  function word(value) {
    return value ? `<span class="word-${value}">${esc(value)}</span>` : "";
  }

  function briefHtml(company) {
    const servers = company.servers.map((s) => `<tr><td>${esc(s.name)} <span class="muted">${esc(s.id)}</span></td>
      <td>${s.exposed ? '<span class="word-yes">internet</span>' : '<span class="muted">inside</span>'}</td><td class="muted">${esc(s.software.join(", "))}</td></tr>`).join("");
    const hasTraits = company.people.some((p) => p.phishing);
    const hasLoyalty = company.people.some((p) => p.loyalty);
    const people = company.people.map((p) => `<tr><td>${esc(p.name)} <span class="muted">${esc(p.role)}</span></td>
      <td>${p.admin === "yes" ? '<span class="word-yes">yes</span>' : `<span class="muted">${esc(p.admin)}</span>`}</td>
      <td class="muted">${esc(p.access.join(", "))}</td>
      ${hasTraits ? `<td>${word(p.phishing)}</td><td>${word(p.passwords)}</td>` : ""}
      ${hasLoyalty ? `<td>${word(p.loyalty)}</td>` : ""}</tr>`).join("");
    const data = company.data.length ? `<div class="panel"><h3>Valuable data</h3><table class="sheet"><tr><th>What</th><th>Where</th><th class="num">Value</th></tr>
      ${company.data.map((d) => `<tr><td>${esc(d.name)}</td><td class="muted">${esc(d.where)}</td><td class="num">${d.value}</td></tr>`).join("")}</table></div>` : "";
    return `<div class="brief">
      <p class="lede" style="margin:0">${esc(company.description)}</p>
      <div class="brief-grid">
        <div class="panel"><h3>Servers</h3><table class="sheet"><tr><th>Server</th><th>Reach</th><th>Software</th></tr>${servers}</table></div>
        ${data}
      </div>
      <div class="panel"><h3>People</h3><table class="sheet"><tr><th>Person</th><th>Admin</th><th>Can log in to</th>
        ${hasTraits ? "<th>Spots phishing</th><th>Passwords</th>" : ""}${hasLoyalty ? "<th>Loyalty</th>" : ""}</tr>${people}</table>
        ${company.hidden_admins ? '<p class="note">Someone may have admin rights by mistake, or nobody. You will find out once you are in.</p>' : ""}
      </div>
    </div>`;
  }

  function renderPicker({ eyebrow, title, intro, options, budget, range, doneLabel, needOne, onDone, color }) {
    const chosen = new Set();
    const draw = () => {
      const spent = options.filter((o) => chosen.has(o.id)).reduce((sum, o) => sum + o.cost, 0);
      const list = options.map((o) => {
        const on = chosen.has(o.id);
        const meta = [o.category, o.mitre && `${o.mitre} ${o.tactic}`].filter(Boolean).join(" · ");
        return `<button class="option ${on ? "on" : ""}" data-id="${o.id}" aria-pressed="${on}">
          <span class="box" aria-hidden="true"></span>
          <span><span class="name">${esc(o.name)}</span>${meta ? ` <span class="muted" style="font:12px var(--mono)">${esc(meta)}</span>` : ""}
          ${o.description ? `<span class="desc">${esc(o.description)}</span>` : ""}</span>
          <span class="cost">${o.cost}</span></button>`;
      }).join("");
      show(`<section class="step">
        <div><p class="eyebrow">${esc(eyebrow)}</p><h2 class="${color}">${esc(title)}</h2><p class="muted" style="margin:6px 0 0">${esc(intro)}</p></div>
        ${briefHtml(S.start.company)}
        <div class="budget">
          <span class="budget-text">Spent ${spent} / ${budget}</span>
          <span class="budget-bar"><span style="width:${Math.min(100, (spent / budget) * 100)}%"></span></span>
          <span class="muted" style="font:12px var(--mono)">${budget - spent} left${range ? ` · budget this game, can be ${range[0]} to ${range[1]}` : ""}</span>
          <button class="btn" id="done">${esc(doneLabel)}</button>
        </div>
        <p class="warn" id="warn" role="alert"></p>
        <div class="options">${list}</div>
      </section>`);
      app.querySelectorAll(".option").forEach((el) => el.addEventListener("click", () => {
        const option = options.find((o) => o.id === el.dataset.id);
        const scroll = window.scrollY;
        if (chosen.has(option.id)) chosen.delete(option.id);
        else if (spent + option.cost > budget) {
          document.getElementById("warn").textContent = `Not enough budget: ${option.name} costs ${option.cost}, you have ${budget - spent} left.`;
          return;
        } else chosen.add(option.id);
        draw();
        window.scrollTo({ top: scroll });
        app.querySelector(`.option[data-id="${option.id}"]`)?.focus({ preventScroll: true });
      }));
      document.getElementById("done").addEventListener("click", () => {
        if (needOne && !chosen.size) { document.getElementById("warn").textContent = "Pick at least one first."; return; }
        onDone([...chosen]);
      });
    };
    draw();
  }

  function renderDefenses() {
    const c = S.start.company;
    renderPicker({
      eyebrow: `${c.name} · ${S.settings.level}`,
      title: S.start.random_side ? "The coin says: you play Blue. Double points if you win." : "Blue team: protect the company",
      intro: "Pick the defenses you can afford. Each one explains what it stops.",
      options: api("defense_options"),
      budget: c.budget, range: c.budget_range, color: "blue",
      doneLabel: S.start.side === "practice" ? "Done, switch to Red" : "Done, start the game",
      onDone: (ids) => {
        const res = api("set_defenses", JSON.stringify(ids));
        if (!res.ok) { document.getElementById("warn").textContent = res.error; return; }
        if (S.start.side === "practice") renderArsenal();
        else startDefending(api("begin"));
      },
    });
  }

  function renderArsenal() {
    const c = S.start.company;
    const intro = S.start.side === "red"
      ? "The defenders already picked defenses you cannot see. A port scan shows what is visible from outside. You buy each attack once and can reuse it on any day."
      : "Now switch sides. You buy each attack once and can reuse it on any day.";
    renderPicker({
      eyebrow: `${c.name} · ${S.settings.level}`,
      title: S.start.random_side ? "The coin says: you play Red. Double points if you win." : "Red team: break in",
      intro,
      options: api("attack_options"),
      budget: c.red_budget, range: c.red_budget_range, color: "red", needOne: true,
      doneLabel: "Done, start the attack",
      onDone: (ids) => {
        const res = api("set_arsenal", JSON.stringify(ids));
        if (!res.ok) { document.getElementById("warn").textContent = res.error; return; }
        S.turn = api("begin");
        renderPlay();
      },
    });
  }

  function mapSvg() {
    const c = S.start.company;
    const W = 760;
    const exposed = c.servers.filter((s) => s.exposed);
    const inside = c.servers.filter((s) => !s.exposed);
    const perRow = 10;
    const peopleRows = [];
    for (let i = 0; i < c.people.length; i += perRow) peopleRows.push(c.people.slice(i, i + perRow));
    const pos = {};
    const spread = (items, y) => items.forEach((item, i) => { pos[item.id] = { x: 70 + ((W - 100) * (i + 0.5)) / items.length, y }; });
    spread(exposed, 60);
    spread(inside, 160);
    peopleRows.forEach((row, r) => spread(row, 275 + r * 82));
    const H = 275 + peopleRows.length * 82;
    const m = S.map;
    const edges = c.people.flatMap((p) => p.access.filter((id) => pos[id]).map((id) => {
      const a = pos[p.id], b = pos[id];
      const hot = m.owned.has(p.id);
      return `<line class="edge ${hot ? "hot" : ""}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`;
    })).join("");
    const state = (id) => [m.admin.has(id) ? "admin" : m.owned.has(id) ? "owned" : "", m.targets.has(id) ? "target" : "", m.isolated && m.isolated.has(id) ? "isolated" : ""].join(" ");
    const extras = (id, p) => `${m.scanned.has(id) ? `<circle class="scan-ring" cx="${p.x}" cy="${p.y}" r="19"/>` : ""}
      ${m.taken.has(id) ? `<text class="taken" x="${p.x + 15}" y="${p.y - 12}">TAKEN</text>` : ""}
      ${m.ping === id ? `<circle class="ping" cx="${p.x}" cy="${p.y}" r="14"/>` : ""}`;
    const servers = c.servers.map((s) => {
      const p = pos[s.id];
      return `<g data-id="${s.id}" class="${m.targets.has(s.id) ? "clickable" : ""}">
        <rect class="node ${state(s.id)}" x="${p.x - 12}" y="${p.y - 12}" width="24" height="24" rx="3"/>${extras(s.id, p)}
        <text class="label" x="${p.x}" y="${p.y + 28}" text-anchor="middle">${esc(s.name)}</text></g>`;
    }).join("");
    const people = c.people.map((person) => {
      const p = pos[person.id];
      return `<g data-id="${person.id}" class="${m.targets.has(person.id) ? "clickable" : ""}">
        <circle class="node ${state(person.id)}" cx="${p.x}" cy="${p.y}" r="11"/>${extras(person.id, p)}
        <text class="label" x="${p.x}" y="${p.y + 26}" text-anchor="middle">${esc(person.name)}</text>
        <text class="sub" x="${p.x}" y="${p.y + 39}" text-anchor="middle">${esc(person.role.split(" ").slice(-1)[0])}</text></g>`;
    }).join("");
    return `<svg class="map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Network map of ${esc(c.name)}">
      <text class="zone" x="6" y="64">Internet</text><text class="zone" x="6" y="164">Inside</text><text class="zone" x="6" y="279">People</text>
      ${edges}${servers}${people}</svg>`;
  }

  function mapInner() {
    return `${mapSvg()}
      <div class="legend"><span><i></i>untouched</span><span><i class="owned"></i>attacker inside</span><span><i class="admin"></i>attacker is admin</span><span><i class="scan"></i>scanned</span></div>`;
  }

  function mapPanel() {
    return `<div class="panel map-panel">${mapInner()}</div>`;
  }

  function syncMapFromTurn(turn) {
    if (!turn.foothold) return;
    const f = turn.foothold;
    S.map.owned = new Set([...f.accounts, ...f.machines]);
    S.map.admin = new Set(f.admin);
    S.map.scanned = new Set(f.scanned);
  }

  function applyEventToMap(event) {
    if (event.type !== "move" || !event.possible) return;
    const m = S.map;
    if (event.tactic === "reconnaissance" && event.succeeded) m.scanned.add(event.target_id);
    const cutOff = event.detected && !event.kicked && event.note.includes("cut that access");
    if (event.succeeded && !cutOff) {
      if (["initial-access", "credential-access", "lateral-movement"].includes(event.tactic)) m.owned.add(event.target_id);
      if (event.tactic === "privilege-escalation") m.admin.add(event.target_id);
      if (["exfiltration", "impact"].includes(event.tactic) && event.points) m.taken.add(event.target_id);
    }
  }

  function logEntry(event) {
    if (event.type === "night") {
      const odds = event.hunt !== undefined ? ` · ${pct(event.hunt)} chance to be found · heat ${pct(event.heat_before)} → ${pct(event.heat_after)}` : "";
      const found = event.found ? `<br><span class="stamp found">Found</span> The Blue Team found the attacker in the logs.` : "";
      return `<div class="entry night">☾ Night ${event.day}: ${event.hunt || event.found ? "their 24/7 SOC reviews the logs" : "the office is empty and nobody watches the logs"}${event.hunt ? odds : ""}${found}</div>`;
    }
    if (event.type === "alert") {
      return `<div class="entry"><span class="stamp ${event.kicked ? "blue" : "spotted"}">${event.kicked ? "Caught" : "Alert"}</span>
        <span class="what">${esc(event.attack)} → ${esc(event.target)}</span><br>
        <span class="detail">${event.kicked ? "You kicked the attacker out." : "Your tools blocked this attempt."}</span></div>`;
    }
    let stamp;
    if (!event.possible) stamp = '<span class="stamp wasted">Wasted</span>';
    else if (event.empty) stamp = '<span class="stamp empty">Nothing here</span>';
    else stamp = event.succeeded ? '<span class="stamp success land">Success</span>' : '<span class="stamp blocked land">Failed</span>';
    const chance = event.chance !== undefined && event.possible ? ` <span class="detail">chance was ${pct(event.chance)}</span>` : "";
    const blockers = event.blockers && event.blockers.length ? `<br><span class="detail">Stopped by: ${esc(event.blockers.join(", "))}</span>` : "";
    const nothing = event.blockers && !event.blockers.length && event.possible && !event.succeeded ? `<br><span class="detail">Nothing blocked it. It just did not work this time.</span>` : "";
    let detection = "";
    if (event.possible && event.chance !== undefined) {
      detection = event.detected
        ? `<br><span class="stamp spotted">Logged</span><span class="detail">This left traces in their logs. Whether anyone reads them is another matter.</span>`
        : `<br><span class="detail">No traces in their logs.</span>`;
    }
    return `<div class="entry"><span class="what">${esc(event.attack)} → ${esc(event.target)}</span><br>${stamp}${chance}
      ${event.note && event.possible ? `<br><span class="detail">${esc(event.note)}</span>` : ""}
      ${!event.possible ? `<span class="detail">${esc(event.note)}</span>` : ""}${blockers}${nothing}${detection}</div>`;
  }

  function renderPlay(log = "") {
    const t = S.turn;
    syncMapFromTurn(t);
    setGauges(t);
    S.map.targets = new Set();
    let side;
    if (S.attack) {
      const targets = api("targets", S.attack);
      targets.filter((x) => !x.disabled).forEach((x) => S.map.targets.add(x.id));
      const attackName = t.actions.find((a) => a.id === S.attack).name;
      side = `<div class="panel"><h3>${esc(attackName)}: pick a target</h3><div class="options">
        ${targets.map((x) => {
          const odds = x.success !== undefined ? `success ${pct(x.success)}<br>spotted ${pct(x.spotted)}<br>heat → ${pct(x.heat_after)}` : "";
          return `<button class="option" data-target="${x.id}" ${x.disabled ? "disabled" : ""}>
            <span></span><span><span class="name">${esc(x.label)}</span>
            ${x.disabled ? `<span class="why">${esc(x.disabled)}</span>` : x.hint ? `<span class="desc">${esc(x.hint)}</span>` : ""}</span>
            <span class="odds">${odds}</span></button>`;
        }).join("")}</div>
        <div class="btn-row" style="margin-top:12px"><button class="btn ghost" id="back">Back</button></div></div>`;
    } else {
      side = `<div class="panel"><h3>Your move</h3>
        ${t.foothold ? footholdHtml(t.foothold) : ""}
        ${t.intel.length ? `<p class="detail" style="font:12px var(--mono);margin:0 0 10px"><b>Intel:</b> ${esc(t.intel.join(", "))}</p>` : ""}
        <div class="options">${t.actions.map((a) => `<button class="option" data-attack="${a.id}" ${a.disabled ? "disabled" : ""}>
          <span></span><span><span class="name">${esc(a.name)}</span>
          ${a.disabled ? `<span class="why">${esc(a.disabled)}</span>` : a.hint ? `<span class="desc">${esc(a.hint)}</span>` : ""}</span>
          <span class="odds">${esc(a.tag || "")}</span></button>`).join("")}</div>
        <div class="btn-row" style="margin-top:12px"><button class="btn ghost" id="end-day">End the day</button><button class="btn ghost" id="give-up">Give up</button></div></div>`;
    }
    const current = document.getElementById("log");
    const logHtml = log || (current ? current.innerHTML : "");
    show(`<section class="layout">
      <div>${mapPanel()}</div>
      <div class="step">${side}
        <div class="panel"><h3>Log</h3><div class="log" id="log" aria-live="polite">${logHtml || '<p class="muted" style="margin:0">Nothing has happened yet. Find a way in.</p>'}</div></div>
      </div></section>`);
    app.querySelectorAll("[data-attack]").forEach((el) => el.addEventListener("click", () => { S.attack = el.dataset.attack; renderPlay(); }));
    app.querySelectorAll("[data-target]").forEach((el) => el.addEventListener("click", () => doMove(el.dataset.target)));
    app.querySelectorAll(".map g.clickable").forEach((el) => el.addEventListener("click", () => doMove(el.dataset.id)));
    document.getElementById("back")?.addEventListener("click", () => { S.attack = null; renderPlay(); });
    document.getElementById("end-day")?.addEventListener("click", endDay);
    document.getElementById("give-up")?.addEventListener("click", () => renderFinal(api("give_up")));
  }

  function footholdHtml(f) {
    const rows = [["Accounts", f.accounts], ["On machines", f.machines], ["Admin on", f.admin], ["Scanned", f.scanned]].filter(([, v]) => v.length);
    if (!rows.length) return '<p class="muted" style="margin:0 0 10px;font-size:13px">No foothold yet. Find a way in first.</p>';
    return `<p style="margin:0 0 10px;font:12px/1.6 var(--mono)">${rows.map(([k, v]) => `<span class="muted">${k}:</span> <span class="red">${esc(v.join(", "))}</span>`).join("<br>")}</p>`;
  }

  function prependLog(html) {
    const log = document.getElementById("log");
    const placeholder = log.querySelector("p.muted");
    if (placeholder) placeholder.remove();
    log.insertAdjacentHTML("afterbegin", html);
  }

  async function doMove(targetId) {
    if (S.busy || !S.attack) return;
    S.busy = true;
    const event = api("move", S.attack, targetId);
    S.attack = null;
    S.map.targets = new Set();
    app.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    for (const line of event.suspense || []) {
      prependLog(`<div class="entry"><span class="suspense">${esc(line)}…</span></div>`);
      await sleep(STEP_MS);
      document.querySelector("#log .entry")?.remove();
    }
    applyEventToMap(event);
    const entry = logEntry(event) + (event.blue || []).map(blueNotice).join("") + (event.kicked_out ? kickedNotice() : "");
    S.turn = api("turn");
    S.busy = false;
    if (S.turn.finished) { prependLog(entry); await sleep(STEP_MS); return renderFinal(api("finish")); }
    renderPlay();
    prependLog(entry);
  }

  function blueNotice(text) {
    return `<div class="entry"><span class="stamp blue">Blue Team</span><span class="detail">${esc(text)}</span></div>`;
  }

  function kickedNotice() {
    return `<div class="entry"><span class="stamp detected">Kicked out</span><span class="detail">The Blue Team closed every way you had in.</span></div>`;
  }

  function endDay() {
    const res = api("end_day");
    S.turn = res.turn;
    S.attack = null;
    const notices = (res.blue || []).map(blueNotice).join("") + (res.kicked_out ? kickedNotice() : "");
    if (S.turn.finished) return renderFinal(api("finish"));
    renderPlay();
    const html = notices + (res.night ? logEntry(res.night) : "");
    if (html) prependLog(html);
  }

  const BLUE_ACTIONS = [
    { id: "logs", name: "See the logs", text: "Read what your tools recorded. Tools that nobody reads catch nobody." },
    { id: "investigate", name: "Investigate an alert", text: "Find out if an alert is a real attack or a false alarm." },
    { id: "reset", name: "Change a password", text: "If the attacker had this account, they lose it. If not, the employee loses some time." },
    { id: "isolate", name: "Isolate a machine", text: "Cut a machine off the network until the end of tomorrow. Stops the attacker there, but work stops too." },
    { id: "hunt", name: "Threat hunt on a machine", text: "Search a machine for an attacker that no alert has shown yet." },
    { id: "block", name: "Block a sender or address", text: "Stop an attempt from outside from ever trying again." },
  ];

  function blueGauges(st) {
    const pips = (on, total, cls = "") => `<span class="pips ${cls}">${Array.from({ length: total }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</span>`;
    gauges.innerHTML = `<span class="gauge">Day <b>${st.day}/${st.max_days}</b> ${pips(st.day, st.max_days)}</span>
      <span class="gauge">Analyst time ${pips(st.time_left, st.time_total, "time")}</span>
      <span class="gauge">New logs <b>${st.new_logs}</b></span>`;
    gauges.hidden = false;
  }

  function blueFeed(event) {
    if (event.type === "tick") return `<div class="entry night">Time passes. Somewhere, someone is trying something.</div>`;
    if (event.type === "night") {
      if (event.found) return `<div class="entry"><span class="stamp blue">Found</span> Your SOC found the attacker overnight and threw them out.</div>`;
      return `<div class="entry night">☾ Night ${event.day}: the office is empty and nobody watches the logs.</div>`;
    }
    if (event.type === "move") return `<div class="entry"><span class="detail">What the attacker just did (only Easy shows this):</span><br>${logEntry(event).replace(/^<div class="entry">|<\/div>$/g, "")}</div>`;
    return "";
  }

  function blueActionHtml(action) {
    const name = (BLUE_ACTIONS.find((a) => a.id === action.kind) || { name: action.kind }).name;
    return `<div class="entry"><span class="stamp ${action.useful ? "blue" : "blocked"}">${esc(name)}</span>${action.target ? `<span class="what">${esc(action.target)}</span>` : ""}<br><span class="detail">${esc(action.text)}</span></div>`;
  }

  function logsTable(st) {
    if (!st.logs.length) return '<p class="muted" style="margin:0">You have not read any logs yet. Your tools are recording, but nobody is looking.</p>';
    const hint = st.logs.some((l) => l.hint);
    return `<table class="sheet"><tr><th>#</th><th>Day</th><th>Source</th><th>What the tool saw</th>${hint ? "<th>Signal</th>" : ""}<th>Verdict</th></tr>
      ${st.logs.map((l) => `<tr${l.seen_now ? ' class="fresh"' : ""}><td class="num">${l.id}</td><td>${l.day}</td><td class="muted">${esc(l.source)}</td><td>${esc(l.text)}</td>
        ${hint ? `<td class="muted">${esc(l.hint || "")}</td>` : ""}
        <td>${l.verdict ? `<span class="${l.verdict.startsWith("False") ? "muted" : "red"}">${esc(l.verdict)}</span>` : '<span class="muted">not checked</span>'}</td></tr>`).join("")}</table>`;
  }

  function startDefending(state) {
    S.blue = { state, pending: null, feed: "" };
    renderBlue();
  }

  function renderBlue() {
    const st = S.blue.state;
    const c = S.start.company;
    blueGauges(st);
    S.map.owned = new Set(st.confirmed);
    S.map.isolated = new Set(st.isolated);
    S.map.targets = new Set();
    const pending = S.blue.pending;
    let side;
    if (st.finished) {
      side = `<div class="panel"><h3>${st.kicked_out ? "You kicked the attacker out." : "The attack is over."}</h3>
        <div class="btn-row"><button class="btn" id="result">See the result</button></div></div>`;
    } else if (pending) {
      let options = [];
      if (pending === "investigate" || pending === "block") {
        options = st.logs.filter((l) => pending === "block" || !l.investigated).map((l) => ({ id: String(l.id), label: `#${l.id} ${l.text}`, sub: `${l.source}, day ${l.day}${l.hint ? ` · ${l.hint}` : ""}` }));
      } else if (pending === "reset") {
        options = c.people.map((p) => ({ id: p.id, label: p.name, sub: p.role }));
      } else {
        options = c.servers.map((s) => ({ id: s.id, label: s.name, sub: s.id, disabled: pending === "isolate" && st.isolated.includes(s.id) ? "already isolated" : "" }));
      }
      if (pending !== "investigate" && pending !== "block") options.filter((o) => !o.disabled).forEach((o) => S.map.targets.add(o.id));
      const action = BLUE_ACTIONS.find((a) => a.id === pending);
      side = `<div class="panel"><h3>${esc(action.name)}: pick one</h3><div class="options">
        ${options.map((o) => `<button class="option" data-blue-target="${esc(o.id)}" ${o.disabled ? "disabled" : ""}><span></span><span><span class="name">${esc(o.label)}</span><span class="desc">${esc(o.disabled || o.sub)}</span></span><span></span></button>`).join("") || '<p class="muted">Nothing to pick yet.</p>'}
        </div><div class="btn-row" style="margin-top:12px"><button class="btn ghost" id="back">Back</button></div></div>`;
    } else {
      const open = st.logs.filter((l) => !l.investigated).length;
      const explain = S.settings.level !== "hard";
      const disabled = { investigate: open ? "" : "read the logs first", block: st.logs.length ? "" : "read the logs first" };
      const tag = { logs: st.new_logs ? `${st.new_logs} new` : "", investigate: open ? `${open} open` : "" };
      const note = st.phase === "day_end" ? "The attacker has stopped for today. Use the rest of your time, or let the night come." : "Each time the attacker moves, you get one move.";
      side = `<div class="panel"><h3>Your move as the analyst</h3><p class="muted" style="margin:0 0 10px;font-size:13px">${note}</p><div class="options">
        ${BLUE_ACTIONS.map((a) => `<button class="option" data-blue="${a.id}" ${disabled[a.id] ? "disabled" : ""}><span></span><span><span class="name">${esc(a.name)}</span>
          ${disabled[a.id] ? `<span class="why">${esc(disabled[a.id])}</span>` : explain ? `<span class="desc">${esc(a.text)}</span>` : ""}</span><span class="odds">${esc(tag[a.id] || "")}</span></button>`).join("")}
        </div><div class="btn-row" style="margin-top:12px"><button class="btn ghost" id="wait">${st.phase === "day_end" ? "End the day" : "Let time pass"}</button></div></div>`;
    }
    show(`<section class="layout">
      <div class="step">${mapPanel()}<div class="panel"><h3>Logs you have read</h3>${logsTable(st)}</div></div>
      <div class="step">${side}
        <div class="panel"><h3>What happened</h3><div class="log" id="log" aria-live="polite">${S.blue.feed || '<p class="muted" style="margin:0">Your tools are recording. The attacker is out there.</p>'}</div></div>
      </div></section>`);
    app.querySelectorAll("[data-blue]").forEach((el) => el.addEventListener("click", () => {
      if (el.dataset.blue === "logs") return blueAct("logs", null);
      S.blue.pending = el.dataset.blue;
      renderBlue();
    }));
    app.querySelectorAll("[data-blue-target]").forEach((el) => el.addEventListener("click", () => blueAct(S.blue.pending, el.dataset.blueTarget)));
    app.querySelectorAll(".map g.clickable").forEach((el) => el.addEventListener("click", () => blueAct(S.blue.pending, el.dataset.id)));
    document.getElementById("back")?.addEventListener("click", () => { S.blue.pending = null; renderBlue(); });
    document.getElementById("wait")?.addEventListener("click", blueWait);
    document.getElementById("result")?.addEventListener("click", () => renderFinal(api("finish")));
  }

  function addFeed(html) {
    S.blue.feed = html + S.blue.feed;
  }

  function takeState(state) {
    for (const event of state.events) addFeed(blueFeed(event));
    S.blue.state = state;
  }

  function blueAct(kind, target) {
    if (!kind || S.busy) return;
    S.busy = true;
    const res = api("blue_act", kind, target);
    S.busy = false;
    S.blue.pending = null;
    if (res.error) { addFeed(`<div class="entry"><span class="why">${esc(res.error)}</span></div>`); return renderBlue(); }
    addFeed(blueActionHtml(res.action));
    const fresh = new Set(res.fresh.map((f) => f.id));
    res.state.logs.forEach((l) => { if (fresh.has(l.id)) l.seen_now = true; });
    takeState(res.state);
    renderBlue();
  }

  function blueWait() {
    S.blue.pending = null;
    takeState(api("blue_wait"));
    renderBlue();
  }

  function renderFinal(final) {
    setGauges(null);
    const profile = JSON.parse(final.profile_json);
    store.set(PROFILE_KEY, profile);
    saveProgress(profile);
    const r = final.result;
    const color = r.defense_score >= 70 ? "var(--green)" : r.defense_score >= 40 ? "var(--amber)" : "var(--red)";
    let scoreHtml = "";
    if (final.score) {
      const s = final.score;
      const bonuses = Object.entries(s.bonuses).map(([k, v]) => `+${v} ${esc(k)}`).join("<br>");
      scoreHtml = `<div class="panel"><p class="eyebrow">${s.side} team</p>
        <span class="stamp big ${s.won ? "success" : "caught"} land">${s.won ? "You win" : "You lose"}</span>
        <div class="score-lines" style="margin-top:14px">Base ${s.base}${bonuses ? `<br>${bonuses}` : ""}${s.multiplier !== 1 ? `<br>×${s.multiplier} multiplier` : ""}</div>
        <p style="margin:10px 0 0">Points this game <span class="score-total">${s.total}</span></p>
        <p class="profile-line">Total ${final.profile.points} points · ${final.profile.games} games</p>
        ${final.unlocked.map((t) => `<p class="unlock">Unlocked: ${esc(t)} is now open.</p>`).join("")}
        ${final.locks.goal ? `<p class="note">${esc(final.locks.goal)}</p>` : ""}</div>`;
    }
    const tips = final.tips ? `<div class="panel"><h3>What you could do</h3><div class="tips">
      <div><p class="blue" style="font-weight:600;margin:0">As Blue</p><ul>${final.tips.blue.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>
      <div><p class="red" style="font-weight:600;margin:0">As Red</p><ul>${final.tips.red.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div></div></div>` : "";
    const pm = final.post_mortem ? `<details class="panel pm"><summary>Post-mortem: every move, step by step</summary><pre>${esc(final.post_mortem)}</pre></details>` : "";
    show(`<section class="step">
      <div><p class="eyebrow">${esc(S.start.company.name)} · ${esc(S.settings.level)}</p><h1>Game over.</h1></div>
      <div class="board">
        <div><small>Defense score</small><strong style="color:${color}">${r.defense_score}/100</strong></div>
        <div><small>Damage</small><strong class="${r.damage ? "red" : ""}">${r.damage}/${r.max_damage}</strong></div>
        <div><small>Attacker</small><strong class="${r.caught ? "blue" : r.damage ? "red" : ""}">${r.caught ? "caught" : r.damage ? "got away" : "stayed outside"}</strong></div>
      </div>
      ${scoreHtml}${tips}${pm}
      <div class="btn-row"><button class="btn" id="again">Play again</button><button class="btn ghost" id="menu">Main menu</button></div>
    </section>`);
    document.getElementById("again").addEventListener("click", startGame);
    document.getElementById("menu").addEventListener("click", renderMenu);
  }

  boot();
})();
