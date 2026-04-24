// Job Hunter dashboard — calendar SPA with theme toggle, refresh,
// Excel export, GitHub-backed cross-device status sync, and carry-forward
// visualization.

const STATUSES = ["accept", "applied", "inprogress", "reject"];
const STATUS_LABEL = { accept: "Accept", applied: "Applied", inprogress: "In Prog", reject: "Reject" };
const STATUS_KEY = "jobhunter.status.v1";
const THEME_KEY  = "jobhunter.theme";
const PAT_KEY    = "jobhunter.pat";
const STATUS_FILE = "output/status.json";
const REPO_SLUG  = detectRepoSlug();

const state = {
  manifest: null,
  byDate: new Map(),
  selected: null,
  view: { y: null, m: null },
  jobs: [],
  filters: { q: "", group: "", status: "unmarked", loc: "" },
  status: loadStatus(),
  statusSha: null,      // sha of output/status.json for GitHub PUTs
  syncState: "local",   // local | syncing | synced | error
  pushTimer: null,
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
function b64utf8(s) {
  // btoa doesn't handle UTF-8; encode as bytes first.
  return btoa(String.fromCharCode(...new TextEncoder().encode(s)));
}

function toast(msg, ms = 2200) {
  let el = document.querySelector(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
  el.textContent = msg;
  requestAnimationFrame(() => el.classList.add("show"));
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), ms);
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

// ───── Status store (localStorage + GitHub sync) ─────────────────────
function loadStatus() {
  try { return JSON.parse(localStorage.getItem(STATUS_KEY) || "{}"); }
  catch { return {}; }
}
function saveStatus() { localStorage.setItem(STATUS_KEY, JSON.stringify(state.status)); }
function hasPAT() { return !!localStorage.getItem(PAT_KEY); }
function setSyncState(s) {
  state.syncState = s;
  const chip = document.getElementById("sync-chip");
  if (!chip) return;
  chip.dataset.state = s;
  const labels = { local: "Local", syncing: "Syncing", synced: "Synced", error: "Sync error", offline: "Offline" };
  chip.querySelector(".sync-label").textContent = labels[s] || s;
  chip.title = {
    local:   "Marks are saved in this browser only. Open Settings to enable cross-device sync.",
    syncing: "Pushing changes to GitHub…",
    synced:  "All marks are synced to GitHub.",
    error:   "Sync failed — check your token or connection.",
    offline: "Offline — changes will sync when you're back online.",
  }[s] || "";
}

function setJobStatus(url, status) {
  if (state.status[url] === status) delete state.status[url];
  else state.status[url] = status;
  saveStatus();
  refreshKpis();
  renderJobs();
  schedulePush();
}

// ───── GitHub sync ───────────────────────────────────────────────────
async function ghGetStatusFile() {
  // Try authenticated first if we have a PAT — fresher + gives us the sha.
  if (hasPAT() && REPO_SLUG) {
    const r = await fetch(`https://api.github.com/repos/${REPO_SLUG}/contents/${STATUS_FILE}`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem(PAT_KEY)}`,
        Accept: "application/vnd.github+json",
      },
    });
    if (r.status === 404) return { statuses: {}, sha: null };
    if (r.ok) {
      const j = await r.json();
      try {
        const text = new TextDecoder().decode(Uint8Array.from(atob(j.content.replace(/\s/g, "")), c => c.charCodeAt(0)));
        const parsed = JSON.parse(text);
        return { statuses: parsed.statuses || {}, sha: j.sha };
      } catch { return { statuses: {}, sha: j.sha }; }
    }
    if (r.status === 401 || r.status === 403) {
      setSyncState("error");
      return null;
    }
  }
  // Fall back to the Pages copy (may be stale due to CDN caching).
  try {
    const r = await fetch(`${STATUS_FILE}?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) return { statuses: {}, sha: null };
    const j = await r.json();
    return { statuses: j.statuses || {}, sha: null };
  } catch {
    return { statuses: {}, sha: null };
  }
}

async function ghPutStatusFile() {
  if (!hasPAT() || !REPO_SLUG) return false;
  const body = {
    updated_at: new Date().toISOString(),
    statuses: state.status,
  };
  const content = b64utf8(JSON.stringify(body, null, 2) + "\n");
  const put = async (sha) => {
    const payload = {
      message: `chore: sync job statuses (${Object.keys(state.status).length} entries)`,
      content,
    };
    if (sha) payload.sha = sha;
    const r = await fetch(`https://api.github.com/repos/${REPO_SLUG}/contents/${STATUS_FILE}`, {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${localStorage.getItem(PAT_KEY)}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    return r;
  };
  let r = await put(state.statusSha);
  // Stale sha on race — fetch fresh and retry once.
  if (r.status === 409 || r.status === 422) {
    const fresh = await ghGetStatusFile();
    if (fresh) {
      state.statusSha = fresh.sha;
      r = await put(state.statusSha);
    }
  }
  if (!r.ok) return false;
  const j = await r.json();
  state.statusSha = j.content?.sha || state.statusSha;
  return true;
}

function schedulePush() {
  if (!hasPAT()) return;
  setSyncState("syncing");
  clearTimeout(state.pushTimer);
  state.pushTimer = setTimeout(async () => {
    if (!navigator.onLine) { setSyncState("offline"); return; }
    const ok = await ghPutStatusFile();
    setSyncState(ok ? "synced" : "error");
  }, 1500);
}

async function pullRemoteStatus() {
  const res = await ghGetStatusFile();
  if (!res) return;
  state.statusSha = res.sha;
  // Merge: remote is authoritative for entries not in local (other
  // devices). Local stays if both disagree and the timestamp on local
  // is fresher — but we don't track per-entry timestamps, so on any
  // disagreement we trust remote (last writer wins at GitHub).
  const remote = res.statuses || {};
  const merged = { ...remote, ...state.status };
  // Actually, prefer remote to make cross-device convergence work.
  // Only keep local entries for URLs remote doesn't know about yet.
  for (const k of Object.keys(remote)) merged[k] = remote[k];
  state.status = merged;
  saveStatus();
  refreshKpis();
  renderJobs();
  if (hasPAT()) setSyncState("synced");
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

async function selectDate(date) {
  state.selected = date;
  renderCalendar();
  updateSubtitle();
  const data = await loadDay(date);
  state.jobs = data.jobs || [];
  renderJobs();
  refreshKpis();
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

// ───── Jobs rendering ────────────────────────────────────────────────
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
    const cur = state.status[j.url] || "";
    if (status === "unmarked" && cur) return false;
    if (status && status !== "unmarked" && cur !== status) return false;
    return true;
  });
}

function jobCard(j) {
  const tags = [...(j.matched_groups || [])];
  if (j.preferred_location) tags.push("preferred");
  if ((j.location || "").toLowerCase().includes("remote") || j.remote) tags.push("remote");
  const cur = state.status[j.url] || "";
  const posted = (j.posted_at || "").slice(0, 10);
  const tagHtml = tags.map(t => `<span class="tag ${t}">${t}</span>`).join("");
  const statusBtns = STATUSES.map(s => `
    <button data-act="${s}" data-url="${encodeURIComponent(j.url)}" class="${cur === s ? "active " + s : ""}">${STATUS_LABEL[s]}</button>
  `).join("");
  const carryBadge = j.carryover
    ? `<span class="carry-badge" title="Carried over from ${safe(j.carried_from || "a previous day")}">carried over</span>`
    : "";
  return `
    <article class="job ${cur ? "status-" + cur : ""} ${j.carryover ? "is-carryover" : ""}">
      <div class="score-pill">${j.score || 0}<small>score</small></div>
      <div class="job-main">
        <h3><a href="${j.url}" target="_blank" rel="noopener">${safe(j.title)}</a>${carryBadge}</h3>
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
        <div class="status-row">${statusBtns}</div>
      </div>
    </article>
  `;
}

function renderJobs() {
  const filtered = applyFilters(state.jobs);
  document.getElementById("count").textContent = `${filtered.length} of ${state.jobs.length}`;
  const host = document.getElementById("jobs");
  if (!state.selected) {
    host.innerHTML = `<div class="empty-state"><h3>Pick a day</h3><p>Click a highlighted day on the calendar to load that day's jobs.</p></div>`;
    return;
  }
  if (filtered.length === 0) {
    host.innerHTML = `<div class="empty-state"><h3>No matches</h3><p>Try clearing filters, or pick a different day on the calendar.</p></div>`;
    return;
  }
  host.innerHTML = filtered.map(jobCard).join("");
  host.querySelectorAll(".status-row button").forEach(btn => {
    btn.addEventListener("click", () => {
      const url = decodeURIComponent(btn.dataset.url);
      setJobStatus(url, btn.dataset.act);
    });
  });
}

// ───── KPIs ──────────────────────────────────────────────────────────
function refreshKpis() {
  const today = todayISO();
  const todayCount = (state.manifest?.days || []).find(d => d.date === today)?.count || 0;
  const total = (state.manifest?.days || []).reduce((s, d) => s + d.count, 0);
  const counts = { accept: 0, applied: 0, inprogress: 0, reject: 0 };
  for (const v of Object.values(state.status)) if (counts[v] !== undefined) counts[v]++;
  document.getElementById("kpi-today").textContent = todayCount;
  document.getElementById("kpi-total").textContent = total;
  document.getElementById("kpi-accept").textContent = counts.accept;
  document.getElementById("kpi-applied").textContent = counts.applied;
  document.getElementById("kpi-inprogress").textContent = counts.inprogress;
  document.getElementById("kpi-reject").textContent = counts.reject;
}

// ───── Excel export ──────────────────────────────────────────────────
function exportExcel() {
  if (typeof XLSX === "undefined") { toast("Export library still loading — try again in a second"); return; }
  const filtered = applyFilters(state.jobs);
  if (filtered.length === 0) { toast("Nothing to export for this view"); return; }
  const rows = filtered.map(j => ({
    Score: j.score || 0,
    Title: j.title || "",
    Company: j.company || "",
    Location: j.location || "",
    Remote: ((j.location || "").toLowerCase().includes("remote") || j.remote) ? "Yes" : "No",
    Posted: (j.posted_at || "").slice(0, 10),
    Source: j.source || "",
    Groups: (j.matched_groups || []).join(", "),
    Preferred: j.preferred_location ? "Yes" : "No",
    Status: state.status[j.url] || "",
    Carryover: j.carryover ? (j.carried_from || "yes") : "",
    URL: j.url || "",
  }));
  const ws = XLSX.utils.json_to_sheet(rows);
  ws["!cols"] = [
    { wch: 6 }, { wch: 42 }, { wch: 22 }, { wch: 24 }, { wch: 7 },
    { wch: 11 }, { wch: 14 }, { wch: 22 }, { wch: 9 }, { wch: 11 },
    { wch: 12 }, { wch: 50 },
  ];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Jobs");
  XLSX.writeFile(wb, `job-hunter-${state.selected || todayISO()}.xlsx`);
  toast(`Exported ${rows.length} job${rows.length === 1 ? "" : "s"}`);
}

// ───── Refresh ───────────────────────────────────────────────────────
async function refreshData() {
  const btn = document.getElementById("refresh-btn");
  btn.classList.add("spinning");
  try {
    state.byDate.clear();
    await loadManifest({ fresh: true });
    await pullRemoteStatus();
    const target = state.selected || state.manifest?.days?.[0]?.date;
    if (target) {
      const data = await loadDay(target, { fresh: true });
      state.jobs = data.jobs || [];
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
  const input = document.getElementById("pat-input");
  input.value = "";   // never pre-fill; just show a status chip
  updatePATStatus();
  updateLastRun();
}
function closeSettings() {
  document.getElementById("settings-modal").hidden = true;
  document.body.style.overflow = "";
}
function updatePATStatus() {
  const chip = document.getElementById("pat-status");
  if (hasPAT()) {
    chip.textContent = "Connected";
    chip.className = "chip chip-ok";
  } else {
    chip.textContent = "Not connected";
    chip.className = "chip chip-muted";
  }
}
function updateLastRun() {
  const el = document.getElementById("last-run");
  if (!el) return;
  const gen = state.manifest?.generated_at;
  el.textContent = gen
    ? `Last run: ${new Date(gen).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`
    : "Last run: —";
}
async function savePAT() {
  const input = document.getElementById("pat-input");
  const v = (input.value || "").trim();
  if (!v) { toast("Paste a token first"); return; }
  // Light-touch shape check: real GitHub PATs start with ghp_, gho_, github_pat_, etc.
  if (!/^(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)/.test(v)) {
    if (!confirm("That doesn't look like a GitHub token prefix. Save anyway?")) return;
  }
  localStorage.setItem(PAT_KEY, v);
  input.value = "";
  updatePATStatus();
  setSyncState("syncing");
  // Validate + pull + initial push so the user sees immediate feedback.
  try {
    await pullRemoteStatus();
    const ok = await ghPutStatusFile();
    setSyncState(ok ? "synced" : "error");
    toast(ok ? "Connected & synced" : "Token saved but push failed — check scope");
  } catch {
    setSyncState("error");
    toast("Couldn't reach GitHub");
  }
}
function clearPAT() {
  localStorage.removeItem(PAT_KEY);
  updatePATStatus();
  setSyncState("local");
  toast("Token removed");
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
  const today = todayISO();
  const days = (state.manifest?.days || []).map(d => d.date);
  const target = days.includes(today) ? today : (days[0] || today);
  const [y, m] = target.split("-").map(Number);
  state.view.y = y; state.view.m = m - 1;
  if (days.includes(target)) selectDate(target); else renderCalendar();
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
  if (e.key === "Escape" && !document.getElementById("settings-modal").hidden) closeSettings();
});
document.getElementById("pat-save").onclick = savePAT;
document.getElementById("pat-clear").onclick = clearPAT;
document.getElementById("purge-local").onclick = () => {
  if (!confirm("Clear all locally-cached marks in this browser? (GitHub sync, if connected, will not be touched.)")) return;
  state.status = {};
  saveStatus();
  refreshKpis();
  renderJobs();
  toast("Local marks cleared");
};

const rerun = document.getElementById("rerun-link");
if (REPO_SLUG) rerun.href = `https://github.com/${REPO_SLUG}/actions/workflows/daily.yml`;
else rerun.style.display = "none";

window.addEventListener("online",  () => hasPAT() && setSyncState("synced"));
window.addEventListener("offline", () => hasPAT() && setSyncState("offline"));

["q", "group", "status", "loc"].forEach(id => {
  const el = document.getElementById(id);
  if (id === "status") el.value = state.filters.status;
  el.addEventListener("input", e => { state.filters[id] = e.target.value; renderJobs(); });
});

setSyncState(hasPAT() ? "synced" : "local");

(async () => {
  // Kick off remote status pull in parallel with manifest load.
  const statusPromise = pullRemoteStatus().catch(() => {});
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
    await statusPromise;
    return;
  }
  const days = state.manifest.days || [];
  const today = todayISO();
  const target = days.find(d => d.date === today)?.date || days[0]?.date;
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
  await statusPromise;
  renderJobs();
  refreshKpis();
})();
