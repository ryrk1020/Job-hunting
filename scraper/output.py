"""Serialize jobs to JSON, CSV, Markdown, plus a calendar SPA dashboard."""
from __future__ import annotations

import csv
import io
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .io_utils import atomic_write_text

WEB_DIR = Path(__file__).parent / "web"

# Cap each posting's stored description so a single 50KB HTML blob can't
# bloat the daily archive. Filtering already operates on the full
# pre-trim text, so this only affects on-disk size + dashboard payload.
DESCRIPTION_CAP_CHARS = 16_000


def _strip_internal(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        clean = {k: v for k, v in r.items() if not k.startswith("_")}
        desc = clean.get("description")
        if isinstance(desc, str) and len(desc) > DESCRIPTION_CAP_CHARS:
            clean["description"] = desc[:DESCRIPTION_CAP_CHARS] + "…"
        out.append(clean)
    return out


def write_json(rows: list[dict], path: Path) -> None:
    payload = json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(rows),
            "jobs": _strip_internal(rows),
        },
        indent=2,
        ensure_ascii=False,
    )
    atomic_write_text(path, payload)


def write_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "score", "directness", "posted_at", "source", "company", "title",
        "location", "url", "salary_min", "salary_max", "required_years",
        "tech_tags", "matched_groups", "preferred_location", "alt_sources",
    ]
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        row = dict(r)
        row["matched_groups"] = ",".join(r.get("matched_groups", []) or [])
        row["tech_tags"] = ",".join(r.get("tech_tags", []) or [])
        # Compress alt_sources to a comma-separated list of URLs so
        # the CSV stays one-row-per-job.
        row["alt_sources"] = ",".join(
            a.get("url", "") for a in (r.get("alt_sources") or []) if a.get("url")
        )
        w.writerow(row)
    atomic_write_text(path, buf.getvalue())


def write_markdown(rows: list[dict], path: Path) -> None:
    lines = [
        f"# Latest Jobs ({len(rows)})",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "| # | Score | Posted | Source | Company | Title | Location | Link |",
        "|---|-------|--------|--------|---------|-------|----------|------|",
    ]
    for i, r in enumerate(rows, 1):
        posted = (r.get("posted_at") or "")[:10]
        lines.append(
            "| {i} | {score} | {posted} | {source} | {company} | {title} | {location} | [apply]({url}) |".format(
                i=i,
                score=r.get("score", 0),
                posted=posted,
                source=r.get("source", ""),
                company=(r.get("company") or "").replace("|", "/"),
                title=(r.get("title") or "").replace("|", "/"),
                location=(r.get("location") or "").replace("|", "/"),
                url=r.get("url", ""),
            )
        )
    atomic_write_text(path, "\n".join(lines))


def write_manifest(out_dir: Path) -> None:
    archive = out_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    days = []
    for p in sorted(archive.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            days.append({"date": p.stem, "count": data.get("count", 0)})
        except (json.JSONDecodeError, OSError):
            continue
    atomic_write_text(
        out_dir / "manifest.json",
        json.dumps(
            {"days": days, "generated_at": datetime.now(timezone.utc).isoformat()},
            indent=2,
        ),
    )


def copy_web_assets(out_dir: Path) -> None:
    """Copy the SPA dashboard (index.html, app.js, styles.css) into output/."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not WEB_DIR.exists():
        return
    for name in ("index.html", "app.js", "styles.css"):
        src = WEB_DIR / name
        if src.exists():
            shutil.copy2(src, out_dir / name)


def write_all(rows: list[dict], out_dir: Path, day: str) -> dict:
    """Write today's snapshot + refresh manifest + copy dashboard assets."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out_dir / "jobs.json",
        "csv": out_dir / "jobs.csv",
        "md": out_dir / "jobs.md",
    }
    write_json(rows, paths["json"])
    write_csv(rows, paths["csv"])
    write_markdown(rows, paths["md"])

    # Same-day re-runs overwrite: rows are already capped at min_jobs_target
    # by main.py, so the archive is always exactly that many top-scored jobs.
    # Cross-day dedup via seen.json means a rerun's fresh picks never
    # duplicate prior days' postings.
    archive = out_dir / "archive" / f"{day}.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    write_json(rows, archive)

    copy_web_assets(out_dir)
    write_manifest(out_dir)
    paths["html"] = out_dir / "index.html"
    paths["manifest"] = out_dir / "manifest.json"
    paths["archive"] = archive
    return {k: str(v) for k, v in paths.items()}
