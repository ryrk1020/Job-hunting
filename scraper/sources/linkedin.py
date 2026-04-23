"""LinkedIn public guest search.

LinkedIn exposes an unauthenticated endpoint used by its own
"see more jobs" widget. It returns HTML job cards that we parse
with a tiny regex rather than bringing in BeautifulSoup.

Endpoint:
  https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
  ?keywords=<q>&location=<loc>&f_TPR=r86400&start=<offset>
    f_TPR=r86400  -> past 24h
    f_TPR=r604800 -> past 7d
"""
from __future__ import annotations

import logging
import re
from typing import Iterable
from urllib.parse import urlencode

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Each card is a <li> containing anchor w/ tracking link, company, location, list-date.
_LI_CARD_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.DOTALL | re.IGNORECASE)
_URL_RE = re.compile(r'href="([^"]+?/jobs/view/[^"]+)"', re.IGNORECASE)
_TITLE_RE = re.compile(
    r'<h3[^>]*class="[^"]*base-search-card__title[^"]*"[^>]*>(.*?)</h3>',
    re.DOTALL | re.IGNORECASE,
)
_COMPANY_RE = re.compile(
    r'<h4[^>]*class="[^"]*base-search-card__subtitle[^"]*"[^>]*>(.*?)</h4>',
    re.DOTALL | re.IGNORECASE,
)
_LOC_RE = re.compile(
    r'<span[^>]*class="[^"]*job-search-card__location[^"]*"[^>]*>(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
_TIME_RE = re.compile(
    r'<time[^>]*datetime="([^"]+)"', re.IGNORECASE,
)


def _canonical(url: str) -> str:
    # Strip query / tracking; the canonical job URL is /jobs/view/<id>
    m = re.match(r"(https?://[^?#]+/jobs/view/[^?#/]+)", url)
    return m.group(1) if m else url


def _parse_cards(html: str) -> list[dict]:
    out: list[dict] = []
    for card in _LI_CARD_RE.findall(html):
        url_m = _URL_RE.search(card)
        if not url_m:
            continue
        title = strip_html((_TITLE_RE.search(card) or [None, ""]).group(1)) if _TITLE_RE.search(card) else ""
        company = strip_html((_COMPANY_RE.search(card) or [None, ""]).group(1)) if _COMPANY_RE.search(card) else ""
        loc = strip_html((_LOC_RE.search(card) or [None, ""]).group(1)) if _LOC_RE.search(card) else ""
        posted = (_TIME_RE.search(card) or [None, None]).group(1) if _TIME_RE.search(card) else None
        out.append(
            {
                "url": _canonical(url_m.group(1)),
                "title": title,
                "company": company,
                "location": loc,
                "posted": posted,
            }
        )
    return out


def fetch(http: HttpClient, queries: Iterable[dict], max_pages: int = 3) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()
    for spec in queries:
        keywords = spec.get("q", "")
        location = spec.get("l", "")
        for page in range(max_pages):
            params = {
                "keywords": keywords,
                "location": location,
                "f_TPR": "r604800",   # past week
                "start": page * 25,
            }
            url = f"{BASE}?{urlencode(params)}"
            try:
                html = http.get_text(
                    url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
            except Exception as e:
                log.warning("linkedin %s/%s p%d failed: %s", keywords, location, page, e)
                break
            cards = _parse_cards(html)
            if not cards:
                break
            new_this_page = 0
            for c in cards:
                if c["url"] in seen or not c["url"]:
                    continue
                seen.add(c["url"])
                new_this_page += 1
                jobs.append(
                    Job(
                        source="linkedin",
                        company=c["company"],
                        title=c["title"],
                        location=c["location"],
                        url=c["url"],
                        posted_at=parse_when(c["posted"]),
                        raw_id=c["url"],
                    )
                )
            if new_this_page == 0:
                break
    log.info("linkedin: %d jobs", len(jobs))
    return jobs
