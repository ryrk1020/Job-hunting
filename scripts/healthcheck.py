"""Apply-link health check.

Walk every URL in output/seen.json, issue a HEAD (with GET fallback) per
URL, and remove entries that return 404/410/DNS-failure. The intent is
to free up dedup slots so postings that have been refreshed by the
employer can resurface in tomorrow's archive.

The script is idempotent and conservative — anything other than a hard
404/410/DNS failure is kept (5xx, timeouts, 401/403 — those frequently
mean rate-limiting or auth, not a dead posting).

Run weekly via .github/workflows/weekly-cleanup.yml or locally:

    python -m scripts.healthcheck --seen output/seen.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import logging
import sys
import time
from pathlib import Path

import requests

log = logging.getLogger("healthcheck")

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 job-hunter-healthcheck/1.0"
)
TIMEOUT = 10
DEAD_CODES = {404, 410}
WORKERS = 16


def _check_url(url: str) -> tuple[str, bool]:
    """Return (url, is_dead). is_dead is True only for 404/410/DNS."""
    try:
        # HEAD is cheaper but some sites reject it; fall back to GET on 405/501.
        r = requests.head(url, timeout=TIMEOUT, allow_redirects=True,
                          headers={"User-Agent": UA})
        if r.status_code in (405, 501):
            r = requests.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True,
                             headers={"User-Agent": UA})
            r.close()
        return url, r.status_code in DEAD_CODES
    except requests.exceptions.ConnectionError as e:
        # DNS failure / dead host counts as dead.
        msg = str(e).lower()
        if "name or service not known" in msg or "getaddrinfo failed" in msg \
           or "no such host" in msg or "nodename nor servname" in msg:
            return url, True
        return url, False
    except requests.exceptions.Timeout:
        return url, False
    except Exception:
        return url, False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Drop dead URLs from seen.json")
    p.add_argument("--seen", default="output/seen.json", type=Path,
                   help="Path to the SeenStore JSON file")
    p.add_argument("--max-urls", type=int, default=2000,
                   help="Cap how many URLs we check per run (oldest first)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.seen.exists():
        log.info("no seen.json at %s; nothing to check", args.seen)
        return 0

    data = json.loads(args.seen.read_text(encoding="utf-8"))
    urls: dict[str, str] = data.get("urls", {}) or {}
    fingerprints: dict[str, str] = data.get("fingerprints", {}) or {}
    log.info("loaded %d urls / %d fingerprints", len(urls), len(fingerprints))

    # Walk oldest-first so churn is bounded across weekly runs.
    ordered = sorted(urls.items(), key=lambda kv: kv[1])  # by date asc
    to_check = ordered[: args.max_urls]
    log.info("checking %d urls (cap=%d)", len(to_check), args.max_urls)

    started = time.time()
    dead_urls: list[str] = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for url, is_dead in pool.map(lambda kv: _check_url(kv[0]), to_check):
            if is_dead:
                dead_urls.append(url)
    elapsed = time.time() - started
    log.info("checked %d urls in %.1fs; %d dead",
             len(to_check), elapsed, len(dead_urls))

    if not dead_urls:
        return 0

    if args.dry_run:
        log.info("[dry-run] would remove %d entries", len(dead_urls))
        for u in dead_urls[:10]:
            log.info("  %s", u)
        return 0

    # Drop dead URLs from the store. Fingerprints stay — even if the URL
    # 404s now, the (company, title, location) fingerprint may still
    # appear under a different URL in the future and we don't want to
    # re-surface it as fresh.
    dropped_urls = 0
    for u in dead_urls:
        if u in urls:
            del urls[u]
            dropped_urls += 1
    data["urls"] = urls
    data["fingerprints"] = fingerprints
    args.seen.write_text(
        json.dumps(data, indent=0, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("dropped %d dead URL entries from %s", dropped_urls, args.seen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
