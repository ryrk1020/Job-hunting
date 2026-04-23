"""Lever job boards — public.

https://api.lever.co/v0/postings/<slug>?mode=json
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

from .base import HttpClient, Job, strip_html

log = logging.getLogger(__name__)

TEMPLATE = "https://api.lever.co/v0/postings/{slug}?mode=json"


def fetch(http: HttpClient, boards: Iterable[str]) -> list[Job]:
    jobs: list[Job] = []
    for slug in boards:
        try:
            payload = http.get_json(TEMPLATE.format(slug=slug))
        except Exception as e:
            log.warning("lever %s failed: %s", slug, e)
            continue
        for item in payload:
            cats = item.get("categories") or {}
            loc = cats.get("location", "")
            created_ms = item.get("createdAt")
            posted_at = None
            if isinstance(created_ms, (int, float)):
                posted_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
            jobs.append(
                Job(
                    source="lever",
                    company=slug,
                    title=item.get("text") or "",
                    location=loc,
                    url=item.get("hostedUrl") or item.get("applyUrl") or "",
                    posted_at=posted_at,
                    description=strip_html(item.get("descriptionPlain") or item.get("description", "")),
                    raw_id=str(item.get("id") or ""),
                    extra={"team": cats.get("team"), "commitment": cats.get("commitment")},
                )
            )
    log.info("lever: %d jobs", len(jobs))
    return jobs
