"""Shared types and helpers for job source adapters."""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from dateutil import parser as dateparser

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 job-hunter/1.0"
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Source directness ranking — used to pick the best representative when
# the same posting appears across multiple sources. Higher = more direct
# apply path (URL leads straight to the company's ATS / application
# form). Lower = aggregator or guest-search redirect.
#
# Direct ATS posts (clicking goes straight to the application form).
# Aggregators / job boards (apply usually one redirect away).
# Guest-search engines (often two redirects to the real form).
SOURCE_DIRECTNESS: dict[str, int] = {
    # Direct ATS — apply form is on the linked page.
    "greenhouse":      100,
    "lever":           100,
    "ashby":           100,
    "workable":         95,
    "workday":          95,
    "smartrecruiters":  90,
    # Public APIs that typically link to the company's official posting.
    "adzuna":           70,
    "usajobs":          70,
    "ycombinator":      65,   # YC has its own apply flow per startup
    "themuse":          60,
    # Pure aggregators — clicking opens the aggregator's view, then a
    # second click redirects to the real apply page.
    "remotive":         55,
    "remoteok":         55,
    "indeed_rss":       40,   # indeed.com → original posting
    "linkedin":         35,   # linkedin guest job → company ATS
}


def directness(source: str) -> int:
    """Rank for a given source name. Unknown sources default to 50."""
    return SOURCE_DIRECTNESS.get((source or "").lower(), 50)


# Title decorators that should not change job identity. Stripped before
# fingerprinting so 'Data Engineer (Remote)' and 'Data Engineer - Remote'
# fingerprint identically to the same role on another board.
_TITLE_NOISE_RE = re.compile(
    r"\s*(?:"
    r"\(remote\)|\(hybrid\)|\(onsite\)|\(on-?site\)|"
    r"\(us\)|\(usa\)|\(united states\)|"
    r"\(contract\)|\(full[- ]time\)|\(ft\)|"
    r"-\s*remote(?:\s|$)|-\s*hybrid(?:\s|$)|-\s*onsite(?:\s|$)|"
    r"\s*\|\s*remote\b|\s*\|\s*hybrid\b|"
    r"#\s*li-\w+"
    r")",
    re.IGNORECASE,
)
# Company suffixes / decorations to strip — same Deloitte should match
# whether it surfaces as "Deloitte", "Deloitte Inc.", "Deloitte LLP",
# "Deloitte Consulting", etc.
_COMPANY_SUFFIX_RE = re.compile(
    r"[,\s]+(?:inc\.?|llc\.?|llp\.?|ltd\.?|limited|corp\.?|corporation|"
    r"co\.?|company|consulting|usa|us|u\.s\.|holdings|group)\b",
    re.IGNORECASE,
)
# Country-suffix tokens to strip so 'Dallas, TX, United States' and
# 'Dallas, TX, USA' fingerprint as the same.
_LOCATION_COUNTRY_RE = re.compile(
    r",\s*(?:united states|usa|u\.s\.a\.?|u\.s\.|america)\b",
    re.IGNORECASE,
)

# Map full US state names to their 2-letter postal code so that
# 'Dallas, Texas' and 'Dallas, TX' fingerprint identically.
_STATE_NAME_TO_CODE = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct",
    "delaware": "de", "florida": "fl", "georgia": "ga", "hawaii": "hi",
    "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
    "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me",
    "maryland": "md", "massachusetts": "ma", "michigan": "mi",
    "minnesota": "mn", "mississippi": "ms", "missouri": "mo",
    "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm",
    "new york": "ny", "north carolina": "nc", "north dakota": "nd",
    "ohio": "oh", "oklahoma": "ok", "oregon": "or",
    "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa",
    "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
    "district of columbia": "dc",
}
_STATE_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in _STATE_NAME_TO_CODE) + r")\b",
    re.IGNORECASE,
)


def _normalize_title(s: str) -> str:
    s = _TITLE_NOISE_RE.sub(" ", s or "")
    s = _WS_RE.sub(" ", s).strip().lower()
    return s


def _normalize_company(s: str) -> str:
    s = _COMPANY_SUFFIX_RE.sub("", s or "")
    s = _WS_RE.sub(" ", s).strip().lower()
    return s


def _normalize_location(s: str) -> str:
    s = s or ""
    # Map state names to their 2-letter codes so 'Texas' == 'TX'.
    s = _STATE_NAME_RE.sub(lambda m: _STATE_NAME_TO_CODE[m.group(1).lower()], s)
    s = _LOCATION_COUNTRY_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip().lower()
    return s


def strip_html(s: Optional[str]) -> str:
    if not s:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", s)).strip()


def parse_when(s: Any) -> Optional[datetime]:
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except (OSError, ValueError):
            return None
    try:
        dt = dateparser.parse(str(s))
    except (ValueError, TypeError, OverflowError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class Job:
    source: str
    company: str
    title: str
    location: str
    url: str
    posted_at: Optional[datetime] = None
    description: str = ""
    remote: bool = False
    raw_id: str = ""
    extra: dict = field(default_factory=dict)

    def fingerprint(self) -> str:
        """Stable cross-source identity hash.

        Same role on Greenhouse vs. on LinkedIn vs. on Indeed must
        produce the same fingerprint so dedup picks one. Normalization
        strips company suffixes (Inc/LLC/LLP/Consulting), title
        decorators ((Remote)/(Hybrid)/etc.), and location decorators
        (', United States') — those vary across sources for the same
        underlying posting.
        """
        key = "|".join([
            _normalize_company(self.company),
            _normalize_title(self.title),
            _normalize_location(self.location),
        ])
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    def directness(self) -> int:
        """Rank for this job's source — used to pick the most-direct
        apply URL when the same job appears across multiple sources.
        """
        return directness(self.source)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["posted_at"] = self.posted_at.isoformat() if self.posted_at else None
        return d


class HttpClient:
    """Tiny wrapper so every adapter gets consistent headers + timeouts."""

    def __init__(self, timeout: int = 20):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept": "application/json, */*"})
        self.timeout = timeout

    def get_json(self, url: str, **kw) -> Any:
        r = self.s.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r.json()

    def get_text(self, url: str, **kw) -> str:
        r = self.s.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r.text
