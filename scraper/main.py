"""Main runner: fan out to every enabled source, then filter + write outputs.

Usage:
    python -m scraper.main [--config config.yaml] [--out output]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from .dedup import SeenStore, commit_seen, filter_unseen, today_str
from .filters import apply_all
from .output import write_all
from .sources.base import HttpClient
from .sources import (
    adzuna,
    ashby,
    builtin,
    dice,
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
            categories=["Data Science", "Data and Analytics"],
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
    if enabled.get("builtin"):
        all_jobs += builtin.fetch(http, cfg.get("builtin_queries", []))
    if enabled.get("dice"):
        all_jobs += dice.fetch(http, cfg.get("dice_queries", []))

    log.info("total raw jobs from all sources: %d", len(all_jobs))
    return all_jobs


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

    day = today_str()

    # Same-day accumulation: if today's archive already has entries
    # (from an earlier run), merge them with the new fresh rows so
    # multiple runs in a day grow toward the target instead of
    # overwriting each other. Cross-day dedup still ensures yesterday's
    # picks aren't re-surfaced today.
    archive_path = out_dir / "archive" / f"{day}.json"
    existing_rows: list[dict] = []
    if archive_path.exists():
        try:
            import json as _json
            prev = _json.loads(archive_path.read_text(encoding="utf-8"))
            existing_rows = prev.get("jobs", []) or []
        except Exception as e:
            log.warning("could not read existing archive %s: %s", archive_path, e)

    if existing_rows:
        # Backfill missing fields on legacy archive entries (older runs
        # before directness/alt_sources existed) so the dashboard renders
        # uniformly across rows.
        from .sources.base import directness as _src_directness
        for r in existing_rows:
            if "directness" not in r:
                r["directness"] = _src_directness(r.get("source", ""))
            if "alt_sources" not in r:
                r["alt_sources"] = []

        seen_urls: set[str] = set()
        merged: list[dict] = []
        # Existing rows first (they're already committed to seen.json),
        # then the freshly-scraped ones.
        for r in existing_rows + rows:
            u = r.get("url") or ""
            if u and u in seen_urls:
                continue
            if u:
                seen_urls.add(u)
            merged.append(r)
        merged.sort(key=lambda r: (r.get("preferred_location", False), r.get("score", 0)), reverse=True)
        log.info(
            "same-day merge: existing=%d fresh=%d -> merged=%d",
            len(existing_rows), len(rows), len(merged),
        )
        rows = merged

    # Hard cap at target — user wants exactly N jobs/day.
    if len(rows) > target:
        log.info("capping %d -> %d (target)", len(rows), target)
        rows = rows[:target]

    paths = write_all(rows, out_dir, day)

    # Commit everything we just emitted to the seen store so tomorrow's
    # run won't re-surface them as fresh. Already-seen URLs are no-ops
    # in SeenStore.add(), so re-committing existing rows is safe.
    commit_seen(rows, store, day)

    log.info("wrote %d jobs to %s", len(rows), out_dir)
    print(f"\nOK {len(rows)} new jobs for {day}")
    for k, v in paths.items():
        print(f"  {k:9}: {v}")
    if len(rows) < target:
        print(
            f"\n[note] target was {target} — once cross-day dedup kicks in this is "
            "expected on slow news days. Add ADZUNA / USAJOBS env vars or more "
            "company boards in config.yaml to increase the funnel."
        )
    # A zero-row day on the data-only profile is a normal slow news day,
    # not a failure — the workflow should still publish the dashboard
    # and commit an empty archive entry. Only return non-zero if writing
    # the outputs themselves blew up (which would have raised already).
    return 0


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
