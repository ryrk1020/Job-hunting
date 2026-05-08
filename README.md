# Job Hunter

A daily, automated job-aggregation pipeline and lightweight calendar
dashboard, narrowly tuned for an F-1 / OPT data-engineering job search
in Dallas–Fort Worth and the broader Texas tech market.

The pipeline runs every morning on GitHub Actions, queries 14 sources
(official ATS APIs, public RSS feeds, and the unauthenticated endpoints
that job sites use for their own embedded widgets), filters down to the
top 10 freshly-posted data roles per day, and publishes a static SPA
dashboard to GitHub Pages.

---

## Highlights

| | |
|---|---|
| **Focus** | Data engineering and data analytics roles only. Software, full-stack, QA, cloud, security and other role families are intentionally excluded. |
| **Volume** | Top 10 highest-scoring postings per day. The archive accumulates monotonically across same-day runs and never shrinks. |
| **Freshness** | Strict 2-day window — postings older than 48 hours are dropped. |
| **Cross-day dedup** | Once a posting has been surfaced on day *X*, it is never resurfaced on a later day. Each daily archive contains only brand-new jobs. |
| **Visa-aware filtering** | Postings with explicit citizenship-only language, no-sponsorship clauses, or security-clearance requirements are dropped automatically. |
| **Seniority filtering** | Senior / Staff / Principal / Lead / Director / Architect / numbered grades (Engineer III, Engineer IV, Level 4+, etc.) are excluded. |
| **YoE ceiling** | Postings demanding more than 3 years of experience are dropped (configurable). |
| **Geographic targeting** | DFW preferred (Dallas, Frisco, Plano, Fort Worth, Irving, Richardson, Addison, McKinney, Allen, Las Colinas, Arlington, Denton). All US states accepted. Foreign locations dropped. |
| **Visa-friendly source mix** | Heavy weight on service-MNC employers (Accenture, Deloitte, Infosys, TCS, IBM, NTT Data, KPMG, PwC, EY, etc.) plus mid-stage product and dev-tooling companies that historically sponsor early-career hires. |
| **Daily automation** | Scheduled GitHub Actions workflow at 06:00 UTC commits a new `output/<date>.json` and republishes Pages without manual intervention. |

---

## Dashboard

The published GitHub Pages site is a single static page backed by
`output/manifest.json` and per-day `output/archive/<date>.json` files.
There is no server, no auth, no analytics — every interaction is
browser-local.

```
┌─ Job Hunter [data only] ─────────────────────  Run scrape | Refresh | Export | Theme ─┐
│                                                                                         │
│  Today  3      Selected day  10      Days tracked  14      All-time  127               │
│                                                                                         │
│  ┌─ Calendar ─────────────┐    ┌─ Jobs ─────────────────────────────────────────┐    │
│  │     May 2026           │    │ Search…                  Loc▾   Sort: Score ▾  │    │
│  │  S M T W T F S         │    │ ┌──────────────────────────────────────────┐  │    │
│  │            1 2 3       │    │ │ 135  Data Engineer, Specialist           │  │    │
│  │  4 5 6 7 8 9 10        │    │ │      Vanguard · Dallas, TX · 2026-05-08  │  │    │
│  │  11 12 13 …            │    │ │      [data] [preferred]    Apply ↗  Detl │  │    │
│  │  [Jump to latest]      │    │ │                                          │  │    │
│  └────────────────────────┘    │ └──────────────────────────────────────────┘  │    │
│                                 └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

Capabilities:

| Feature | How |
|---|---|
| Browse a day | Click any highlighted day on the calendar. |
| Filter by location | DFW preferred / Remote / All. |
| Sort | Score · Posted date · Company · Title. |
| Search | Free-text across company, title, location, source. |
| Inspect | Click **Details** to open the slide-in drawer with the full posting description. |
| Apply | Click the **Apply** button on a card or **Open posting** in the drawer — opens the source page in a new tab. |
| Export | One-click XLSX export of the current filtered view. |
| Trigger an ad-hoc scrape | Click **Run scrape** to open the GitHub Actions workflow page; click *Run workflow* there. |

The dashboard intentionally does **not** track application status, notes,
salary, contact info, interview stages, or carry jobs from one day to the
next. Each day's archive is an independent batch of brand-new postings;
once you have applied (or rejected) a posting, it is gone from the feed
because it has already been recorded in the cross-day dedup store.

---

## Sources

| Source | Type | Auth | Notes |
|---|---|---|---|
| LinkedIn | Public guest search | None | `jobs-guest/jobs/api/seeMoreJobPostings` |
| Indeed | Public RSS | None | Per-query × per-location feeds |
| Remotive | Public JSON API | None | Remote-only |
| RemoteOK | Public JSON API | None | Remote-only |
| The Muse | Public JSON API | None | Data-Science / Data-and-Analytics categories |
| Adzuna | Public JSON API | Free key | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` |
| USAJobs | Public JSON API | Free key | `USAJOBS_EMAIL`, `USAJOBS_API_KEY` |
| Greenhouse | Per-company ATS | None | `boards-api.greenhouse.io/v1/boards/<slug>/jobs` (118 boards) |
| Lever | Per-company ATS | None | `api.lever.co/v0/postings/<slug>` (37 boards) |
| Ashby | Per-company ATS | None | `api.ashbyhq.com/posting-api/job-board/<slug>` (44 boards) |
| SmartRecruiters | Per-company ATS | None | `api.smartrecruiters.com/v1/companies/<slug>/postings` |
| Workable | Per-company ATS | None | `apply.workable.com/api/v3/accounts/<slug>/jobs` |
| Workday | Per-tenant search | None | 57 tenants spanning TX-headquartered enterprises (USAA, JPMC, AT&T, Capital One, Fidelity, Schwab, Dell, McKesson, Phillips 66, BNSF, Comerica, Vistra, etc.) and visa-friendly large employers (Salesforce, VMware, Intuit, Adobe, Oracle, Wells Fargo, Citi, T-Mobile, etc.) |
| Y Combinator | Public Algolia index | None | Surfaces early-stage data roles |

A full breakdown of slugs, queries, and tenants lives in
[`config.yaml`](./config.yaml).

---

## Filtering pipeline

1. **Source fetch** — every enabled adapter pulls fresh postings.
2. **Exclusion gate** — drops postings whose company, title, or
   description matches any rule under `exclude:`:
   - `companies` — explicit company denylist (currently `capgemini`).
   - `companies_early_stage` — pre-revenue / stealth tokens.
   - `titles` — substring fallback for senior keywords.
   - `employment` — part-time, intern, co-op, apprentice, seasonal.
   - `work_auth` — citizenship-only language, no-sponsorship clauses,
     security-clearance requirements.
3. **Freshness** — drops anything posted more than `max_age_days` (2)
   ago, or any posting whose `posted_at` cannot be parsed.
4. **Keyword match** — title-scope only. Must contain at least one of
   the data tokens: `data engineer`, `data analyst`, `data scientist`,
   `data warehouse`, `data platform`, `analytics engineer`,
   `bi developer / engineer`, `etl`, `elt`, `snowflake`, `databricks`,
   `redshift`, `bigquery`, `spark`, `airflow`, `dbt`, `kafka`, `hadoop`,
   `informatica`, `tableau`, `power bi`. Short tokens (`bi`, `etl`,
   `dbt`, `elt`) are word-boundary matched so they do not false-positive
   inside unrelated words.
5. **Description guard** — under `strict_experience_filter`, postings
   whose description is shorter than `min_description_chars` (120) are
   dropped, because a hidden "5+ years" requirement cannot be verified.
6. **Years-of-experience** — regex extracts the lower-bound YoE from
   phrases such as `5+ years`, `at least 7 years`, `requires 4 yrs of
   industry experience`, etc. Postings demanding more than
   `max_experience_years` (3) are dropped.
7. **Seniority regex** — drops senior, staff, principal, lead, director,
   VP, head-of, chief, distinguished, fellow, plus numbered grades
   (Engineer III / IV / 4+) and levels (L4, L5, Grade 4, Tier 5).
8. **Location** — DFW preferred (boost), all US states accepted, remote
   accepted only when a US signal is present, foreign-country tokens
   reject the row.
9. **Cross-day dedup** — each previously-emitted URL and
   (company, title, location) fingerprint is recorded in
   `output/seen.json`; matches are dropped from this run's output.
10. **Auto-widen** — if fewer than `min_jobs_target` (10) postings
    survive the strict pipeline, a second pass drops the location
    requirement (foreign-country exclusion still applies) to top up the
    daily floor.
11. **Same-day merge** — today's archive (if any) is merged with this
    run's surviving rows, deduped by URL, sorted by preferred-location
    then score, and capped at 10.

---

## Quick start

```bash
# one-shot — sets up venv, installs deps, runs the scraper, opens the dashboard
./run.sh

# or manually
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scraper.main --config config.yaml --out output

# open the dashboard
open output/index.html      # macOS
xdg-open output/index.html  # Linux
start output/index.html     # Windows
```

### Output layout

| Path | Purpose |
|---|---|
| `output/index.html` | Dashboard SPA entry point |
| `output/app.js` | Dashboard logic |
| `output/styles.css` | Dashboard theme |
| `output/manifest.json` | List of available days; drives the calendar |
| `output/archive/YYYY-MM-DD.json` | That day's top-10 archive |
| `output/seen.json` | Cumulative URL + fingerprint dedup store |
| `output/jobs.json` | Most recent run's machine-readable output |
| `output/jobs.csv` | Same data for spreadsheets |
| `output/jobs.md` | Same data as a Markdown table |

---

## Optional API keys

The pipeline runs with zero credentials by default. Two free public APIs
materially boost the funnel — sign up only if you want them:

| API | Sign-up | Environment variables |
|---|---|---|
| Adzuna | https://developer.adzuna.com | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` |
| USAJobs | https://developer.usajobs.gov | `USAJOBS_EMAIL`, `USAJOBS_API_KEY` |

Drop them into your shell, a sourced `.env`, or *Settings → Secrets and
variables → Actions → New repository secret* on GitHub. The scraper
auto-skips a source whose keys are missing.

---

## Daily automation

[`.github/workflows/daily.yml`](./.github/workflows/daily.yml) runs the
pipeline every day at **06:00 UTC** (≈ 01:00 US Central), commits the
new `output/` directory back to `main` (including `seen.json` so
cross-day dedup survives), and republishes the calendar dashboard to
GitHub Pages.

The workflow also re-triggers on any push to `main` that touches
`scraper/**`, `config.yaml`, or the workflow itself, so iterative
config edits land on the published dashboard within minutes.

### Enable Pages (one-time setup)

1. **Settings → Pages → Source: GitHub Actions**.
2. **Actions → daily-scrape → Run workflow** to seed `manifest.json`
   immediately, or wait for the next 06:00 UTC tick.
3. Open `https://<your-username>.github.io/Job-hunting/` — the
   dashboard loads with the latest day pre-selected.

---

## Customization

| To change… | Edit |
|---|---|
| The keyword set | `keywords:` block in `config.yaml`. Add new token-lists; every token must appear in the title for a match. |
| Title-scope vs. full-text matching | `keyword_match_scope: title \| blob` in `config.yaml`. |
| Daily cap | `min_jobs_target` in `config.yaml`. |
| Freshness window | `max_age_days` in `config.yaml`. |
| Years-of-experience ceiling | `max_experience_years` in `config.yaml`. |
| A new excluded company | Append to `exclude.companies` in `config.yaml`. |
| A new Greenhouse / Lever / Ashby / SmartRecruiters / Workable company | Append the slug to the matching list in `config.yaml`. |
| A new Workday tenant | Append `{tenant, host, site}` under `workday_tenants:` (find them from the company's careers URL: `<tenant>.<host>.myworkdayjobs.com/<site>`). |
| A new Indeed / LinkedIn search | Append `{q, l}` to `indeed_rss_queries` / `linkedin_queries`. |
| An entirely new source | Add an adapter under `scraper/sources/`, follow the `Job` dataclass shape, then call it from `scraper/main.py:gather()`. |

---

## Project layout

```
Job-hunting/
├── README.md
├── requirements.txt
├── config.yaml                 # all tunables — keywords, locations, queries, boards
├── run.sh                      # venv + run + open dashboard
├── .github/workflows/daily.yml # daily scrape + commit + Pages publish
└── scraper/
    ├── main.py                 # runner: gather → filter → dedup → merge → write
    ├── filters.py              # keyword / location / freshness / YoE / seniority filters + scoring
    ├── dedup.py                # cross-day SeenStore (output/seen.json)
    ├── output.py               # JSON / CSV / Markdown / manifest writers; copies dashboard assets
    ├── web/                    # SPA dashboard sources, copied to output/ each run
    │   ├── index.html
    │   ├── styles.css
    │   └── app.js
    └── sources/                # one adapter per source
        ├── base.py             # shared HttpClient + Job dataclass
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

## Operational notes

- **Same-day reruns are safe.** If you push a config change midday,
  the workflow re-runs and merges its findings with the existing
  archive — today's archive only ever grows toward the 10-job cap, never
  shrinks.
- **Zero-row days are not failures.** On slow news days the scraper
  may surface 0 fresh data jobs (everything matched is already in
  `seen.json`). The workflow exits cleanly and republishes the
  dashboard regardless.
- **Reverting a change.** Each material change ships as a
  `--no-ff` merge commit, so a single
  `git revert -m 1 <merge-sha> && git push origin main` undoes
  everything in that change.

---

## Ethics

Every endpoint hit is one of:

- An **official public API** (Greenhouse, Lever, Ashby, SmartRecruiters,
  Workable, Remotive, RemoteOK, The Muse, Adzuna, USAJobs, YC Algolia).
- A **documented public RSS feed** (Indeed).
- The **unauthenticated endpoint a site uses for its own embedded
  widget** (LinkedIn guest jobs, Workday careers page).

No login, no cookies, no scraping of authenticated content, no
circumvention of access controls. Per-source rate limiting is
conservative — single-digit pages, one query at a time.

---

## License

Personal-use repository. No license granted; do not republish without
permission.
