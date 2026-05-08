"""Built In — public HTML scrape of the per-city job listing pages.

Built In aggregates tech-only postings for major US tech metros (Austin,
Dallas, Houston, Remote). Each posting links to the company's own apply
page (one redirect away in most cases — directness ~70).

This adapter is a *best-effort* HTML scraper. If Built In changes their
markup, the adapter logs a warning and contributes 0 jobs without
breaking the rest of the pipeline. URL pattern:

    https://builtin.com/jobs/<city-slug>?search=<query>
"""
from __future__ import annotations

import html as html_mod
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .base import HttpClient, Job, strip_html


def _clean(s: str) -> str:
    """Strip HTML tags, decode entities, collapse whitespace."""
    return re.sub(r"\s+", " ", html_mod.unescape(strip_html(s or ""))).strip()

log = logging.getLogger(__name__)

ENDPOINT = "https://builtin.com/jobs"

# A job card on builtin.com is a chunk of HTML containing:
#   <a ... data-builtin-track-job-id="<id>" ...>Job title</a>
#   <a ... cursor-pointer ...><span>Company name</span></a>
#   <span class="...">An Hour Ago</span> | "2 Days Ago" | "Posted 3 hours ago"
#   <span class="font-barlow text-gray-04">Hybrid|Remote|Onsite</span>
#   <span class="font-barlow text-gray-04">City, ST</span>
#
# We split the page on track-job-id markers and pull each card out
# heuristically. Robustness > completeness — missing fields just mean
# the row is skipped.
_CARD_SPLIT = re.compile(r'data-builtin-track-job-id="(\d+)"')
_TITLE_RE = re.compile(
    r'data-id="job-card-title"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)
_TITLE_URL_RE = re.compile(
    r'href="(/job/[^"]+)"[^>]*data-id="job-card-title"',
    re.IGNORECASE,
)
_COMPANY_RE = re.compile(
    r'cursor-pointer[^"]*"[^>]*><span[^>]*>([^<]+)</span></a>',
    re.IGNORECASE,
)
_AGO_RE = re.compile(
    r'>(\d+|an?|few)\s*(minute|min|hour|hr|day|week|month)s?\s*ago<',
    re.IGNORECASE,
)
_LOCATION_RE = re.compile(
    r'fa-location-dot[^<]*</i>[^<]*</div>\s*<span[^>]*>([^<]+)</span>',
    re.IGNORECASE,
)
_REMOTE_HINT_RE = re.compile(r'\b(Remote|Hybrid|Onsite)\b', re.IGNORECASE)


def _parse_ago(text: str) -> datetime | None:
    """Convert 'An Hour Ago' / '2 Days Ago' / 'Few Minutes Ago' to a UTC
    datetime. Returns None if the phrase can't be parsed."""
    if not text:
        return None
    m = _AGO_RE.search(text)
    if not m:
        return None
    qty_raw = m.group(1).lower()
    unit = m.group(2).lower()
    if qty_raw in ("a", "an"):
        qty = 1
    elif qty_raw == "few":
        qty = 3
    else:
        try:
            qty = int(qty_raw)
        except ValueError:
            return None
    seconds = {
        "minute": 60, "min": 60,
        "hour": 3600, "hr": 3600,
        "day": 86400,
        "week": 86400 * 7,
        "month": 86400 * 30,
    }.get(unit)
    if seconds is None:
        return None
    return datetime.now(timezone.utc) - timedelta(seconds=qty * seconds)


def _extract_cards(html: str) -> list[dict]:
    """Heuristically pull job-card data out of the listing HTML."""
    cards: list[dict] = []
    # Split on track-job-id markers — each marker is at the start of a
    # job card. Keep the marker and its trailing chunk for parsing.
    parts = _CARD_SPLIT.split(html)
    # parts is ['... pre ...', id1, 'card1 html', id2, 'card2 html', ...]
    for i in range(1, len(parts), 2):
        job_id = parts[i]
        chunk = parts[i + 1] if i + 1 < len(parts) else ""
        # Look back into the previous chunk too — sometimes the title
        # link is on the same line as the data-builtin-track-job-id.
        prev = parts[i - 1][-2000:] if i - 1 < len(parts) else ""
        merged = prev + chunk[:4000]

        m_title = _TITLE_RE.search(merged)
        m_url = _TITLE_URL_RE.search(merged)
        m_company = _COMPANY_RE.search(merged)
        m_loc = _LOCATION_RE.search(chunk[:4000])
        m_ago = _AGO_RE.search(chunk[:4000])
        m_mode = _REMOTE_HINT_RE.search(chunk[:4000])

        if not (m_title and m_url):
            continue
        title = _clean(m_title.group(1)).strip()
        path = m_url.group(1)
        url = f"https://builtin.com{path}"
        company = _clean(m_company.group(1)).strip() if m_company else ""
        location = _clean(m_loc.group(1)).strip() if m_loc else ""
        posted_at = _parse_ago(m_ago.group(0)) if m_ago else None
        remote = bool(m_mode and m_mode.group(1).lower() in ("remote", "hybrid"))
        cards.append({
            "id": job_id,
            "title": title,
            "url": url,
            "company": company,
            "location": location,
            "posted_at": posted_at,
            "remote": remote,
        })
    return cards


def fetch(http: HttpClient, queries: Iterable[dict]) -> list[Job]:
    """Fetch Built In postings for each (city, query) pair.

    queries: iterable of {"city": "dallas-tx", "q": "data engineer"}.
    """
    jobs: list[Job] = []
    seen: set[str] = set()
    for q in queries:
        city = q.get("city", "").strip()
        query = q.get("q", "").strip()
        if not city:
            continue
        url = f"{ENDPOINT}/{city}"
        params = {"search": query} if query else {}
        try:
            html = http.get_text(url, params=params)
        except Exception as e:
            log.warning("builtin %s/%s failed: %s", city, query, e)
            continue
        cards = _extract_cards(html)
        for c in cards:
            if c["url"] in seen:
                continue
            seen.add(c["url"])
            jobs.append(Job(
                source="builtin",
                company=c["company"],
                title=c["title"],
                location=c["location"] or "Remote",
                url=c["url"],
                posted_at=c["posted_at"],
                description="",  # list-only page; would require per-job fetch
                remote=c["remote"],
                raw_id=c["id"],
            ))
    log.info("builtin: %d jobs", len(jobs))
    return jobs
