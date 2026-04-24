"""Filtering, scoring, and deduplication for scraped jobs."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .sources.base import Job

log = logging.getLogger(__name__)


def _contains_all(haystack: str, tokens: Iterable[str]) -> bool:
    return all(tok in haystack for tok in tokens)


def matches_keywords(job: Job, groups: dict) -> list[str]:
    """Return the list of matching keyword-group names for this job."""
    blob = f"{job.title}\n{job.description}".lower()
    hits: list[str] = []
    for group_name, token_lists in groups.items():
        for tokens in token_lists:
            if _contains_all(blob, [t.lower() for t in tokens]):
                hits.append(group_name)
                break
    return hits


def location_ok(job: Job, locs: dict) -> tuple[bool, bool]:
    """Return (allowed, preferred). Remote is allowed if configured."""
    low = (job.location or "").lower()
    remote_ok = bool(locs.get("allow_remote", True))
    if job.remote or "remote" in low:
        return remote_ok, False
    preferred = [p.lower() for p in locs.get("preferred", [])]
    allowed_states = [s.lower() for s in locs.get("allowed_states", [])]
    is_preferred = any(p in low for p in preferred)
    is_allowed = is_preferred or any(s in low for s in allowed_states)
    return is_allowed, is_preferred


def excluded(job: Job, rules: dict) -> bool:
    blob = f"{job.company} {job.title} {job.description}".lower()
    for term in rules.get("companies", []):
        if term.lower() in (job.company or "").lower():
            return True
    for term in rules.get("companies_early_stage", []) or []:
        if term.lower() in (job.company or "").lower() or term.lower() in blob:
            return True
    title_low = (job.title or "").lower()
    for term in rules.get("titles", []):
        if term.lower() in title_low:
            return True
    return False


def fresh(job: Job, max_age_days: int) -> bool:
    if job.posted_at is None:
        # Unknown date — keep (many ATS feeds don't expose one).
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return job.posted_at >= cutoff


def score(job: Job, matched_groups: list[str], is_preferred_loc: bool) -> int:
    s = 0
    if is_preferred_loc:
        s += 50
    if job.remote or "remote" in (job.location or "").lower():
        s += 10
    if "data" in matched_groups:
        s += 20
    if "vibecoding" in matched_groups:
        s += 25
    if "fullstack" in matched_groups:
        s += 20
    if "software" in matched_groups:
        s += 15
    if "qa" in matched_groups:
        s += 15
    if "cloud" in matched_groups:
        s += 15
    if "security" in matched_groups:
        s += 10
    if "analyst" in matched_groups:
        s += 10
    if "product" in matched_groups:
        s += 5
    if "junior" in matched_groups:
        s += 10
    if job.posted_at is not None:
        age_h = (datetime.now(timezone.utc) - job.posted_at).total_seconds() / 3600
        if age_h < 24:
            s += 20
        elif age_h < 72:
            s += 10
    return s


def apply_all(
    jobs: list[Job],
    cfg: dict,
    *,
    require_location: bool = True,
) -> list[dict]:
    """Filter, score, and dedup. Returns list of dicts ready for serialization."""
    kw = cfg.get("keywords", {})
    locs = cfg.get("locations", {})
    exc = cfg.get("exclude", {})
    max_age = int(cfg.get("max_age_days", 7))

    seen: dict[str, dict] = {}
    kept = 0
    dropped_loc = 0
    dropped_kw = 0
    dropped_exc = 0
    dropped_old = 0

    for j in jobs:
        if excluded(j, exc):
            dropped_exc += 1
            continue
        if not fresh(j, max_age):
            dropped_old += 1
            continue
        hits = matches_keywords(j, kw)
        if not hits:
            dropped_kw += 1
            continue
        allowed, preferred = location_ok(j, locs)
        if require_location and not allowed:
            dropped_loc += 1
            continue
        row = j.to_dict()
        row["matched_groups"] = hits
        row["preferred_location"] = preferred
        row["score"] = score(j, hits, preferred)
        row["_fp"] = j.fingerprint()
        fp = j.fingerprint()
        prev = seen.get(fp)
        if prev is None or row["score"] > prev["score"]:
            seen[fp] = row
            kept += 1

    log.info(
        "filter: kept=%d unique=%d dropped(exc=%d,kw=%d,loc=%d,old=%d)",
        kept, len(seen), dropped_exc, dropped_kw, dropped_loc, dropped_old,
    )
    out = list(seen.values())
    out.sort(key=lambda r: r["score"], reverse=True)
    return out
