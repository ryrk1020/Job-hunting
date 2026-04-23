"""USAJOBS.gov — free API, register for a key.

https://developer.usajobs.gov
Set env: USAJOBS_EMAIL, USAJOBS_API_KEY
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

ENDPOINT = "https://data.usajobs.gov/api/search"


def fetch(http: HttpClient, queries: Iterable[str], locations: Iterable[str]) -> list[Job]:
    email = os.environ.get("USAJOBS_EMAIL")
    key = os.environ.get("USAJOBS_API_KEY")
    if not email or not key:
        log.info("usajobs: skipped (USAJOBS_EMAIL / USAJOBS_API_KEY not set)")
        return []
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": email,
        "Authorization-Key": key,
    }
    jobs: list[Job] = []
    for q in queries:
        for loc in locations:
            params = {"Keyword": q, "LocationName": loc, "ResultsPerPage": 50}
            try:
                payload = http.get_json(ENDPOINT, params=params, headers=headers)
            except Exception as e:
                log.warning("usajobs %s/%s failed: %s", q, loc, e)
                continue
            items = (
                payload.get("SearchResult", {}).get("SearchResultItems", []) or []
            )
            for item in items:
                d = item.get("MatchedObjectDescriptor", {})
                pos_locs = d.get("PositionLocationDisplay") or ""
                jobs.append(
                    Job(
                        source="usajobs",
                        company=d.get("OrganizationName") or "",
                        title=d.get("PositionTitle") or "",
                        location=pos_locs,
                        url=d.get("PositionURI") or "",
                        posted_at=parse_when(d.get("PublicationStartDate")),
                        description=strip_html(
                            (d.get("UserArea", {}).get("Details", {}) or {}).get(
                                "JobSummary", ""
                            )
                        ),
                        raw_id=str(d.get("PositionID") or ""),
                    )
                )
    log.info("usajobs: %d jobs", len(jobs))
    return jobs
