// Job Hunter dashboard — calendar SPA, browse-and-apply only.
// Each day's archive is shown standalone. No carry-forward, no Kanban,
// no per-job marks. Just the top 10 fresh data jobs for the selected day.

const THEME_KEY = "jobhunter.theme";
const SORT_KEY  = "jobhunter.sort";

const REPO_SLUG = detectRepoSlug();

const state = {
  manifest: null,
  byDate: new Map(),
  selected: null,
  view: { y: null, m: null },
  jobs: [],
  filters: { q: "", loc: "" },
  sortBy: localStorage.getItem(SORT_KEY) || "score",
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

async function selectDate(date) {
  state.selected = date;
  renderCalendar();
  const data = await loadDay(date);
  state.jobs = (data.jobs || []).map(j => ({ ...j }));
  renderJobs();
  updateSubtitle();
  refreshKpis();
}

function updateSubtitle() {
  const el = document.getElementById("subtitle");
  if (!state.selected) { el.textContent = "Pick a day on the calendar"; return; }
  const gen = state.manifest?.generated_at
    ? new Date(state.manifest.generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : null;
  el.textContent = `${fmtDate(state.selected)}${gen ? ` · scraped ${gen}` : ""}`;
}

// ───── Sort + Filter ─────────────────────────────────────────────────
function sortJobs(jobs, by) {
  const arr = [...jobs];
  switch (by) {
    case "posted":
      return arr.sort((a, b) => new Date(b.posted_at || 0) - new Date(a.posted_at || 0));
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

function applyFilters(jobs) {
  const { q, loc } = state.filters;
  const ql = q.toLowerCase();
  return jobs.filter(j => {
    if (q) {
      const blob = `${j.company || ""} ${j.title || ""} ${j.location || ""} ${j.source || ""}`.toLowerCase();
      if (!blob.includes(ql)) return false;
    }
    if (loc === "preferred" && !j.preferred_location) return false;
    if (loc === "remote" && !((j.location || "").toLowerCase().includes("remote") || j.remote)) return false;
    return true;
  });
}

// ───── Card rendering ────────────────────────────────────────────────
function jobCard(j) {
  const tags = [];
  if (j.preferred_location) tags.push("preferred");
  if ((j.location || "").toLowerCase().includes("remote") || j.remote) tags.push("remote");
  for (const g of (j.matched_groups || [])) tags.push(g);
  const tagHtml = tags.map(t => `<span class="tag tag-${t}">${safe(t)}</span>`).join("");
  const posted = (j.posted_at || "").slice(0, 10);
  return `
    <article class="job" data-url="${encodeURIComponent(j.url)}">
      <div class="job-score" title="Match score">${j.score || 0}</div>
      <div class="job-main">
        <h3 class="job-title">
          <a href="${j.url}" target="_blank" rel="noopener">${safe(j.title)}</a>
        </h3>
        <div class="job-meta">
          <span class="job-company">${safe(j.company)}</span>
          <span class="meta-sep">·</span>
          <span class="job-loc">${safe(j.location)}</span>
          <span class="meta-sep">·</span>
          <span class="job-posted">${posted || "—"}</span>
          <span class="meta-sep">·</span>
          <span class="job-source">${safe(j.source)}</span>
        </div>
        <div class="job-tags">${tagHtml}</div>
      </div>
      <div class="job-actions">
        <a class="btn btn-primary" href="${j.url}" target="_blank" rel="noopener">Apply ↗</a>
        <button class="btn btn-ghost" data-details="${encodeURIComponent(j.url)}">Details</button>
      </div>
    </article>
  `;
}

function renderJobs() {
  const filtered = applyFilters(state.jobs);
  const sorted = sortJobs(filtered, state.sortBy);
  document.getElementById("count").textContent = `${sorted.length} of ${state.jobs.length}`;
  const host = document.getElementById("jobs");

  if (!state.selected) {
    host.innerHTML = `<div class="empty-state"><h3>Pick a day</h3><p>Click a highlighted day on the calendar.</p></div>`;
    return;
  }
  if (sorted.length === 0) {
    host.innerHTML = `<div class="empty-state"><h3>No matches</h3><p>This day has no jobs that fit your filters — try clearing the search.</p></div>`;
    return;
  }
  host.innerHTML = sorted.map(jobCard).join("");
  host.querySelectorAll("[data-details]").forEach(el => {
    el.addEventListener("click", e => {
      if (e.target.closest("a")) return;
      e.preventDefault();
      openDrawer(decodeURIComponent(el.dataset.details));
    });
  });
}

// ───── Detail drawer ─────────────────────────────────────────────────
function findJob(url) { return state.jobs.find(j => j.url === url); }

function openDrawer(url) {
  const j = findJob(url);
  if (!j) { toast("Job not found"); return; }
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
  const tags = [];
  if (j.preferred_location) tags.push("preferred");
  if ((j.location || "").toLowerCase().includes("remote") || j.remote) tags.push("remote");
  for (const g of (j.matched_groups || [])) tags.push(g);
  const tagHtml = tags.map(t => `<span class="tag tag-${t}">${safe(t)}</span>`).join("");

  document.getElementById("drawer-body").innerHTML = `
    <div class="drawer-head-meta">
      <div class="drawer-score">${j.score || 0}<small>score</small></div>
      <div class="drawer-head-text">
        <h3>${safe(j.title)}</h3>
        <div class="drawer-sub">
          <span><strong>${safe(j.company)}</strong></span>
          <span class="meta-sep">·</span>
          <span>${safe(j.location)}</span>
        </div>
        <div class="drawer-sub">
          <span>Posted ${fmtDate(j.posted_at)}</span>
          <span class="meta-sep">·</span>
          <span class="meta-source">${safe(j.source)}</span>
        </div>
        <div class="drawer-actions">
          <a class="btn btn-primary" href="${j.url}" target="_blank" rel="noopener">Open posting ↗</a>
        </div>
      </div>
    </div>
    ${tags.length ? `<section class="drawer-section"><h4>Tags</h4><div class="job-tags">${tagHtml}</div></section>` : ""}
    <section class="drawer-section">
      <h4>Description</h4>
      <div class="drawer-desc">${safe(j.description || "").slice(0, 4000) || "No description available."}</div>
    </section>
  `;
}

// ───── KPIs ──────────────────────────────────────────────────────────
function refreshKpis() {
  const today = todayISO();
  const days = state.manifest?.days || [];
  const todayCount = days.find(d => d.date === today)?.count || 0;
  const total = days.reduce((s, d) => s + d.count, 0);
  const sel = state.selected ? (days.find(d => d.date === state.selected)?.count || 0) : 0;
  document.getElementById("kpi-today").textContent = todayCount;
  document.getElementById("kpi-total").textContent = total;
  document.getElementById("kpi-selected").textContent = sel;
  document.getElementById("kpi-days").textContent = days.length;
}

// ───── Excel export ──────────────────────────────────────────────────
function exportExcel() {
  if (typeof XLSX === "undefined") { toast("Export library still loading"); return; }
  const filtered = sortJobs(applyFilters(state.jobs), state.sortBy);
  if (filtered.length === 0) { toast("Nothing to export"); return; }
  const rows = filtered.map(j => ({
    Score: j.score || 0,
    Title: j.title || "",
    Company: j.company || "",
    Location: j.location || "",
    Remote: ((j.location || "").toLowerCase().includes("remote") || j.remote) ? "Yes" : "No",
    Posted: (j.posted_at || "").slice(0, 10),
    Source: j.source || "",
    Preferred: j.preferred_location ? "Yes" : "No",
    URL: j.url || "",
  }));
  const ws = XLSX.utils.json_to_sheet(rows);
  ws["!cols"] = [{wch:6},{wch:42},{wch:22},{wch:24},{wch:7},{wch:11},{wch:14},{wch:9},{wch:50}];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Jobs");
  XLSX.writeFile(wb, `job-hunter-${state.selected || todayISO()}.xlsx`);
  toast(`Exported ${rows.length} jobs`);
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
      const data = state.byDate.get(target);
      state.jobs = (data?.jobs || []).map(j => ({ ...j }));
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

// ───── Boot ──────────────────────────────────────────────────────────
initTheme();

document.getElementById("cal-prev").onclick = () => {
  const v = state.view; v.m--; if (v.m < 0) { v.m = 11; v.y--; } renderCalendar();
};
document.getElementById("cal-next").onclick = () => {
  const v = state.view; v.m++; if (v.m > 11) { v.m = 0; v.y++; } renderCalendar();
};
document.getElementById("today-btn").onclick = () => {
  const target = (state.manifest?.days || [])[0]?.date;
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

document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  const drawer = document.getElementById("detail-drawer");
  if (!drawer.hidden) closeDrawer();
});
document.getElementById("detail-drawer").addEventListener("click", e => {
  if (e.target.dataset.close === "1") closeDrawer();
});

const sortSel = document.getElementById("sort");
sortSel.value = state.sortBy;
sortSel.addEventListener("change", e => {
  state.sortBy = e.target.value;
  localStorage.setItem(SORT_KEY, state.sortBy);
  renderJobs();
});

["q", "loc"].forEach(id => {
  const el = document.getElementById(id);
  el.addEventListener("input", e => { state.filters[id] = e.target.value; renderJobs(); });
});

const rerun = document.getElementById("rerun-link");
if (REPO_SLUG) rerun.href = `https://github.com/${REPO_SLUG}/actions/workflows/daily.yml`;
else rerun.style.display = "none";

(async () => {
  try {
    await loadManifest();
  } catch {
    document.getElementById("subtitle").textContent =
      "No data yet — wait for tomorrow's 06:00 UTC scrape, or trigger one from Actions.";
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
    document.getElementById("subtitle").textContent = "No archives yet — first scrape will run on schedule.";
    renderCalendar();
    refreshKpis();
  }
})();
