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
    watch: new Set(),
    peopleFilter: { role: null, server: null, admin: false, starred: false, q: "" },
    start: null,
    turn: null,
    attack: null,
    busy: false,
    map: null,
    user: null,
    accounts: false,
    notice: "",
  };

  const REALISM = { id: "realism", name: "Realism", text: "Real logs, a real search bar, real addresses. No hints, no hand-holding." };
  const LEVELS = [
    { id: "easy", name: "Easy", text: "Attacks work more often. You see the odds, the heat and advice at the end." },
    { id: "medium", name: "Medium", text: "A fairer fight. Moves are explained, but no numbers." },
    { id: "hard", name: "Hard", text: "The defenders have the edge. No help at all, only the result." },
  ];
  const SIDES = [
    { id: "blue", name: "Blue", text: "Defend the company. The computer runs the attack.", cls: "blue-side" },
    { id: "red", name: "Red", text: "Break in. The computer picked defenses you cannot see.", cls: "red-side" },
    { id: "random", name: "Random", text: "A coin decides your side. Double points if you win." },
  ];

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (value) => `${Math.round(value * 100)}%`;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const store = {
    get(key, fallback) { try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} },
  };

  // moves whose dice the server rolls when you are signed in; everything else is a read
  const MOVES = new Set(["start", "set_defenses", "set_arsenal", "begin", "move", "end_day", "give_up", "finish",
    "blue_act", "blue_wait", "terminal", "realism_search", "realism_act", "realism_wait"]);

  function serverRoll(method, args) {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "api/roll.php", false);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("X-Bastion", "1");
    xhr.send(JSON.stringify({ game: S.dice.game, n: S.dice.n, call: [method, args] }));
    let reply = null;
    try { reply = JSON.parse(xhr.responseText); } catch {}
    if (xhr.status !== 200 || !reply || typeof reply.roll !== "number") {
      throw new Error((reply && reply.error) || "The dice server did not answer.");
    }
    S.dice.game = reply.game;
    S.dice.n += 1;
    return reply.roll;
  }

  function diceFailed(error) {
    S.dice = null;
    S.rec = false;
    show(`<section class="step"><div><p class="eyebrow">Connection lost</p><h1>The dice server did not answer.</h1>
      <p class="muted">${esc(error.message)} Signed-in games roll their dice on the server so nobody can fake a result, so this game cannot go on. Check your connection and start again.</p></div>
      <div class="btn-row"><button class="btn" id="dice-home">Home</button></div></section>`);
    document.getElementById("dice-home").addEventListener("click", renderHome);
  }

  function api(method, ...args) {
    if (S.rec) S.transcript.push([method, args]);
    if (S.dice && MOVES.has(method)) {
      let value;
      try {
        value = serverRoll(method, method === "start" ? args.slice(0, 3) : args);
      } catch (error) {
        diceFailed(error);
        throw error;
      }
      if (method === "start") args = [args[0], args[1], args[2], value];
      else S.session.reseed(value);
    }
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

  function show(html, keepScroll) {
    const y = window.scrollY;
    app.innerHTML = html;
    app.focus({ preventScroll: true });
    window.scrollTo({ top: keepScroll ? y : 0 });
  }

  // choose which connections the network map draws
  function redrawMaps() {
    app.querySelectorAll(".map-panel").forEach((el) => { el.innerHTML = mapInner(); });
  }
  function setFocus(value) {
    if (!S.map || !S.start) return;
    const v = value.trim().toLowerCase();
    if (v === "none" || v === "all" || v === "") S.map.focus = v || "none";
    else {
      const c = S.start.company;
      const node = c.people.find((p) => p.name.toLowerCase() === v) || c.servers.find((s) => s.name.toLowerCase() === v || s.id.toLowerCase() === v);
      S.map.focus = node ? node.id : S.map.focus;
    }
    redrawMaps();
  }
  app.addEventListener("change", (e) => {
    if (e.target.closest(".map-focus")) setFocus(e.target.value);
  });
  app.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-focus]");
    if (chip) setFocus(chip.dataset.focus);
  });

  // live filter: an <input class="row-filter" data-rows=".selector"> hides rows whose data-search misses the query
  app.addEventListener("input", (e) => {
    const box = e.target.closest(".row-filter");
    if (!box) return;
    const q = box.value.trim().toLowerCase();
    const collapse = box.dataset.collapse;  // when set, an empty search lists nobody
    let shown = 0;
    app.querySelectorAll(box.dataset.rows).forEach((row) => {
      const hit = q ? (row.dataset.search || "").includes(q) : (!collapse || row.dataset.keep === "1");
      row.hidden = !hit;
      if (hit) shown += 1;
    });
    const count = box.parentElement.querySelector(".row-count");
    if (count) {
      const total = app.querySelectorAll(box.dataset.rows).length;
      count.textContent = q ? `${shown} shown` : (collapse ? `${total} people — search to list them` : "");
    }
  });

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

  const NAMES = { small: "Olive Byte", medium: "Harbor Clinic", large: "Meridian Bank" };

  function renderMenu() { renderHome(); }

  function renderHome() {
    setGauges(null);
    const menu = api("menu");
    const p = menu.profile;
    const learn = learnTotals();
    const feats = api("achievements");
    const featsDone = feats.filter((a) => a.done).length;
    const wins = Object.entries(p.wins).map(([k, n]) => { const [t, l] = k.split("/"); return `${NAMES[t] || t} ${l ? l[0].toUpperCase() + l.slice(1) : ""} ${n}`; }).join(", ") || "none yet";
    const knownQuests = menu.quests.filter((q) => q.known);
    const anyQuest = knownQuests.length > 0;
    const notice = S.notice ? `<p class="notice" role="status">${esc(S.notice)}</p>` : "";
    S.notice = "";
    const saveNote = S.user ? "Progress saved to your GitHub account." : S.accounts ? "Progress saved in this browser — sign in to keep it everywhere." : "";
    const row = (id, num, title, desc, meta, cls = "") => `<button class="nav-row ${cls}" data-nav="${id}">
      <span class="nav-num">${num}</span>
      <span class="nav-text"><strong>${title}</strong><small>${desc}</small></span>
      <span class="nav-meta">${meta || ""}</span><span class="nav-arrow">→</span></button>`;
    show(`<section class="step home" id="home">
      ${notice}
      <header class="hero">
        <p class="eyebrow">Purple-team cyber range</p>
        <h1 class="wordmark">BASTION</h1>
        <p class="hero-sub">Attack a company or defend it. Every move maps to a real technique — nothing here touches a real system.</p>
        <p class="profile-line">${p.points} points · ${p.games} games · wins: ${esc(wins)}${saveNote ? `<br>${esc(saveNote)}` : ""}</p>
      </header>
      <nav class="nav-rows">
        ${row("play", "01", "Play", "Choose a side, a target and a difficulty, then go.", "")}
        ${row("tutorial", "02", "Tutorial", "Red, Blue and WAF tracks: techniques, defenses and how to combine them.", `<span class="bar mini"><span style="width:${Math.round((learn.done / learn.total) * 100)}%"></span></span> ${learn.done}/${learn.total}`)}
        ${row("leaderboards", "03", "Leaderboards", "Realism high scores, Red and Blue.", "")}
        ${row("achievements", "04", "Achievements", "Ten feats. Few players will see them all.", `${featsDone}/${feats.length}`)}
        ${anyQuest
          ? row("quests", "◆", "Dossiers", `${knownQuests.length} classified objective${knownQuests.length > 1 ? "s" : ""} in play.`, '<span class="pill">classified</span>')
          : `<button class="nav-row nav-classified locked" data-nav="quests"><span class="nav-num">▓▓</span>
             <span class="nav-text"><strong>█████████</strong><small>Some files are not on any inventory.</small></span><span class="nav-arrow">→</span></button>`}
      </nav>
    </section>`);
    app.querySelectorAll("[data-nav]").forEach((el) => el.addEventListener("click", () => {
      const to = el.dataset.nav;
      if (to === "play") { S.play = { step: "side" }; renderSetup(); }
      else if (to === "tutorial") renderLearn();
      else if (to === "leaderboards") renderLeaderboard();
      else if (to === "quests") renderQuests();
      else if (to === "achievements") renderAchievements();
    }));
  }

  function renderAchievements() {
    setGauges(null);
    const list = api("achievements");
    const done = list.filter((a) => a.done).length;
    const cards = list.map((a) => `<div class="feat ${a.done ? "done" : ""} ${a.classified ? "classified" : ""}">
      <span class="feat-mark">${a.done ? "★" : a.classified ? "▓" : "☆"}</span>
      <span class="feat-text"><strong>${esc(a.name)}</strong><small>${esc(a.text)}</small></span>
      <span class="feat-state">${a.done ? "earned" : a.classified ? "classified" : "locked"}</span></div>`).join("");
    const how = S.user
      ? "Earned only in signed-in games, where the server rolls the dice. A referee replays every finished game and awards these on its own, usually within the hour."
      : "Sign in with GitHub to earn these: they count only in games where the server rolls the dice and a referee replays the result.";
    show(`<section class="step">
      ${backBar("Home")}
      <div><p class="eyebrow">${done} of ${list.length} earned</p><h1>Achievements.</h1>
      <p class="muted">${esc(how)}</p></div>
      <div class="feats">${cards}</div>
    </section>`);
    wireBack(renderHome);
  }

  function renderQuests() {
    setGauges(null);
    const menu = api("menu");
    const rows = menu.quests.map((q) => `<tr class="${q.known ? (q.done ? "done" : "known") : "hidden"}">
      <td>${esc(q.title)}</td><td>${esc(q.text)}</td><td class="num">${esc(q.progress)}</td><td>${esc(q.reward)}</td></tr>`).join("");
    show(`<section class="step">
      ${backBar("Home")}
      <div><p class="eyebrow">Classified</p><h1>Dossiers.</h1>
      <p class="muted">Hidden objectives. You will not see one until something in a game points you to it.</p></div>
      <div class="panel quests"><table class="sheet"><tr><th>Quest</th><th>What to do</th><th class="num">Progress</th><th>Reward</th></tr>${rows}</table></div>
    </section>`);
    wireBack(renderHome);
  }

  function renderSetup(keepScroll) {
    setGauges(null);
    const menu = api("menu");
    S.play = S.play || { step: "side" };
    const sel = S.settings;
    // keep selections valid against what is unlocked
    const companyAvailable = (cid) => !menu.locks.easy[cid];
    const levelAvailable = (lvl, cid) => lvl === "realism"
      ? (menu.realism && !menu.locks.realism[cid])
      : (!menu.levels[lvl] && !menu.locks[lvl][cid]);
    if (sel.company && (menu.companies.find((c) => c.id === sel.company)?.classified || !companyAvailable(sel.company))) sel.company = null;
    if (sel.level && sel.company && !levelAvailable(sel.level, sel.company)) sel.level = null;

    const step = S.play.step;
    const crumb = (key, label, active, ok) => `<button class="crumb ${active ? "active" : ""} ${ok ? "ok" : ""}" data-step="${key}" ${ok || active ? "" : "disabled"}>${ok ? "✓ " : ""}${label}</button>`;
    const crumbs = `<div class="crumbs">
      ${crumb("side", sel.side ? capital(sel.side) : "Side", step === "side", !!sel.side)}<span class="crumb-sep">▸</span>
      ${crumb("company", sel.company ? NAMES[menu.companies.find((c) => c.id === sel.company)?.tier] || "Map" : "Map", step === "company", !!sel.company)}<span class="crumb-sep">▸</span>
      ${crumb("difficulty", sel.level ? capital(sel.level) : "Difficulty", step === "difficulty", !!sel.level)}</div>`;

    let body = "";
    if (step === "side") {
      body = `<div><p class="eyebrow">Step 1 of 3</p><h1>Pick your side.</h1></div>
        <div class="choices play-reveal">${SIDES.map((s, i) => `<button class="choice ${s.cls || ""} ${sel.side === s.id ? "selected" : ""}" style="animation-delay:${i * 60}ms" data-pick="side" data-id="${s.id}">
          <strong>${esc(s.name)}</strong><small>${esc(s.text)}</small></button>`).join("")}</div>`;
    } else if (step === "company") {
      const cards = menu.companies.map((c, i) => {
        if (c.classified) return `<button class="choice classified" style="animation-delay:${i * 70}ms" disabled><span class="tag">classified · ??? people</span><strong>${esc(c.name)}</strong><small>Unlock conditions: unknown. ${esc(c.description)}</small></button>`;
        const locked = !companyAvailable(c.id) ? menu.locks.easy[c.id] : null;
        return `<button class="choice ${sel.company === c.id ? "selected" : ""}" style="animation-delay:${i * 70}ms" data-pick="company" data-id="${c.id}" ${locked ? "disabled" : ""}>
          <span class="tag">${esc(c.tier)} · ${c.people} people</span><strong>${esc(c.name)}</strong>
          <small>${esc(locked ? `Locked: ${locked}` : c.description)}</small></button>`;
      }).join("");
      body = `<div><p class="eyebrow">Step 2 of 3 · playing ${capital(sel.side)}</p><h1>Choose the target.</h1></div>
        <div class="choices play-reveal">${cards}</div>`;
    } else {
      const levelCard = (l, i) => {
        const avail = levelAvailable(l.id, sel.company);
        const reason = l.id === "realism" ? "unlock conditions unknown" : (menu.levels[l.id] || menu.locks[l.id][sel.company]);
        if (!avail) return `<button class="choice ${l.id === "realism" ? "classified" : ""}" style="animation-delay:${i * 60}ms" disabled><strong>${l.id === "realism" ? "████████" : esc(l.name)}</strong><small>${l.id === "realism" ? "Unlock conditions: unknown." : `Locked: ${esc(reason)}`}</small></button>`;
        return `<button class="choice ${l.id === "realism" ? "classified-open" : ""} ${sel.level === l.id ? "selected" : ""}" style="animation-delay:${i * 60}ms" data-pick="level" data-id="${l.id}">
          <strong>${esc(l.name)}</strong><small>${esc(l.text)}</small></button>`;
      };
      const all = [...LEVELS, REALISM];
      const target = menu.companies.find((c) => c.id === sel.company);
      body = `<div><p class="eyebrow">Step 3 of 3 · ${capital(sel.side)} vs ${esc(target ? target.name : "")}</p><h1>How hard?</h1></div>
        <div class="choices play-reveal">${all.map(levelCard).join("")}</div>
        ${sel.level ? `<div class="btn-row start-row"><button class="btn big" id="go">Start — ${capital(sel.side)} · ${esc(target ? target.name : "")} · ${capital(sel.level)}</button></div>` : ""}`;
    }
    const prev = { side: ["Home", null], company: ["Change side", "side"], difficulty: ["Change the map", "company"] }[step];
    show(`<section class="step play-flow">
      <div class="back-bar"><button class="back-btn" id="play-prev">← ${esc(prev[0])}</button>${crumbs}</div>
      <div class="play-step">${body}</div>
    </section>`, keepScroll);
    app.querySelectorAll("[data-pick]").forEach((el) => el.addEventListener("click", () => {
      const group = el.dataset.pick;
      sel[group === "level" ? "level" : group] = el.dataset.id;
      store.set(SETTINGS_KEY, sel);
      if (group === "side") S.play.step = "company";
      else if (group === "company") S.play.step = "difficulty";
      renderSetup(group === "level");  // keep scroll when picking a difficulty (same step reveals Start)
    }));
    app.querySelectorAll("[data-step]").forEach((el) => el.addEventListener("click", () => { S.play.step = el.dataset.step; renderSetup(); }));
    document.getElementById("play-prev").addEventListener("click", () => {
      if (prev[1]) { S.play.step = prev[1]; renderSetup(); } else renderHome();
    });
    document.getElementById("go")?.addEventListener("click", startGame);
  }

  function capital(s) { return s ? s[0].toUpperCase() + s.slice(1) : s; }

  // one consistent "previous" control at the top-left of every screen
  const backBar = (label, extra = "") => `<div class="back-bar"><button class="back-btn" id="back-prev">← ${esc(label)}</button>${extra}</div>`;
  const wireBack = (fn) => document.getElementById("back-prev")?.addEventListener("click", fn);
  const backToSetup = () => { S.play = { step: "difficulty" }; renderSetup(); };

  function learnTotals() {
    const h = api("learn_hub");
    const parts = [h.red.techniques, h.red.chains, h.blue.defenses, h.blue.guards];
    return { hub: h, done: parts.reduce((n, p) => n + p.done, 0), total: parts.reduce((n, p) => n + p.total, 0) };
  }

  const progressPanel = (title, done, total, unit, text) => `<div class="panel" style="margin-top:28px">
      <div class="learn-banner-top"><strong>${title}</strong><span class="learn-count">${done}/${total} ${unit}</span></div>
      <div class="bar big"><span style="width:${total ? Math.round((done / total) * 100) : 0}%"></span></div>
      ${text ? `<p class="muted" style="margin:12px 0 0;font-size:14px">${text}</p>` : ""}</div>`;

  function renderLearn() {
    setGauges(null);
    const { hub } = learnTotals();
    const waf = store.get(WAF_BEST_KEY, 0);
    const red = hub.red.techniques.done + hub.red.chains.done, redAll = hub.red.techniques.total + hub.red.chains.total;
    const blue = hub.blue.defenses.done + hub.blue.guards.done, blueAll = hub.blue.defenses.total + hub.blue.guards.total;
    const cat = (id, cls, title, text, done, total, unit) => `<button class="learn-cat ${cls}" data-cat="${id}">
      <span class="learn-cat-top"><strong>${title}</strong><span class="learn-count">${done}/${total} ${unit}</span></span>
      <small>${text}</small>
      <span class="bar"><span style="width:${total ? Math.round((done / total) * 100) : 0}%"></span></span></button>`;
    show(`<section class="step">
      ${backBar("Home")}
      <div><p class="eyebrow">Learning mode</p><h1>Learn to play.</h1>
      <p class="muted">Three tracks. Every lesson is built from the game's own rules and real MITRE ATT&CK techniques, so what you learn here is exactly how the game behaves.</p></div>
      <div class="learn-cats">
        ${cat("red", "red-cat", "Red · attack", `${hub.red.techniques.total} techniques, then ${hub.red.chains.total} combinations: chain them into an attack that gets through.`, red, redAll, "done")}
        ${cat("blue", "blue-cat", "Blue · defend", `${hub.blue.defenses.total} defenses, then ${hub.blue.guards.total} combinations: stop a real attack chain on a budget.`, blue, blueAll, "done")}
        ${cat("waf", "waf-cat", "WAF Lab", "Train the doorman: stop 40 web attacks without turning away 25 real customers.", waf, 100, "best")}
      </div>
    </section>`);
    app.querySelectorAll("[data-cat]").forEach((el) => el.addEventListener("click", () => {
      const c = el.dataset.cat;
      if (c === "red") renderLearnRed(); else if (c === "blue") renderLearnBlue(); else renderWafLab();
    }));
    wireBack(renderHome);
  }

  function renderLearnRed() {
    setGauges(null);
    const { hub } = learnTotals();
    const s = hub.red.techniques, c = hub.red.chains;
    const lessons = s.lessons.map((l, i) => `<button class="lesson-row ${l.done ? "done" : ""}" data-lesson="${l.id}">
      <span class="num">${String(i + 1).padStart(2, "0")}</span>
      <span class="lesson-name"><strong>${esc(l.name)}</strong><small>${esc(l.mitre)} · ${esc(l.tactic)}</small></span>
      <span class="lesson-mark">${l.done ? "✓ learned" : "learn →"}</span></button>`).join("");
    const chains = c.chains.map((ch) => `<button class="lesson-row ${ch.done ? "done" : ""}" data-chain="${ch.id}">
      <span class="num">⛓</span>
      <span class="lesson-name"><strong>${esc(ch.goal)}</strong><small>${ch.steps} steps to order</small></span>
      <span class="lesson-mark">${ch.done ? "✓ solved" : "build →"}</span></button>`).join("");
    show(`<section class="step">
      ${backBar("Learning")}
      <div><p class="eyebrow">Learning · Red</p><h1>Think like the attacker.</h1></div>
      ${progressPanel("Techniques", s.done, s.total, "learned", "Spot each technique, then learn what it needs before it can work.")}
      <div class="lesson-list">${lessons}</div>
      ${progressPanel("Combinations — chain them into an attack", c.done, c.total, "solved", "A technique rarely works alone. Order these into an attack that actually gets through; the engine checks it the way a real one would.")}
      <div class="lesson-list">${chains}</div>
    </section>`);
    app.querySelectorAll("[data-lesson]").forEach((el) => el.addEventListener("click", () => renderLesson("red", el.dataset.lesson)));
    app.querySelectorAll("[data-chain]").forEach((el) => el.addEventListener("click", () => renderChain(el.dataset.chain)));
    wireBack(renderLearn);
  }

  function renderLearnBlue() {
    setGauges(null);
    const { hub } = learnTotals();
    const s = hub.blue.defenses, g = hub.blue.guards;
    const lessons = s.lessons.map((l, i) => `<button class="lesson-row ${l.done ? "done" : ""}" data-lesson="${l.id}">
      <span class="num">${String(i + 1).padStart(2, "0")}</span>
      <span class="lesson-name"><strong>${esc(l.name)}</strong><small>${esc(l.sub)}</small></span>
      <span class="lesson-mark">${l.done ? "✓ learned" : "learn →"}</span></button>`).join("");
    const guards = g.guards.map((ch) => `<button class="lesson-row ${ch.done ? "done" : ""}" data-guard="${ch.id}">
      <span class="num">🛡</span>
      <span class="lesson-name"><strong>Stop: ${esc(ch.goal)}</strong><small>${ch.steps}-step attack</small></span>
      <span class="lesson-mark">${ch.done ? "✓ stopped" : "defend →"}</span></button>`).join("");
    show(`<section class="step">
      ${backBar("Learning")}
      <div><p class="eyebrow">Learning · Blue</p><h1>Think like the defender.</h1></div>
      ${progressPanel("Defenses", s.done, s.total, "learned", "What each control is for, and whether it stops an attack, spots it, or helps you recover.")}
      <div class="lesson-list">${lessons}</div>
      ${progressPanel("Combinations — stop an attack chain", g.done, g.total, "stopped", "One control always fails sometimes. Within a budget, stop one step and watch another: defense in depth.")}
      <div class="lesson-list">${guards}</div>
    </section>`);
    app.querySelectorAll("[data-lesson]").forEach((el) => el.addEventListener("click", () => renderLesson("blue", el.dataset.lesson)));
    app.querySelectorAll("[data-guard]").forEach((el) => el.addEventListener("click", () => renderGuard(el.dataset.guard)));
    wireBack(renderLearn);
  }

  function renderGuard(id, picked = new Set(), result = null) {
    setGauges(null);
    const g = api("guard", id);
    const cost = [...picked].reduce((n, d) => n + (g.options.find((o) => o.id === d)?.cost || 0), 0);
    const steps = g.steps.map((st, i) => {
      const row = result && result.rows[i];
      const cls = row ? (row.blocked.length ? "ok" : row.spotted.length ? "watch" : "bad") : "";
      const how = row ? [row.blocked.length ? `stopped by ${row.blocked.join(", ")}` : "", row.spotted.length ? `spotted by ${row.spotted.join(", ")}` : ""].filter(Boolean).join(" · ") || "nothing covers this step" : `${st.mitre}`;
      return `<div class="chain-slot ${cls}"><span class="num">${i + 1}</span><span class="chain-card-name"><strong>${esc(st.name)}</strong><small>${esc(how)}</small></span></div>`;
    }).join("");
    const opts = g.options.map((o) => `<button class="choice guard-opt ${picked.has(o.id) ? "selected" : ""}" data-def="${o.id}">
      <strong>${esc(o.name)}</strong><small>${esc(o.category)} · costs ${o.cost}</small></button>`).join("");
    show(`<section class="step">
      ${backBar("Blue lessons")}
      <div><p class="eyebrow">Blue · combination</p><h1>Stop the attack.</h1></div>
      <div class="panel coach"><p class="coach-label">The attacker's plan</p><p>${esc(g.goal)}</p></div>
      <div class="panel"><h3>Their steps</h3><div class="chain-slots">${steps}</div>
        ${result ? `<p class="intel-note" style="color:var(${result.passed ? "--green" : "--red"})">${esc(result.note)}</p>` : ""}</div>
      <div class="panel"><div class="learn-banner-top"><h3 style="margin:0">Your controls</h3>
        <span class="learn-count ${cost > g.budget ? "over" : ""}">spent ${cost} / ${g.budget}</span></div>
        <p class="muted">Stop at least one step and spot at least one other, without going over budget.</p>
        <div class="choices">${opts}</div>
        <div class="btn-row" style="margin-top:14px"><button class="btn" id="guard-check" ${picked.size ? "" : "disabled"}>Check my defense</button>
          <button class="btn ghost" id="guard-clear">Clear</button></div></div>
    </section>`, true);
    app.querySelectorAll("[data-def]").forEach((el) => el.addEventListener("click", () => {
      const d = el.dataset.def;
      if (picked.has(d)) picked.delete(d); else picked.add(d);
      renderGuard(id, picked, null);
    }));
    document.getElementById("guard-clear").addEventListener("click", () => renderGuard(id, new Set(), null));
    document.getElementById("guard-check").addEventListener("click", () => {
      const r = api("check_guard", id, JSON.stringify([...picked]));
      const profile = JSON.parse(r.profile_json);
      store.set(PROFILE_KEY, profile); saveProgress(profile);
      renderGuard(id, picked, r);
    });
    wireBack(renderLearnBlue);
  }

  const WAF_BEST_KEY = "bastion-waf-best";
  const WAF_PICK_KEY = "bastion-waf-pick";
  const KIND_NAMES = { sqli: "SQL injection", xss: "XSS", traversal: "Path traversal" };

  function renderWafLab() {
    setGauges(null);
    const lab = api("waf_lab");
    const picked = new Set(store.get(WAF_PICK_KEY, []));
    const firstTime = !store.get(WAF_BEST_KEY, 0) && !picked.size;
    const card = (i) => `<button class="choice waf-item ${picked.has(i.id) ? "selected" : ""}" data-waf="${esc(i.id)}" aria-pressed="${picked.has(i.id)}">
      <strong>${esc(i.title)}</strong><small>${esc(i.explain)}</small></button>`;
    show(`<section class="step waf-lab">
      ${backBar("Learning")}
      <div><p class="eyebrow">WAF Lab · practice, no points</p><h1>Train the doorman.</h1></div>
      <details class="panel waf-intro" ${firstTime ? "open" : ""}><summary><strong>What is a WAF? (read this first)</strong></summary>
        <ol class="waf-steps">
          <li><strong>A normal login.</strong> You type a name and a password. The site asks its database:<code>find user maria AND password 1234</code></li>
          <li><strong>SQL injection.</strong> A hacker types <code class="bad">' OR 1=1</code> as the password. The question becomes:<code>find user maria AND password '' OR 1=1</code>1=1 is always true, so the database lets them in without a password.</li>
          <li><strong>XSS.</strong> A hacker leaves a product review containing <code class="bad">&lt;script&gt;…&lt;/script&gt;</code>. Every visitor's browser runs that code.</li>
          <li><strong>The WAF.</strong> A doorman in front of the site who reads every message first. Too relaxed and attacks slip past in disguise; too strict and real customers like <em>Mr O'Brien</em> are turned away. Each innocent customer you block costs ${lab.penalty} points.</li>
        </ol></details>
      <div class="waf-board panel" id="waf-board" aria-live="polite"></div>
      <div class="panel"><h3>1 · Clean up first</h3><p class="muted">Attackers disguise their messages. These steps undo the disguise before any rule looks.</p>
        <div class="choices waf-grid">${lab.items.filter((i) => i.kind === "clean").map(card).join("")}</div></div>
      <div class="panel"><h3>2 · Then block</h3><p class="muted">Some of these are traps: they catch attacks but also block real customers.</p>
        <div class="choices waf-grid">${lab.items.filter((i) => i.kind === "rule").map(card).join("")}</div></div>
      <div class="panel waf-detail" id="waf-detail"></div>
    </section>`);
    const update = () => {
      const r = api("waf_check", JSON.stringify([...picked]));
      store.set(WAF_PICK_KEY, [...picked]);
      if (r.score > store.get(WAF_BEST_KEY, 0)) store.set(WAF_BEST_KEY, r.score);
      const bar = (n, total, cls) => `<span class="bar ${cls}"><span style="width:${total ? Math.round((n / total) * 100) : 0}%"></span></span>`;
      const color = r.score >= 85 ? "good" : r.score >= 60 ? "mid" : "low";
      document.getElementById("waf-board").innerHTML = `
        <div class="waf-score ${color}"><span class="waf-num">${r.score}</span><span class="muted">/100 WAF score · best ${store.get(WAF_BEST_KEY, 0)}</span></div>
        <div class="waf-meters">
          <div><span class="waf-label">Hackers blocked <b>${r.caught}/${r.attacks}</b></span>${bar(r.caught, r.attacks, "good")}</div>
          <div><span class="waf-label">Innocent customers blocked <b>${r.wrongly.length}/${r.innocent}</b></span>${bar(r.wrongly.length, r.innocent, "bad")}</div>
          <div class="waf-kinds">${Object.entries(r.kinds).map(([k, v]) => `<span>${KIND_NAMES[k]} <b>${v.caught}/${v.total}</b></span>`).join("")}</div>
        </div>
        ${r.score === 100 ? '<p class="waf-perfect">Perfect: every attack stopped and nobody innocent turned away.</p>' : ""}`;
      const title = (id) => (lab.items.find((i) => i.id === id) || {}).title || id;
      const missed = r.missed.map((m) => `<li><code>${esc(m.text)}</code><span>${esc(KIND_NAMES[m.kind])} · ${esc(m.hint)}</span></li>`).join("");
      const wrong = r.wrongly.map((w) => `<li><code>${esc(w.text)}</code><span>${esc(w.why)} · blocked by “${esc(title(w.rule))}”</span></li>`).join("");
      document.getElementById("waf-detail").innerHTML = `
        <div class="waf-cols">
          <div><h3>Still getting in (${r.missed.length})</h3>${missed ? `<ul class="waf-list bad">${missed}</ul>` : '<p class="muted">Nothing. Every attack is stopped.</p>'}</div>
          <div><h3>Wrongly blocked (${r.wrongly.length})</h3>${wrong ? `<ul class="waf-list warn">${wrong}</ul>` : '<p class="muted">Nobody. Every real customer gets in.</p>'}</div>
        </div>`;
    };
    app.querySelectorAll("[data-waf]").forEach((el) => el.addEventListener("click", () => {
      const id = el.dataset.waf;
      if (picked.has(id)) picked.delete(id); else picked.add(id);
      el.classList.toggle("selected", picked.has(id));
      el.setAttribute("aria-pressed", String(picked.has(id)));
      update();
    }));
    update();
    wireBack(renderLearn);
  }

  function renderChain(id) {
    setGauges(null);
    const ch = api("chain", id);
    S.chain = { id, order: [] };
    drawChain(ch);
  }

  function drawChain(ch, result, keepScroll) {
    const picked = S.chain.order;
    const slots = Array.from({ length: ch.length }, (_, i) => {
      const aid = picked[i];
      const card = aid ? ch.cards.find((c) => c.id === aid) : null;
      const stepRes = result && result.steps[i];
      const cls = stepRes ? (stepRes.ok ? "ok" : "bad") : (card ? "filled" : "");
      return `<div class="chain-slot ${cls}"><span class="num">${i + 1}</span>${card ? `<span class="chain-card-name"><strong>${esc(card.name)}</strong><small>${esc(card.mitre)} · ${esc(card.tactic)}</small></span>` : '<span class="chain-empty">—</span>'}</div>`;
    }).join("");
    const used = new Set(picked);
    const pool = ch.cards.filter((c) => !used.has(c.id)).map((c) =>
      `<button class="choice chain-card" data-card="${c.id}"><strong>${esc(c.name)}</strong><small>${esc(c.mitre)} · ${esc(c.tactic)}</small></button>`).join("");
    const failStep = result && result.steps.find((x) => !x.ok);
    show(`<section class="step">
      ${backBar("Red lessons")}
      <div><p class="eyebrow">Red · combination</p><h1>Build the attack.</h1></div>
      <div class="panel coach"><p class="coach-label">Goal</p><p>${esc(ch.goal)}</p></div>
      <div class="panel"><h3>Your chain</h3><div class="chain-slots">${slots}</div>
        ${failStep ? `<p class="intel-note" style="color:var(--red)">${esc(failStep.reason)}</p>` : ""}
        ${result && result.passed ? `<p class="intel-note" style="color:var(--green)">${esc(result.note)}</p>` : ""}
        <div class="btn-row" style="margin-top:14px">
          <button class="btn" id="chain-check" ${picked.length === ch.length ? "" : "disabled"}>Check the chain</button>
          <button class="btn ghost" id="chain-reset">Clear</button></div></div>
      ${pool ? `<div class="panel"><h3>Techniques — tap in order</h3><div class="choices">${pool}</div></div>` : ""}
    </section>`, keepScroll);
    app.querySelectorAll("[data-card]").forEach((el) => el.addEventListener("click", () => {
      S.chain.order.push(el.dataset.card); drawChain(ch, null, true);
    }));
    document.getElementById("chain-reset").addEventListener("click", () => { S.chain.order = []; drawChain(ch, null, true); });
    wireBack(renderLearnRed);
    document.getElementById("chain-check")?.addEventListener("click", () => {
      const r = api("check_chain", ch.id, JSON.stringify(S.chain.order));
      const profile = JSON.parse(r.profile_json);
      store.set(PROFILE_KEY, profile); saveProgress(profile);
      drawChain(ch, r, true);
    });
  }

  function renderLesson(kind, id) {
    setGauges(null);
    const l = kind === "blue" ? api("blue_lesson", id) : api("lesson", id);
    const back = kind === "blue" ? renderLearnBlue : renderLearnRed;
    S.lesson = { id, kind, attackChoice: null };
    const opts = (items, group) => items.map((o) => `<button class="choice learn-opt" data-pick="${group}" data-id="${esc(o.id)}">${esc(o.label)}</button>`).join("");
    show(`<section class="step">
      ${backBar(kind === "blue" ? "Blue lessons" : "Red lessons")}
      <div><p class="eyebrow">${kind === "blue" ? "Blue" : "Red"} · ${esc(l.eyebrow)}</p><h1>${esc(l.name)}</h1></div>
      <div class="panel coach"><p class="coach-label">Coach</p><p>${esc(l.teach)}</p>
        ${l.intel_only ? '<p class="intel-note">On its own this is just intelligence — it does not break anything. It sets up the steps that do.</p>' : ""}</div>
      <div class="panel" id="step-attack"><h3>${esc(l.step1.title)}</h3><p>${esc(l.step1.prompt)}</p>
        <div class="choices">${opts(l.step1.options, "attack")}</div></div>
      <div class="panel" id="step-defense" hidden><h3>${esc(l.step2.title)}</h3><p>${esc(l.step2.prompt)}</p>
        <div class="choices">${opts(l.step2.options, "defense")}</div></div>
      <div id="lesson-result"></div>
    </section>`);
    app.querySelectorAll('[data-pick="attack"]').forEach((el) => el.addEventListener("click", () => {
      S.lesson.attackChoice = el.dataset.id;
      app.querySelectorAll('[data-pick="attack"]').forEach((b) => b.classList.toggle("selected", b === el));
      const d = document.getElementById("step-defense");
      d.hidden = false; d.scrollIntoView({ behavior: "smooth", block: "center" });
    }));
    app.querySelectorAll('[data-pick="defense"]').forEach((el) => el.addEventListener("click", () => {
      if (!S.lesson.attackChoice) return;
      app.querySelectorAll('[data-pick="defense"]').forEach((b) => b.classList.toggle("selected", b === el));
      finishLesson(kind, id, S.lesson.attackChoice, el.dataset.id);
    }));
    wireBack(back);
  }

  function finishLesson(kind, id, attackChoice, defenseChoice) {
    const back = kind === "blue" ? renderLearnBlue : renderLearnRed;
    const r = api("learn_check", kind, id, attackChoice, defenseChoice);
    const profile = JSON.parse(r.profile_json);
    store.set(PROFILE_KEY, profile);
    saveProgress(profile);
    const mark = (ok) => ok ? '<span class="tick good">✓</span>' : '<span class="tick bad">✗</span>';
    const next = r.summary.lessons.find((x) => !x.done);
    document.getElementById("lesson-result").innerHTML = `<div class="panel coach ${r.passed ? "pass" : "retry"}">
      <p class="coach-label">Coach</p>
      <p>${mark(r.ok1)} ${esc(r.note1)}</p>
      <p>${mark(r.ok2)} ${esc(r.note2)}</p>
      <p class="learn-count">${r.summary.done}/${r.summary.total} learned</p>
      <div class="btn-row">${r.passed
        ? (next ? `<button class="btn" id="lesson-next">Next ${kind === "blue" ? "defense" : "technique"}</button>` : `<button class="btn" id="lesson-next">Finish</button>`)
        : `<button class="btn" id="lesson-retry">Try again</button>`}
        <button class="btn ghost" id="lesson-list">All lessons</button></div></div>`;
    document.getElementById("lesson-result").scrollIntoView({ behavior: "smooth", block: "center" });
    document.getElementById("lesson-next")?.addEventListener("click", () => next ? renderLesson(kind, next.id) : back());
    document.getElementById("lesson-retry")?.addEventListener("click", () => renderLesson(kind, id));
    document.getElementById("lesson-list").addEventListener("click", back);
  }

  function startGame() {
    const { company, level, side } = S.settings;
    S.transcript = [];
    S.watch = new Set();
    S.peopleFilter = { role: null, server: null, admin: false, starred: false, q: "" };
    S.rec = true;
    S.dice = S.user ? { game: null, n: 0 } : null;  // signed in: the server rolls the dice
    try {
      S.start = api("start", company, level, side, Math.floor(Math.random() * 1e9));
    } catch { return; }
    S.startedAt = Date.now();
    S.turn = null;
    S.attack = null;
    S.map = { owned: new Set(), admin: new Set(), scanned: new Set(), taken: new Set(), targets: new Set(), ping: null, focus: S.start.company.people.length > 14 ? "none" : "all" };
    S.targetSort = undefined;
    if (S.start.side === "red") renderArsenal();
    else renderDefenses();
  }

  function word(value) {
    return value ? `<span class="word-${value}">${esc(value)}</span>` : "";
  }

  const BIG_ORG = 30;
  function filterActive(f) { return !!(f.role || f.server || f.admin || f.starred || f.q); }
  function personVisible(p, company) {
    const f = S.peopleFilter;
    if (!filterActive(f)) return company.people.length <= BIG_ORG || S.watch.has(p.id);
    if (f.role && p.role !== f.role) return false;
    if (f.server && !p.access.includes(f.server)) return false;
    if (f.admin && p.admin !== "yes") return false;
    if (f.starred && !S.watch.has(p.id)) return false;
    if (f.q && !(p.name + " " + p.role).toLowerCase().includes(f.q)) return false;
    return true;
  }
  function applyPeopleFilter() {
    const company = S.start && S.start.company;
    if (!company) return;
    const f = S.peopleFilter;
    let shown = 0;
    app.querySelectorAll("#people-tbl tbody tr[data-pid]").forEach((row) => {
      const person = company.people.find((x) => x.id === row.dataset.pid);
      const vis = person ? personVisible(person, company) : true;
      row.hidden = !vis;
      if (vis) shown += 1;
    });
    app.querySelectorAll("[data-pf]").forEach((b) => {
      const k = b.dataset.pf;
      if (k === "clear") return;
      b.classList.toggle("on", k === "admin" || k === "starred" ? !!f[k] : f[k] === b.dataset.v);
    });
    const hint = document.getElementById("pf-hint");
    if (hint) {
      hint.textContent = filterActive(f)
        ? `${shown} of ${company.people.length} shown`
        : company.people.length > BIG_ORG
          ? `${company.people.length} people. Pick a role, a server or Admins to list them${S.watch.size ? ` — your ${S.watch.size} future target${S.watch.size > 1 ? "s are" : " is"} shown below` : ""}.`
          : "";
    }
    const n = document.getElementById("watch-n");
    if (n) n.textContent = S.watch.size;
  }
  app.addEventListener("click", (e) => {
    const pf = e.target.closest("[data-pf]");
    if (pf) {
      const f = S.peopleFilter, k = pf.dataset.pf, v = pf.dataset.v;
      if (k === "clear") { Object.assign(f, { role: null, server: null, admin: false, starred: false, q: "" }); const q = app.querySelector(".people-q"); if (q) q.value = ""; }
      else if (k === "admin" || k === "starred") f[k] = !f[k];
      else f[k] = f[k] === v ? null : v;
      applyPeopleFilter();
      return;
    }
    const star = e.target.closest("[data-star]");
    if (star) {
      e.stopPropagation();
      const id = star.dataset.star;
      if (S.watch.has(id)) S.watch.delete(id); else S.watch.add(id);
      app.querySelectorAll(`[data-star="${CSS.escape(id)}"]`).forEach((b) => { b.classList.toggle("on", S.watch.has(id)); b.textContent = S.watch.has(id) ? "★" : "☆"; });
      applyPeopleFilter();
      app.querySelectorAll(".map-panel").forEach((el) => { el.innerHTML = mapInner(); });
    }
  });
  app.addEventListener("input", (e) => {
    if (!e.target.classList.contains("people-q")) return;
    S.peopleFilter.q = e.target.value.trim().toLowerCase();
    applyPeopleFilter();
  });

  function briefHtml(company) {
    const servers = company.servers.map((s) => `<tr><td>${esc(s.name)} <span class="muted">${esc(s.id)}</span></td>
      <td>${s.exposed ? '<span class="word-yes">internet</span>' : '<span class="muted">inside</span>'}</td><td class="muted">${esc(s.software.join(", "))}</td></tr>`).join("");
    const hasTraits = company.people.some((p) => p.phishing);
    const hasLoyalty = company.people.some((p) => p.loyalty);
    const f = S.peopleFilter;
    const people = company.people.map((p) => `<tr data-pid="${esc(p.id)}"${personVisible(p, company) ? "" : " hidden"}>
      <td><button class="star ${S.watch.has(p.id) ? "on" : ""}" data-star="${esc(p.id)}" title="Add to future targets" aria-label="Add ${esc(p.name)} to future targets">${S.watch.has(p.id) ? "★" : "☆"}</button>${esc(p.name)} <span class="muted">${esc(p.role)}</span></td>
      <td>${p.admin === "yes" ? '<span class="word-yes">yes</span>' : `<span class="muted">${esc(p.admin)}</span>`}</td>
      <td class="muted">${esc(p.access.join(", "))}</td>
      ${hasTraits ? `<td>${word(p.phishing)}</td><td>${word(p.passwords)}</td>` : ""}
      ${hasLoyalty ? `<td>${word(p.loyalty)}</td>` : ""}</tr>`).join("");
    let peopleSearch = "";
    if (company.people.length > 12) {
      const count = (pred) => company.people.filter(pred).length;
      const roles = [...new Set(company.people.map((p) => p.role))].sort();
      const servers = company.servers.map((s) => s.id).filter((id) => company.people.some((p) => p.access.includes(id)));
      const chip = (kind, value, label, n) => `<button class="chip ${f[kind] === value ? "on" : ""}" data-pf="${kind}" data-v="${esc(value)}">${esc(label)}${n !== undefined ? ` <span class="chip-n">${n}</span>` : ""}</button>`;
      peopleSearch = `<div class="people-filters">
        <div class="pf-row"><span class="pf-label">Role</span>${roles.map((r) => chip("role", r, r, count((p) => p.role === r))).join("")}</div>
        <div class="pf-row"><span class="pf-label">Can log in to</span>${servers.map((s) => chip("server", s, s, count((p) => p.access.includes(s)))).join("")}</div>
        <div class="pf-row"><span class="pf-label">Show</span>
          <button class="chip ${f.admin ? "on" : ""}" data-pf="admin" data-v="1">Admins</button>
          <button class="chip star-chip ${f.starred ? "on" : ""}" data-pf="starred" data-v="1">★ Future targets <span class="chip-n" id="watch-n">${S.watch.size}</span></button>
          <input class="people-q" placeholder="or type a name…" value="${esc(f.q)}">
          <button class="linkish" data-pf="clear" data-v="1">clear filters</button></div>
        <p class="pf-hint muted" id="pf-hint"></p>
      </div>`;
    }
    const data = company.data.length ? `<div class="panel"><h3>Valuable data</h3><table class="sheet"><tr><th>What</th><th>Where</th><th class="num">Value</th></tr>
      ${company.data.map((d) => `<tr><td>${esc(d.name)}</td><td class="muted">${esc(d.where)}</td><td class="num">${d.value}</td></tr>`).join("")}</table></div>` : "";
    return `<div class="brief">
      <p class="lede" style="margin:0">${esc(company.description)}</p>
      <div class="brief-grid">
        <div class="panel"><h3>Servers</h3><table class="sheet"><tr><th>Server</th><th>Reach</th><th>Software</th></tr>${servers}</table></div>
        ${data}
      </div>
      <div class="panel"><h3>People</h3>${peopleSearch}<table class="sheet" id="people-tbl"><thead><tr><th>Person</th><th>Admin</th><th>Can log in to</th>
        ${hasTraits ? "<th>Spots phishing</th><th>Passwords</th>" : ""}${hasLoyalty ? "<th>Loyalty</th>" : ""}</tr></thead><tbody>${people}</tbody></table>
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
        ${backBar("Change difficulty")}
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
      wireBack(backToSetup);
      applyPeopleFilter();
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
        else if (S.settings.level === "realism") startSiem(api("begin"));
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
        if (S.settings.level === "realism") return startTerminal(api("begin"));
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
    const focus = m.focus;
    const edges = c.people.flatMap((p) => p.access.filter((id) => pos[id]).map((id) => {
      if (focus === "none") return "";
      if (focus && focus !== "all" && focus !== p.id && focus !== id) return "";
      const a = pos[p.id], b = pos[id];
      const hot = m.owned.has(p.id);
      return `<line class="edge ${hot ? "hot" : ""} ${focus && focus !== "all" ? "lit" : ""}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`;
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
        ${S.watch.has(person.id) ? `<text class="watch-star" x="${p.x - 17}" y="${p.y - 9}" text-anchor="middle">★</text>` : ""}
        <text class="label" x="${p.x}" y="${p.y + 26}" text-anchor="middle">${esc(person.name)}</text>
        <text class="sub" x="${p.x}" y="${p.y + 39}" text-anchor="middle">${esc(person.role.split(" ").slice(-1)[0])}</text></g>`;
    }).join("");
    return `<svg class="map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Network map of ${esc(c.name)}">
      <text class="zone" x="6" y="64">Internet</text><text class="zone" x="6" y="164">Inside</text><text class="zone" x="6" y="279">People</text>
      ${edges}${servers}${people}</svg>`;
  }

  function mapInner() {
    const c = S.start.company;
    const f = S.map.focus;
    const opt = (v, label) => `<option value="${esc(v)}" ${f === v ? "selected" : ""}>${esc(label)}</option>`;
    const current = f === "none" || f === "all" ? f
      : (c.people.find((p) => p.id === f)?.name || c.servers.find((s) => s.id === f)?.name || "");
    const control = c.people.length > 14
      ? `<div class="filterbar"><label>Connections for: <input class="map-focus" list="focus-list" value="${esc(current)}" placeholder="type a name or machine…" autocomplete="off"></label>
          <button class="chip ${f === "none" ? "on" : ""}" data-focus="none">none</button>
          <button class="chip ${f === "all" ? "on" : ""}" data-focus="all">all</button>
          <datalist id="focus-list">${c.servers.map((s) => `<option value="${esc(s.name)}">`).join("")}${c.people.map((p) => `<option value="${esc(p.name)}">`).join("")}</datalist></div>`
      : "";
    return `${control}${mapSvg()}
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
      const hasOdds = targets.some((x) => x.success !== undefined);
      if (hasOdds && (S.targetSort === undefined)) S.targetSort = "success";
      const reachable = targets.filter((x) => !x.disabled);
      if (hasOdds && S.targetSort) {
        const key = S.targetSort === "spotted" ? (x) => x.spotted : (x) => -x.success;
        reachable.sort((a, b) => key(a) - key(b));
      }
      const ordered = hasOdds ? reachable.concat(targets.filter((x) => x.disabled)) : targets;
      const bigList = targets.length > 30;  // too many to show at once — search to list them
      const controls = targets.length > 10
        ? `<div class="filterbar"><input class="row-filter" data-rows="#target-list .option"${bigList ? ' data-collapse="1"' : ""} placeholder="${bigList ? `Search ${targets.length} targets — name or role (e.g. admin)` : `Search ${targets.length} targets…`}"><span class="row-count muted">${bigList ? `${targets.length} targets — search to list them${S.watch.size ? " (★ future targets shown)" : ""}` : ""}</span>
            ${hasOdds ? `<span class="sorters">sort: <button class="chip ${S.targetSort === "success" ? "on" : ""}" data-sort="success">best chance</button><button class="chip ${S.targetSort === "spotted" ? "on" : ""}" data-sort="spotted">least spotted</button></span>` : ""}</div>`
        : "";
      side = `<div class="panel"><h3>${esc(attackName)}: pick a target</h3>${controls}<div class="options" id="target-list">
        ${ordered.map((x) => {
          const odds = x.success !== undefined ? `success ${pct(x.success)}<br>spotted ${pct(x.spotted)}<br>heat → ${pct(x.heat_after)}` : "";
          const kept = S.watch.has(x.id);
          return `<button class="option${kept ? " watched" : ""}" data-target="${x.id}" data-search="${esc(x.label.toLowerCase())}"${kept ? ' data-keep="1"' : ""} ${bigList && !kept ? "hidden" : ""} ${x.disabled ? "disabled" : ""}>
            <span></span><span><span class="name">${kept ? '<span class="star-mark">★</span>' : ""}${esc(x.label)}</span>
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
    app.querySelectorAll("[data-sort]").forEach((el) => el.addEventListener("click", () => { S.targetSort = el.dataset.sort; renderPlay(); }));
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
      const bigPick = options.length > 30;  // too many to show at once — search to list them
      const pickControls = options.length > 10
        ? `<div class="filterbar"><input class="row-filter" data-rows="#blue-pick .option"${bigPick ? ' data-collapse="1"' : ""} placeholder="${bigPick ? `Search ${options.length} — name or role (e.g. admin)` : `Search ${options.length}…`}"><span class="row-count muted">${bigPick ? `${options.length} — search to list them` : ""}</span></div>`
        : "";
      side = `<div class="panel"><h3>${esc(action.name)}: pick one</h3>${pickControls}<div class="options" id="blue-pick">
        ${options.map((o) => { const kept = S.watch.has(o.id); return `<button class="option${kept ? " watched" : ""}" data-blue-target="${esc(o.id)}" data-search="${esc((o.label + " " + (o.sub || "")).toLowerCase())}"${kept ? ' data-keep="1"' : ""} ${bigPick && !kept ? "hidden" : ""} ${o.disabled ? "disabled" : ""}><span></span><span><span class="name">${kept ? '<span class="star-mark">★</span>' : ""}${esc(o.label)}</span><span class="desc">${esc(o.disabled || o.sub)}</span></span><span></span></button>`; }).join("") || '<p class="muted">Nothing to pick yet.</p>'}
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

  const EXAMPLES = [
    ["Failed logins by address", "index=security EventCode=4625 | stats count by src_ip | sort -count"],
    ["Password spraying", "index=security EventCode=4625 | stats dc(user) as users by src_ip | where users > 5"],
    ["Successful logins from outside", "index=security EventCode=4624 src_ip!=10.* | table _time user src_ip dest"],
    ["Encoded PowerShell", 'index=sysmon "-enc" | table _time host user ParentImage CommandLine'],
    ["Mail with attachments", "index=mail attachment!=none | table _time sender recipient subject attachment verdict"],
    ["Web attacks", 'index=web status=500 OR useragent=sqlmap* | table _time clientip uri status'],
    ["Big uploads", "index=firewall bytes_out>10000000 | table _time src_ip dest_ip bytes_out"],
    ["Kerberos and replication", "index=security EventCode=4769 OR EventCode=4662 | table _time user EventCode ServiceName TicketEncryptionType src_ip"],
    ["Top blocked addresses", "index=firewall action=blocked | top src_ip"],
  ];
  const IP_RE = /^\d{1,3}(\.\d{1,3}){3}$/;

  function startSiem(state) {
    S.siem = { state, query: "index=security EventCode=4625 | stats count by src_ip | sort -count", result: null, feed: "", error: "" };
    runSearch();
  }

  function siemGauges(st) {
    const pips = (on, total, cls = "") => `<span class="pips ${cls}">${Array.from({ length: total }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</span>`;
    gauges.innerHTML = `<span class="gauge">Day <b>${st.day}/${st.max_days}</b> ${pips(st.day, st.max_days)}</span>
      <span class="gauge">Analyst time ${pips(st.time_left, st.time_total, "time")}</span>`;
    gauges.hidden = false;
  }

  function runSearch() {
    const res = api("realism_search", S.siem.query);
    if (res.error) { S.siem.error = res.error; S.siem.result = null; }
    else { S.siem.error = ""; S.siem.result = res; }
    renderSiem();
  }

  function cell(value) {
    if (value === null || value === undefined) return '<td class="muted">-</td>';
    const text = Array.isArray(value) ? value.join(", ") : String(value);
    if (IP_RE.test(text)) return `<td><button class="ip" data-ip="${esc(text)}">${esc(text)}</button></td>`;
    return `<td>${esc(text)}</td>`;
  }

  function resultsHtml() {
    const s = S.siem;
    if (s.error) return `<p class="why" style="margin:0">${esc(s.error)}</p>`;
    if (!s.result) return "";
    const r = s.result;
    const shown = r.rows.slice(0, 100);
    const count = `<p class="muted" style="margin:0 0 8px;font:12px var(--mono)">${r.total} result${r.total === 1 ? "" : "s"}${r.total > shown.length ? `, showing ${shown.length}` : ""}</p>`;
    if (!shown.length) return count + '<p class="muted">Nothing matched. Check the index name and the field values.</p>';
    if (r.columns) {
      return count + `<div class="results"><table class="sheet mono"><tr>${r.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>
        ${shown.map((row) => `<tr>${r.columns.map((c) => cell(row[c])).join("")}</tr>`).join("")}</table></div>`;
    }
    return count + `<div class="results raw">${shown.map((e) => `<div class="rawline"><span class="tag">${esc(e.index)} · ${esc(e.host)}</span>${esc(e._raw)}</div>`).join("")}</div>`;
  }

  function renderSiem() {
    const st = S.siem.state;
    siemGauges(st);
    const hosts = st.hosts.filter((h) => !h.isolated);
    const actions = st.finished
      ? `<div class="panel"><h3>${st.kicked_out ? "You kicked the attacker out." : "The attack is over."}</h3><div class="btn-row"><button class="btn" id="result">See the result</button></div></div>`
      : `<div class="panel"><h3>Respond</h3><p class="muted" style="margin:0 0 12px;font-size:13px">Searching is free. Each action below takes analyst time. ${st.phase === "day_end" ? "The attacker has stopped for today." : ""}</p>
        <form class="act" data-kind="block"><label>Block an address at the firewall</label><div class="row"><input id="block-ip" placeholder="203.0.113.7" autocomplete="off"><button class="btn">Block</button></div></form>
        <form class="act" data-kind="disable"><label>Disable an account</label><div class="row"><select id="disable-user">${st.accounts.map((a) => `<option value="${esc(a.username)}">${esc(a.username)} (${esc(a.name)})</option>`).join("")}</select><button class="btn">Disable</button></div></form>
        <form class="act" data-kind="isolate"><label>Isolate a machine</label><div class="row"><select id="isolate-host">${hosts.map((h) => `<option value="${esc(h.hostname)}">${esc(h.hostname)} (${esc(h.name)})</option>`).join("")}</select><button class="btn">Isolate</button></div></form>
        <div class="btn-row" style="margin-top:8px"><button class="btn ghost" id="wait">${st.phase === "day_end" ? "End the day" : "Let time pass"}</button><button class="btn ghost" id="giveup">End it now</button></div></div>`;
    show(`<section class="step siem">
      <div class="panel">
        <form id="search" class="searchbar"><input id="query" value="${esc(S.siem.query)}" spellcheck="false" autocomplete="off" aria-label="Search"><button class="btn">Search</button></form>
        <div class="chips">${EXAMPLES.map(([label], i) => `<button class="chip" data-example="${i}">${esc(label)}</button>`).join("")}</div>
        <p class="muted" style="margin:8px 0 0;font:12px var(--mono)">You can search: ${st.indexes.map((i) => `index=${esc(i)}`).join(" · ")}. Fields work like user=emily, src_ip=203.0.113.*, bytes_out>1000000.</p>
      </div>
      <div class="layout">
        <div class="panel"><h3>Results</h3>${resultsHtml()}</div>
        <div class="step">${actions}
          <div class="panel"><h3>What happened</h3><div class="log" id="log">${S.siem.feed || '<p class="muted" style="margin:0">Your SIEM is collecting. Somewhere in there is an attacker.</p>'}</div></div>
          <details class="panel"><summary><b>Inventory</b> <span class="muted">machines and accounts</span></summary>
            <table class="sheet mono"><tr><th>Host</th><th>Internal</th><th>Public</th><th>What</th></tr>
            ${st.hosts.map((h) => `<tr><td>${esc(h.hostname)}${h.isolated ? ' <span class="why">isolated</span>' : ""}</td><td>${esc(h.ip)}</td><td>${esc(h.public_ip || "-")}</td><td>${esc(h.name)}</td></tr>`).join("")}</table>
            <table class="sheet mono" style="margin-top:12px"><tr><th>User</th><th>Name</th><th>Workstation</th><th>IP</th></tr>
            ${st.accounts.map((a) => `<tr><td>${esc(a.username)}</td><td>${esc(a.name)}</td><td>${esc(a.workstation)}</td><td>${esc(a.ip)}</td></tr>`).join("")}</table>
            ${st.blocked.length ? `<p class="muted" style="font:12px var(--mono)">Blocked: ${st.blocked.map(esc).join(", ")}</p>` : ""}
          </details>
        </div>
      </div></section>`);
    document.getElementById("search").addEventListener("submit", (e) => { e.preventDefault(); S.siem.query = document.getElementById("query").value; runSearch(); });
    app.querySelectorAll("[data-example]").forEach((el) => el.addEventListener("click", () => { S.siem.query = EXAMPLES[Number(el.dataset.example)][1]; runSearch(); }));
    app.querySelectorAll("button.ip").forEach((el) => el.addEventListener("click", () => { const box = document.getElementById("block-ip"); if (box) { box.value = el.dataset.ip; box.focus(); } }));
    app.querySelectorAll("form.act").forEach((form) => form.addEventListener("submit", (e) => {
      e.preventDefault();
      const kind = form.dataset.kind;
      const value = kind === "block" ? document.getElementById("block-ip").value : kind === "disable" ? document.getElementById("disable-user").value : document.getElementById("isolate-host").value;
      siemAct(kind, value);
    }));
    document.getElementById("wait")?.addEventListener("click", () => { siemTake(api("realism_wait")); renderSiem(); });
    document.getElementById("giveup")?.addEventListener("click", () => renderFinal(api("give_up")));
    document.getElementById("result")?.addEventListener("click", () => renderFinal(api("finish")));
  }

  function siemFeed(html) {
    S.siem.feed = html + S.siem.feed;
  }

  function siemTake(state) {
    for (const event of state.events) siemFeed(blueFeed(event));
    S.siem.state = state;
  }

  function siemAct(kind, value) {
    if (!value || !value.trim()) return;
    const res = api("realism_act", kind, value);
    if (res.error) { siemFeed(`<div class="entry"><span class="why">${esc(res.error)}</span></div>`); return renderSiem(); }
    const names = { block: "Block", disable: "Disable", isolate: "Isolate" };
    siemFeed(`<div class="entry"><span class="stamp blue">${names[kind]}</span><span class="what">${esc(value)}</span><br><span class="detail">${esc(res.text)}</span></div>`);
    siemTake(res.state);
    if (S.siem.result) runSearch(); else renderSiem();
  }

  function startTerminal(reply) {
    S.term = { lines: [], history: [], pointer: 0, state: reply };
    termPush(reply.lines);
    renderTerminal();
  }

  function termPush(lines, prompt) {
    if (prompt) S.term.lines.push({ kind: "cmd", text: prompt });
    for (const line of lines) {
      const kind = line.startsWith("! ") ? "alert" : line.startsWith("  ") || line.startsWith("Your footprint") ? "trace" : "out";
      S.term.lines.push({ kind, text: line });
    }
    S.term.lines = S.term.lines.slice(-400);
  }

  function renderTerminal() {
    const st = S.term.state;
    const pips = (on, total, cls = "") => `<span class="pips ${cls}">${Array.from({ length: total }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</span>`;
    gauges.innerHTML = `<span class="gauge">Day <b>${st.day}/${st.max_days}</b> ${pips(st.day, st.max_days)}</span><span class="gauge">Moves ${pips(st.moves_left, st.moves_per_day, "moves")}</span>`;
    gauges.hidden = false;
    show(`<section class="step">
      <div class="panel terminal" id="term">
        <div class="screen" id="screen">${S.term.lines.map((l) => `<div class="${l.kind}">${l.kind === "cmd" ? '<span class="prompt">red@bastion:~$</span> ' : ""}${esc(l.text)}</div>`).join("")}</div>
        ${st.finished ? "" : `<form id="cmd" class="cmdline"><span class="prompt">red@bastion:~$</span><input id="cmd-input" autocomplete="off" spellcheck="false" aria-label="Command"></form>`}
      </div>
      ${st.finished ? '<div class="btn-row"><button class="btn" id="result">See the result</button></div>' : '<p class="muted" style="margin:0;font-size:13px">Every move leaves traces in their logs. A computer analyst is reading them.</p>'}
    </section>`);
    const screen = document.getElementById("screen");
    screen.scrollTop = screen.scrollHeight;
    const input = document.getElementById("cmd-input");
    if (input) {
      input.focus();
      input.addEventListener("keydown", (e) => {
        if (e.key === "ArrowUp" && S.term.history.length) { S.term.pointer = Math.max(0, S.term.pointer - 1); input.value = S.term.history[S.term.pointer]; e.preventDefault(); }
        if (e.key === "ArrowDown" && S.term.history.length) { S.term.pointer = Math.min(S.term.history.length, S.term.pointer + 1); input.value = S.term.history[S.term.pointer] || ""; e.preventDefault(); }
      });
      document.getElementById("cmd").addEventListener("submit", (e) => {
        e.preventDefault();
        const command = input.value.trim();
        if (!command) return;
        S.term.history.push(command);
        S.term.pointer = S.term.history.length;
        if (command === "clear") { S.term.lines = []; return renderTerminal(); }
        const reply = api("terminal", command);
        S.term.state = reply;
        termPush(reply.lines, command);
        renderTerminal();
      });
    }
    document.getElementById("result")?.addEventListener("click", () => renderFinal(api("finish")));
  }

  function renderFinal(final) {
    setGauges(null);
    const profile = JSON.parse(final.profile_json);
    store.set(PROFILE_KEY, profile);
    saveProgress(profile);
    if (final.realism && final.realism_side && final.score && S.user && S.dice && S.dice.game) {
      const seconds = S.startedAt ? Math.round((Date.now() - S.startedAt) / 1000) : 0;
      fetch("api/score.php", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Bastion": "1" },
        body: JSON.stringify({ side: final.realism_side, points: final.score.total, seconds, game: S.dice.game }) }).catch(() => {});
    }
    S.rec = false;
    S.dice = null;
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
      <div class="btn-row"><button class="btn" id="again">Play again</button><button class="btn ghost" id="menu">Main menu</button>${final.realism ? '<button class="btn ghost" id="board">Leaderboard</button>' : ""}</div>
    </section>`);
    document.getElementById("again").addEventListener("click", startGame);
    document.getElementById("menu").addEventListener("click", renderMenu);
    document.getElementById("board")?.addEventListener("click", renderLeaderboard);
  }

  async function renderLeaderboard() {
    setGauges(null);
    show('<section class="step"><p class="eyebrow">Realism</p><h1>Leaderboard.</h1><p class="muted">Loading…</p></section>');
    let data;
    try {
      const r = await fetch("api/leaderboard.php", { credentials: "same-origin", cache: "no-store" });
      data = await r.json();
    } catch { data = { error: "The leaderboard is not available right now." }; }
    const fmtTime = (s) => s > 0 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "—";
    const table = (side) => {
      const rows = (data.board && data.board[side]) || [];
      const body = rows.length
        ? rows.map((e, i) => `<tr class="${data.me && data.me.login === e.login ? "mine" : ""}"><td class="num">${i + 1}</td><td>${e.avatar ? `<img src="${esc(e.avatar)}" alt="">` : ""}${esc(e.login)}</td><td class="num">${e.score}</td><td class="num">${fmtTime(e.secs)}</td></tr>`).join("")
        : '<tr><td colspan="4" class="muted">No scores yet. Be the first.</td></tr>';
      const mine = data.me && data.me[side] ? `<p class="profile-line">Your best: ${data.me[side]} · ${fmtTime(data.me[side + "_secs"])}</p>` : "";
      return `<div class="panel"><h3 class="${side}">${side === "red" ? "Red" : "Blue"} Team</h3>
        <table class="sheet board-table"><thead><tr><th class="num">#</th><th>Player</th><th class="num">Score</th><th class="num">Time</th></tr></thead><tbody>${body}</tbody></table>${mine}</div>`;
    };
    show(`<section class="step">
      ${backBar("Home")}
      <div><p class="eyebrow">Realism · best score per player</p><h1>Leaderboard.</h1>
      ${S.user ? "" : '<p class="muted">Sign in with GitHub to appear here.</p>'}</div>
      ${data.error ? `<p class="why">${esc(data.error)}</p>` : `<div class="brief-grid">${table("red")}${table("blue")}</div>`}
    </section>`);
    wireBack(renderHome);
  }

  boot();
})();
