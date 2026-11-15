(() => {
  "use strict";
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s) => document.querySelector(s);
  const sleep = (ms) => new Promise((r) => setTimeout(r, reduce ? 0 : ms));
  const NS = "http://www.w3.org/2000/svg";
  const O = { mode: "menu", side: "red", minutes: 9 * 60, target: 9 * 60, day: 0, night: false, rain: false, heat: 0, sound: false, music: false, zoomed: false, company: "" };
  const FULL = [0, 0, 1600, 900], PORTRAIT = [300, 60, 1000, 820], SCREEN = [684, 384, 272, 168];
  let svg, vb = FULL.slice();

  const mix = (a, b, t) => { const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); const A = p(a), B = p(b);
    return "#" + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, "0")).join(""); };
  const SKY = [[0, "#070a1c", "#141a3a"], [5, "#070a1c", "#141a3a"], [6.2, "#3b2f6b", "#ff9a7a"], [7.5, "#7fb2ff", "#ffd7a8"],
    [16, "#7fb2ff", "#ffe4c4"], [18, "#ff8a5c", "#ffcf8a"], [19.3, "#3b2f6b", "#c46a7a"], [20.5, "#0b1030", "#1d2350"], [24, "#070a1c", "#141a3a"]];
  const skyAt = (h) => { for (let i = 0; i < SKY.length - 1; i++) { const [h0, t0, b0] = SKY[i], [h1, t1, b1] = SKY[i + 1];
    if (h >= h0 && h <= h1) { const k = (h - h0) / (h1 - h0); return [mix(t0, t1, k), mix(b0, b1, k)]; } } return [SKY[0][1], SKY[0][2]]; };
  const arc = (t) => [1020 + t * 400, 420 - Math.sin(t * Math.PI) * 240];

  /* audio */
  let ac = null, noiseBuf = null, rainNode = null, musicTimer = null, step = 0;
  const audio = () => (ac = ac || new (window.AudioContext || window.webkitAudioContext)());
  function beep(f = 660, d = .06, type = "square", vol = .04) {
    if (!O.sound) return; const a = audio(), o = a.createOscillator(), g = a.createGain();
    o.type = type; o.frequency.value = f; g.gain.value = vol; o.connect(g); g.connect(a.destination);
    g.gain.exponentialRampToValueAtTime(.0001, a.currentTime + d); o.start(); o.stop(a.currentTime + d);
  }
  function noise() { const a = audio(); if (noiseBuf) return noiseBuf; noiseBuf = a.createBuffer(1, a.sampleRate * 2, a.sampleRate);
    const d = noiseBuf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1; return noiseBuf; }
  function ambience() {
    const want = O.sound && O.night && O.rain;
    if (want && !rainNode) { const a = audio(), src = a.createBufferSource(), f = a.createBiquadFilter(), g = a.createGain();
      src.buffer = noise(); src.loop = true; f.type = "lowpass"; f.frequency.value = 1100; g.gain.value = 0; g.gain.linearRampToValueAtTime(.06, a.currentTime + 2);
      src.connect(f); f.connect(g); g.connect(a.destination); src.start(); rainNode = { src, g }; }
    else if (!want && rainNode) { const a = audio(), n = rainNode; rainNode = null; n.g.gain.linearRampToValueAtTime(0, a.currentTime + 1.5); setTimeout(() => n.src.stop(), 1600); }
  }
  function music() {
    clearInterval(musicTimer); musicTimer = null; if (!O.music) return;
    const a = audio(), out = a.createGain(); out.gain.value = .05; out.connect(a.destination);
    const lp = a.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 900; lp.connect(out);
    const note = (f, t, len, type, vol = 1) => { const o = a.createOscillator(), g = a.createGain(); o.type = type; o.frequency.value = f;
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol, t + .04); g.gain.exponentialRampToValueAtTime(.0001, t + len); o.connect(g); g.connect(lp); o.start(t); o.stop(t + len + .05); };
    musicTimer = setInterval(() => {
      const t = a.currentTime + .05;
      if (O.side === "red") { const seq = [110, 130.8, 164.8, 220, 196, 164.8, 130.8, 146.8]; note(seq[step % 8] * 2, t, .35, "sawtooth", .5); if (step % 8 === 0) note(55, t, 2.2, "triangle", .9); }
      else { const ch = [[261.6, 329.6, 392, 493.9], [220, 261.6, 329.6, 392], [174.6, 220, 261.6, 329.6], [196, 246.9, 293.7, 349.2]];
        if (step % 8 === 0) ch[(step / 8) % 4].forEach((f) => note(f, t, 3.6, "sine", .35)); if (step % 2 === 0) note(ch[Math.floor(step / 8) % 4][(step / 2) % 4] * 2, t, .5, "triangle", .2); }
      step++;
    }, 280);
  }

  /* drawing */
  function paintTime() {
    const h = (O.minutes / 60) % 24, [top, bottom] = skyAt(h);
    $("#sky1").setAttribute("stop-color", top); $("#sky2").setAttribute("stop-color", bottom);
    const night = h >= 20.5 || h < 5 ? 1 : h >= 18 ? (h - 18) / 2.5 : h < 7 ? 1 - (h - 5) / 2 : 0;
    const ts = (h - 6) / 14, up = ts > -0.05 && ts < 1.05, [sx, sy] = arc(Math.min(1, Math.max(0, ts)));
    ["#sun", "#sunglow"].forEach((id) => { $(id).setAttribute("cx", sx.toFixed(1)); $(id).setAttribute("cy", sy.toFixed(1)); $(id).style.opacity = up ? "" : 0; });
    $("#sun").setAttribute("fill", h > 17 || h < 7.5 ? "#ffb070" : "#fff3c4");
    const tm = ((h - 19 + 24) % 24) / 12, [mx, my] = arc(Math.min(1, tm));
    $("#moon").setAttribute("transform", `translate(${mx.toFixed(1)} ${my.toFixed(1)})`);
    $("#moon").setAttribute("opacity", tm <= 1 ? Math.min(1, night * 1.4).toFixed(2) : 0);
    $("#stars").setAttribute("opacity", (night * .9).toFixed(2));
    document.querySelectorAll("#lights rect").forEach((r, i) => { r.style.opacity = Math.min(1, night * 1.5) * (i % 3 ? 1 : .4); });
    $("#rain").setAttribute("opacity", O.rain && night > .5 ? 1 : 0);
    $("#dark").setAttribute("opacity", (night * (O.side === "red" ? .25 : .45)).toFixed(2));
    const d = Math.floor(O.minutes) % 1440, hh = Math.floor(d / 60), mm = d % 60;
    $("#mhand").setAttribute("transform", `rotate(${mm * 6})`); $("#hhand").setAttribute("transform", `rotate(${(hh % 12) * 30 + mm / 2})`);
    const time = `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
    document.querySelectorAll(".clockchip").forEach((c) => { c.classList.toggle("night", night > .5); c.querySelector("i").textContent = night > .5 ? "☾" : "☀";
      c.querySelector("small").textContent = `${O.night ? "Night" : "Day"} ${Math.max(1, O.day)}`; c.querySelector("b").textContent = time; });
  }
  function decorate() {
    const lights = $("#lights");
    [[1010, 300, 60, 130], [1075, 260, 48, 170], [1128, 320, 70, 110], [1205, 240, 56, 190], [1266, 300, 64, 130], [1335, 275, 45, 155], [1385, 330, 50, 100]].forEach(([bx, by, bw, bh]) => {
      for (let y = by + 10; y < by + bh - 12; y += 18) for (let x = bx + 8; x < bx + bw - 10; x += 14) {
        if (Math.random() < .45) continue; const r = document.createElementNS(NS, "rect");
        r.setAttribute("x", x); r.setAttribute("y", y); r.setAttribute("width", 6); r.setAttribute("height", 8); r.setAttribute("class", "lit"); r.style.opacity = 0; lights.appendChild(r);
      } });
    const rain = $("#rain");
    for (let i = 0; i < 40; i++) { const l = document.createElementNS(NS, "line"), x = 1010 + Math.random() * 440, y = 100 + Math.random() * 300;
      l.setAttribute("x1", x); l.setAttribute("y1", y); l.setAttribute("x2", x - 6); l.setAttribute("y2", y + 22); l.style.animationDelay = (-Math.random()).toFixed(2) + "s"; rain.appendChild(l); }
    const stars = $("#stars");
    for (let i = 0; i < 40; i++) stars.insertAdjacentHTML("beforeend", `<circle cx="${1012 + Math.random() * 416}" cy="${132 + Math.random() * 150}" r="${(Math.random() * 1.4 + .4).toFixed(1)}" opacity="${(Math.random() * .6 + .4).toFixed(2)}"/>`);
    const rack = $("#rack");
    for (let r = 0; r < 8; r++) { const y = 20 + r * 46;
      rack.insertAdjacentHTML("beforeend", `<rect x="14" y="${y}" width="152" height="36" rx="3" fill="#1c1c24"/><rect x="24" y="${y + 14}" width="60" height="6" rx="3" fill="#2a2a33"/>`);
      for (let k = 0; k < 4; k++) rack.insertAdjacentHTML("beforeend", `<circle class="led" cx="${110 + k * 14}" cy="${y + 18}" r="3.5" fill="${["#3ddc84", "#08f7fe", "#ff2e63", "#3ddc84"][(r + k) % 4]}" style="animation-delay:${(Math.random() * 1.6).toFixed(2)}s;animation-duration:${(0.8 + Math.random() * 1.6).toFixed(2)}s"/>`); }
  }
  function paintSide() {
    document.body.dataset.side = O.side;
    const g = $("#minisc"); g.innerHTML = "";
    const lines = O.side === "red" ? ["> recon", "> exploit", "> escalate", "> exfil", "> sleep"] : ["09:12 login ok", "09:14 dns query", "09:15 FAILED login", "09:16 mail in", "09:17 port probe"];
    lines.concat(lines).forEach((t, i) => { const x = document.createElementNS(NS, "text"); x.setAttribute("x", 694); x.setAttribute("y", 404 + i * 18); x.setAttribute("class", "code-line");
      x.setAttribute("fill", O.side === "red" ? "#3ddc84" : (/FAILED|probe/.test(t) ? "#ff6b81" : "#9cc8ff")); x.setAttribute("font-family", "JetBrains Mono"); x.setAttribute("font-size", "12"); x.textContent = t; g.appendChild(x); });
    const notes = $("#notes"); notes.innerHTML = "";
    const items = O.side === "red" ? ["Scout", "Get in", "Climb"] : ["Logs", "Block", "Cut off"], colors = O.side === "red" ? ["#ffe36e", "#ff9fb2", "#a6f0c6"] : ["#ffe36e", "#a8d4ff", "#c8f7a6"];
    items.forEach((t, i) => notes.insertAdjacentHTML("beforeend", `<g transform="translate(${140 + i * 115} ${200 + (i % 2) * 40}) rotate(${(i - 1) * 4})"><rect width="96" height="86" fill="${colors[i]}"/><text x="10" y="30" font-family="Space Grotesk" font-weight="700" font-size="17" fill="#222">${t}</text></g>`));
    const tv = $("#tvName"); if (tv) tv.textContent = `SOC · ${(O.company || "").toUpperCase()}`;
  }

  /* camera */
  const restBox = () => (innerHeight > innerWidth ? PORTRAIT : FULL);
  function fit() { if (O.zoomed) return; svg.setAttribute("preserveAspectRatio", innerHeight > innerWidth ? "xMidYMid meet" : "xMidYMid slice"); vb = restBox().slice(); svg.setAttribute("viewBox", vb.join(" ")); }
  function animateBox(to, ms) {
    return new Promise((done) => {
      if (reduce) { vb = to.slice(); svg.setAttribute("viewBox", vb.join(" ")); return done(); }
      const from = vb.slice(), t0 = performance.now(), ease = (t) => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      (function stepF(now) { const t = Math.min(1, (now - t0) / ms), e = ease(t); vb = from.map((v, i) => v + (to[i] - v) * e); svg.setAttribute("viewBox", vb.join(" "));
        t < 1 ? requestAnimationFrame(stepF) : done(); })(t0);
    });
  }
  function setMode(mode) {
    O.mode = mode; document.body.classList.remove("of-menu", "of-room", "of-laptop", "of-home"); if (mode !== "home" && $("#of-home")) $("#of-home").innerHTML = ""; document.body.classList.add("of-" + mode);
  }
  async function openLaptop() {
    if (O.mode !== "room" || O.night || O.zoomed) return;
    O.zoomed = true; beep(520, .1, "sine"); await animateBox(SCREEN, 1000); setMode("laptop"); beep(780, .12, "sine");
  }
  async function closeLaptop() {
    if (O.mode !== "laptop") return;
    setMode("room"); await animateBox(restBox(), 800); O.zoomed = false;
  }

  /* the game tells us what happens */
  let tween = null;
  function runClock() {
    if (tween) return;
    const tick = () => { const diff = O.target - O.minutes; if (Math.abs(diff) < .5) { O.minutes = O.target; paintTime(); tween = null; return; }
      O.minutes += diff * .06; paintTime(); tween = requestAnimationFrame(tick); };
    tween = requestAnimationFrame(tick);
  }
  let nightSkip = null;
  async function playNight(nextDay) {
    if (tween) { cancelAnimationFrame(tween); tween = null; }
    O.night = true; O.rain = Math.random() < .5; ambience();
    const wasLaptop = O.mode === "laptop"; if (wasLaptop) await closeLaptop();
    const card = $("#of-night"); card.querySelector("b").textContent = `Night ${nextDay - 1}`; card.classList.add("show");
    $("#of-skip").hidden = false;
    const start = performance.now(), total = reduce ? 1500 : 60000, from = 18 * 60, to = 33 * 60;
    await new Promise((done) => {
      nightSkip = done;
      (function nf(now) { if (!nightSkip) return; const t = Math.min(1, (now - start) / total); O.minutes = from + (to - from) * t; paintTime();
        if (t > .04) card.classList.remove("show"); if (t < 1 && nightSkip) requestAnimationFrame(nf); else done(); })(start);
    });
    nightSkip = null; $("#of-skip").hidden = true; card.classList.remove("show");
    O.night = false; O.day = nextDay; O.minutes = O.target = 9 * 60; paintTime(); ambience();
    const later = O.pending; O.pending = null; if (later && later.day === nextDay) turn(later);
    toast(`Day ${nextDay}`, O.side === "blue" ? "Morning. See what came in overnight." : "A new day. Coffee is ready.");
    if (wasLaptop) { await sleep(600); openLaptop(); }
  }
  function toast(title, text) {
    const t = $("#of-toast"); t.innerHTML = `<b>${title}</b>${text}`; t.classList.add("show"); beep(990, .08, "triangle");
    clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 3200);
  }
  let starting = false;
  async function turn(t, side, company) {
    if (side) O.side = side; if (company) O.company = company;
    if (!t) {
      if (O.night) return;
      if (O.mode !== "menu") { if (O.zoomed) { O.zoomed = false; vb = restBox().slice(); svg.setAttribute("viewBox", vb.join(" ")); } setMode("menu"); }
      O.day = 0; O.heat = 0; O.progStart = null; document.body.style.setProperty("--of-heat", 0);
      return;
    }
    O.heat = t.heat || 0; document.body.style.setProperty("--of-heat", O.heat.toFixed(2));
    if (O.night) { O.pending = t; return; }
    if (O.mode === "menu" && !starting) {
      starting = true; O.day = t.day; O.minutes = O.target = 9 * 60; O.progStart = t.progress; paintSide(); paintTime(); setMode("room");
      await sleep(1200); starting = false; openLaptop(); return;
    }
    if (t.day > O.day && O.day > 0) { O.progStart = t.progress; return playNight(t.day); }
    O.day = t.day;
    if (t.progress !== undefined) {
      if (O.progStart == null) O.progStart = t.progress;
      O.target = Math.max(O.target, 9 * 60 + Math.min(510, (t.moves_per_day - t.moves_left) * 50 + (t.progress - O.progStart) * 25));
    } else if (t.moves_per_day && t.moves_left !== undefined) O.target = 9 * 60 + (t.moves_per_day - t.moves_left) * (510 / t.moves_per_day);
    else O.target = Math.min(17.5 * 60, O.target + 30);
    runClock();
  }

  /* phone rings now and then while you are in the room */
  const CALLS = { red: ["Your contact: “Their IT guy is on holiday this week. Move fast.”", "Unknown number: “We know what you are doing.” Click."],
    blue: ["CEO: “Are we safe? I need a short report by 17:00.”", "Maria from finance: “I got a strange invoice email. Should I open it?”"] };
  function ring() { if (O.mode === "room" && !O.night) { $("#phone").classList.add("ring"); if (O.sound) [0, 300, 600].forEach((d) => setTimeout(() => beep(1200, .12, "sine", .05), d)); } }

  async function boot() {
    const res = await fetch("office/scene.svg?v=" + (window.OFFICE_V || "1"));
    document.body.insertAdjacentHTML("afterbegin", await res.text());
    svg = $("#scene"); document.body.classList.add("of-on");
    document.body.insertAdjacentHTML("beforeend", `
      <div class="of-hud"><span></span><span class="of-right"><button class="of-pill" id="of-sound">Sound off</button><button class="of-pill" id="of-music">Music off</button>
        <span class="clockchip"><i>☀</i><small>Day 1</small><b>09:00</b></span></span></div>
      <div class="of-hint" id="of-hint">Click the laptop</div>
      <div class="of-night" id="of-night"><div><b>Night</b><small>the office goes quiet</small></div></div>
      <button class="of-pill of-skip" id="of-skip" hidden>Skip night</button>
      <div class="of-toast" id="of-toast"></div><div class="of-vignette"></div><div class="of-hm" id="of-home"></div><div class="of-flash" id="of-flash"></div>`);
    const right = document.querySelector(".topbar-right");
    if (right) right.insertAdjacentHTML("afterbegin", `<span class="clockchip inos of-only"><i>☀</i><small>Day 1</small><b>09:00</b></span><button class="of-close of-only" id="of-close">Close laptop</button>`);
    decorate(); paintSide(); paintTime(); fit(); setMode("menu"); watchGame();
    if (pendingMenu) { menu(...pendingMenu); pendingMenu = null; }
    addEventListener("resize", fit);
    $("#laptop").addEventListener("click", openLaptop);
    $("#laptop").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") openLaptop(); });
    $("#of-close").addEventListener("click", closeLaptop);
    $("#of-skip").addEventListener("click", () => nightSkip && nightSkip());
    $("#of-sound").addEventListener("click", (e) => { O.sound = !O.sound; e.target.textContent = O.sound ? "Sound on" : "Sound off"; e.target.classList.toggle("on", O.sound); beep(880); ambience(); });
    $("#of-music").addEventListener("click", (e) => { O.music = !O.music; e.target.textContent = O.music ? "Music on" : "Music off"; e.target.classList.toggle("on", O.music); music(); });
    $("#phone").addEventListener("click", () => { if (!$("#phone").classList.contains("ring")) return; $("#phone").classList.remove("ring");
      const l = CALLS[O.side]; toast("Incoming call", l[Math.floor(Math.random() * l.length)]); });
    setInterval(() => { if (!$("#phone").classList.contains("ring") && Math.random() < .4) ring(); }, 20000);
  }


  /* main menu over the office */
  const TIER_DAYS = { small: "Small", medium: "Medium", large: "Large", huge: "Huge" };
  let B = null, M = null, pick = { side: null, company: null, level: null };
  function menu(data, bridge) {
    M = data; B = bridge;
    pick = { side: bridge.settings.side || "red", company: bridge.settings.company || null, level: bridge.settings.level || "easy" };
    if (pick.side !== "random") { O.side = pick.side; paintSide(); }
    setMode("home"); homeMain();
    if (bridge.notice) toast("Welcome", bridge.notice);
  }
  function homeMain() {
    const p = M.profile || {}, anyQuest = (M.quests || []).some((q) => q.known);
    const item = (id, ico, name, sub, locked) => `<button class="hm-item ${locked ? "locked" : ""}" ${locked ? "disabled" : `data-go="${id}"`}>
      <span class="hm-ico">${ico}</span><span class="hm-txt"><b>${name}</b><small>${sub}</small></span><span class="hm-arrow">›</span></button>`;
    $("#of-home").innerHTML = `<div class="hm-wrap">
      <h1 class="hm-logo">BASTION</h1>
      <nav class="hm-list">
        ${item("play", "▶", "Play", "Pick a side, a target and a difficulty")}
        ${item("tutorial", "✎", "Tutorial", "Red, Blue and WAF tracks")}
        ${item("shop", "◈", "Shop", "New attacks, defenses and quests")}
        ${item("achievements", "★", "Achievements", "Few will see them all")}
        ${M.realism ? item("leaderboards", "☰", "Leaderboard", "The best players") : item("", "🔒", "Classified", "Opens when you find what is hidden", true)}
        ${item("quests", "▤", "Classified", anyQuest ? "Hidden objectives in play" : "Some files are not on any inventory", false)}
      </nav>
      <div class="hm-foot">${B.user ? `<span class="hm-user">Signed in as <b>${B.user.login}</b> · ${p.wins || 0} wins</span>` : `<span class="hm-user">Playing as a guest</span>`}
        <button class="of-pill" data-snd>${O.sound ? "Sound on" : "Sound off"}</button><button class="of-pill" data-mus>${O.music ? "Music on" : "Music off"}</button></div>
    </div>`;
    wireHome();
    $("#of-home").querySelectorAll("[data-go]").forEach((b, i) => {
      b.style.animationDelay = `${80 + i * 60}ms`;
      b.addEventListener("mouseenter", () => beep(500 + i * 40, .03, "triangle", .02));
      b.addEventListener("click", () => { beep(720, .06, "triangle"); if (b.dataset.go === "play") homePlay(); else { leaveHome(); B.nav(b.dataset.go); } });
    });
  }
  function wireHome() {
    $("#of-home").querySelector("[data-snd]")?.addEventListener("click", (e) => { $("#of-sound").click(); e.target.textContent = O.sound ? "Sound on" : "Sound off"; e.target.classList.toggle("on", O.sound); });
    $("#of-home").querySelector("[data-mus]")?.addEventListener("click", (e) => { $("#of-music").click(); e.target.textContent = O.music ? "Music on" : "Music off"; e.target.classList.toggle("on", O.music); });
  }
  function homePlay(still) {
    const companyOpen = (c) => !c.classified && !M.locks.easy[c.id];
    const levelOpen = (l) => l === "realism" ? (M.realism && pick.company && !M.locks.realism[pick.company]) : (!M.levels[l] && !(pick.company && M.locks[l][pick.company]));
    if (pick.company && !(M.companies.find((c) => c.id === pick.company) && companyOpen(M.companies.find((c) => c.id === pick.company)))) pick.company = null;
    if (!pick.company) pick.company = (M.companies.find(companyOpen) || {}).id || null;
    if (pick.level && !levelOpen(pick.level)) pick.level = "easy";
    const card = (group, id, html, on, locked) => `<button class="hm-card ${on ? "on" : ""} ${locked ? "locked" : ""} ${group === "side" ? "side-" + id : ""}" ${locked ? "disabled" : `data-g="${group}" data-v="${id}"`}>${html}</button>`;
    const sides = B.sides.map((s) => card("side", s.id, `<span class="hm-big">${{ red: "🥷", blue: "🛡️", random: "🎲" }[s.id] || ""}</span><b>${s.name}</b><small>${s.text}</small>`, pick.side === s.id)).join("");
    const maps = M.companies.map((c) => c.classified
      ? card("company", c.id, `<b>████████</b><small>Classified</small><em>Locked</em>`, false, true)
      : card("company", c.id, `<b>${c.name}</b><small>${c.description || ""}</small><em>${TIER_DAYS[c.tier] || c.tier} · ${c.people} people</em>`, pick.company === c.id, !companyOpen(c))).join("");
    const levels = [...B.levels, B.realism].map((l) => {
      const open = levelOpen(l.id);
      return card("level", l.id, `<b>${l.id === "realism" && !open ? "████████" : l.name}</b><small>${open ? l.text : (l.id === "realism" ? "Classified" : "Locked")}</small>`, pick.level === l.id, !open);
    }).join("");
    $("#of-home").innerHTML = `<div class="hm-wrap play ${still ? "still" : ""}">
      <div class="hm-top"><button class="hm-back" data-back>‹ Back</button><h2>New game</h2></div>
      <section><h3>Side</h3><div class="hm-grid">${sides}</div></section>
      <section><h3>Target</h3><div class="hm-grid">${maps}</div></section>
      <section><h3>Difficulty</h3><div class="hm-grid">${levels}</div></section>
      <div class="hm-go"><button class="hm-start" data-start ${pick.side && pick.company && pick.level ? "" : "disabled"}>Start</button></div>
    </div>`;
    $("#of-home").querySelector("[data-back]").addEventListener("click", () => { beep(400, .05, "triangle"); homeMain(); });
    $("#of-home").querySelectorAll("[data-g]").forEach((b, i) => {
      b.style.animationDelay = `${i * 40}ms`;
      b.addEventListener("click", () => {
        pick[b.dataset.g] = b.dataset.v; beep(700, .05, "triangle");
        if (b.dataset.g === "side" && b.dataset.v !== "random") { O.side = b.dataset.v; paintSide(); }
        const y = $("#of-home").scrollTop; homePlay(true); $("#of-home").scrollTop = y;
      });
    });
    $("#of-home").querySelector("[data-start]").addEventListener("click", () => {
      beep(520, .1, "triangle"); setTimeout(() => beep(780, .14, "triangle"), 120);
      leaveHome(); B.start(pick.side, pick.company, pick.level);
    });
  }
  function leaveHome() { $("#of-home").innerHTML = ""; setMode("menu"); }

  /* the game's own screens come alive */
  const seen = new Set();
  function shakeApp() { const a = $("#app"); a.classList.remove("of-shake"); void a.offsetWidth; a.classList.add("of-shake"); }
  function flash(color) { const f = $("#of-flash"); f.style.background = color; f.classList.remove("go"); void f.offsetWidth; f.classList.add("go"); }
  function alarm() {
    if (!O.sound) return; const a = audio(), o = a.createOscillator(), g = a.createGain(); o.type = "square"; g.gain.value = .03;
    for (let i = 0; i < 6; i++) o.frequency.setValueAtTime(i % 2 ? 620 : 880, a.currentTime + i * .16);
    g.gain.setValueAtTime(.03, a.currentTime + .9); g.gain.exponentialRampToValueAtTime(.0001, a.currentTime + 1); o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + 1.02);
  }
  async function roll(entry) {
    const stamp = entry.querySelector(".stamp.land"), det = [...entry.querySelectorAll(".detail")].find((d) => /chance was/.test(d.textContent));
    if (!stamp || !det) return;
    const chance = parseInt(det.textContent.match(/(\d+)%/)?.[1] || "0", 10) / 100, ok = stamp.classList.contains("success");
    const land = ok ? Math.random() * chance * .98 : chance + Math.random() * (1 - chance) * .98;
    stamp.style.visibility = "hidden";
    const meter = document.createElement("span"); meter.className = "of-roll";
    meter.innerHTML = `<span class="trk"><span class="zone" style="width:${chance * 100}%"></span><span class="ndl"></span></span><b>…</b>`;
    stamp.before(meter);
    const ndl = meter.querySelector(".ndl"), out = meter.querySelector("b"), frames = reduce ? 1 : 12;
    document.body.classList.add("of-rolling");
    for (let i = 1; i <= frames; i++) {
      const v = i === frames ? land : Math.random(); ndl.style.left = `calc(${(v * 100).toFixed(1)}% - 1px)`; out.textContent = Math.round(v * 100) + "%";
      beep(400 + v * 600, .02, "square", .015); await sleep(22 + i * 3);
    }
    document.body.classList.remove("of-rolling");
    await sleep(120); stamp.style.visibility = ""; stamp.classList.remove("land"); void stamp.offsetWidth; stamp.classList.add("land");
  }
  async function react(entry) {
    await roll(entry);
    const st = entry.querySelector(".stamp");
    if (!st) return;
    if (st.classList.contains("success")) { flash("rgba(61,220,132,.25)"); beep(660, .08, "triangle"); setTimeout(() => beep(990, .12, "triangle"), 90); }
    else if (st.classList.contains("blocked")) { shakeApp(); beep(140, .18, "sawtooth", .05); }
    if (entry.querySelector(".stamp.spotted, .stamp.caught, .stamp.detected")) { await sleep(250); flash("rgba(255,60,80,.25)"); alarm(); }
    if (entry.querySelector(".stamp.found")) { shakeApp(); alarm(); }
  }
  function confetti() {
    if (reduce) return; const colors = ["#ff2e63", "#08f7fe", "#ffd27a", "#3ddc84", "#7a3fc0"];
    for (let i = 0; i < 120; i++) { const p = document.createElement("i"); p.className = "of-conf"; p.style.left = Math.random() * 100 + "vw"; p.style.background = colors[i % 5];
      p.style.animationDuration = (2 + Math.random() * 2.5) + "s"; p.style.animationDelay = Math.random() * .6 + "s";
      p.style.setProperty("--dx", (Math.random() * 200 - 100) + "px"); p.style.setProperty("--r", (Math.random() * 720) + "deg"); document.body.appendChild(p); setTimeout(() => p.remove(), 5500); }
  }
  function countUp(el) {
    const to = parseInt(el.textContent.replace(/[^\d-]/g, ""), 10); if (isNaN(to) || to === 0) return;
    const suffix = el.textContent.replace(/^[\d\s+-]+/, ""), t0 = performance.now(), ms = reduce ? 1 : 900;
    (function stepC(now) { const t = Math.min(1, (now - t0) / ms); el.textContent = Math.round(to * (1 - Math.pow(1 - t, 3))) + suffix; if (t < 1) requestAnimationFrame(stepC); })(t0);
  }
  function watchGame() {
    const app = $("#app"); if (!app) return;
    new MutationObserver(() => {
      const counts = new Map();
      [...app.querySelectorAll(".entry")].reverse().forEach((e) => {
        if (e.querySelector(".suspense")) return;
        const text = [...e.childNodes].filter((n) => !(n.classList && n.classList.contains("of-roll"))).map((n) => n.textContent).join("").trim().slice(0, 200);
        const n = (counts.get(text) || 0) + 1; counts.set(text, n);
        if (e.dataset.of) return; e.dataset.of = "1";
        const key = text + "#" + n;
        if (seen.has(key)) return; seen.add(key);
        if (O.mode === "laptop") { e.classList.add("of-new"); react(e); }
      });
      const big = app.querySelector(".stamp.big:not(.of-done)");
      if (big) { big.classList.add("of-done"); app.querySelectorAll(".board strong").forEach(countUp);
        if (big.classList.contains("success") || /won|victory/i.test(big.textContent)) { confetti(); beep(660, .3, "triangle", .05); } else { shakeApp(); beep(140, .4, "sawtooth", .05); } }
      if (!app.querySelector(".entry")) seen.clear();
    }).observe(app, { childList: true, subtree: true });
  }

  let pendingMenu = null;
  window.Office = { turn: (t, side, company) => { if (svg) turn(t, side, company); }, menu: (d, b) => { if (svg) menu(d, b); else pendingMenu = [d, b]; } };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
