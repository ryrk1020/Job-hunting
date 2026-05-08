"""Dice — best-effort adapter against the public marketplace API.

Dice migrated their public API behind authentication some time ago.
This adapter tries the documented dhigroupinc endpoint with the same
referer headers a browser would send, but in practice GitHub Actions
runners typically receive HTTP 403. The adapter logs the failure and
contributes 0 jobs without breaking the rest of the pipeline.

If Dice opens up a public API (or you have a key), drop the auth header
into the HttpClient session and this adapter starts producing rows.
"""
from __future__ import annotations

import logging
from typing import Iterable

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

ENDPOINT = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"
REFERER = "https://www.dice.com/"


def fetch(http: HttpClient, queries: Iterable[dict]) -> list[Job]:
    """Pull Dice postings for each (q, location) pair.

    queries: iterable of {"q": "data engineer", "l": "Dallas, TX"}.
    """
    jobs: list[Job] = []
    seen: set[str] = set()
    headers = {"Referer": REFERER, "Origin": "https://www.dice.com"}
    for q in queries:
        params = {
            "q": q.get("q", ""),
            "location": q.get("l", ""),
            "radius": "30",
            "radiusUnit": "mi",
            "page": "1",
            "pageSize": "20",
            "filters.postedDate": "SEVEN",
        }
        try:
            payload = http.get_json(ENDPOINT, params=params, headers=headers)
        except Exception as e:
            log.warning("dice %s/%s failed: %s", q.get("q"), q.get("l"), e)
            continue
        results = payload.get("data") or payload.get("results") or []
        for item in results:
            url = item.get("detailUrl") or item.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            jobs.append(Job(
                source="dice",
                company=item.get("companyName") or item.get("company") or "",
                title=item.get("title") or "",
                location=item.get("locationName") or item.get("location") or "",
                url=url,
                posted_at=parse_when(item.get("postedDate") or item.get("posted_date")),
                description=strip_html(item.get("summary") or item.get("description")),
                remote=bool(item.get("isRemote") or "remote" in (item.get("locationName") or "").lower()),
                raw_id=str(item.get("id") or ""),
            ))
    log.info("dice: %d jobs", len(jobs))
    return jobs
