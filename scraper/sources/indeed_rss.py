"""Indeed public RSS — no key required.

Indeed exposes an RSS feed per search:
https://www.indeed.com/rss?q=<query>&l=<location>&fromage=7
"""
from __future__ import annotations

import logging
from typing import Iterable
from urllib.parse import urlencode, urlparse, parse_qs

import feedparser

from .base import Job, parse_when, strip_html

log = logging.getLogger(__name__)

BASE = "https://www.indeed.com/rss"


def _clean_url(link: str) -> str:
    # Indeed RSS links include tracking redirects; keep the jk so
    # the viewer can jump straight to the job page.
    try:
        u = urlparse(link)
        q = parse_qs(u.query)
        jk = q.get("jk", [None])[0]
        if jk:
            return f"https://www.indeed.com/viewjob?jk={jk}"
    except Exception:
        pass
    return link


def fetch(queries: Iterable[dict]) -> list[Job]:
    jobs: list[Job] = []
    for spec in queries:
        q = spec.get("q", "")
        loc = spec.get("l", "")
        url = f"{BASE}?{urlencode({'q': q, 'l': loc, 'fromage': 7, 'sort': 'date'})}"
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            log.warning("indeed_rss %s/%s failed: %s", q, loc, e)
            continue
        for entry in feed.entries:
            title = entry.get("title") or ""
            # Indeed titles are formatted "Data Engineer - Company - Dallas, TX"
            company = ""
            location = loc
            parts = [p.strip() for p in title.split(" - ")]
            if len(parts) >= 3:
                title = parts[0]
                company = parts[1]
                location = parts[2]
            link = _clean_url(entry.get("link") or "")
            if not link:
                continue
            jobs.append(
                Job(
                    source="indeed_rss",
                    company=company,
                    title=title,
                    location=location,
                    url=link,
                    posted_at=parse_when(entry.get("published")),
                    description=strip_html(entry.get("summary")),
                    raw_id=link,
                )
            )
    log.info("indeed_rss: %d jobs", len(jobs))
    return jobs
