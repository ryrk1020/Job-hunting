"""SmartRecruiters — public postings API.

https://api.smartrecruiters.com/v1/companies/<slug>/postings
"""
from __future__ import annotations

import logging
from typing import Iterable

from .base import HttpClient, Job, parse_when

log = logging.getLogger(__name__)

TEMPLATE = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"


def fetch(http: HttpClient, boards: Iterable[str]) -> list[Job]:
    jobs: list[Job] = []
    for slug in boards:
        try:
            payload = http.get_json(TEMPLATE.format(slug=slug))
        except Exception as e:
            log.warning("smartrecruiters %s failed: %s", slug, e)
            continue
        for item in payload.get("content", []):
            loc_obj = item.get("location") or {}
            parts = [
                loc_obj.get("city"),
                loc_obj.get("region"),
                loc_obj.get("country"),
            ]
            loc = ", ".join([p for p in parts if p])
            jobs.append(
                Job(
                    source="smartrecruiters",
                    company=slug,
                    title=item.get("name") or "",
                    location=loc,
                    url=f"https://jobs.smartrecruiters.com/{slug}/{item.get('id', '')}",
                    posted_at=parse_when(item.get("releasedDate") or item.get("createdOn")),
                    remote=bool(loc_obj.get("remote")),
                    raw_id=str(item.get("id") or ""),
                )
            )
    log.info("smartrecruiters: %d jobs", len(jobs))
    return jobs
