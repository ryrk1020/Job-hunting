"""The Muse — public jobs API (no key needed).

https://www.themuse.com/developers/api/v2
"""
from __future__ import annotations

import logging
from typing import Iterable

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

ENDPOINT = "https://www.themuse.com/api/public/jobs"


def fetch(http: HttpClient, categories: Iterable[str], locations: Iterable[str]) -> list[Job]:
    jobs: list[Job] = []
    # Paginate a few pages; 20 items/page is the public cap.
    for page in range(0, 5):
        params: list[tuple[str, str]] = [("page", str(page))]
        for c in categories:
            params.append(("category", c))
        for loc in locations:
            params.append(("location", loc))
        try:
            payload = http.get_json(ENDPOINT, params=params)
        except Exception as e:
            log.warning("themuse page %d failed: %s", page, e)
            break
        results = payload.get("results", [])
        if not results:
            break
        for item in results:
            url = ""
            refs = item.get("refs") or {}
            if isinstance(refs, dict):
                url = refs.get("landing_page") or ""
            if not url:
                continue
            loc_name = ""
            locs = item.get("locations") or []
            if locs:
                loc_name = locs[0].get("name", "")
            company = ""
            comp = item.get("company") or {}
            if isinstance(comp, dict):
                company = comp.get("name", "")
            jobs.append(
                Job(
                    source="themuse",
                    company=company,
                    title=item.get("name") or "",
                    location=loc_name,
                    url=url,
                    posted_at=parse_when(item.get("publication_date")),
                    description=strip_html(item.get("contents")),
                    remote="remote" in loc_name.lower(),
                    raw_id=str(item.get("id") or ""),
                )
            )
    log.info("themuse: %d jobs", len(jobs))
    return jobs
