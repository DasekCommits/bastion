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
    O.mode = mode; document.body.classList.remove("of-menu", "of-room", "of-laptop"); document.body.classList.add("of-" + mode);
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
      <div class="of-toast" id="of-toast"></div><div class="of-vignette"></div>`);
    const right = document.querySelector(".topbar-right");
    if (right) right.insertAdjacentHTML("afterbegin", `<span class="clockchip inos of-only"><i>☀</i><small>Day 1</small><b>09:00</b></span><button class="of-close of-only" id="of-close">Close laptop</button>`);
    decorate(); paintSide(); paintTime(); fit(); setMode("menu");
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

  window.Office = { turn: (t, side, company) => { if (svg) turn(t, side, company); } };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
