"""Adzuna — free API, requires app id + key.

Sign up: https://developer.adzuna.com
Set env: ADZUNA_APP_ID, ADZUNA_APP_KEY
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

BASE = "https://api.adzuna.com/v1/api/jobs/us/search"


def fetch(http: HttpClient, queries: Iterable[str], where: Iterable[str]) -> list[Job]:
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        log.info("adzuna: skipped (ADZUNA_APP_ID / ADZUNA_APP_KEY not set)")
        return []

    jobs: list[Job] = []
    for q in queries:
        for loc in where:
            for page in (1, 2):
                params = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": q,
                    "where": loc,
                    "results_per_page": 50,
                    "max_days_old": 7,
                    "sort_by": "date",
                    "content-type": "application/json",
                }
                try:
                    payload = http.get_json(f"{BASE}/{page}", params=params)
                except Exception as e:
                    log.warning("adzuna %s/%s p%d failed: %s", q, loc, page, e)
                    break
                results = payload.get("results", [])
                if not results:
                    break
                for item in results:
                    company = ""
                    comp = item.get("company") or {}
                    if isinstance(comp, dict):
                        company = comp.get("display_name", "")
                    loc_name = ""
                    loc_obj = item.get("location") or {}
                    if isinstance(loc_obj, dict):
                        loc_name = loc_obj.get("display_name", "")
                    jobs.append(
                        Job(
                            source="adzuna",
                            company=company,
                            title=item.get("title") or "",
                            location=loc_name,
                            url=item.get("redirect_url") or "",
                            posted_at=parse_when(item.get("created")),
                            description=strip_html(item.get("description")),
                            raw_id=str(item.get("id") or ""),
                        )
                    )
    log.info("adzuna: %d jobs", len(jobs))
    return jobs
