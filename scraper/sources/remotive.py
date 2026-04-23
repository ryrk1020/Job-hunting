"""Remotive — public JSON feed, no key required.

https://remotive.com/api/remote-jobs
"""
from __future__ import annotations

import logging
from typing import Iterable

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

ENDPOINT = "https://remotive.com/api/remote-jobs"


def fetch(http: HttpClient, queries: Iterable[str]) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()
    for q in queries:
        try:
            payload = http.get_json(ENDPOINT, params={"search": q, "limit": 50})
        except Exception as e:
            log.warning("remotive %s failed: %s", q, e)
            continue
        for item in payload.get("jobs", []):
            url = item.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            jobs.append(
                Job(
                    source="remotive",
                    company=item.get("company_name") or "",
                    title=item.get("title") or "",
                    location=item.get("candidate_required_location") or "Remote",
                    url=url,
                    posted_at=parse_when(item.get("publication_date")),
                    description=strip_html(item.get("description")),
                    remote=True,
                    raw_id=str(item.get("id") or ""),
                )
            )
    log.info("remotive: %d jobs", len(jobs))
    return jobs
