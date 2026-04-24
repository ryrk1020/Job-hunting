"""Serialize jobs to JSON, CSV, Markdown, plus a calendar SPA dashboard."""
from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WEB_DIR = Path(__file__).parent / "web"


def _strip_internal(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({k: v for k, v in r.items() if not k.startswith("_")})
    return out


def write_json(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "count": len(rows),
                "jobs": _strip_internal(rows),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "score", "posted_at", "source", "company", "title",
        "location", "url", "matched_groups", "preferred_location",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = dict(r)
            row["matched_groups"] = ",".join(r.get("matched_groups", []))
            w.writerow(row)


def write_markdown(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    path.write_text("\n".join(lines), encoding="utf-8")


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
    (out_dir / "manifest.json").write_text(
        json.dumps({"days": days, "generated_at": datetime.now(timezone.utc).isoformat()},
                   indent=2),
        encoding="utf-8",
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
