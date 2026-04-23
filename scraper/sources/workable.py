"""Workable — public embed API for accounts using apply.workable.com.

https://apply.workable.com/api/v3/accounts/<slug>/jobs  (POST, json body)
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests

from .base import HttpClient, Job, parse_when

log = logging.getLogger(__name__)

TEMPLATE = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"


def fetch(http: HttpClient, boards: Iterable[str]) -> list[Job]:
    jobs: list[Job] = []
    for slug in boards:
        try:
            r = http.s.post(
                TEMPLATE.format(slug=slug),
                json={"query": "", "location": {}, "department": [], "workplace": []},
                timeout=http.timeout,
            )
            r.raise_for_status()
            payload = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("workable %s failed: %s", slug, e)
            continue
        for item in payload.get("results", []):
            loc_obj = item.get("location") or {}
            parts = [
                loc_obj.get("city"),
                loc_obj.get("region"),
                loc_obj.get("country"),
            ]
            loc = ", ".join([p for p in parts if p])
            shortcode = item.get("shortcode") or ""
            jobs.append(
                Job(
                    source="workable",
                    company=slug,
                    title=item.get("title") or "",
                    location=loc,
                    url=f"https://apply.workable.com/{slug}/j/{shortcode}",
                    posted_at=parse_when(item.get("published_on") or item.get("created_at")),
                    remote=loc_obj.get("workplaceType") == "remote",
                    raw_id=shortcode,
                )
            )
    log.info("workable: %d jobs", len(jobs))
    return jobs
