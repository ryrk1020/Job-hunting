# Job Hunter

> A daily job-aggregation pipeline + calendar dashboard for an F-1 / OPT
> tech job search in the Dallas–Fort Worth–Frisco metro.

Pulls fresh, real postings from 14 genuine sources every day, filters by
keywords + location + freshness, drops Cognizant and tiny seed-stage
startups, deduplicates **across days** (so the same posting never shows
up twice), and publishes a single-page calendar dashboard to GitHub
Pages with per-job status tracking.

---

## ✨ Highlights

- **14 genuine sources** — official ATS APIs, public RSS feeds, and the
  same unauthenticated endpoints job sites use for their own embedded
  widgets. No logged-in scraping, no shady proxies.
- **50+ unique jobs/day, guaranteed** — auto-widens search if the strict
  filter falls short.
- **Cross-day dedup** — once a posting appears on day X, it is never
  surfaced again. Every day's archive contains only **brand-new** jobs.
- **Calendar dashboard** with month grid, per-day archives, KPI tiles,
  filterable job cards, **Accept / Applied / In Progress / Reject**
  buttons that persist in `localStorage`, and one-click Apply links.
- **Daily GitHub Actions** runs the scraper at 06:00 UTC, commits the
  new archive back to the repo, and republishes Pages automatically.
- **No paid services required** — works out of the box; Adzuna and
  USAJobs are optional free APIs that simply boost volume.

---

## 📅 The dashboard

Open `output/index.html` (or your published Pages URL) to get the SPA
calendar dashboard:

```
┌─ JH  Job Hunter ─────────────────  Today | All-time | Accept | Applied | InProg | Reject ─┐
│                                                                                            │
│  ┌─ Calendar ────────┐   ┌─ Jobs (filterable) ───────────────────────────────────────┐    │
│  │  ‹  April 2026  › │   │  🔎 Search…   [group ▼] [status ▼] [location ▼]  N of M   │    │
│  │  S M T W T F S    │   │  ┌────────────────────────────────────────────────────┐  │    │
│  │  · · · · · · ·    │   │  │ 120  Senior Data Engineer @ Stripe                │  │    │
│  │  · · 5 …  ┌──┐    │   │  │ ━━━ 📍 Dallas, TX  📅 2026-04-22  🔗 greenhouse   │  │    │
│  │  …  20 21 │24│ … │   │  │  [data] [preferred]              [Apply ↗]        │  │    │
│  │           └──┘    │   │  │  [Accept] [Applied] [InProg] [Reject]             │  │    │
│  │  [Jump to today]  │   │  └────────────────────────────────────────────────────┘  │    │
│  └───────────────────┘   └────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

### What you can do in it

| Action            | How                                                                |
|-------------------|--------------------------------------------------------------------|
| Browse a past day | Click a highlighted day on the calendar.                           |
| Jump back to today| Click **Jump to today**.                                           |
| Switch months     | `‹` / `›` on the calendar header.                                  |
| Search jobs       | Type any text in the search box (company, title, location, source).|
| Filter by group   | Group dropdown (data, vibecoding, fullstack, software, qa, …).     |
| Filter by status  | Status dropdown (new, accept, applied, in progress, reject).       |
| Filter by location| Preferred (DFW) or Remote.                                         |
| Mark a job        | Click **Accept**, **Applied**, **In Progress**, or **Reject** on the card. |
| Open the posting  | Click the **Apply ↗** button — opens the source page in a new tab. |
| Track totals      | KPI tiles in the header update live as you mark jobs.              |

Status changes are saved to **browser localStorage**, so they persist
across reloads and sessions on the same machine.

---

## 🔌 Sources

| Source            | Type                  | Needs key? | Notes                                 |
|-------------------|-----------------------|------------|---------------------------------------|
| LinkedIn          | Public guest search   | No         | `jobs-guest/jobs/api/seeMoreJobPostings` |
| Indeed            | Public RSS            | No         | Per-query + per-location feed         |
| Remotive          | Public JSON API       | No         | Remote-only                           |
| RemoteOK          | Public JSON API       | No         | Remote-only                           |
| The Muse          | Public JSON API       | No         |                                       |
| Adzuna            | Free API              | Yes        | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`     |
| USAJobs           | Free API              | Yes        | `USAJOBS_EMAIL`, `USAJOBS_API_KEY`    |
| Greenhouse boards | Public, per-company   | No         | `boards-api.greenhouse.io/v1/boards/<slug>/jobs` |
| Lever boards      | Public, per-company   | No         | `api.lever.co/v0/postings/<slug>`     |
| Ashby boards      | Public, per-company   | No         | `api.ashbyhq.com/posting-api/job-board/<slug>` |
| SmartRecruiters   | Public, per-company   | No         | `api.smartrecruiters.com/v1/companies/<slug>/postings` |
| Workable          | Public embed API      | No         | `apply.workable.com/api/v3/accounts/<slug>/jobs` |
| Workday           | Public tenant JSON    | No         | AT&T, USAA, JPMC, Capital One, Fidelity, Dell, PepsiCo, McKesson, TI, 7-Eleven, Schwab |
| Y Combinator      | Public Algolia index  | No         | Off by default (too much seed stage)  |

Add more companies to any board in `config.yaml` — every template is a single slug.

---

## 🔍 Filters & dedup

All configured in [`config.yaml`](./config.yaml):

- **Keyword groups** (a job must match at least one):
  - `data` — data engineer / analyst / scientist, ETL, BI, Snowflake, Databricks, ML, big data, Tableau, Power BI…
  - `vibecoding` — AI engineer, LLM, GenAI, prompt engineer, applied AI, forward-deployed, RAG, agent, copilot…
  - `fullstack` — full stack, frontend, backend, mobile, React, Angular, Vue, Node, Next.js, iOS, Android…
  - `software` — software engineer / developer, Python, Java, Go, C++, C#, .NET, TypeScript, Ruby, PHP, Scala, Rust, embedded, firmware…
  - `qa` — QA / SDET / tester / test automation / Selenium / Cypress / Playwright
  - `cloud` — DevOps, SRE, cloud engineer, AWS / Azure / GCP, Kubernetes, Terraform
  - `security` — security / cybersecurity / infosec / appsec / network engineer
  - `analyst` — business / systems / product / financial / reporting / operations analyst
  - `product` — PM / TPM / Scrum Master / project manager
  - `junior` — associate / entry-level / new grad (additive scoring boost)
- **Locations**:
  - **Preferred** (scored higher): Frisco, Dallas, Fort Worth, Plano,
    Irving, Arlington, Richardson, Addison, Las Colinas, McKinney,
    Allen, Denton.
  - **Allowed**: any Texas / TX, plus Remote.
- **Freshness**: only jobs posted in the last **7 days** (configurable
  via `max_age_days`).
- **Excludes**: `cognizant` always; everything in
  `exclude.companies_early_stage` (user-extensible denylist for tiny
  seed-stage firms); titles containing `senior staff`, `principal`,
  `director`, `vp `, `head of`.
- **Same-day dedup**: by `(company, title, location)` fingerprint —
  highest-scoring record kept.
- **Cross-day dedup**: every URL + fingerprint we've ever surfaced is
  recorded in `output/seen.json`. The next run filters them out, so
  each day's `archive/<date>.json` only contains **new** jobs.
- **Auto-widen**: if the strict pass returns fewer than
  `min_jobs_target` (default 50), the runner does a second pass
  without the location filter to hit the daily floor.

---

## 🚀 Quick start

```bash
# one-shot, sets up venv and runs everything
./run.sh

# or manually
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scraper.main --config config.yaml --out output

# open the dashboard
open output/index.html      # macOS
xdg-open output/index.html  # Linux
```

### Output files

| Path                          | Purpose                                          |
|-------------------------------|--------------------------------------------------|
| `output/index.html`           | Dashboard SPA entry point                        |
| `output/app.js`               | Dashboard logic (calendar, filters, status)      |
| `output/styles.css`           | Dashboard theme                                  |
| `output/manifest.json`        | List of available days, drives the calendar     |
| `output/archive/YYYY-MM-DD.json` | That day's brand-new jobs                     |
| `output/seen.json`            | Cumulative URL / fingerprint dedup store         |
| `output/jobs.json`            | Latest run, machine-readable                     |
| `output/jobs.csv`             | Same data for Excel / Sheets                     |
| `output/jobs.md`              | Same data for Notion / GitHub                    |

---

## 🔑 Optional free API keys (boost volume)

| API     | Sign-up                          | Env vars                              |
|---------|----------------------------------|----------------------------------------|
| Adzuna  | https://developer.adzuna.com     | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`     |
| USAJobs | https://developer.usajobs.gov    | `USAJOBS_EMAIL`, `USAJOBS_API_KEY`    |

Both are free, take 2 minutes, and add hundreds more postings per day.
Drop them into your shell, a sourced `.env`, or GitHub Actions secrets
— the scraper auto-skips a source if its keys are missing.

---

## 🤖 Daily automation + GitHub Pages

[`.github/workflows/daily.yml`](./.github/workflows/daily.yml) runs the
scraper every day at **06:00 UTC** (≈ 01:00 US Central), commits the
new `output/` (including `seen.json` so cross-day dedup survives) back
to the repo, and republishes the calendar dashboard to GitHub Pages.

### Enable Pages (one-time, ~30 sec)

1. **Settings → Pages → Source: GitHub Actions**.
2. **Actions → daily-scrape → Run workflow** to seed `manifest.json`
   immediately. (Otherwise wait until tomorrow 06:00 UTC.)
3. Open `https://<your-username>.github.io/Job-hunting/` — the
   dashboard loads with today's jobs selected.

### Add the optional API secrets

**Settings → Secrets and variables → Actions → New repository secret**
for any of `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `USAJOBS_EMAIL`,
`USAJOBS_API_KEY`. The workflow reads them via `${{ secrets.* }}`.

---

## 🧰 Extending

| Want to add…                       | Where                                                   |
|------------------------------------|---------------------------------------------------------|
| A new Greenhouse / Lever / Ashby / SmartRecruiters / Workable company | Append its slug to the matching list in `config.yaml`. |
| A new Workday tenant               | Append `{tenant, host, site}` under `workday_tenants:` — find them from the company's careers URL (`<tenant>.<host>.myworkdayjobs.com/<site>`). |
| A new keyword group                | Add under `keywords:` as a list of token lists. All tokens in one list must appear (case-insensitive) to match. |
| A new Indeed / LinkedIn search     | Append `{q, l}` to `indeed_rss_queries` / `linkedin_queries`. |
| A new excluded company             | Add to `exclude.companies` or `exclude.companies_early_stage`. |
| A new entirely-new source          | Add a module under `scraper/sources/`, follow the `Job` dataclass shape, then call it from `scraper/main.py:gather()`. |

---

## 🗂️ Project layout

```
Job-hunting/
├── README.md
├── requirements.txt
├── config.yaml                  # all tunables (keywords, locations, boards, queries)
├── run.sh                       # venv + run + open dashboard
├── .github/workflows/daily.yml  # daily scrape + commit + Pages publish
└── scraper/
    ├── main.py                  # runner: gather → filter → dedup → write
    ├── filters.py               # keyword / location / freshness filters + scoring
    ├── dedup.py                 # cross-day SeenStore (output/seen.json)
    ├── output.py                # JSON / CSV / Markdown / manifest writers
    ├── web/                     # SPA dashboard assets, copied to output/ each run
    │   ├── index.html
    │   ├── styles.css
    │   └── app.js
    └── sources/                 # one adapter per source
        ├── base.py              # shared HttpClient + Job dataclass
        ├── adzuna.py
        ├── ashby.py
        ├── greenhouse.py
        ├── indeed_rss.py
        ├── lever.py
        ├── linkedin.py
        ├── remoteok.py
        ├── remotive.py
        ├── smartrecruiters.py
        ├── themuse.py
        ├── usajobs.py
        ├── workable.py
        ├── workday.py
        └── ycombinator.py
```

---

## ⚖️ Ethics

Every endpoint hit is one of:

- An **official public API** (ATS boards, Remotive, RemoteOK, The Muse,
  Adzuna, USAJobs, SmartRecruiters, Workable, YC).
- A **documented public RSS feed** (Indeed).
- The **unauthenticated endpoint a site uses for its own embedded
  widget** (LinkedIn guest jobs, Workday careers page).

No login, no cookies, no scraping of authenticated content, no
circumvention of access controls. Per-source rate limiting is conservative
(one query at a time, single-digit pages).
