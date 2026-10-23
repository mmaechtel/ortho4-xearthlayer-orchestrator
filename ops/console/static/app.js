// OXO console: one /api/state poll feeds the band (motion) and the tile map (glow).
// All API text goes through textContent; nothing from the API reaches innerHTML.

const $ = id => document.getElementById(id);
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
const ms = s => (s ? Date.parse(s) : NaN);
const reduceMQ = matchMedia("(prefers-reduced-motion: reduce)");
const lightMQ = matchMedia("(prefers-color-scheme: light)");
const phoneMQ = matchMedia("(max-width: 700px)");
const STEPS = ["1", "2", "2.5", "3"], STEP_NAMES = ["Vektordaten", "Mesh", "Masken", "DSF"];
const STATES = ["pending", "claimed", "succeeded", "packaged", "abandoned"];
const STALE_MS = 90e3, STEP_SCALE = 30 * 60e3, POLL_MS = 3000, BACKOFF_MS = 10000;
const pad = n => String(n).padStart(2, "0");
const dur = s => { s = Math.max(0, Math.floor(s)); const h = s / 3600 | 0, m = (s % 3600) / 60 | 0; return (h ? h + ":" + pad(m) : m) + ":" + pad(s % 60); };
const ago = s => { s = Math.max(0, Math.round(s)); return s < 90 ? s + " s" : s < 5400 ? Math.round(s / 60) + " min" : Math.round(s / 3600) + " h"; };
const hhmm = t => new Date(t).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
const wname = n => n.replace(/^oxo-/, "").replace(/-worker$/, "");
const stepIdx = text => { const m = /Step (\d(?:\.5)?)/.exec(text || ""); return m ? STEPS.indexOf(m[1]) : -1; };
const pkgName = job => `zzXEL_${job.package ?? job.region_code}_ortho`;
const cleanLog = line => line.replace(/^\d{4}-\d\d-\d\dT\S+Z\s+[A-Z]+\s+/, "").trim();
const cancelled = t => /cancelled by operator/.test(t.last_failure || "");
const jobLabel = job => `${job.region_code} r${job.revision}`;
const rank = s => (s === "claimed" ? 3 : s === "pending" ? 2 : 1);
function prio(p) { // A00 < A0 < A4 < A5 < A10 ... < other own < samsoir
  if (p.owner === "samsoir") return 1e6;
  const m = /^A(\d+)/.exec(p.code);
  return m ? +m[1] * 10 + (m[1].length > 1 && +m[1] === 0 ? 0 : 1) : 1e5;
}
function tileBounds(tile) {
  const m = /^([+-]\d{2})([+-]\d{3})$/.exec(tile || "");
  return m ? [[+m[1], +m[2]], [+m[1] + 1, +m[2] + 1]] : null;
}
// Put nodes into parent in this order, reusing them; drop every other child.
function sync(parent, nodes) {
  nodes.forEach((n, i) => { if (parent.children[i] !== n) parent.insertBefore(n, parent.children[i] || null); });
  while (parent.children.length > nodes.length) parent.lastElementChild.remove();
}

/* ---------- model: one entry per task, the newest per (package, tile, type) is current;
   an older task still pending/claimed stays current too, because a worker will build it ---------- */
function model(s) {
  const gen = ms(s.generated_at), installed = new Map(), byTask = new Map();
  for (const i of s.installs) for (const tile of i.tiles) { const k = i.package + "|" + tile; if (!installed.has(k)) installed.set(k, i.code); }
  for (const w of s.workers) if (w.current) byTask.set(w.current.task_id, w);
  const jobs = [...s.jobs].sort((a, b) => ms(b.created_at) - ms(a.created_at));
  const seen = new Set(), tasks = new Map(), tiles = new Map();
  for (const job of jobs) for (const t of job.tasks) {
    const k = job.package + "|" + t.tile + "|" + t.task_type, live = t.state === "pending" || t.state === "claimed";
    const current = live || !seen.has(k);
    seen.add(k);
    const code = t.state === "succeeded" ? installed.get(pkgName(job) + "|" + t.tile) : undefined;
    const hb = ms(t.last_heartbeat_at);
    const x = { t, job, s: code ? "packaged" : t.state, code, current, w: byTask.get(t.id),
      stale: t.state === "claimed" && !(gen - hb <= STALE_MS) };
    tasks.set(t.id, x);
    if (!current || !tileBounds(t.tile)) continue;
    const e = tiles.get(t.tile);
    if (!e) tiles.set(t.tile, { list: [x], win: x });
    else { e.list.push(x); if (rank(x.s) > rank(e.win.s)) e.win = x; } // ties: the newer job wins
  }
  return { s, gen, jobs, tasks, tiles };
}

/* ---------- view state, kept across polls ---------- */
const chips = new Map(), groups = new Map(), lanes = new Map(), jrows = new Map();
let cur = null, last = null, pollAt = 0, failing = false;
let sel = null, hover = null; // sel: {tile} | {job}; hover: tile
const now = () => (last ? ms(last.generated_at) + performance.now() - pollAt : Date.now());

function chip(x) {
  const { t, job, s } = x;
  let c = chips.get(t.id);
  if (!c) {
    c = el("button", "tok"); c.type = "button";
    c.append(el("span", null, t.tile), el("span", "att"), el("span", "why"));
    chips.set(t.id, c);
  }
  c.dataset.s = s; c.dataset.tile = t.tile; c.dataset.job = job.id;
  const live = s === "pending" || s === "claimed", n = s === "pending" ? t.attempts + 1 : t.attempts;
  c.children[1].textContent = live && n > 1 ? `${n}/${job.max_attempts}` : "";
  c.children[2].textContent = s === "abandoned" ? t.last_failure || "" : "";
  c.classList.toggle("stale", x.stale && !!x.w);
  c.title = [`${t.tile} · ${jobLabel(job)} · ${s}${x.code ? " in " + x.code : ""} · Versuche ${t.attempts}/${job.max_attempts}`,
    t.last_failure && "Fehler: " + t.last_failure, t.replaces && "ersetzt " + t.replaces,
    t.patches?.length && "Patches: " + t.patches.join(", ")].filter(Boolean).join("\n");
  return c;
}
function group(key, title) {
  let g = groups.get(key);
  if (!g) {
    g = el("div", "grp");
    const h = el("div", "ghead");
    h.append(el("span"), el("span", "c"));
    g.append(h, el("div", "gbody"));
    groups.set(key, g);
  }
  g.firstChild.firstChild.textContent = title;
  return g;
}

/* ---------- worker lanes: Ortho4XP step bar, clock ring, last log line ---------- */
function makeLane() {
  const L = el("div", "lane"), head = el("div", "lhead"), steps = el("div", "steps");
  const _ = { name: el("span", "lname"), hb: el("span", "hb"), att: el("span", "latt"), idle: el("span", "lidle"), segs: [], slots: [],
    meter: el("div", "meter"), ring: el("span", "ring"), mtxt: el("span"), raw: el("div", "raw"), ticker: el("div", "ticker"), cur: null };
  head.append(_.name, _.hb, _.att, _.idle);
  STEPS.forEach((k, i) => {
    const seg = el("div", "seg"), lab = el("span", "slab", "S" + k), slot = el("div", "slot");
    lab.append(el("span", "sname", " " + STEP_NAMES[i]));
    seg.append(lab, slot); steps.append(seg);
    _.segs.push(seg); _.slots.push(slot);
  });
  _.meter.append(_.ring, _.mtxt);
  L.append(head, steps, _.raw, _.ticker);
  L._ = _;
  return L;
}
function renderLanes(m) {
  const slotOf = new Map(), nodes = [];
  for (const w of [...m.s.workers].sort((a, b) => a.name.localeCompare(b.name, "de", { numeric: true }))) {
    let L = lanes.get(w.name);
    if (!L) { L = makeLane(); lanes.set(w.name, L); }
    nodes.push(L);
    const _ = L._, c = w.current, x = c && m.tasks.get(c.task_id), lastLine = w.log_tail?.at(-1);
    _.name.textContent = wname(w.name); _.name.title = w.name;
    L.classList.toggle("idle", !c);
    L.classList.toggle("down", w.state !== "running");
    L.classList.toggle("stale", !!x?.stale);
    _.ticker.textContent = lastLine ? cleanLog(lastLine.line) : "";
    _.ticker.title = _.ticker.textContent;
    if (!c) {
      _.cur = null;
      _.idleSince = ms(lastLine?.at) || ms(w.started_at);
      _.state = w.state;
      continue;
    }
    const idx = stepIdx(c.step);
    _.segs.forEach((g, i) => { g.classList.toggle("done", i < idx); g.classList.toggle("active", i === idx); });
    _.segs[Math.max(0, idx)].append(_.meter);
    _.raw.textContent = idx < 0 ? c.step || "bereitet vor …" : "";
    _.att.textContent = `Versuch ${c.attempt}/${x?.job.max_attempts ?? "?"}`;
    _.att.classList.toggle("r", c.attempt > 1);
    _.cur = { since: ms(c.step_since || c.since), hb: ms(x?.t.last_heartbeat_at), k: idx < 0 ? "?" : STEPS[idx] };
    slotOf.set(c.task_id, _.slots[Math.max(0, idx)]);
  }
  for (const [name, L] of lanes) if (!nodes.includes(L)) lanes.delete(name);
  sync($("lanes"), nodes);
  $("nl").textContent = nodes.length;
  $("el").hidden = nodes.length > 0;
  return slotOf;
}

/* ---------- band: queue | lanes | delivered | packaged, reject gutter ---------- */
function renderBand(m, prev) {
  const slotOf = renderLanes(m), boxes = new Map(), cols = { q: new Set(), d: new Set(), p: new Set() }, scrap = [], seen = new Set();
  const put = (box, c) => { if (!boxes.has(box)) boxes.set(box, []); boxes.get(box).push(c); };
  for (const job of [...m.jobs].reverse()) for (const t of job.tasks) { // oldest job first: queue order
    const x = m.tasks.get(t.id);
    if (!x.current) continue;
    const c = chip(x);
    seen.add(t.id);
    const slot = x.s === "claimed" && slotOf.get(t.id);
    if (slot) { put(slot, c); continue; }
    if (x.s === "abandoned") { scrap.push(c); continue; }
    const col = x.s === "packaged" ? "p" : x.s === "succeeded" ? "d" : "q";
    const g = group(col + (x.code || job.id), x.code || jobLabel(job));
    g._code = x.code;
    cols[col].add(g);
    put(g.lastChild, c);
  }
  for (const [id, c] of chips) if (!seen.has(id)) { c.remove(); chips.delete(id); }
  for (const L of lanes.values()) for (const slot of L._.slots) sync(slot, boxes.get(slot) || []);
  for (const [box, list] of boxes) if (box.classList.contains("gbody")) {
    sync(box, list);
    box.previousSibling.lastChild.textContent = list.length;
  }
  // packaged rows in priority order, with the package's total tile count
  const pk = new Map(m.s.packages.map(p => [p.code, p]));
  const prows = [...cols.p].sort((a, b) => prio(pk.get(a._code) || a) - prio(pk.get(b._code) || b));
  for (const g of prows) {
    const p = pk.get(g._code);
    if (p) g.firstChild.lastChild.textContent = `${p.tiles.toLocaleString("de-DE")} Tiles im Paket`;
  }
  const fresh = new Set(prev ? m.s.installs.filter(i => !prev.s.installs.some(j => j.at === i.at && j.code === i.code)).map(i => i.code) : []);
  for (const g of prows) if (fresh.has(g._code)) {
    g.classList.add("fresh"); clearTimeout(g._t); g._t = setTimeout(() => g.classList.remove("fresh"), 6000);
  }
  sync($("q"), [...cols.q]); sync($("d"), [...cols.d]); sync($("p"), prows); sync($("scrap"), scrap);
  for (const [k, g] of groups) if (!g.isConnected) groups.delete(k);
  for (const k of ["q", "d", "p"]) {
    const n = $(k).querySelectorAll(".tok").length;
    $("n" + k).textContent = n; $("e" + k).hidden = n > 0;
    $(k).parentNode.classList.toggle("dense", n >= 40);
  }
  $("ns").textContent = scrap.length; $("scrapbox").hidden = !scrap.length;
  $("scrap").classList.toggle("dense", scrap.length >= 40);
  const all = [...m.s.packages].sort((a, b) => prio(a) - prio(b) || a.code.localeCompare(b.code));
  $("npk").textContent = `(${all.length})`;
  sync($("allpk"), all.map(p => { const li = el("li"); li.append(el("span", null, p.code), el("span", null, `${p.tiles.toLocaleString("de-DE")} · ${p.owner}`)); return li; }));
}

/* ---------- FLIP: a chip that changed column glides from where it was ---------- */
function measure() {
  const r = new Map();
  if (!reduceMQ.matches) for (const [id, c] of chips) if (c.isConnected) r.set(id, [c.getBoundingClientRect(), c.parentNode]);
  return r;
}
function glide(before) {
  for (const [id, c] of chips) {
    const a = before.get(id);
    if (!a || a[1] === c.parentNode || !a[0].width) continue;
    const b = c.getBoundingClientRect();
    if (!b.width) continue;
    c.animate([{ transform: `translate(${a[0].left - b.left}px, ${a[0].top - b.top}px)` }, { transform: "none" }],
      { duration: 650, easing: "cubic-bezier(.2,.7,.2,1)" });
  }
}

/* ---------- job strip ---------- */
function renderJobs(m, prev) {
  const problem = j => j.tasks.some(t => { const x = m.tasks.get(t.id); return x.current && ((x.s === "abandoned" && !cancelled(t)) || (x.stale && x.w)); });
  const hasCurrent = j => j.tasks.some(t => m.tasks.get(t.id).current);
  const order = j => problem(j) ? 0 : !hasCurrent(j) ? 3 : j.state === "complete" ? 2 : 1;
  const nodes = [...m.jobs].sort((a, b) => order(a) - order(b) || ms(b.created_at) - ms(a.created_at)).map(j => {
    let r = jrows.get(j.id);
    if (!r) {
      r = el("button", "jrow"); r.type = "button"; r.dataset.jobRow = j.id;
      const bar = el("span", "bar");
      for (const k of ["packaged", "succeeded", "claimed", "pending", "abandoned"]) bar.append(el("span", "b-" + k));
      r.append(el("span", "reg"), el("span", "rev"), bar, el("span", "nums"), el("span", "st"));
      jrows.set(j.id, r);
    }
    const n = Object.fromEntries(STATES.map(k => [k, 0]));
    for (const t of j.tasks) n[t.state === "succeeded" && m.tasks.get(t.id).code ? "packaged" : t.state]++;
    r.children[0].textContent = j.region_code;
    r.children[1].textContent = "r" + j.revision;
    ["packaged", "succeeded", "claimed", "pending", "abandoned"].forEach((k, i) => { r.children[2].children[i].style.flexGrow = n[k]; });
    r.children[2].title = STATES.map(k => `${n[k]} ${k}`).join(" · ");
    r.children[3].textContent = `${n.succeeded + n.packaged}/${j.total}`;
    r.children[4].textContent = j.state; r.children[4].dataset.st = j.state;
    r.classList.toggle("old", !hasCurrent(j));
    r.title = `${jobLabel(j)} · Paket ${pkgName(j)} · angelegt ${hhmm(ms(j.created_at))}` + (hasCurrent(j) ? "" : " · durch neuere Revision ersetzt");
    return r;
  });
  for (const [id, r] of jrows) if (!nodes.includes(r)) jrows.delete(id);
  sync($("jobs"), nodes);
  if (!prev) return;
  const was = new Map(prev.s.jobs.map(j => [j.id, j.state]));
  const news = m.s.jobs.filter(j => was.get(j.id) !== j.state).map(j => `${jobLabel(j)}: ${j.state}`);
  if (news.length) $("live").textContent = news.join(". ");
}

/* ---------- map: rectangles per tile, glow when claimed, one ping on claim/delivery ---------- */
let map = null, glowR, hlR, hlLayer, fitted = false, themeV = 0;
const rects = new Map(), callsigns = new Map(), cells = new Map(), C = {};
function readTheme() {
  const cs = getComputedStyle(document.documentElement);
  for (const k of [...STATES, "warn", "line"]) C[k] = cs.getPropertyValue("--" + k).trim();
  themeV++;
}
const rectStyle = s => ({ color: C[s], weight: s === "pending" ? 1 : 1.5, opacity: .95, dashArray: s === "pending" ? "4 3" : null,
  fillColor: C[s], fillOpacity: s === "claimed" ? .1 : s === "pending" ? .15 : .38 });
function tip(tile) {
  const box = el("div"), e = cur?.tiles.get(tile);
  box.append(el("b", null, tile));
  for (const x of e?.list || []) {
    const r = el("div"), sw = el("i", "sw");
    sw.style.setProperty("--sc", `var(--${x.s})`);
    r.append(sw, `${jobLabel(x.job)} · ${x.s}${x.code ? " " + x.code : ""} · ${x.t.attempts}/${x.job.max_attempts}`);
    box.append(r);
  }
  return box;
}
function initMap() {
  if (!window.L) { $("map").classList.add("grid"); return; }
  map = L.map("map", { preferCanvas: true, minZoom: 2, maxZoom: 12, zoomSnap: .5, worldCopyJump: true }).setView([48.5, 11], 6);
  map.createPane("glow").style.zIndex = 420;
  map.createPane("hl").style.zIndex = 430;
  glowR = L.svg({ pane: "glow" }); hlR = L.svg({ pane: "hl" });
  hlLayer = L.layerGroup().addTo(map);
  readTheme();
  // OSM standard tiles (CARTO now needs an API key); dark mode dims them via CSS. Offline or
  // blocked: the first tile error adds a lat/lon graticule instead.
  const base = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map);
  base.once("tileerror", () => {
    map.createPane("grid").style.zIndex = 350; // below the tile canvas, or it would swallow clicks
    const g = L.canvas({ pane: "grid" }), st = { renderer: g, interactive: false, color: C.line, weight: .6 };
    for (let la = -80; la <= 80; la++) L.polyline([[la, -180], [la, 180]], st).addTo(map);
    for (let lo = -180; lo <= 180; lo++) L.polyline([[-80, lo], [80, lo]], st).addTo(map);
  });
  const legend = L.control({ position: "bottomleft" });
  legend.onAdd = () => {
    const d = el("div", "legend");
    for (const k of STATES) { const s = el("span"), sw = el("i", "sw"); sw.style.setProperty("--sc", `var(--${k})`); s.append(sw, k); d.append(s); }
    return d;
  };
  legend.addTo(map);
  lightMQ.addEventListener("change", () => { readTheme(); if (cur) renderMap(cur, null); });
}
function ping(tile, s) {
  if (reduceMQ.matches || !map) return;
  const b = tileBounds(tile), a = map.latLngToLayerPoint(b[0]), c = map.latLngToLayerPoint(b[1]);
  const d = el("div", "ping");
  d.style.setProperty("--sc", `var(--${s})`);
  const mk = L.marker([b[0][0] + .5, b[0][1] + .5], { interactive: false, keyboard: false,
    icon: L.divIcon({ className: "", html: d, iconSize: [Math.abs(c.x - a.x), Math.abs(c.y - a.y)] }) }).addTo(map);
  setTimeout(() => mk.remove(), 1300);
}
function fitTo(tiles, animate) {
  const bs = [...tiles].map(tileBounds).filter(Boolean);
  if (!map || !bs.length || !map.getSize().x) return false;
  const lb = L.latLngBounds(bs.flat()).pad(.6);
  animate && !reduceMQ.matches ? map.flyToBounds(lb, { maxZoom: 9, duration: .8 }) : map.fitBounds(lb, { maxZoom: 8, animate: false });
  return true;
}
function fitStart() {
  if (fitted || !cur || !cur.tiles.size) return;
  const active = [...cur.tiles].filter(([, e]) => e.list.some(x => x.s === "claimed" || x.s === "pending")).map(([t]) => t);
  fitted = fitTo(active.length ? active : cur.tiles.keys(), false);
}
function renderMap(m, prev) {
  if (!map) return renderGrid(m);
  for (const [tile, e] of m.tiles) {
    let o = rects.get(tile);
    if (!o) {
      o = { r: L.rectangle(tileBounds(tile)).addTo(map) };
      o.r.on("mouseover", () => setHover(tile)).on("mouseout", () => setHover(null)).on("click", () => toggleTile(tile));
      o.r.bindTooltip(() => tip(tile), { sticky: true });
      rects.set(tile, o);
    }
    const s = e.win.s, key = s + themeV;
    if (o.k !== key) { o.k = key; o.r.setStyle(rectStyle(s)); }
    if (s === "claimed" && !o.glow) o.glow = L.rectangle(tileBounds(tile), { renderer: glowR, className: "glow", interactive: false }).addTo(map);
    if (s !== "claimed" && o.glow) { o.glow.remove(); o.glow = null; }
    o.glow?.getElement()?.classList.toggle("stale", e.win.stale);
  }
  for (const [tile, o] of rects) if (!m.tiles.has(tile)) { o.r.remove(); o.glow?.remove(); rects.delete(tile); }
  if (prev) for (const [id, x] of m.tasks) {
    const p = prev.tasks.get(id);
    if (!x.current || !p || p.t.state === x.t.state) continue;
    if (x.t.state === "claimed") ping(x.t.tile, "claimed");
    else if (p.t.state === "claimed" && x.t.state === "succeeded") ping(x.t.tile, x.s);
  }
  const live = new Set();
  for (const w of m.s.workers) {
    const b = w.current && tileBounds(w.current.tile);
    if (!b) continue;
    live.add(w.name);
    let o = callsigns.get(w.name);
    if (!o) {
      o = { tag: el("div", "cs") };
      o.m = L.marker(b[1], { interactive: false, keyboard: false, icon: L.divIcon({ className: "cs-icon", html: o.tag, iconSize: null }) }).addTo(map);
      callsigns.set(w.name, o);
    }
    o.m.setLatLng(b[1]);
    o.w = w;
    o.tag.classList.toggle("stale", !!m.tasks.get(w.current.task_id)?.stale);
  }
  for (const [n, o] of callsigns) if (!live.has(n)) { o.m.remove(); callsigns.delete(n); }
  fitStart();
}
function renderGrid(m) { // offline: compact tile grid, north up, same palette and coupling
  const bs = [...m.tiles.keys()].map(t => [t, tileBounds(t)]);
  const lat1 = Math.max(...bs.map(b => b[1][0][0])), lon0 = Math.min(...bs.map(b => b[1][0][1]));
  const lon1 = Math.max(...bs.map(b => b[1][0][1]));
  const box = $("map");
  box.style.gridTemplateColumns = `repeat(${bs.length ? lon1 - lon0 + 1 : 1}, minmax(0, 52px))`;
  if (!box.firstChild) box.append(el("p", null, "Karte offline — kompakte Kachelansicht."));
  const nodes = [box.firstChild];
  for (const [tile, b] of bs) {
    let c = cells.get(tile);
    if (!c) { c = el("button", "cell", tile); c.type = "button"; c.dataset.tile = tile; cells.set(tile, c); }
    c.dataset.s = m.tiles.get(tile).win.s;
    c.style.gridRow = lat1 - b[0][0] + 2; c.style.gridColumn = b[0][1] - lon0 + 1;
    c.title = tip(tile).textContent;
    nodes.push(c);
  }
  for (const t of cells.keys()) if (!m.tiles.has(t)) cells.delete(t);
  sync(box, nodes);
}

/* ---------- shared selection: chip <-> tile <-> job ---------- */
function jobTiles(id) { return new Set([...(cur?.tasks.values() || [])].filter(x => x.job.id === id).map(x => x.t.tile)); }
function highlight() {
  const tiles = hover ? new Set([hover]) : sel?.tile ? new Set([sel.tile]) : sel?.job ? jobTiles(sel.job) : new Set();
  const byJob = !hover && sel?.job;
  for (const c of chips.values()) {
    c.classList.toggle("hl", byJob ? c.dataset.job === sel.job : tiles.has(c.dataset.tile));
    c.setAttribute("aria-pressed", String(sel?.tile === c.dataset.tile));
  }
  for (const [id, r] of jrows) r.setAttribute("aria-pressed", String(sel?.job === id));
  for (const [t, c] of cells) c.classList.toggle("hl", tiles.has(t));
  if (!map) return;
  hlLayer.clearLayers();
  for (const t of tiles) if (tileBounds(t)) L.rectangle(tileBounds(t), { renderer: hlR, className: "hl", interactive: false }).addTo(hlLayer);
}
function renderDetail() {
  const box = $("detail"), list = el("ul");
  let head = null;
  if (sel?.tile) {
    head = sel.tile;
    for (const x of cur?.tiles.get(sel.tile)?.list || []) {
      const li = el("li"), sw = el("i", "sw"), t = x.t;
      sw.style.setProperty("--sc", `var(--${x.s})`);
      li.append(sw, `${jobLabel(x.job)} · ${x.s}${x.code ? " in " + x.code : ""} · Versuch ${t.attempts}/${x.job.max_attempts}`
        + (x.w ? ` · ${wname(x.w.name)}: ${x.w.current.step || "startet"}` : ""));
      const more = [t.last_failure && "Fehler: " + t.last_failure, t.replaces && "ersetzt " + t.replaces,
        t.patches?.length && "Patches: " + t.patches.join(", ")].filter(Boolean).join(" · ");
      if (more) li.append(el("small", null, more));
      list.append(li);
    }
  } else if (sel?.job) {
    const j = cur?.s.jobs.find(j => j.id === sel.job);
    if (j) {
      head = jobLabel(j);
      list.append(el("li", null, `${j.state} · ${j.counts.succeeded}/${j.total} fertig · ${j.counts.abandoned} abandoned · Paket ${pkgName(j)} · angelegt ${hhmm(ms(j.created_at))}`));
    }
  }
  box.classList.toggle("none", !head);
  if (!head) { box.replaceChildren("Chip, Kachel oder Job anklicken hebt sie überall hervor; Esc hebt die Auswahl auf."); return; }
  const x = el("button", "x", "Auswahl aufheben"); x.type = "button";
  x.addEventListener("click", () => select(null));
  box.replaceChildren(el("h3", null, head), list, x);
}
function select(s) { sel = s; hover = null; highlight(); renderDetail(); }
function setHover(tile) { if (hover !== tile) { hover = tile; highlight(); } }
function toggleTile(tile) { select(sel?.tile === tile ? null : { tile }); }
function toggleJob(id) {
  select(sel?.job === id ? null : { job: id });
  if (!sel) return;
  if (phoneMQ.matches) setTab("map", true);
  fitTo(jobTiles(id), true);
}

/* ---------- status bar: one sentence for the most urgent problem; clocks tick here ---------- */
function tick() {
  if (!last) { // nothing loaded yet: only a failure is worth saying
    if (failing) { $("status").dataset.level = "off"; $("summary").textContent = "Console-Server nicht erreichbar"; }
    return;
  }
  const t = now(), m = cur, bar = $("status");
  $("clock").textContent = new Date(t).toLocaleTimeString("de-DE");
  $("ago").textContent = `aktualisiert vor ${ago((performance.now() - pollAt) / 1000)}`;
  for (const L of lanes.values()) {
    const _ = L._, c = _.cur;
    if (!c) { _.idle.textContent = _.state === "running" ? `idle seit ${ago((t - _.idleSince) / 1000)}` : `Container ${_.state}`; continue; }
    const el_ = t - c.since;
    _.ring.style.setProperty("--p", Math.min(1, el_ / STEP_SCALE).toFixed(3));
    _.meter.classList.toggle("over", el_ > STEP_SCALE);
    _.mtxt.textContent = dur(el_ / 1000);
    _.meter.title = `Step ${c.k} läuft seit ${dur(el_ / 1000)} (Ring = 30 min)`;
    _.hb.textContent = c.hb ? `♥ vor ${ago((t - c.hb) / 1000)}` : "♥ –";
  }
  for (const o of callsigns.values()) {
    const c = o.w.current, i = stepIdx(c.step);
    o.tag.textContent = `${wname(o.w.name)} · S${i >= 0 ? STEPS[i] : "?"} · ${ago((t - ms(c.since)) / 1000)}`;
  }
  let level = "", text = "";
  if (failing) { level = "off"; text = `Console-Server nicht erreichbar · Stand ${hhmm(ms(last.generated_at))}`; }
  else if (!last.database.reachable) { level = "off"; text = `Datenbank nicht erreichbar · Stand ${m ? hhmm(m.gen) : "–"}`; }
  else if (m) {
    const stale = [...m.tasks.values()].find(x => x.stale && x.w);
    const down = m.s.workers.find(w => w.state !== "running");
    const bad = m.jobs.map(j => [j, j.tasks.filter(t => { const x = m.tasks.get(t.id); return x.current && x.s === "abandoned" && !cancelled(t); })]).find(([, ts]) => ts.length);
    if (stale) { level = "warn"; text = `${wname(stale.w.name)}: Heartbeat ${stale.t.last_heartbeat_at ? "seit " + ago((t - ms(stale.t.last_heartbeat_at)) / 1000) : "fehlt"} · ${stale.t.tile}`; }
    else if (down) { level = "warn"; text = `${wname(down.name)}: Container ${down.state}`; }
    else if (bad) { level = "bad"; text = `${jobLabel(bad[0])}: ${bad[1].length} Tiles abandoned · ${bad[1][0].last_failure || "?"}`; }
  }
  if (level) bar.dataset.level = level; else delete bar.dataset.level;
  $("msg").textContent = text;
  $("db").title = last.database.reachable ? "Datenbank erreichbar" : "Datenbank: " + (last.database.error || "nicht erreichbar");
  $("main").classList.toggle("offline", failing || !last.database.reachable);
}
function summary(m) {
  const n = k => [...m.tasks.values()].filter(x => x.current && x.s === k).length;
  const active = m.s.jobs.filter(j => j.state === "in_progress" || j.state === "pending").length;
  const busy = m.s.workers.filter(w => w.current).length;
  $("summary").textContent = `${active} aktive Jobs · ${n("pending")} in der Queue · ${busy}/${m.s.workers.length} Worker beschäftigt`;
}

/* ---------- poll ---------- */
function render(s) {
  const prev = cur, before = prev ? measure() : new Map();
  cur = model(s);
  renderBand(cur, prev);
  renderJobs(cur, prev);
  if (prev) glide(before);
  renderMap(cur, prev);
  if (sel?.tile && !cur.tiles.has(sel.tile)) sel = null;
  if (sel?.job && !jrows.has(sel.job)) sel = null;
  highlight(); renderDetail(); summary(cur);
}
async function poll() {
  let wait = POLL_MS;
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const s = await r.json();
    last = s; pollAt = performance.now(); failing = false;
    if (s.database.reachable || !cur) render(s); // DB down: keep the last good picture, greyed
  } catch {
    failing = true; wait = BACKOFF_MS;
  }
  tick();
  setTimeout(poll, wait);
}

/* ---------- tabs (phone), events ---------- */
function setTab(tab, save) {
  document.body.dataset.tab = tab;
  for (const b of document.querySelectorAll(".tabs button")) {
    const on = b.dataset.tab === tab;
    b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1;
  }
  if (save) try { localStorage.setItem("oxo-console-tab", tab); } catch { /* storage blocked: tab not remembered */ }
  if (map) { map.invalidateSize(); fitStart(); }
}
let startTab = "band";
try { startTab = localStorage.getItem("oxo-console-tab") === "map" ? "map" : "band"; } catch { /* default tab */ }
setTab(startTab, false);
document.querySelector(".tabs").addEventListener("click", e => { const b = e.target.closest("button"); if (b) setTab(b.dataset.tab, true); });
document.querySelector(".tabs").addEventListener("keydown", e => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  const next = document.body.dataset.tab === "band" ? "map" : "band";
  setTab(next, true); $("tab-" + next).focus();
});
document.addEventListener("click", e => {
  const j = e.target.closest("[data-job-row]");
  if (j) return toggleJob(j.dataset.jobRow);
  const t = e.target.closest(".tok, .cell");
  if (t) toggleTile(t.dataset.tile);
});
for (const [on, off] of [["pointerover", "pointerout"], ["focusin", "focusout"]]) {
  document.addEventListener(on, e => { const t = e.target.closest?.(".tok, .cell"); if (t) setHover(t.dataset.tile); });
  document.addEventListener(off, e => {
    const t = e.target.closest?.(".tok, .cell");
    if (t && e.relatedTarget?.closest?.(".tok, .cell") !== t) setHover(null);
  });
}
document.addEventListener("keydown", e => { if (e.key === "Escape") select(null); });
phoneMQ.addEventListener("change", () => map && map.invalidateSize());
if (!phoneMQ.matches) $("scrapbox").open = true;

initMap();
renderDetail();
poll();
setInterval(tick, 1000);
