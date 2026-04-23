"""RemoteOK — https://remoteok.com/api returns a JSON array."""
from __future__ import annotations

import logging

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

ENDPOINT = "https://remoteok.com/api"


def fetch(http: HttpClient) -> list[Job]:
    try:
        data = http.get_json(ENDPOINT)
    except Exception as e:
        log.warning("remoteok failed: %s", e)
        return []
    jobs: list[Job] = []
    # First element is a metadata / legal header dict — skip anything without an id.
    for item in data:
        if not isinstance(item, dict) or "id" not in item:
            continue
        url = item.get("url") or item.get("apply_url") or ""
        if not url:
            continue
        jobs.append(
            Job(
                source="remoteok",
                company=item.get("company") or "",
                title=item.get("position") or item.get("title") or "",
                location=item.get("location") or "Remote",
                url=url,
                posted_at=parse_when(item.get("date") or item.get("epoch")),
                description=strip_html(item.get("description")),
                remote=True,
                raw_id=str(item.get("id")),
            )
        )
    log.info("remoteok: %d jobs", len(jobs))
    return jobs
