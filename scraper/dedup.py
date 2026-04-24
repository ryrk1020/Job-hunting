"""Cross-day dedup store.

Tracks every job URL + (company,title,location) fingerprint we've ever
emitted, so the same posting never appears on two different days. The
store is a JSON file committed to the repo by the daily workflow.

Format:
    {
        "urls": {"<url>": "<first_seen_yyyy-mm-dd>"},
        "fingerprints": {"<fp>": "<first_seen_yyyy-mm-dd>"}
    }
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class SeenStore:
    def __init__(self, path: Path):
        self.path = path
        self.urls: dict[str, str] = {}
        self.fingerprints: dict[str, str] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.urls = data.get("urls", {}) or {}
                self.fingerprints = data.get("fingerprints", {}) or {}
            except (json.JSONDecodeError, OSError) as e:
                log.warning("seen store unreadable, starting fresh: %s", e)

    def has(self, url: str, fingerprint: str) -> bool:
        return (url and url in self.urls) or (fingerprint and fingerprint in self.fingerprints)

    def add(self, url: str, fingerprint: str, day: str) -> None:
        if url and url not in self.urls:
            self.urls[url] = day
        if fingerprint and fingerprint not in self.fingerprints:
            self.fingerprints[fingerprint] = day

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"urls": self.urls, "fingerprints": self.fingerprints},
                indent=0,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def stats(self) -> dict:
        return {"urls": len(self.urls), "fingerprints": len(self.fingerprints)}


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def filter_unseen(rows: list[dict], store: SeenStore) -> list[dict]:
    """Return only rows that haven't been seen on any prior day."""
    out = []
    for r in rows:
        url = r.get("url") or ""
        fp = r.get("_fp") or ""
        if store.has(url, fp):
            continue
        out.append(r)
    return out


def commit_seen(rows: list[dict], store: SeenStore, day: str) -> None:
    for r in rows:
        store.add(r.get("url") or "", r.get("_fp") or "", day)
    store.save()
