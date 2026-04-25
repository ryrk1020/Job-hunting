// Job Hunter dashboard v2 — calendar SPA + Kanban board + detail drawer.
// Share the Pages URL with anyone; no auth, no tokens, no setup.
// Marks (status, notes, salary, contact, dates) live in each viewer's localStorage.
// Carry-forward runs purely in the browser: when you view today, jobs from
// prior days that you haven't closed out are merged in.

// ───── Pipeline definition ──────────────────────────────────────────
// Five canonical stages. Each one accepts legacy single-word values
// from v1 storage so existing marks keep working without migration.
const PIPELINE = [
  { key: "interested", label: "Interested", color: "success",     compat: ["accept"] },
  { key: "applied",    label: "Applied",    color: "primary",     compat: [] },
  { key: "interview",  label: "Interview",  color: "warning",     compat: ["inprogress"] },
  { key: "offer",      label: "Offer",      color: "purple",      compat: [] },
  { key: "closed",     label: "Closed",     color: "destructive", compat: ["reject"] },
];
const PIPELINE_KEYS = PIPELINE.map(p => p.key);
const SUB_STAGES = [
  { key: "",          label: "—" },
  { key: "phone",     label: "Phone screen" },
  { key: "technical", label: "Technical / take-home" },
  { key: "onsite",    label: "Onsite / final round" },
];
const STALE_DAYS = 14;
const STALE_STAGES = new Set(["applied", "interview", "offer"]);

const STATUS_KEY = "jobhunter.status.v1";   // schema kept stable for backward-compat
const THEME_KEY  = "jobhunter.theme";
const CARRY_KEY  = "jobhunter.carry";       // "1" = on (default), "0" = off
const VIEW_KEY   = "jobhunter.view";        // "list" | "board"
const SORT_KEY   = "jobhunter.sort";        // "score" | "posted" | "company" | "title"
const CARRY_MAX_DAYS = 14;

const REPO_SLUG = detectRepoSlug();

const state = {
  manifest: null,
  byDate: new Map(),
  selected: null,
  view: { y: null, m: null },
  jobs: [],
  filters: { q: "", group: "", status: "unmarked", loc: "" },
  status: loadStatus(),
  carryEnabled: localStorage.getItem(CARRY_KEY) !== "0",
  viewMode: localStorage.getItem(VIEW_KEY) || "list",
  sortBy:   localStorage.getItem(SORT_KEY) || "score",
  drawerUrl: null,
};

// ───── Utility ───────────────────────────────────────────────────────
function detectRepoSlug() {
  try {
    const h = location.hostname;
    const m = h.match(/^([^.]+)\.github\.io$/);
    if (m) {
      const user = m[1];
      const seg = location.pathname.split("/").filter(Boolean)[0] || user + ".github.io";
      return `${user}/${seg}`;
    }
  } catch {}
  return null;
}
function safe(s) { return (s || "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }
function todayISO() { return new Date().toISOString().slice(0, 10); }
function nowISO()   { return new Date().toISOString(); }
function isoFromYMD(y, m, d) { return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`; }

function toast(msg, ms = 2200) {
  let el = document.querySelector(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
  el.textContent = msg;
  requestAnimationFrame(() => el.classList.add("show"));
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), ms);
}

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }); }
  catch { return iso.slice(0, 10); }
}
function fmtAgo(iso) {
  if (!iso) return "";
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  return `${months}mo ago`;
}

// ───── Theme ─────────────────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(THEME_KEY, theme);
}
function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));
}

// ───── Status store ──────────────────────────────────────────────────
// Storage: localStorage[STATUS_KEY] = { url: rawMark }, where rawMark is either
//   - a string  (v1 legacy): "accept" | "applied" | "inprogress" | "reject"
//   - an object (v2):        { s, sub, n, c, $, x, ad, u }
//        s   stage key (canonical, see PIPELINE)
//        sub sub-stage when s === "interview"
//        n   notes
//        c   contact
//        $   salary (note: dollar sign, kept short for storage)
//        x   next step text
//        ad  ISO datetime first marked Applied
//        u   ISO datetime last updated
// Reading via getMark() always returns the v2 shape (or null), with legacy
// strings auto-mapped to canonical stage keys via PIPELINE.compat.
function loadStatus() {
  try { return JSON.parse(localStorage.getItem(STATUS_KEY) || "{}"); }
  catch { return {}; }
}
function saveStatus() { localStorage.setItem(STATUS_KEY, JSON.stringify(state.status)); }

function legacyToCanonical(raw) {
  for (const col of PIPELINE) {
    if (col.key === raw) return col.key;
    if (col.compat.includes(raw)) return col.key;
  }
  return raw || "";
}
function getMark(url) {
  const raw = state.status[url];
  if (!raw) return null;
  if (typeof raw === "string") return { s: legacyToCanonical(raw) };
  return { ...raw, s: legacyToCanonical(raw.s || "") };
}
function getStage(url) { return getMark(url)?.s || ""; }

function patchMark(url, patch) {
  const cur = getMark(url) || {};
  const next = { ...cur, ...patch, u: nowISO() };
  if (patch.s === "applied" && !cur.ad) next.ad = next.u;
  // Empty mark? remove entry to keep storage tidy.
  const empty = !next.s && !next.n && !next.c && !next.$ && !next.x && !next.sub;
  if (empty) delete state.status[url];
  else state.status[url] = next;
  saveStatus();
}
function clearMark(url) {
  delete state.status[url];
  saveStatus();
}
function toggleStage(url, stage) {
  const cur = getMark(url);
  if (cur && cur.s === stage) {
    // Toggling off the stage but keep notes/contact/etc if present.
    const { s, sub, ...rest } = cur;
    if (Object.keys(rest).filter(k => rest[k] !== undefined && rest[k] !== "" && k !== "u" && k !== "ad").length === 0) {
      clearMark(url);
    } else {
      patchMark(url, { s: "", sub: "" });
    }
  } else {
    patchMark(url, { s: stage });
  }
}

// ───── Calendar ──────────────────────────────────────────────────────
const MONTHS = ["January","February","March","April","May","June",
                "July","August","September","October","November","December"];

function renderCalendar() {
  const { y, m } = state.view;
  document.getElementById("cal-title").textContent = `${MONTHS[m]} ${y}`;
  const grid = document.getElementById("calendar");
  grid.innerHTML = "";
  const first = new Date(y, m, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const today = todayISO();
  const counts = new Map((state.manifest?.days || []).map(d => [d.date, d.count]));

  for (let i = 0; i < startDow; i++) {
    const c = document.createElement("div");
    c.className = "cell empty";
    grid.appendChild(c);
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = isoFromYMD(y, m, d);
    const cnt = counts.get(iso) || 0;
    const cell = document.createElement("div");
    cell.className = "cell";
    if (cnt > 0) { cell.classList.add("has-jobs"); cell.dataset.count = cnt; }
    if (iso === today) cell.classList.add("today");
    if (iso === state.selected) cell.classList.add("selected");
    cell.textContent = d;
    cell.dataset.date = iso;
    if (cnt > 0) cell.addEventListener("click", () => selectDate(iso));
    grid.appendChild(cell);
  }
}

// ───── Data loading ──────────────────────────────────────────────────
async function loadManifest({ fresh = false } = {}) {
  const url = fresh ? `manifest.json?t=${Date.now()}` : "manifest.json";
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error("manifest.json not found");
  state.manifest = await r.json();
}

async function loadDay(date, { fresh = false } = {}) {
  if (!fresh && state.byDate.has(date)) return state.byDate.get(date);
  const url = fresh ? `archive/${date}.json?t=${Date.now()}` : `archive/${date}.json`;
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) return { jobs: [], count: 0 };
  const data = await r.json();
  state.byDate.set(date, data);
  return data;
}

function latestDay() {
  const days = state.manifest?.days || [];
  return days[0]?.date || null;
}

async function buildJobsForDate(date) {
  const data = await loadDay(date);
  const fresh = (data.jobs || []).map(j => ({ ...j }));
  const isLatest = date === latestDay();
  if (!isLatest || !state.carryEnabled) return fresh;

  const days = state.manifest?.days || [];
  const priors = days.filter(d => d.date < date).slice(0, CARRY_MAX_DAYS);

  const seen = new Set(fresh.map(j => j.url).filter(Boolean));
  const carryLoads = await Promise.all(priors.map(d => loadDay(d.date)));

  const carried = [];
  carryLoads.forEach((d, i) => {
    const origin = priors[i].date;
    for (const j of (d.jobs || [])) {
      if (!j.url || seen.has(j.url)) continue;
      const stage = getStage(j.url);
      // Drop carryover anything already Applied (user has acted) or Closed.
      if (stage === "applied" || stage === "closed") continue;
      carried.push({ ...j, carryover: true, carried_from: j.carried_from || origin });
      seen.add(j.url);
    }
  });
  return [...fresh, ...carried];
}

async function selectDate(date) {
  state.selected = date;
  renderCalendar();
  state.jobs = await buildJobsForDate(date);
  renderJobs();
  refreshKpis();
  updateSubtitle();
}

function updateSubtitle() {
  const el = document.getElementById("subtitle");
  if (!state.selected) { el.textContent = "No day selected"; return; }
  const gen = state.manifest?.generated_at
    ? new Date(state.manifest.generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : null;
  const carryover = state.jobs.filter(j => j.carryover).length;
  const carryTxt = carryover > 0 ? ` · ${carryover} carried over` : "";
  el.textContent = `Viewing ${state.selected}${gen ? ` · updated ${gen}` : ""}${carryTxt}`;
}

// ───── Sort ──────────────────────────────────────────────────────────
function sortJobs(jobs, by) {
  const arr = [...jobs];
  switch (by) {
    case "posted":
      return arr.sort((a, b) => {
        const ta = new Date(a.posted_at || 0).getTime();
        const tb = new Date(b.posted_at || 0).getTime();
        return tb - ta;
      });
    case "company":
      return arr.sort((a, b) => (a.company || "").localeCompare(b.company || ""));
    case "title":
      return arr.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
    case "score":
    default:
      return arr.sort((a, b) => {
        const pa = a.preferred_location ? 1 : 0;
        const pb = b.preferred_location ? 1 : 0;
        if (pa !== pb) return pb - pa;
        return (b.score || 0) - (a.score || 0);
      });
  }
}

// ───── Filtering ─────────────────────────────────────────────────────
function applyFilters(jobs) {
  const { q, group, status, loc } = state.filters;
  const ql = q.toLowerCase();
  return jobs.filter(j => {
    if (q) {
      const blob = `${j.company || ""} ${j.title || ""} ${j.location || ""} ${j.source || ""} ${(j.matched_groups || []).join(" ")}`.toLowerCase();
      if (!blob.includes(ql)) return false;
    }
    if (group && !(j.matched_groups || []).includes(group)) return false;
    if (loc === "preferred" && !j.preferred_location) return false;
    if (loc === "remote" && !((j.location || "").toLowerCase().includes("remote") || j.remote)) return false;
    const cur = getStage(j.url);
    if (status === "unmarked" && cur) return false;
    if (status && status !== "unmarked" && cur !== status) return false;
    return true;
  });
}

// ───── Stale detection ───────────────────────────────────────────────
function isStale(mark) {
  if (!mark || !STALE_STAGES.has(mark.s)) return false;
  if (!mark.u) return false;
  const days = (Date.now() - new Date(mark.u).getTime()) / 86400000;
  return days >= STALE_DAYS;
}

// ───── Card rendering ────────────────────────────────────────────────
function jobCard(j) {
  const tags = [...(j.matched_groups || [])];
  if (j.preferred_location) tags.push("preferred");
  if ((j.location || "").toLowerCase().includes("remote") || j.remote) tags.push("remote");
  const mark = getMark(j.url);
  const cur = mark?.s || "";
  const posted = (j.posted_at || "").slice(0, 10);
  const tagHtml = tags.map(t => `<span class="tag ${t}">${safe(t)}</span>`).join("");
  const quickStages = ["interested", "applied", "interview", "closed"];
  const stageBtns = quickStages.map(s => `
    <button data-act="${s}" data-url="${encodeURIComponent(j.url)}" class="${cur === s ? "active " + s : ""}" title="Mark as ${s}">${labelFor(s)}</button>
  `).join("");
  const carryBadge = j.carryover
    ? `<span class="carry-badge" title="Carried over from ${safe(j.carried_from || "a previous day")}">carried</span>`
    : "";
  const noteIcon = mark?.n
    ? `<span class="note-icon" title="Has notes">
         <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 13h6"/><path d="M9 17h4"/></svg>
       </span>`
    : "";
  const offerBadge = cur === "offer" ? `<span class="offer-badge" title="Offer received">offer</span>` : "";
  const stale = isStale(mark);
  const staleBadge = stale
    ? `<span class="stale-badge" title="No update in ${STALE_DAYS}+ days">stale ${fmtAgo(mark.u)}</span>`
    : "";
  return `
    <article class="job stage-${cur || "none"} ${j.carryover ? "is-carryover" : ""} ${stale ? "is-stale" : ""}" data-url="${encodeURIComponent(j.url)}">
      <div class="score-pill">${j.score || 0}<small>score</small></div>
      <div class="job-main">
        <h3>
          <a href="${j.url}" target="_blank" rel="noopener">${safe(j.title)}</a>
          ${noteIcon}${offerBadge}${carryBadge}${staleBadge}
        </h3>
        <div class="meta">
          <span class="meta-company">${safe(j.company)}</span>
          <span class="meta-sep">·</span>
          <span>${safe(j.location)}</span>
          <span class="meta-sep">·</span>
          <span>${posted || "—"}</span>
          <span class="meta-sep">·</span>
          <span class="meta-source">${safe(j.source)}</span>
        </div>
        <div class="tags">${tagHtml}</div>
      </div>
      <div class="actions">
        <a class="apply" href="${j.url}" target="_blank" rel="noopener">Apply</a>
        <div class="status-row">${stageBtns}</div>
        <button class="details-btn" data-details="${encodeURIComponent(j.url)}">Details</button>
      </div>
    </article>
  `;
}
function labelFor(stageKey) {
  switch (stageKey) {
    case "interested": return "Interest";
    case "applied":    return "Applied";
    case "interview":  return "Intvw";
    case "offer":      return "Offer";
    case "closed":     return "Reject";
  }
  return stageKey;
}

// Compact card variant for the board view (no quick-status row, no Apply
// button — they live on the detail drawer to keep columns scannable).
function boardCard(j) {
  const mark = getMark(j.url);
  const tags = [...(j.matched_groups || [])];
  if (j.preferred_location) tags.push("preferred");
  if ((j.location || "").toLowerCase().includes("remote") || j.remote) tags.push("remote");
  const tagHtml = tags.slice(0, 3).map(t => `<span class="tag ${t}">${safe(t)}</span>`).join("");
  const stale = isStale(mark);
  const staleBadge = stale ? `<span class="stale-badge mini" title="No update in ${STALE_DAYS}+ days">stale</span>` : "";
  const noteIcon = mark?.n
    ? `<svg class="board-note-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" title="Has notes"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>`
    : "";
  const subTxt = (mark?.s === "interview" && mark.sub)
    ? `<div class="board-sub">${safe(SUB_STAGES.find(s => s.key === mark.sub)?.label || mark.sub)}</div>`
    : "";
  const nextTxt = mark?.x ? `<div class="board-next" title="Next step">→ ${safe(mark.x)}</div>` : "";
  return `
    <div class="board-card ${stale ? "is-stale" : ""}" data-details="${encodeURIComponent(j.url)}">
      <div class="board-card-head">
        <span class="board-score">${j.score || 0}</span>
        ${noteIcon}
        ${staleBadge}
      </div>
      <div class="board-title">${safe(j.title)}</div>
      <div class="board-company">${safe(j.company)}</div>
      <div class="board-meta">${safe(j.location)} · ${safe(j.source)}</div>
      ${subTxt}${nextTxt}
      <div class="board-tags">${tagHtml}</div>
    </div>
  `;
}

function renderJobs() {
  const filtered = applyFilters(state.jobs);
  const sorted = sortJobs(filtered, state.sortBy);
  document.getElementById("count").textContent = `${sorted.length} of ${state.jobs.length}`;
  const host = document.getElementById("jobs");
  host.classList.toggle("view-board", state.viewMode === "board");
  host.classList.toggle("view-list",  state.viewMode === "list");

  if (!state.selected) {
    host.innerHTML = `<div class="empty-state"><h3>Pick a day</h3><p>Click a highlighted day on the calendar to load that day's jobs.</p></div>`;
    return;
  }
  if (sorted.length === 0) {
    host.innerHTML = `<div class="empty-state"><h3>No matches</h3><p>Try clearing filters, or pick a different day on the calendar.</p></div>`;
    return;
  }

  if (state.viewMode === "board") renderBoard(host, sorted);
  else renderList(host, sorted);

  attachCardHandlers(host);
}

function renderList(host, jobs) {
  host.innerHTML = jobs.map(jobCard).join("");
}

function renderBoard(host, jobs) {
  // Stable bucketing — Unmarked first, then the 5 pipeline stages.
  const buckets = new Map();
  buckets.set("",          { label: "Unmarked", color: "muted",       items: [] });
  for (const col of PIPELINE) buckets.set(col.key, { label: col.label, color: col.color, items: [] });

  for (const j of jobs) {
    const stage = getStage(j.url);
    const target = buckets.has(stage) ? stage : "";
    buckets.get(target).items.push(j);
  }

  const cols = [...buckets.entries()].map(([key, col]) => `
    <div class="board-col stage-col-${key || "none"}">
      <div class="board-col-head">
        <span class="board-col-label dot-${col.color}">${col.label}</span>
        <span class="board-col-count">${col.items.length}</span>
      </div>
      <div class="board-col-body">
        ${col.items.length === 0
          ? `<div class="board-empty">—</div>`
          : col.items.map(boardCard).join("")}
      </div>
    </div>
  `).join("");
  host.innerHTML = `<div class="board-grid">${cols}</div>`;
}

function attachCardHandlers(host) {
  host.querySelectorAll(".status-row button").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const url = decodeURIComponent(btn.dataset.url);
      toggleStage(url, btn.dataset.act);
      refreshKpis();
      renderJobs();
    });
  });
  host.querySelectorAll("[data-details]").forEach(el => {
    el.addEventListener("click", (e) => {
      // Don't intercept clicks on the Apply <a> tag inside cards.
      if (e.target.closest("a")) return;
      e.preventDefault();
      const url = decodeURIComponent(el.dataset.details);
      openDrawer(url);
    });
  });
}

// ───── Detail drawer ─────────────────────────────────────────────────
function findJob(url) { return state.jobs.find(j => j.url === url); }

function openDrawer(url) {
  const j = findJob(url);
  if (!j) { toast("Job not found in current view"); return; }
  state.drawerUrl = url;
  const drawer = document.getElementById("detail-drawer");
  drawer.hidden = false;
  document.body.style.overflow = "hidden";
  renderDrawer();
}
function closeDrawer() {
  document.getElementById("detail-drawer").hidden = true;
  document.body.style.overflow = "";
  state.drawerUrl = null;
}
function renderDrawer() {
  if (!state.drawerUrl) return;
  const j = findJob(state.drawerUrl);
  if (!j) { closeDrawer(); return; }
  const mark = getMark(j.url) || {};
  const stage = mark.s || "";
  const sub = mark.sub || "";

  const stageOpts = [`<option value="">— Unmarked —</option>`]
    .concat(PIPELINE.map(c => `<option value="${c.key}" ${stage === c.key ? "selected" : ""}>${c.label}</option>`))
    .join("");
  const subOpts = SUB_STAGES.map(s => `<option value="${s.key}" ${sub === s.key ? "selected" : ""}>${s.label}</option>`).join("");
  const stale = isStale(mark);

  document.getElementById("drawer-body").innerHTML = `
    <div class="drawer-head-meta">
      <div class="drawer-score-pill">${j.score || 0}<small>score</small></div>
      <div class="drawer-head-text">
        <h3>${safe(j.title)}</h3>
        <div class="drawer-sub">
          <span>${safe(j.company)}</span>
          <span class="meta-sep">·</span>
          <span>${safe(j.location)}</span>
          <span class="meta-sep">·</span>
          <span>${(j.posted_at || "").slice(0, 10) || "—"}</span>
          <span class="meta-sep">·</span>
          <span class="meta-source">${safe(j.source)}</span>
        </div>
        <div class="drawer-actions">
          <a class="btn btn-primary" href="${j.url}" target="_blank" rel="noopener">Open posting ↗</a>
          ${stale ? `<span class="stale-badge">stale ${fmtAgo(mark.u)}</span>` : ""}
        </div>
      </div>
    </div>

    <section class="drawer-section">
      <h4>Stage</h4>
      <div class="drawer-grid-2">
        <label class="drawer-field">
          <span>Pipeline</span>
          <select id="d-stage">${stageOpts}</select>
        </label>
        <label class="drawer-field" id="d-sub-wrap" ${stage !== "interview" ? "hidden" : ""}>
          <span>Interview round</span>
          <select id="d-sub">${subOpts}</select>
        </label>
      </div>
    </section>

    <section class="drawer-section">
      <h4>Tracking</h4>
      <div class="drawer-grid-2">
        <label class="drawer-field">
          <span>Salary range</span>
          <input id="d-salary" type="text" placeholder="e.g. 120-140k base + equity" value="${safe(mark["$"] || "")}" />
        </label>
        <label class="drawer-field">
          <span>Recruiter / contact</span>
          <input id="d-contact" type="text" placeholder="name@company.com or LinkedIn" value="${safe(mark.c || "")}" />
        </label>
      </div>
      <label class="drawer-field">
        <span>Next step</span>
        <input id="d-next" type="text" placeholder="e.g. Phone screen Apr 30 with Sarah" value="${safe(mark.x || "")}" />
      </label>
      <label class="drawer-field">
        <span>Notes</span>
        <textarea id="d-notes" rows="6" placeholder="Interview prep, questions to ask, why this role excites you, prep links…">${safe(mark.n || "")}</textarea>
      </label>
    </section>

    <section class="drawer-section">
      <h4>History</h4>
      <ul class="drawer-history">
        <li><span>Applied</span><span>${mark.ad ? fmtDate(mark.ad) : "—"}</span></li>
        <li><span>Last updated</span><span>${mark.u ? `${fmtDate(mark.u)} (${fmtAgo(mark.u)})` : "—"}</span></li>
        <li><span>Posted</span><span>${j.posted_at ? fmtDate(j.posted_at) : "—"}</span></li>
        ${j.carryover ? `<li><span>Carried from</span><span>${safe(j.carried_from || "—")}</span></li>` : ""}
      </ul>
    </section>

    <section class="drawer-section">
      <h4>Tags</h4>
      <div class="tags">
        ${(j.matched_groups || []).map(t => `<span class="tag ${t}">${safe(t)}</span>`).join("") || `<span class="settings-help">No tags</span>`}
        ${j.preferred_location ? `<span class="tag preferred">preferred</span>` : ""}
        ${((j.location || "").toLowerCase().includes("remote") || j.remote) ? `<span class="tag remote">remote</span>` : ""}
      </div>
    </section>

    <div class="drawer-footer">
      <button id="d-clear" class="btn btn-ghost btn-danger">Clear all marks for this job</button>
    </div>
  `;

  const stageSel = document.getElementById("d-stage");
  const subSel = document.getElementById("d-sub");
  const subWrap = document.getElementById("d-sub-wrap");
  const salary = document.getElementById("d-salary");
  const contact = document.getElementById("d-contact");
  const next = document.getElementById("d-next");
  const notes = document.getElementById("d-notes");

  const persist = () => {
    const s = stageSel.value;
    patchMark(j.url, {
      s,
      sub: s === "interview" ? subSel.value : "",
      "$": salary.value.trim(),
      c: contact.value.trim(),
      x: next.value.trim(),
      n: notes.value,
    });
    refreshKpis();
    renderJobs();
  };

  stageSel.addEventListener("change", () => {
    subWrap.hidden = stageSel.value !== "interview";
    persist();
  });
  subSel.addEventListener("change", persist);
  [salary, contact, next, notes].forEach(el => {
    el.addEventListener("blur", persist);
  });
  document.getElementById("d-clear").addEventListener("click", () => {
    if (!confirm("Clear status, notes, salary, contact and dates for this job?")) return;
    clearMark(j.url);
    refreshKpis();
    renderJobs();
    closeDrawer();
    toast("Job marks cleared");
  });
}

// ───── KPIs ──────────────────────────────────────────────────────────
function refreshKpis() {
  const today = todayISO();
  const todayCount = (state.manifest?.days || []).find(d => d.date === today)?.count || 0;
  const total = (state.manifest?.days || []).reduce((s, d) => s + d.count, 0);
  const counts = { interested: 0, applied: 0, interview: 0, offer: 0, closed: 0 };
  for (const url of Object.keys(state.status)) {
    const stage = getStage(url);
    if (counts[stage] !== undefined) counts[stage]++;
  }
  document.getElementById("kpi-today").textContent = todayCount;
  document.getElementById("kpi-total").textContent = total;
  document.getElementById("kpi-accept").textContent     = counts.interested;
  document.getElementById("kpi-applied").textContent    = counts.applied;
  document.getElementById("kpi-inprogress").textContent = counts.interview;
  document.getElementById("kpi-reject").textContent     = counts.closed;
  const offerKpi = document.getElementById("kpi-offer");
  if (offerKpi) offerKpi.textContent = counts.offer;
  const mc = document.getElementById("marks-count");
  if (mc) mc.textContent = String(Object.keys(state.status).length);
}

// ───── Excel export ──────────────────────────────────────────────────
function exportExcel() {
  if (typeof XLSX === "undefined") { toast("Export library still loading — try again in a second"); return; }
  const filtered = sortJobs(applyFilters(state.jobs), state.sortBy);
  if (filtered.length === 0) { toast("Nothing to export for this view"); return; }
  const rows = filtered.map(j => {
    const m = getMark(j.url) || {};
    return {
      Score: j.score || 0,
      Title: j.title || "",
      Company: j.company || "",
      Location: j.location || "",
      Remote: ((j.location || "").toLowerCase().includes("remote") || j.remote) ? "Yes" : "No",
      Posted: (j.posted_at || "").slice(0, 10),
      Source: j.source || "",
      Groups: (j.matched_groups || []).join(", "),
      Preferred: j.preferred_location ? "Yes" : "No",
      Stage: m.s || "",
      Round: m.sub || "",
      Salary: m["$"] || "",
      Contact: m.c || "",
      "Next step": m.x || "",
      Notes: m.n || "",
      "Applied at": m.ad ? m.ad.slice(0, 10) : "",
      "Last updated": m.u ? m.u.slice(0, 10) : "",
      Carryover: j.carryover ? (j.carried_from || "yes") : "",
      URL: j.url || "",
    };
  });
  const ws = XLSX.utils.json_to_sheet(rows);
  ws["!cols"] = [
    { wch: 6 }, { wch: 42 }, { wch: 22 }, { wch: 24 }, { wch: 7 },
    { wch: 11 }, { wch: 14 }, { wch: 22 }, { wch: 9 }, { wch: 11 },
    { wch: 13 }, { wch: 22 }, { wch: 24 }, { wch: 28 }, { wch: 50 },
    { wch: 12 }, { wch: 12 }, { wch: 12 }, { wch: 50 },
  ];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Jobs");
  XLSX.writeFile(wb, `job-hunter-${state.selected || todayISO()}.xlsx`);
  toast(`Exported ${rows.length} job${rows.length === 1 ? "" : "s"}`);
}

// ───── Marks export / import / clear ─────────────────────────────────
function exportMarks() {
  const payload = {
    exported_at: nowISO(),
    schema: "v2",
    statuses: state.status,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `job-hunter-marks-${todayISO()}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
  toast("Marks exported");
}
function triggerImport() { document.getElementById("import-file").click(); }
async function importMarks(ev) {
  const file = ev.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const data = JSON.parse(text);
    const incoming = data.statuses || data;
    if (typeof incoming !== "object" || Array.isArray(incoming)) throw new Error("bad shape");
    const merged = { ...state.status, ...incoming };
    state.status = merged;
    saveStatus();
    refreshKpis();
    renderJobs();
    toast(`Imported ${Object.keys(incoming).length} marks`);
  } catch {
    toast("Couldn't read that file");
  } finally {
    ev.target.value = "";
  }
}
function purgeLocal() {
  if (!confirm(`Clear all ${Object.keys(state.status).length} marks in this browser? This can't be undone.`)) return;
  state.status = {};
  saveStatus();
  refreshKpis();
  renderJobs();
  toast("Marks cleared");
}

// ───── Refresh ───────────────────────────────────────────────────────
async function refreshData() {
  const btn = document.getElementById("refresh-btn");
  btn.classList.add("spinning");
  try {
    state.byDate.clear();
    await loadManifest({ fresh: true });
    const target = state.selected || latestDay();
    if (target) {
      await loadDay(target, { fresh: true });
      state.jobs = await buildJobsForDate(target);
    }
    renderCalendar();
    renderJobs();
    refreshKpis();
    updateSubtitle();
    toast("Data refreshed");
  } catch {
    toast("Refresh failed — check network");
  } finally {
    setTimeout(() => btn.classList.remove("spinning"), 400);
  }
}

// ───── Settings modal ────────────────────────────────────────────────
function openSettings() {
  const modal = document.getElementById("settings-modal");
  modal.hidden = false;
  document.body.style.overflow = "hidden";
  updateLastRun();
  refreshKpis();
  document.getElementById("carry-toggle").checked = state.carryEnabled;
}
function closeSettings() {
  document.getElementById("settings-modal").hidden = true;
  document.body.style.overflow = "";
}
function updateLastRun() {
  const el = document.getElementById("last-run");
  if (!el) return;
  const gen = state.manifest?.generated_at;
  el.textContent = gen
    ? `Last run: ${new Date(gen).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`
    : "Last run: —";
}

// ───── View toggle + Sort ────────────────────────────────────────────
function setViewMode(mode) {
  state.viewMode = mode;
  localStorage.setItem(VIEW_KEY, mode);
  document.querySelectorAll("[data-view-toggle]").forEach(b => {
    b.classList.toggle("active", b.dataset.viewToggle === mode);
  });
  renderJobs();
}
function setSortBy(by) {
  state.sortBy = by;
  localStorage.setItem(SORT_KEY, by);
  renderJobs();
}

// ───── Boot ──────────────────────────────────────────────────────────
initTheme();

document.getElementById("cal-prev").onclick = () => {
  const v = state.view; v.m--; if (v.m < 0) { v.m = 11; v.y--; } renderCalendar();
};
document.getElementById("cal-next").onclick = () => {
  const v = state.view; v.m++; if (v.m > 11) { v.m = 0; v.y++; } renderCalendar();
};
document.getElementById("today-btn").onclick = () => {
  const days = (state.manifest?.days || []).map(d => d.date);
  const target = days[0];
  if (!target) return;
  const [y, m] = target.split("-").map(Number);
  state.view.y = y; state.view.m = m - 1;
  selectDate(target);
};
document.getElementById("theme-btn").onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme") || "light";
  applyTheme(cur === "dark" ? "light" : "dark");
};
document.getElementById("refresh-btn").onclick = refreshData;
document.getElementById("export-btn").onclick = exportExcel;
document.getElementById("settings-btn").onclick = openSettings;
document.getElementById("settings-modal").addEventListener("click", e => {
  if (e.target.dataset.close === "1") closeSettings();
});
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  const drawer = document.getElementById("detail-drawer");
  const settings = document.getElementById("settings-modal");
  if (!drawer.hidden) closeDrawer();
  else if (!settings.hidden) closeSettings();
});
document.getElementById("carry-toggle").addEventListener("change", async (e) => {
  state.carryEnabled = e.target.checked;
  localStorage.setItem(CARRY_KEY, state.carryEnabled ? "1" : "0");
  if (state.selected) {
    state.jobs = await buildJobsForDate(state.selected);
    renderJobs();
    updateSubtitle();
  }
});
document.getElementById("export-marks").onclick = exportMarks;
document.getElementById("import-marks").onclick = triggerImport;
document.getElementById("import-file").addEventListener("change", importMarks);
document.getElementById("purge-local").onclick = purgeLocal;

// View toggle (List ↔ Board)
document.querySelectorAll("[data-view-toggle]").forEach(btn => {
  btn.addEventListener("click", () => setViewMode(btn.dataset.viewToggle));
});
setViewMode(state.viewMode);

// Sort selector
const sortSel = document.getElementById("sort");
if (sortSel) {
  sortSel.value = state.sortBy;
  sortSel.addEventListener("change", e => setSortBy(e.target.value));
}

// Detail drawer close handlers
document.getElementById("detail-drawer").addEventListener("click", e => {
  if (e.target.dataset.close === "1") closeDrawer();
});

const rerun = document.getElementById("rerun-link");
if (REPO_SLUG) rerun.href = `https://github.com/${REPO_SLUG}/actions/workflows/daily.yml`;
else rerun.style.display = "none";

["q", "group", "status", "loc"].forEach(id => {
  const el = document.getElementById(id);
  if (id === "status") el.value = state.filters.status;
  el.addEventListener("input", e => { state.filters[id] = e.target.value; renderJobs(); });
});

(async () => {
  try {
    await loadManifest();
  } catch {
    document.getElementById("subtitle").textContent =
      "No data yet — open Settings and click 'Run new scrape'.";
    const now = new Date();
    state.view.y = now.getFullYear();
    state.view.m = now.getMonth();
    renderCalendar();
    refreshKpis();
    return;
  }
  const target = latestDay();
  if (target) {
    const [y, m] = target.split("-").map(Number);
    state.view.y = y; state.view.m = m - 1;
    await selectDate(target);
  } else {
    const now = new Date();
    state.view.y = now.getFullYear();
    state.view.m = now.getMonth();
    document.getElementById("subtitle").textContent = "No archives yet — open Settings and click 'Run new scrape'.";
    renderCalendar();
  }
  refreshKpis();
})();
