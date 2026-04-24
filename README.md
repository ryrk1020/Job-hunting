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
- `output/index.html` — interactive dashboard with text filter and tag filters
- `output/archive/YYYY-MM-DD.json` — dated snapshot per run

## Optional free API keys (recommended, boosts volume)

- **Adzuna**: https://developer.adzuna.com → `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`
- **USAJobs**: https://developer.usajobs.gov → `USAJOBS_EMAIL`, `USAJOBS_API_KEY`

Set them in your shell, a `.env` you source, or GitHub Actions secrets.

## Daily automation

`.github/workflows/daily.yml` runs the scraper every day at 06:00 UTC, commits
the latest `output/` back to the repo, and publishes the HTML dashboard to
GitHub Pages.

To enable Pages: **Repo Settings → Pages → Source: GitHub Actions**. Then
every morning the dashboard at `https://<you>.github.io/Job-hunting/` reflects
the latest scrape automatically.

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
