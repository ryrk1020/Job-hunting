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
        # Used for dedup across sources. URL alone isn't enough because
        # the same job appears on Greenhouse and on the company site.
        key = "|".join([
            (self.company or "").strip().lower(),
            (self.title or "").strip().lower(),
            (self.location or "").strip().lower(),
        ])
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

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
