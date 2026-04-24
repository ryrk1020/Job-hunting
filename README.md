# Job Hunter

End-to-end job aggregator built for an F-1/OPT job search in the Dallas–Fort
Worth–Frisco metro. Pulls real, fresh postings from many genuine sources,
filters by keywords + location + freshness, drops Cognizant and tiny seed-stage
startups, scores and deduplicates, and writes JSON / CSV / Markdown / a
single-file HTML dashboard.

## Sources

| Source            | Type                  | Needs key? | Notes                                 |
|-------------------|-----------------------|------------|---------------------------------------|
| LinkedIn          | Public guest search   | No         | `jobs-guest/jobs/api/seeMoreJobPostings` |
| Indeed            | Public RSS            | No         | Per-query + per-location feed         |
| Remotive          | Public JSON API       | No         | Remote-only                           |
| RemoteOK          | Public JSON API       | No         | Remote-only                           |
| The Muse          | Public JSON API       | No         |                                       |
| Adzuna            | Free API              | Yes        | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`     |
| USAJobs           | Free API              | Yes        | `USAJOBS_EMAIL`, `USAJOBS_API_KEY`    |
| Greenhouse boards | Public, per-company   | No         | `boards-api.greenhouse.io/...`        |
| Lever boards      | Public, per-company   | No         | `api.lever.co/v0/postings/...`        |
| Ashby boards      | Public, per-company   | No         | `api.ashbyhq.com/posting-api/...`     |
| SmartRecruiters   | Public, per-company   | No         |                                       |
| Workable          | Public embed API      | No         |                                       |
| Workday           | Public tenant JSON    | No         | AT&T, USAA, JPMC, Capital One, Fidelity, Dell, PepsiCo, McKesson, TI, 7-Eleven, Schwab |
| Y Combinator      | Public Algolia index  | No         | Off by default (too much seed stage)  |

Add more companies in `config.yaml` — every board template is a single slug.

## Filters (configured in `config.yaml`)

- **Keywords**: `data`, `vibecoding` (AI/LLM/GenAI/agent/copilot/RAG),
  `fullstack` (full stack / frontend / backend / mobile / React / Angular /
  Vue / Node / Next), `software` (Python / Java / Go / C++ / C# / .NET /
  TypeScript / Ruby / etc.), `qa` (QA / SDET / tester / automation),
  `cloud` (DevOps / SRE / AWS / Azure / GCP / Kubernetes / Terraform),
  `security`, `analyst` (business / systems / product / financial),
  `product` (PM / TPM / Scrum), and `junior` (associate / entry-level / new
  grad).
- **Locations (preferred)**: Frisco, Dallas, Fort Worth, Plano, Irving, Arlington,
  Richardson, Addison, Las Colinas, McKinney, Allen, Denton. Remote allowed.
  Anything in Texas kept but ranked lower than the DFW preferred list.
- **Freshness**: only jobs posted in the last 7 days (configurable).
- **Excludes**: Cognizant (company match), plus `companies_early_stage` denylist
  for any small seed-stage firms you want to skip.
- **Seniority**: drops titles containing `senior staff`, `principal`, `director`,
  `vp `, `head of`.
- **Dedup**: by `(company, title, location)` fingerprint, keeping the
  highest-scoring record.
- **Auto-widen**: if the strict filter returns fewer than `min_jobs_target`
  (default 50), the runner appends a location-agnostic pass so you still hit
  the daily floor.
- **Cross-day dedup**: every job ever surfaced is recorded in `output/seen.json`
  (committed by the daily workflow). Once a posting appears on day X it will
  never appear on day X+1 — every day's archive is the *new* jobs only.

## Dashboard (Calendar SPA)

`output/index.html` is a single-page dashboard backed by `manifest.json` and
`archive/<date>.json`. Features:

- **Calendar** — month view, days with jobs are highlighted with the count.
  Click any day to load that day's unique jobs. "Jump to today" button.
- **Per-job status** — four buttons (Accept / Applied / In Progress / Reject)
  on every job card. Status persists in browser `localStorage` so it survives
  reloads and follows you across sessions on the same machine.
- **KPIs** — today's count, all-time count, and your own accept/applied/in-progress/reject totals.
- **Filters** — text search across company/title/location/source/source, group
  (data, vibecoding, fullstack, software, qa, cloud, security, analyst, product),
  status, and location (preferred DFW / Remote).
- **One-click apply** — every card has a direct "Apply ↗" link to the source.

## Quick start

```bash
# one-shot run
./run.sh

# or manually
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scraper.main --config config.yaml --out output
open output/index.html
```

Outputs:

- `output/jobs.json` — canonical, machine-readable
- `output/jobs.csv` — open in Excel / Sheets
- `output/jobs.md` — paste into Notion / GitHub
- `output/index.html` + `app.js` + `styles.css` — calendar SPA dashboard
- `output/manifest.json` — list of available days for the calendar
- `output/seen.json` — cross-day dedup store (committed daily)
- `output/archive/YYYY-MM-DD.json` — that day's unique new jobs

## Optional free API keys (recommended, boosts volume)

- **Adzuna**: https://developer.adzuna.com → `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`
- **USAJobs**: https://developer.usajobs.gov → `USAJOBS_EMAIL`, `USAJOBS_API_KEY`

Set them in your shell, a `.env` you source, or GitHub Actions secrets.

## Daily automation

`.github/workflows/daily.yml` runs the scraper every day at 06:00 UTC, commits
the latest `output/` (including `seen.json` so cross-day dedup survives) back
to the repo, and publishes the calendar dashboard to GitHub Pages.

**To enable Pages** (one-time):

1. Repo **Settings → Pages → Source: GitHub Actions**.
2. **Actions → daily-scrape → Run workflow** to do a first run immediately
   (otherwise wait for tomorrow 06:00 UTC).
3. Open `https://<your-username>.github.io/Job-hunting/` and you'll see the
   calendar with today's jobs loaded.

Each subsequent day the workflow appends a new `archive/<date>.json`,
refreshes `manifest.json` for the calendar, and updates `seen.json` so
duplicates are dropped.

To add secrets: **Repo Settings → Secrets and variables → Actions → New
repository secret** for any of `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`,
`USAJOBS_EMAIL`, `USAJOBS_API_KEY`.

## Extending

- New Greenhouse/Lever/Ashby/SmartRecruiters/Workable company?
  Add its slug to the right list in `config.yaml`.
- New Workday tenant? Add `{tenant, host, site}` — find them from the company's
  public careers URL (`<tenant>.<host>.myworkdayjobs.com/<site>`).
- New keyword group? Add under `keywords:` as a list of token lists. All
  tokens in a single list must appear (case-insensitive) for a match.
- New startup to skip? Add to `exclude.companies_early_stage`.

## Ethics

Every endpoint hit is either an official public API (ATS boards, Remotive,
RemoteOK, The Muse, Adzuna, USAJobs, SmartRecruiters, Workable, YC), a
documented public RSS feed (Indeed), or the public unauthenticated endpoint
used by the site's own embedded widget (LinkedIn guest search, Workday careers
page). No login, cookies, or scraping of logged-in content.
