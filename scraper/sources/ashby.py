"""Ashby job boards — public.

https://api.ashbyhq.com/posting-api/job-board/<slug>
"""
from __future__ import annotations

import logging
from typing import Iterable

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

TEMPLATE = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def fetch(http: HttpClient, boards: Iterable[str]) -> list[Job]:
    jobs: list[Job] = []
    for slug in boards:
        try:
            payload = http.get_json(TEMPLATE.format(slug=slug))
        except Exception as e:
            log.warning("ashby %s failed: %s", slug, e)
            continue
        for item in payload.get("jobs", []):
            jobs.append(
                Job(
                    source="ashby",
                    company=slug,
                    title=item.get("title") or "",
                    location=item.get("location") or "",
                    url=item.get("jobUrl") or item.get("applyUrl") or "",
                    posted_at=parse_when(item.get("publishedDate") or item.get("updatedAt")),
                    description=strip_html(item.get("descriptionHtml") or item.get("descriptionPlain", "")),
                    remote=bool(item.get("isRemote")),
                    raw_id=str(item.get("id") or ""),
                    extra={"department": item.get("department"), "team": item.get("team")},
                )
            )
    log.info("ashby: %d jobs", len(jobs))
    return jobs
