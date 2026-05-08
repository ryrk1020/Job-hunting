<div align="center">

# Job Hunter

**A precision job-aggregation pipeline for an F-1 / OPT data-engineering search in Texas.**

Aggregates roles from 16 sources, filters to fewer than 0.2% of intake,
ranks by directness-to-apply, and publishes the day's top 20 to a
static dashboard — fully automated on GitHub Actions, no servers, no
secrets required.

[![daily-scrape](https://github.com/ryrk1020/Job-hunting/actions/workflows/daily.yml/badge.svg)](https://github.com/ryrk1020/Job-hunting/actions/workflows/daily.yml)
[![weekly-cleanup](https://github.com/ryrk1020/Job-hunting/actions/workflows/weekly-cleanup.yml/badge.svg)](https://github.com/ryrk1020/Job-hunting/actions/workflows/weekly-cleanup.yml)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![License](https://img.shields.io/badge/license-personal--use-lightgrey.svg)

</div>

---

## At a glance

```
                       ┌────────────────────┐
                       │   16 sources       │
                       │   ATS · RSS · APIs │
                       └─────────┬──────────┘
                                 │  ~12,000 raw postings/day
                                 ▼
   ┌─────────────────────────────────────────────────────────┐
   │  Pipeline (scraper/filters.py)                          │
   │  ├─ Excludes: senior, no-sponsorship, clearance, etc.   │
   │  ├─ Title-scope keyword match (data only)               │
   │  ├─ Years-of-experience cap (≤ 3 yrs)                   │
   │  ├─ US-only location, DFW preferred                     │
   │  ├─ 7-day freshness window                              │
   │  ├─ Cross-source dedup → most-direct apply URL          │
   │  ├─ Cross-day dedup (output/seen.json)                  │
   │  └─ Top-20 cap, sorted by score                         │
   └─────────────────────────────┬───────────────────────────┘
                                 │
                                 ▼
                ┌────────────────────────────────┐
                │  output/archive/YYYY-MM-DD.json│
                │  output/manifest.json          │
                │  output/seen.json              │
                └────────────────┬───────────────┘
                                 │
                                 ▼
            ┌────────────────────────────────────────┐
            │  Static SPA dashboard (GitHub Pages)   │
            │  Calendar · Search · Sort · Drawer     │
            └────────────────────────────────────────┘
```

---

## What ships

| Capability | Detail |
|---|---|
| **Daily run** | GitHub Actions cron at 06:00 UTC. Every push to `main` that touches scraping logic re-runs the full pipeline. |
| **Sources (16)** | LinkedIn, Indeed, Remotive, RemoteOK, The Muse, Adzuna, USAJobs, Greenhouse (118 boards), Lever (37), Ashby (44), SmartRecruiters (16), Workable (13), Workday (57 tenants), Y Combinator, Built In, Dice. |
| **Daily volume** | Cap of 20 highest-scoring postings. Same-day re-runs *accumulate* — they never shrink the archive. |
| **Freshness** | 7-day rolling window. Older postings drop, fresher postings out-rank stale ones via graduated decay scoring. |
| **Cross-source dedup** | The same role posted on Greenhouse + LinkedIn + Indeed is collapsed to a single card whose primary URL is the most-direct apply path; the others appear under *Also seen on*. |
| **Cross-day dedup** | A persistent `seen.json` ensures no posting is ever surfaced twice. Refreshed-by-employer postings can resurface only after a weekly link-health sweep removes dead URLs from the store. |
| **Visa-aware filtering** | Postings naming citizenship-only requirements, security clearance, or explicit no-sponsorship language are dropped before scoring. |
| **Salary parsing** | Extracts `$Xk-$Yk`, `$X,XXX-$Y,YYY`, `salary range: A-B`, *up to / from* phrasings. Score boost when published. |
| **Tech-stack tagging** | Auto-detects Snowflake, Databricks, Spark, Airflow, dbt, Kafka, Hadoop, Redshift, BigQuery, Tableau, Power BI, Informatica, Python, SQL, AWS, Azure, GCP, Kubernetes per posting. |
| **Resilient** | Per-source crash isolation, urllib3 retries with backoff, atomic file writes, Workday tenant circuit breaker, 33 unit tests gating CI. |
| **Costs** | Zero. Free tier of GitHub Actions + GitHub Pages. Two optional free APIs (Adzuna, USAJobs) boost volume but aren't required. |

---

## Dashboard

Static SPA hosted on GitHub Pages. No backend, no auth, no analytics —
every interaction is browser-local.

```
┌─ Job Hunter [data only] ─────────────────  Run scrape · Refresh · Export · Theme ─┐
│                                                                                     │
│  Today  20      Selected day  20      Days tracked  14      All-time  287          │
│                                                                                     │
│  ┌─ Calendar ───────────┐    ┌─ Jobs ─────────────────────────────────────────┐   │
│  │      May 2026        │    │  Search…                Loc▾   Sort: Score ▾  │   │
│  │  S M T W T F S       │    │  ┌──────────────────────────────────────────┐  │   │
│  │            1 2 3     │    │  │ 135  Data Engineer, Specialist  $95-130k │  │   │
│  │  4 5 6 7 8 9 10      │    │  │      Vanguard · Dallas, TX · 2026-05-08  │  │   │
│  │  11 12 13 …          │    │  │      [data] [preferred] [direct apply]   │  │   │
│  │  [Jump to latest]    │    │  │       snowflake · airflow · dbt · sql    │  │   │
│  └──────────────────────┘    │  │                       Apply ↗   Details  │  │   │
│                              │  └──────────────────────────────────────────┘  │   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

| Action | How |
|---|---|
| Browse a day | Click any highlighted day on the calendar. |
| Search | Free-text across company, title, location, source. |
| Sort | Score · Salary (high → low) · Posted date · Company · Title. |
| Filter location | DFW preferred · Remote · All. |
| Inspect | *Details* opens a slide-in drawer with the full description, tags, salary, alt-source links. |
| Apply | *Apply ↗* button on a card or *Open posting ↗* in the drawer. Opens the most-direct URL we found across sources. |
| Export | One-click XLSX of the current filtered view. |
| Trigger an ad-hoc run | *Run scrape* opens the GitHub Actions workflow page; click *Run workflow* there. |

---

## Quick start

```bash
# one-shot: venv + deps + run + open dashboard
./run.sh

# or, manually:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v        # gate
python -m scraper.main --config config.yaml --out output

# open output/index.html in any browser
```

### Output layout

| Path | Purpose |
|---|---|
| `output/index.html` | Dashboard SPA entry point |
| `output/app.js` · `styles.css` | Dashboard logic + theme |
| `output/manifest.json` | Index of available days; drives the calendar |
| `output/archive/YYYY-MM-DD.json` | That day's top-20 archive (atomic-written) |
| `output/seen.json` | Cumulative URL + fingerprint dedup store |
| `output/jobs.{json,csv,md}` | Most recent run's machine-readable output |

---

## Filtering pipeline

Every posting passes through eleven stages before it can appear in
the day's archive:

1. **Exclusion rules** — denylisted companies (`capgemini`, etc.),
   early-stage firms, employment types (intern, part-time, contract
   cycles to skip), citizenship-only language, no-sponsorship clauses,
   active security clearance.
2. **Freshness** — drops anything posted more than `max_age_days`
   ago. With `strict_freshness: true`, postings without a parseable
   date are also dropped.
3. **Keyword match** — *title-scope only*. Title must contain at
   least one entry from the data keyword set: `data engineer/analyst/
   scientist/warehouse/platform/modeler`, `analytics engineer`,
   `bi developer/engineer/analyst`, `etl/elt`, `snowflake`,
   `databricks`, `spark`, `airflow`, `dbt`, `kafka`, `hadoop`,
   `informatica`, `tableau`, `power bi/powerbi`, `machine learning`,
   `ml engineer`, `mlops`, `reporting analyst/developer`,
   `data visualization`, `analytics developer`. Short tokens
   (`bi`, `etl`, `dbt`) are word-boundary matched so they cannot
   false-match inside unrelated words like *mobile*.
4. **Description guard** — under `strict_experience_filter`, postings
   whose description is shorter than `min_description_chars` are
   dropped. Without a body, a hidden "5+ years" requirement can't be
   detected.
5. **Years-of-experience** — regex extracts the lower-bound YoE
   from natural-language phrasings (`5+ years`, `at least 7 years`,
   `requires 4 yrs`, etc.). Postings demanding more than
   `max_experience_years` are dropped.
6. **Seniority** — drops Senior, Staff, Principal, Lead, Director,
   VP, Head-of, Chief, Distinguished, Fellow, plus numbered grades
   (Engineer III/IV/V, Level 4+, Grade 5).
7. **Location** — DFW preferred (boost), all US states accepted,
   remote accepted only with a US-positive signal.
8. **Cross-source dedup** — when two postings share a normalized
   `(company, title, location)` fingerprint, the one with the
   highest *directness* rank wins. Loser URLs are kept on the
   winner's `alt_sources` list.
9. **Cross-day dedup** — `output/seen.json` records every URL +
   fingerprint emitted on a prior day. Matches drop here.
10. **Auto-widen** — if the strict pipeline produces fewer than the
    daily target, a second pass relaxes the location requirement
    (foreign-country exclusion still applies).
11. **Same-day merge** — today's archive (if any) is merged with
    this run's surviving rows, deduped by URL *and* fingerprint,
    sorted by preferred-location and score, capped at the target.

### Source directness ranking

| Tier | Sources | Rank |
|---|---|---|
| Direct ATS — apply form on the linked page | Greenhouse, Lever, Ashby | 100 |
|  | Workable, Workday | 95 |
|  | SmartRecruiters | 90 |
| Aggregators — typically one redirect to the apply form | Adzuna, USAJobs | 70 |
|  | Built In | 70 |
|  | Y Combinator, Dice | 65 |
|  | The Muse | 60 |
| Guest search — multiple redirects, occasional dead-end | Remotive, RemoteOK | 55 |
|  | Indeed RSS | 40 |
|  | LinkedIn | 35 |

---

## Reliability

| Concern | Mitigation |
|---|---|
| One bad adapter killing the run | Each `source.fetch()` is wrapped in `_safe_fetch` — exceptions log a warning and contribute zero jobs while the rest of the funnel proceeds. |
| Transient network / 5xx blips | `urllib3.Retry` mounted on the shared `requests.Session` with 3 retries, exponential backoff (0.7s · 1.4s · 2.8s), and `Retry-After` header support. |
| Dead Workday tenants | Circuit breaker — first-query first-offset failure flags the tenant unreachable and skips its remaining 23 requests. |
| Crash mid-write corrupts state | All JSON / CSV / Markdown writes go through `atomic_write_text` (temp + `os.replace`). |
| Workflow concurrency race on `seen.json` | `daily-scrape` and `weekly-cleanup` share the same concurrency group; runs queue rather than interleave. |
| Workflow fails on a slow news day | A zero-row scrape is no longer a failure. Pages still republishes; tomorrow gets a fresh shot. |
| Stale `seen.json` blocking refreshed roles | `weekly-cleanup` workflow runs Sundays 07:00 UTC, parallel-HEAD-checks every URL, drops 404 / 410 / DNS-dead entries. |
| Regression in load-bearing logic | 33 unit tests gate every CI run. Salary parsing (14 phrasings + ReDoS guard), keyword matching with word boundaries, location edge cases, fingerprint cross-source identity, freshness, atomic-write semantics, SeenStore JSON-shape validation. |
| ReDoS on huge HTML descriptions | Salary regex input capped at 50,000 chars. |
| Unbounded archive size | Per-posting description capped at 16,000 chars at write time. Filtering still uses the full pre-trim text. |

---

## Configuration

Everything tunable lives in [`config.yaml`](./config.yaml):

| Setting | Default | Effect |
|---|---|---|
| `keyword_match_scope` | `title` | `title` requires a data keyword in the role title. `blob` accepts description matches (looser). |
| `max_age_days` | `7` | Postings older than this drop. |
| `strict_freshness` | `true` | Drop postings with no parseable posted date. |
| `min_jobs_target` | `20` | Daily cap. Same-day re-runs accumulate up to this number. |
| `candidate_experience_years` | `2` | Your real YoE — used as a soft anchor. |
| `max_experience_years` | `3` | Hard ceiling on what postings you'll see. |
| `strict_experience_filter` | `true` | Drop postings whose description is shorter than `min_description_chars`. |
| `min_description_chars` | `120` | See above. |
| `exclude.companies` | `[capgemini]` | Substring denylist on company name. |
| `exclude.work_auth` | (citizenship / clearance / no-sponsorship language) | Dropped on substring match in title + description. |
| `exclude.employment` | (intern, part-time, co-op, seasonal, …) | As above. |
| `sources.<name>` | `true` for all 16 | Toggle a source on/off without removing its config. |
| `indeed_rss_queries` · `linkedin_queries` · `workday_queries` · `builtin_queries` · `dice_queries` | (location-qualified data terms × TX cities) | Search terms fired at each list-style source. |
| `greenhouse_boards` · `lever_boards` · `ashby_boards` · `smartrecruiters_boards` · `workable_boards` | (118 / 37 / 44 / 16 / 13 boards) | Per-company ATS slugs. |
| `workday_tenants` | (57 tenants) | `{tenant, host, site}` triples mapping to `<tenant>.<host>.myworkdayjobs.com/<site>`. |

### Optional API keys

Two free public APIs materially increase the funnel; everything else
runs without credentials.

| API | Sign-up | Environment variables |
|---|---|---|
| Adzuna | https://developer.adzuna.com | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` |
| USAJobs | https://developer.usajobs.gov | `USAJOBS_EMAIL`, `USAJOBS_API_KEY` |

Drop them into a sourced `.env` for local runs, or *Settings → Secrets
and variables → Actions* on GitHub. Sources auto-skip when their keys
are missing.

---

## Daily automation

[`.github/workflows/daily.yml`](./.github/workflows/daily.yml) runs the
scraper every day at **06:00 UTC** (≈ 01:00 US Central) and on every
push to `main` that touches `scraper/**`, `config.yaml`, or the
workflow file itself. Steps:

1. Checkout
2. Set up Python 3.11
3. Install pinned `requirements.txt`
4. Run unit tests (gate — failures abort the rest of the run)
5. Run `python -m scraper.main`
6. Verify dashboard assets exist
7. Commit `output/` back to `main`
8. Configure & deploy to GitHub Pages

[`.github/workflows/weekly-cleanup.yml`](./.github/workflows/weekly-cleanup.yml)
runs Sundays at **07:00 UTC** to sweep dead URLs out of `seen.json`.

### One-time GitHub Pages setup

1. *Settings → Pages → Source: GitHub Actions*.
2. *Actions → daily-scrape → Run workflow* to seed `manifest.json`
   immediately, or wait for the next 06:00 UTC tick.
3. Open `https://<your-username>.github.io/Job-hunting/`.

---

## Project layout

```
Job-hunting/
├── README.md
├── requirements.txt              # pinned versions
├── config.yaml                   # all tunables
├── run.sh                        # venv + run + open dashboard
├── .github/workflows/
│   ├── daily.yml                 # daily scrape + Pages publish
│   └── weekly-cleanup.yml        # link-health sweep on seen.json
├── scraper/
│   ├── main.py                   # gather → filter → dedup → merge → write
│   ├── filters.py                # keyword / location / YoE / seniority / salary / tech-tag
│   ├── dedup.py                  # cross-day SeenStore
│   ├── output.py                 # JSON / CSV / Markdown / manifest
│   ├── io_utils.py               # atomic_write_text
│   ├── web/                      # SPA assets (copied to output/ each run)
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── app.js
│   └── sources/                  # one adapter per source
│       ├── base.py               # HttpClient with retries · Job dataclass · directness map
│       ├── adzuna.py
│       ├── ashby.py
│       ├── builtin.py
│       ├── dice.py
│       ├── greenhouse.py
│       ├── indeed_rss.py
│       ├── lever.py
│       ├── linkedin.py
│       ├── remoteok.py
│       ├── remotive.py
│       ├── smartrecruiters.py
│       ├── themuse.py
│       ├── usajobs.py
│       ├── workable.py
│       ├── workday.py
│       └── ycombinator.py
├── scripts/
│   └── healthcheck.py            # weekly seen.json sweep
└── tests/
    ├── test_filters.py
    └── test_io.py
```

---

## Design decisions

**Title-scope keyword matching, not blob.** Single-token data terms
(`sql`, `snowflake`, `tableau`) appear in the descriptions of many
non-data roles. Restricting matches to the role title cuts false
positives without measurably hurting recall — the data-engineering
keyword set is broad enough that any genuine data role names itself
in the title.

**Source directness as the cross-source tiebreaker.** When the same
role is posted on Greenhouse and LinkedIn, the LinkedIn version
typically requires two redirects to reach the apply form. Picking
Greenhouse first (rank 100 vs. 35) saves clicks on every application
without losing the LinkedIn link, which is preserved under
*Also seen on* in the drawer.

**Fingerprint normalization.** Same role often appears across sources
with different decorations: *Deloitte* / *Deloitte LLP* / *Deloitte
Consulting* · *Dallas, TX* / *Dallas, Texas* / *Dallas, TX, USA* ·
*Data Engineer* / *Data Engineer (Remote)*. The fingerprint hash
strips company suffixes, canonicalizes US state names to 2-letter
codes, and removes title decorators so all three fingerprint
identically.

**Cross-day dedup over carry-forward.** The original v1 carried
unread postings forward into subsequent days' views, which produced
a snowballing backlog. The current model is binary: a posting either
appears in *the* day it was discovered or never. Roles that get
re-posted by the employer can resurface only after the weekly health
check removes the original URL from `seen.json`.

**No application-status tracking.** Removing the Kanban board /
applied-state UI eliminated a class of UX complexity in exchange for
a much simpler mental model: every day is an independent batch of
brand-new postings to triage. *Apply ↗* opens the source page; the
rest is up to your inbox.

**Pinned dependencies + atomic writes + retries.** Single-purpose
personal infrastructure deserves the same reliability discipline as
production systems — a corrupted `seen.json` from a mid-write crash
or a flaky network on a single 5xx response should not derail
tomorrow's run.

---

## Ethics

Every endpoint hit is one of:

- An **official public API** — Greenhouse, Lever, Ashby,
  SmartRecruiters, Workable, Remotive, RemoteOK, The Muse, Adzuna,
  USAJobs, YC Algolia.
- A **documented public RSS feed** — Indeed.
- The **unauthenticated endpoint a site uses for its own embedded
  widget** — LinkedIn guest jobs, Workday careers page, Built In's
  per-city listing pages.

No login. No cookies. No scraping of authenticated content. No
circumvention of access controls. Per-source rate limiting is
conservative — single-digit pages, one query at a time, with HTTP
retries respecting `Retry-After` headers.

---

## License

Personal-use repository. No license granted; do not republish without
permission.
