"""Y Combinator — Work at a Startup.

Public Algolia-backed jobs search. For our purposes we only want jobs
at later-stage, well-funded YC companies (Series B+), so by default this
source is DISABLED unless the user explicitly enables it — it's a firehose
of early-stage roles otherwise.
"""
from __future__ import annotations

import logging

from .base import HttpClient, Job, parse_when

log = logging.getLogger(__name__)

# Simple, read-only Algolia endpoint used by the public site.
ENDPOINT = (
    "https://45bwzj1sgc-dsn.algolia.net/1/indexes/WaaSPublicCompanyJob/query"
    "?x-algolia-agent=Algolia%20for%20JavaScript%20(4.22.1)%3B%20Browser"
    "&x-algolia-api-key=55c37b4379e3fce35b7c7b36186f9b8f"
    "&x-algolia-application-id=45BWZJ1SGC"
)


def fetch(http: HttpClient, queries: list[str], allowed_stages: list[str] | None = None) -> list[Job]:
    allowed_stages = [s.lower() for s in (allowed_stages or ["series b", "series c", "series d", "public"])]
    jobs: list[Job] = []
    for i, q in enumerate(queries):
        try:
            r = http.s.post(
                ENDPOINT,
                json={"query": q, "hitsPerPage": 50},
                timeout=http.timeout,
            )
            r.raise_for_status()
            payload = r.json()
        except Exception as e:
            # If the very first query fails with 401/403/404, the
            # endpoint is dead/changed — bail out instead of spamming
            # a warning per query for the rest of the list.
            msg = str(e)
            if i == 0 and any(code in msg for code in ("401", "403", "404")):
                log.warning(
                    "ycombinator endpoint unreachable (%s); skipping remaining %d queries",
                    msg.split(":")[0], len(queries) - 1,
                )
                return jobs
            log.warning("ycombinator %s failed: %s", q, e)
            continue
        for hit in payload.get("hits", []):
            stage = (hit.get("company_stage") or "").lower()
            # Filter out too-early stage companies unless explicitly allowed.
            if allowed_stages and not any(s in stage for s in allowed_stages):
                continue
            slug = hit.get("company_slug") or ""
            jobs.append(
                Job(
                    source="ycombinator",
                    company=hit.get("company_name") or "",
                    title=hit.get("title") or "",
                    location=hit.get("location") or "",
                    url=f"https://www.workatastartup.com/jobs/{hit.get('id', '')}" if hit.get("id") else
                        f"https://www.workatastartup.com/companies/{slug}",
                    posted_at=parse_when(hit.get("created_at") or hit.get("posted_at")),
                    remote=bool(hit.get("remote")),
                    raw_id=str(hit.get("id") or ""),
                    extra={"stage": hit.get("company_stage"), "size": hit.get("company_size")},
                )
            )
    log.info("ycombinator: %d jobs", len(jobs))
    return jobs
