"""Workday — many large employers host jobs here.

Workday tenants expose a JSON endpoint used by their public careers site:
  POST https://<tenant>.<host>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs
  body: { "appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "<q>" }

Job detail page format:
  https://<tenant>.<host>.myworkdayjobs.com/<site><externalPath>
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests

from .base import HttpClient, Job, parse_when

log = logging.getLogger(__name__)


def _tenant_url(tenant: str, host: str, site: str) -> str:
    return f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"


def _site_base(tenant: str, host: str, site: str) -> str:
    return f"https://{tenant}.{host}.myworkdayjobs.com/{site}"


def _posted_to_datetime(posted: str):
    # Workday returns strings like "Posted Yesterday" / "Posted 3 Days Ago".
    # We can't parse reliably; return None and let the freshness filter skip
    # via the posted_at=None branch (treated as "unknown, keep").
    return None


def fetch(http: HttpClient, tenants: Iterable[dict], queries: Iterable[str]) -> list[Job]:
    jobs: list[Job] = []
    for t in tenants:
        tenant = t["tenant"]
        host = t.get("host", "wd1")
        site = t["site"]
        endpoint = _tenant_url(tenant, host, site)
        base = _site_base(tenant, host, site)
        for q in queries:
            for offset in (0, 20, 40):
                try:
                    r = http.s.post(
                        endpoint,
                        json={
                            "appliedFacets": {},
                            "limit": 20,
                            "offset": offset,
                            "searchText": q,
                        },
                        headers={"Accept": "application/json", "Content-Type": "application/json"},
                        timeout=http.timeout,
                    )
                    r.raise_for_status()
                    payload = r.json()
                except (requests.RequestException, ValueError) as e:
                    log.warning("workday %s/%s %s o=%d failed: %s", tenant, site, q, offset, e)
                    break
                postings = payload.get("jobPostings", [])
                if not postings:
                    break
                for item in postings:
                    ext = item.get("externalPath") or ""
                    url = f"{base}{ext}" if ext.startswith("/") else f"{base}/{ext}"
                    jobs.append(
                        Job(
                            source="workday",
                            company=tenant,
                            title=item.get("title") or "",
                            location=item.get("locationsText") or "",
                            url=url,
                            posted_at=_posted_to_datetime(item.get("postedOn") or ""),
                            raw_id=item.get("bulletFields", [""])[0] or ext,
                            extra={"postedOn": item.get("postedOn")},
                        )
                    )
    log.info("workday: %d jobs", len(jobs))
    return jobs
