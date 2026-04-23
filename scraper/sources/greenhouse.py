"""Greenhouse job boards — public, no key required.

https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true
"""
from __future__ import annotations

import logging
from typing import Iterable

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

TEMPLATE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def fetch(http: HttpClient, boards: Iterable[str]) -> list[Job]:
    jobs: list[Job] = []
    for slug in boards:
        try:
            payload = http.get_json(TEMPLATE.format(slug=slug))
        except Exception as e:
            log.warning("greenhouse %s failed: %s", slug, e)
            continue
        for item in payload.get("jobs", []):
            loc = ""
            loc_obj = item.get("location") or {}
            if isinstance(loc_obj, dict):
                loc = loc_obj.get("name", "")
            company = slug
            meta_fields = item.get("metadata") or []
            jobs.append(
                Job(
                    source="greenhouse",
                    company=company,
                    title=item.get("title") or "",
                    location=loc,
                    url=item.get("absolute_url") or "",
                    posted_at=parse_when(item.get("updated_at") or item.get("created_at")),
                    description=strip_html(item.get("content", "")),
                    raw_id=str(item.get("id") or ""),
                    extra={"departments": [d.get("name") for d in item.get("departments", [])], "metadata": meta_fields},
                )
            )
    log.info("greenhouse: %d jobs", len(jobs))
    return jobs
