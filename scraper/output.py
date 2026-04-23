"""Serialize jobs to JSON, CSV, Markdown, and HTML dashboard."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def write_json(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "count": len(rows),
                "jobs": rows,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "score",
        "posted_at",
        "source",
        "company",
        "title",
        "location",
        "url",
        "matched_groups",
        "preferred_location",
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


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Job Hunter – {count} jobs</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root {{
    --bg: #0f172a; --panel: #1e293b; --ink: #e2e8f0;
    --muted: #94a3b8; --accent: #38bdf8; --good: #22c55e; --warn: #f59e0b;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg); color: var(--ink);
  }}
  header {{ padding: 24px; border-bottom: 1px solid #334155; }}
  header h1 {{ margin: 0 0 6px; font-size: 20px; }}
  header p {{ margin: 0; color: var(--muted); font-size: 13px; }}
  .controls {{ padding: 16px 24px; display: flex; gap: 12px; flex-wrap: wrap;
               background: var(--panel); border-bottom: 1px solid #334155; }}
  .controls input, .controls select {{
    background: #0f172a; color: var(--ink); border: 1px solid #334155;
    padding: 8px 10px; border-radius: 6px; font-size: 13px;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #334155;
           vertical-align: top; }}
  th {{ position: sticky; top: 0; background: var(--panel); color: var(--muted);
         font-weight: 600; text-transform: uppercase; font-size: 11px;
         letter-spacing: 0.05em; }}
  tr:hover {{ background: #172032; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .score {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
            background: #0b3a66; color: #bae6fd; font-weight: 600; }}
  .tag {{ display: inline-block; padding: 1px 7px; border-radius: 10px;
           background: #334155; color: var(--ink); font-size: 11px; margin-right: 4px; }}
  .tag.data {{ background: #1e3a8a; }}
  .tag.marketing {{ background: #5b21b6; }}
  .tag.vibecoding {{ background: #065f46; color: #d1fae5; }}
  .tag.junior {{ background: #7c2d12; }}
  .tag.preferred {{ background: #14532d; color: #bbf7d0; }}
  .source {{ color: var(--muted); font-size: 11px; }}
</style>
</head>
<body>
<header>
  <h1>Job Hunter — {count} fresh jobs</h1>
  <p>Generated {generated}. Filter by typing any keyword (company, title, location, source).</p>
</header>
<div class="controls">
  <input id="q" placeholder="Search…" autofocus />
  <select id="group">
    <option value="">All groups</option>
    <option value="data">Data</option>
    <option value="marketing">Marketing</option>
    <option value="vibecoding">Vibecoding / AI</option>
  </select>
  <select id="loc">
    <option value="">All locations</option>
    <option value="preferred">Preferred (TX metro)</option>
    <option value="remote">Remote</option>
  </select>
</div>
<table id="jobs">
  <thead>
    <tr>
      <th>#</th><th>Score</th><th>Posted</th><th>Company</th>
      <th>Title</th><th>Location</th><th>Tags</th><th>Link</th>
    </tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>
<script>
const q = document.getElementById('q');
const group = document.getElementById('group');
const loc = document.getElementById('loc');
const rows = Array.from(document.querySelectorAll('#jobs tbody tr'));
function apply() {{
  const s = q.value.toLowerCase();
  const g = group.value;
  const l = loc.value;
  for (const r of rows) {{
    const txt = r.dataset.text;
    const tags = r.dataset.tags;
    const locType = r.dataset.loc;
    const matchText = !s || txt.includes(s);
    const matchGroup = !g || tags.includes(g);
    const matchLoc = !l || locType === l;
    r.style.display = (matchText && matchGroup && matchLoc) ? '' : 'none';
  }}
}}
[q, group, loc].forEach(el => el.addEventListener('input', apply));
</script>
</body>
</html>
"""


def _row_html(i: int, r: dict) -> str:
    tags = list(r.get("matched_groups", []))
    if r.get("preferred_location"):
        tags.append("preferred")
    tag_html = "".join(f'<span class="tag {t}">{t}</span>' for t in tags)
    loc = r.get("location") or ""
    loc_type = "remote" if "remote" in loc.lower() else (
        "preferred" if r.get("preferred_location") else "other"
    )
    text_blob = " ".join([
        (r.get("company") or ""),
        (r.get("title") or ""),
        loc,
        r.get("source") or "",
        " ".join(r.get("matched_groups", [])),
    ]).lower().replace('"', "'")
    posted = (r.get("posted_at") or "")[:10]
    url = r.get("url") or "#"
    company = (r.get("company") or "").replace("<", "&lt;")
    title = (r.get("title") or "").replace("<", "&lt;")
    location = loc.replace("<", "&lt;")
    source = r.get("source") or ""
    return (
        f'<tr data-text="{text_blob}" data-tags="{",".join(tags)}" data-loc="{loc_type}">'
        f'<td>{i}</td>'
        f'<td><span class="score">{r.get("score", 0)}</span></td>'
        f'<td>{posted}</td>'
        f'<td>{company}<div class="source">{source}</div></td>'
        f'<td>{title}</td>'
        f'<td>{location}</td>'
        f'<td>{tag_html}</td>'
        f'<td><a href="{url}" target="_blank" rel="noopener">apply ↗</a></td>'
        f'</tr>'
    )


def write_html(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(_row_html(i, r) for i, r in enumerate(rows, 1))
    html = HTML_TEMPLATE.format(
        count=len(rows),
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        rows=body,
    )
    path.write_text(html, encoding="utf-8")


def write_all(rows: list[dict], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out_dir / "jobs.json",
        "csv": out_dir / "jobs.csv",
        "md": out_dir / "jobs.md",
        "html": out_dir / "index.html",
    }
    write_json(rows, paths["json"])
    write_csv(rows, paths["csv"])
    write_markdown(rows, paths["md"])
    write_html(rows, paths["html"])
    # Also keep a dated archive copy.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive = out_dir / "archive" / f"{stamp}.json"
    write_json(rows, archive)
    return {k: str(v) for k, v in paths.items()}
