"""LinkedIn public guest search.

LinkedIn exposes an unauthenticated endpoint used by its own
"see more jobs" widget. It returns HTML job cards that we parse
with a tiny regex rather than bringing in BeautifulSoup.

Endpoint:
  https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
  ?keywords=<q>&location=<loc>&f_TPR=r86400&start=<offset>
    f_TPR=r86400  -> past 24h
    f_TPR=r604800 -> past 7d

After the card list is built we fetch each job's detail page in
parallel and extract its full description. Without that step, downstream
filters (YoE, work_auth) have empty text to work with and citizenship /
experience requirements hidden in the body sneak through.
"""
from __future__ import annotations

import concurrent.futures
import logging
import re
from typing import Iterable
from urllib.parse import urlencode

from .base import HttpClient, Job, parse_when, strip_html

log = logging.getLogger(__name__)

BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
JOB_VIEW = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"

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
_JOB_ID_RE = re.compile(r"/jobs/view/[^/]*?(\d{8,})(?:[/?#]|$)")
_DESC_RE = re.compile(
    r'<div[^>]*class="[^"]*(?:show-more-less-html__markup|description__text)[^"]*"[^>]*>'
    r"(.*?)</div>",
    re.DOTALL | re.IGNORECASE,
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


def _job_id(url: str) -> str | None:
    m = _JOB_ID_RE.search(url or "")
    return m.group(1) if m else None


def _fetch_description(http: HttpClient, url: str) -> str:
    """Fetch the LinkedIn job detail page and extract the full description.

    LinkedIn exposes a logged-out HTML snippet of the full JD at
    /jobs-guest/jobs/api/jobPosting/<id>. Falling back to the canonical
    /jobs/view/<id> URL if the id can't be parsed out.
    """
    jid = _job_id(url)
    detail_url = f"{JOB_VIEW}{jid}" if jid else url
    try:
        html = http.get_text(
            detail_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
    except Exception:
        return ""
    m = _DESC_RE.search(html)
    return strip_html(m.group(1)) if m else ""


def _enrich_descriptions(http: HttpClient, jobs: list[Job], max_workers: int = 10) -> int:
    """Fill in Job.description for each URL via a bounded thread pool.

    Returns the number of jobs that got a non-empty description back.
    """
    if not jobs:
        return 0
    filled = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_description, http, j.url): j for j in jobs}
        for f in concurrent.futures.as_completed(futures):
            j = futures[f]
            try:
                desc = f.result(timeout=15) or ""
            except Exception:
                desc = ""
            if desc:
                j.description = desc
                filled += 1
    return filled


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
    filled = _enrich_descriptions(http, jobs)
    log.info("linkedin: %d jobs (%d with description)", len(jobs), filled)
    return jobs
