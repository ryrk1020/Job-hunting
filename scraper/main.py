"""Main runner: fan out to every enabled source, then filter + write outputs.

Usage:
    python -m scraper.main [--config config.yaml] [--out output]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .dedup import SeenStore, commit_seen, filter_unseen, today_str
from .filters import apply_all
from .output import write_all
from .sources.base import HttpClient
from .sources import (
    adzuna,
    ashby,
    greenhouse,
    indeed_rss,
    lever,
    linkedin,
    remoteok,
    remotive,
    smartrecruiters,
    themuse,
    usajobs,
    workable,
    workday,
    ycombinator,
)

log = logging.getLogger("scraper")


def _keywords_flat(cfg: dict) -> list[str]:
    """Flatten every keyword group's first token into a query list."""
    out: list[str] = []
    for tokens_lists in (cfg.get("keywords") or {}).values():
        for tokens in tokens_lists:
            out.append(" ".join(tokens))
    # De-dup while preserving order.
    seen: set[str] = set()
    result: list[str] = []
    for q in out:
        if q not in seen:
            seen.add(q)
            result.append(q)
    return result


def gather(cfg: dict) -> list:
    http = HttpClient()
    enabled = cfg.get("sources", {})
    queries = _keywords_flat(cfg)
    tx_locations = ["Dallas, TX", "Frisco, TX", "Fort Worth, TX", "Plano, TX", "Texas"]

    all_jobs = []

    if enabled.get("remotive"):
        all_jobs += remotive.fetch(http, queries)
    if enabled.get("remoteok"):
        all_jobs += remoteok.fetch(http)
    if enabled.get("themuse"):
        all_jobs += themuse.fetch(
            http,
            categories=["Data Science", "Data and Analytics", "Marketing",
                        "Engineering", "Software Engineer"],
            locations=["Dallas, TX", "Fort Worth, TX", "Austin, TX", "Houston, TX",
                       "Flexible / Remote"],
        )
    if enabled.get("adzuna"):
        all_jobs += adzuna.fetch(http, queries, tx_locations)
    if enabled.get("usajobs"):
        all_jobs += usajobs.fetch(http, queries, tx_locations)
    if enabled.get("indeed_rss"):
        all_jobs += indeed_rss.fetch(cfg.get("indeed_rss_queries", []))
    if enabled.get("linkedin"):
        all_jobs += linkedin.fetch(http, cfg.get("linkedin_queries", []))
    if enabled.get("greenhouse"):
        all_jobs += greenhouse.fetch(http, cfg.get("greenhouse_boards", []))
    if enabled.get("lever"):
        all_jobs += lever.fetch(http, cfg.get("lever_boards", []))
    if enabled.get("ashby"):
        all_jobs += ashby.fetch(http, cfg.get("ashby_boards", []))
    if enabled.get("smartrecruiters"):
        all_jobs += smartrecruiters.fetch(http, cfg.get("smartrecruiters_boards", []))
    if enabled.get("workable"):
        all_jobs += workable.fetch(http, cfg.get("workable_boards", []))
    if enabled.get("workday"):
        all_jobs += workday.fetch(
            http, cfg.get("workday_tenants", []), cfg.get("workday_queries", queries)
        )
    if enabled.get("ycombinator"):
        all_jobs += ycombinator.fetch(http, queries)

    log.info("total raw jobs from all sources: %d", len(all_jobs))
    return all_jobs


def _load_statuses(out_dir: Path) -> dict:
    """Load output/status.json written by the dashboard's sync feature.

    The file is managed by the browser-side app; scraper only reads. If
    missing or malformed, return an empty map and let the carry-forward
    logic fall through (everything is treated as unmarked).
    """
    f = out_dir / "status.json"
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("statuses", {}) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _carry_forward(out_dir: Path, statuses: dict, today_rows: list[dict],
                   today: str, max_age_days: int) -> list[dict]:
    """Yesterday's unmarked jobs get rolled into today's list.

    A job carries forward when ALL of these hold:
      - It's in an archive file with a date strictly before `today`.
      - It isn't in today's fresh list (URL dedup).
      - Its status in status.json is NOT 'applied' or 'reject' (those
        are 'done' states the user doesn't want to see again).
      - Its posted_at is still within max_age_days (freshness).

    Each carried row gets a 'carryover': true marker and the original
    day it was first surfaced as 'carried_from'. The dashboard uses
    these to show a small 'carryover' badge.
    """
    archive_dir = out_dir / "archive"
    if not archive_dir.exists():
        return []

    prior_files = sorted(
        (f for f in archive_dir.glob("*.json") if f.stem < today),
        reverse=True,
    )
    if not prior_files:
        return []

    done = {"applied", "reject"}
    today_urls = {r.get("url") for r in today_rows if r.get("url")}
    now = datetime.now(timezone.utc)
    cutoff_days = int(max_age_days)

    seen_urls: set[str] = set(today_urls)
    carried: list[dict] = []
    for f in prior_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for j in data.get("jobs", []) or []:
            url = j.get("url")
            if not url or url in seen_urls:
                continue
            if statuses.get(url) in done:
                continue
            posted = j.get("posted_at")
            if posted:
                try:
                    dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (now - dt).days > cutoff_days:
                        continue
                except (ValueError, TypeError):
                    pass
            row = dict(j)
            # Flag so the dashboard can render a "carryover" badge and
            # so repeated carries don't lose the origin day.
            row["carryover"] = True
            row.setdefault("carried_from", f.stem)
            carried.append(row)
            seen_urls.add(url)
    return carried


def run(cfg_path: Path, out_dir: Path) -> int:
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    jobs = gather(cfg)

    # First pass: full filters (location required).
    rows = apply_all(jobs, cfg, require_location=True)
    target = int(cfg.get("min_jobs_target", 50))

    # Cross-day dedup: drop anything we've already surfaced on a prior day.
    store = SeenStore(out_dir / "seen.json")
    before = len(rows)
    rows = filter_unseen(rows, store)
    log.info("cross-day dedup: %d -> %d (store has %s)", before, len(rows), store.stats())

    # If below target, widen once by dropping the location filter,
    # then dedup again.
    if len(rows) < target:
        log.info("only %d jobs after strict filter, widening (drop location)", len(rows))
        widened = apply_all(jobs, cfg, require_location=False)
        widened = filter_unseen(widened, store)
        seen_urls = {r.get("url") for r in rows if r.get("url")}
        for r in widened:
            if r.get("url") and r["url"] not in seen_urls:
                rows.append(r)
                seen_urls.add(r["url"])

    # Final sort: preferred_location desc, then score desc.
    rows.sort(key=lambda r: (r.get("preferred_location", False), r.get("score", 0)), reverse=True)

    # Hard cap at target — user wants exactly N fresh jobs/day.
    if len(rows) > target:
        log.info("capping fresh %d -> %d (target)", len(rows), target)
        rows = rows[:target]

    day = today_str()

    # Carry-forward: yesterday's still-actionable (unmarked or in-progress
    # / accepted) jobs get rolled onto today so the user can pick up where
    # they left off. Only 'applied' and 'reject' statuses stop the roll.
    if bool(cfg.get("carry_forward", True)):
        statuses = _load_statuses(out_dir)
        carried = _carry_forward(
            out_dir, statuses, rows, day,
            max_age_days=int(cfg.get("max_age_days", 7)),
        )
        if carried:
            log.info("carry-forward: +%d unmarked jobs from prior days", len(carried))
            rows.extend(carried)

    paths = write_all(rows, out_dir, day)

    # Commit everything we just emitted to the seen store so tomorrow's
    # run won't re-surface them as 'fresh'. Carried rows already had
    # their fingerprints committed on the day they were first surfaced.
    commit_seen(rows, store, day)

    log.info("wrote %d jobs to %s", len(rows), out_dir)
    print(f"\n✓ {len(rows)} new jobs for {day}")
    for k, v in paths.items():
        print(f"  {k:9}: {v}")
    if len(rows) < target:
        print(
            f"\n⚠ target was {target} — once cross-day dedup kicks in this is "
            "expected on slow news days. Add ADZUNA / USAJOBS env vars or more "
            "company boards in config.yaml to increase the funnel."
        )
    return 0 if rows else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Multi-source job scraper")
    p.add_argument("--config", default="config.yaml", type=Path)
    p.add_argument("--out", default="output", type=Path)
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return run(args.config, args.out)


if __name__ == "__main__":
    sys.exit(main())
