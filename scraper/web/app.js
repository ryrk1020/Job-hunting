// Job Hunter dashboard — calendar SPA.
// Reads manifest.json + archive/<date>.json. Per-job status persists in localStorage.

const STATUSES = ["accept", "applied", "inprogress", "reject"];
const STATUS_LABEL = { accept: "Accept", applied: "Applied", inprogress: "In Progress", reject: "Reject" };
const STATUS_KEY = "jobhunter.status.v1";

const state = {
  manifest: null,           // {days: [{date, count}], generated_at}
  byDate: new Map(),        // date -> jobs cache
  selected: null,           // selected date string YYYY-MM-DD
  view: { y: null, m: null }, // calendar month being viewed
  jobs: [],                 // currently loaded jobs
  filters: { q: "", group: "", status: "", loc: "" },
  status: loadStatus(),     // url -> status string
};

// ───── Status persistence ────────────────────────────────────────────
function loadStatus() {
  try { return JSON.parse(localStorage.getItem(STATUS_KEY) || "{}"); }
  catch { return {}; }
}
function saveStatus() {
  localStorage.setItem(STATUS_KEY, JSON.stringify(state.status));
}
function setJobStatus(url, status) {
  if (state.status[url] === status) {
    delete state.status[url];   // toggle off
  } else {
    state.status[url] = status;
  }
  saveStatus();
  refreshKpis();
  renderJobs();
}

// ───── Calendar ──────────────────────────────────────────────────────
const MONTHS = ["January","February","March","April","May","June",
                "July","August","September","October","November","December"];
function todayISO() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}
function isoFromYMD(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

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
    if (cnt > 0) {
      cell.classList.add("has-jobs");
      cell.dataset.count = cnt;
    }
    if (iso === today) cell.classList.add("today");
    if (iso === state.selected) cell.classList.add("selected");
    cell.textContent = d;
    cell.dataset.date = iso;
    if (cnt > 0) {
      cell.addEventListener("click", () => selectDate(iso));
    }
    grid.appendChild(cell);
  }
}

document.getElementById("cal-prev").onclick = () => {
  const v = state.view;
  v.m--; if (v.m < 0) { v.m = 11; v.y--; }
  renderCalendar();
};
document.getElementById("cal-next").onclick = () => {
  const v = state.view;
  v.m++; if (v.m > 11) { v.m = 0; v.y++; }
  renderCalendar();
};
document.getElementById("today-btn").onclick = () => {
  const today = todayISO();
  const days = (state.manifest?.days || []).map(d => d.date);
  const target = days.includes(today) ? today : (days[0] || today);
  const [y, m] = target.split("-").map(Number);
  state.view.y = y; state.view.m = m - 1;
  selectDate(target);
};

// ───── Data loading ──────────────────────────────────────────────────
async function loadManifest() {
  const r = await fetch("manifest.json", { cache: "no-store" });
  if (!r.ok) throw new Error("manifest.json not found");
  state.manifest = await r.json();
}

async function loadDay(date) {
  if (state.byDate.has(date)) return state.byDate.get(date);
  const r = await fetch(`archive/${date}.json`, { cache: "no-store" });
  if (!r.ok) return { jobs: [], count: 0 };
  const data = await r.json();
  state.byDate.set(date, data);
  return data;
}

async function selectDate(date) {
  state.selected = date;
  renderCalendar();
  document.getElementById("subtitle").textContent = `Viewing ${date}`;
  const data = await loadDay(date);
  state.jobs = data.jobs || [];
  renderJobs();
  refreshKpis();
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
    const cur = state.status[j.url] || "new";
    if (status && cur !== status) return false;
    return true;
  });
}

function jobCard(j) {
  const tags = [...(j.matched_groups || [])];
  if (j.preferred_location) tags.push("preferred");
  if ((j.location || "").toLowerCase().includes("remote") || j.remote) tags.push("remote");
  const cur = state.status[j.url] || "";
  const safe = (s) => (s || "").replace(/</g, "&lt;");
  const posted = (j.posted_at || "").slice(0, 10);
  const tagHtml = tags.map(t => `<span class="tag ${t}">${t}</span>`).join("");
  const statusBtns = STATUSES.map(s => `
    <button data-act="${s}" data-url="${encodeURIComponent(j.url)}" class="${cur === s ? "active " + s : ""}">${STATUS_LABEL[s]}</button>
  `).join("");
  return `
    <article class="job ${cur ? "status-" + cur : ""}">
      <div class="score-pill">${j.score || 0}<small>score</small></div>
      <div class="job-main">
        <h3><a href="${j.url}" target="_blank" rel="noopener">${safe(j.title)}</a></h3>
        <div class="meta">
          <span>🏢 ${safe(j.company)}</span>
          <span>📍 ${safe(j.location)}</span>
          <span>📅 ${posted || "—"}</span>
          <span>🔗 ${safe(j.source)}</span>
        </div>
        <div class="tags">${tagHtml}</div>
      </div>
      <div class="actions">
        <a class="apply" href="${j.url}" target="_blank" rel="noopener">Apply ↗</a>
        <div class="status-row">${statusBtns}</div>
      </div>
    </article>
  `;
}

function renderJobs() {
  const filtered = applyFilters(state.jobs);
  document.getElementById("count").textContent = `${filtered.length} of ${state.jobs.length} jobs`;
  const host = document.getElementById("jobs");
  if (!state.selected) {
    host.innerHTML = `<div class="empty-state"><h3>Pick a day</h3><p>Click a highlighted day on the calendar to load that day's jobs.</p></div>`;
    return;
  }
  if (filtered.length === 0) {
    host.innerHTML = `<div class="empty-state"><h3>No matches</h3><p>Try clearing filters or pick a different day.</p></div>`;
    return;
  }
  host.innerHTML = filtered.map(jobCard).join("");
  host.querySelectorAll(".status-row button").forEach(btn => {
    btn.addEventListener("click", e => {
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
  for (const v of Object.values(state.status)) {
    if (counts[v] !== undefined) counts[v]++;
  }
  document.getElementById("kpi-today").textContent = todayCount;
  document.getElementById("kpi-total").textContent = total;
  document.getElementById("kpi-accept").textContent = counts.accept;
  document.getElementById("kpi-applied").textContent = counts.applied;
  document.getElementById("kpi-inprogress").textContent = counts.inprogress;
  document.getElementById("kpi-reject").textContent = counts.reject;
}

// ───── Filters wiring ────────────────────────────────────────────────
["q", "group", "status", "loc"].forEach(id => {
  document.getElementById(id).addEventListener("input", e => {
    state.filters[id] = e.target.value;
    renderJobs();
  });
});

// ───── Boot ──────────────────────────────────────────────────────────
(async () => {
  try {
    await loadManifest();
  } catch (e) {
    document.getElementById("subtitle").textContent =
      "manifest.json missing — run the scraper at least once.";
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
    document.getElementById("subtitle").textContent = "No archives yet.";
    renderCalendar();
  }
  refreshKpis();
})();
