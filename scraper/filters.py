"""Filtering, scoring, and deduplication for scraped jobs."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .sources.base import Job

log = logging.getLogger(__name__)

_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
}

# Years-of-experience detection. The goal is to capture the LOWER-bound
# (minimum required) number from phrasings like:
#   "5+ years", "5-8 years", "5 to 8 years", "at least 5 years",
#   "minimum 5 years", "5 or more years", "8 yrs of professional exp",
#   "eight years of engineering experience", "must have 5 years".
_RANGE_SUFFIX = (
    r"(?:\s*(?:\+|\-\s*\d{1,2}|to\s+\d{1,2}|or\s*more|or\s*above|plus))?"
)
_EXP_CONTEXT = (
    r"(?:experience|exp\.?|industry|working|professional|hands\-?on|"
    r"background|software|development|engineering|programming|"
    r"coding|relevant|similar)"
)

_YOE_PATTERNS = [
    # "5+ years", "5-8 years", "5 years" followed within 80 chars by an
    # experience-context word.
    re.compile(
        r"(\d{1,2})" + _RANGE_SUFFIX + r"\s*(?:years?|yrs?)"
        r"\b[^.]{0,80}?" + _EXP_CONTEXT,
        re.IGNORECASE,
    ),
    # Leading keyword: "minimum / at least / requires / must have / needs
    # / bringing / has / with N years".
    re.compile(
        r"(?:minimum|min\.?|at\s*least|requires?|require|must\s*have|"
        r"must\s*possess|needs?|need|bring(?:ing)?|having|has|with)\s*"
        r"(?:of\s*)?(\d{1,2})" + _RANGE_SUFFIX + r"\s*(?:years?|yrs?)",
        re.IGNORECASE,
    ),
    # Standalone "N+ years" anywhere — the + is strong enough on its own.
    re.compile(r"\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b", re.IGNORECASE),
    # Trailing keyword: "N years minimum / required".
    re.compile(
        r"(\d{1,2})\s*(?:years?|yrs?)\s*(?:of\s*)?"
        r"(?:minimum|required|experience\s+minimum|industry\s+experience)",
        re.IGNORECASE,
    ),
    # Word form near experience context.
    re.compile(
        r"\b(" + "|".join(_WORD_NUM.keys()) + r")\b\s*"
        r"(?:\+|or\s*more|plus)?\s*(?:years?|yrs?)\b"
        r"[^.]{0,80}?" + _EXP_CONTEXT,
        re.IGNORECASE,
    ),
]


def _required_years(text: str) -> int:
    """Return the highest required years-of-experience mentioned, or 0."""
    if not text:
        return 0
    high = 0
    for pat in _YOE_PATTERNS:
        for m in pat.finditer(text):
            tok = m.group(1).lower()
            n = _WORD_NUM.get(tok)
            if n is None:
                try:
                    n = int(tok)
                except ValueError:
                    continue
            if n > high:
                high = n
    return high


# ──────────────────────────── Salary parsing ───────────────────────────
# Goal: extract the dollar floor (and ceiling, when present) from common
# US salary phrasings so the dashboard can sort/filter by pay. Examples:
#   "$95,000 - $130,000", "$95k-$130k", "$95K to $130K",
#   "salary range: $90,000.00 - $130,000.00 USD",
#   "compensation: 110-145k", "base salary 100-120k",
#   "up to $150k", "from $90k"
#
# We intentionally ignore postings that mention only an hourly rate
# (e.g. "$45/hr") because those numbers do not compare cleanly against
# annual ranges.
# Capture a number that's either k-shorthand (95k), comma-grouped
# (95,000), decimal (95,000.00), or plain (95000). Returns the dollar
# value as an integer when interpreted as either annual or k-shorthand.
_NUM = r"(\d{2,3})(?:,(\d{3}))?(?:\.\d+)?\s*([kK])?"
# Range pattern parts
_DASH = r"\s*(?:-|–|—|to)\s*"

# 1. Explicit $-prefixed range: "$95k-$130k" or "$95,000 - $130,000".
_SAL_DOLLAR_RANGE = re.compile(rf"\$\s*{_NUM}{_DASH}\$?\s*{_NUM}", re.IGNORECASE)
# 2. Plain k-suffixed range without $: "95-130k" or "110k-145k".
_SAL_K_RANGE = re.compile(
    rf"\b(\d{{2,3}})\s*([kK])?{_DASH}(\d{{2,3}})\s*[kK]\b",
    re.IGNORECASE,
)
# 3. Salary-context anchored numeric range: "salary range: 200000-280000",
#    "compensation: 90,000 - 130,000", "pay: 100,000.00 - 150,000.00".
_SAL_CONTEXT_RANGE = re.compile(
    r"(?:salary(?:\s+range)?|compensation|pay(?:\s+range)?|base\s+pay|annual\s+salary)"
    rf"[:\s]+\$?\s*{_NUM}{_DASH}\$?\s*{_NUM}",
    re.IGNORECASE,
)
# 3b. Long-form integer range in salary context: "compensation 200000 -
#     280000 USD" / "salary 90000 to 130000". 5-6 digit annual numbers
#     without commas or k-shorthand.
_SAL_CONTEXT_LONG = re.compile(
    r"(?:salary(?:\s+range)?|compensation|pay(?:\s+range)?|base\s+pay|annual\s+salary)"
    rf"[:\s]+\$?\s*(\d{{4,6}}){_DASH}\$?\s*(\d{{4,6}})",
    re.IGNORECASE,
)
# 4. "up to $150k" / "up to 150000" — only a ceiling.
_SAL_UP_TO = re.compile(rf"up\s*to\s*\$?\s*{_NUM}", re.IGNORECASE)
# 5. "from $90k" / "starting at $95,000" — only a floor.
_SAL_FROM = re.compile(
    rf"(?:from|starting\s*at|minimum\s*of?)\s*\$?\s*{_NUM}", re.IGNORECASE,
)


def _coerce_num(integer: str, thousands: str | None, k_suffix: str | None) -> int:
    """Resolve a captured _NUM group into a dollar value."""
    n = int(integer)
    if thousands:
        n = n * 1000 + int(thousands)
    elif k_suffix:
        n = n * 1000
    elif n < 1000:
        # Bare 2-3 digit number with no decoration — assume k-shorthand.
        n = n * 1000
    return n


def _sanitize_salary(n: int | None) -> int | None:
    if n is None:
        return None
    return n if 30_000 <= n <= 600_000 else None


def _extract_salary(text: str) -> tuple[int | None, int | None]:
    """Return (annual_min_usd, annual_max_usd) or (None, None).

    Tries pattern families in priority order. Numbers are sanity-checked
    to fall in [30k, 600k] (annual USD) — outside that window is almost
    always a parse error or a non-salary number.
    """
    if not text:
        return None, None

    # Either-side k-suffix unifies as k for both ends (so "$95k - $130"
    # is interpreted as "$95k - $130k"). Same for plain-range.
    for pat in (_SAL_DOLLAR_RANGE, _SAL_K_RANGE, _SAL_CONTEXT_RANGE):
        for m in pat.finditer(text):
            g = m.groups()
            # Dollar/context: 6 groups (a, a_thou, a_k, b, b_thou, b_k).
            # K-range: (a, a_k, b)  + implicit k on b.
            if pat is _SAL_K_RANGE:
                a_int, a_k, b_int = g
                b_k = "k"  # always present in the regex
                a_thou = b_thou = None
                # If only one side has the k explicitly, propagate it so
                # "110-145k" → both treated as k.
                if not a_k:
                    a_k = "k"
            else:
                a_int, a_thou, a_k, b_int, b_thou, b_k = g
                # Propagate k between sides when only one is annotated.
                if a_k and not b_k:
                    b_k = a_k
                if b_k and not a_k:
                    a_k = b_k
            lo = _sanitize_salary(_coerce_num(a_int, a_thou, a_k))
            hi = _sanitize_salary(_coerce_num(b_int, b_thou, b_k))
            if lo and hi and lo <= hi:
                return lo, hi

    # Long-form integer range in salary context.
    for m in _SAL_CONTEXT_LONG.finditer(text):
        lo = _sanitize_salary(int(m.group(1)))
        hi = _sanitize_salary(int(m.group(2)))
        if lo and hi and lo <= hi:
            return lo, hi

    m = _SAL_UP_TO.search(text)
    if m:
        n = _sanitize_salary(_coerce_num(*m.groups()))
        if n:
            return None, n

    m = _SAL_FROM.search(text)
    if m:
        n = _sanitize_salary(_coerce_num(*m.groups()))
        if n:
            return n, None

    return None, None


# ─────────────────────── Tech-stack auto-tagging ──────────────────────
# Detect named data tools / clouds / languages in title + description so
# the dashboard can render them as quick-glance chips. Matches are
# word-boundary, case-insensitive.
_TECH_TAGS: dict[str, list[str]] = {
    "snowflake":   ["snowflake"],
    "databricks":  ["databricks"],
    "spark":       ["spark", "pyspark"],
    "airflow":     ["airflow"],
    "dbt":         ["dbt"],
    "kafka":       ["kafka"],
    "hadoop":      ["hadoop", "hdfs", "hive"],
    "redshift":    ["redshift"],
    "bigquery":    ["bigquery"],
    "tableau":     ["tableau"],
    "power bi":    ["power bi", "powerbi"],
    "informatica": ["informatica"],
    "python":      ["python"],
    "sql":         ["sql"],
    "aws":         ["aws", "amazon web services"],
    "azure":       ["azure"],
    "gcp":         ["gcp", "google cloud"],
    "kubernetes":  ["kubernetes", "k8s"],
}
_TECH_TAG_RES = {
    label: re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(t) for t in toks) + r")(?![a-z])", re.IGNORECASE)
    for label, toks in _TECH_TAGS.items()
}


def _detect_tech_tags(text: str) -> list[str]:
    """Return the set of tech-stack labels found in the text."""
    if not text:
        return []
    return [label for label, pat in _TECH_TAG_RES.items() if pat.search(text)]


def _has_token(haystack: str, token: str) -> bool:
    """Word-boundary match for short tokens (≤3 chars, plus alpha ≤4) to
    avoid noise like 'bi' inside 'mobile', 'or' inside 'corporate', or
    'etl' inside unrelated substrings. Longer tokens fall back to
    substring match — phrases like 'United States' or 'engineer' don't
    have collisions worth worrying about.
    """
    t = token.strip().lower()
    if not t:
        return False
    if len(t) <= 3 or (t.isalpha() and len(t) <= 4):
        return re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", haystack) is not None
    return t in haystack


def _contains_all(haystack: str, tokens: Iterable[str]) -> bool:
    """Every token must appear in haystack, with word-boundary handling
    for short tokens via _has_token."""
    return all(_has_token(haystack, tok) for tok in tokens)


def matches_keywords(job: Job, groups: dict, scope: str = "blob") -> list[str]:
    """Return the list of matching keyword-group names for this job.

    scope:
        "blob"  — match against title + description (legacy default).
        "title" — match against title only. Much stricter; intended for
                  the data-only profile where single-token keywords
                  ("sql", "snowflake", etc.) appear in the description
                  of many non-data roles and would otherwise leak.
    """
    if scope == "title":
        haystack = (job.title or "").lower()
    else:
        haystack = f"{job.title}\n{job.description}".lower()
    hits: list[str] = []
    for group_name, token_lists in groups.items():
        for tokens in token_lists:
            if _contains_all(haystack, [t.lower() for t in tokens]):
                hits.append(group_name)
                break
    return hits


def location_ok(job: Job, locs: dict) -> tuple[bool, bool]:
    """Return (allowed, preferred).

    Order matters here:
      1. If we find a positive US signal (state, US city/preferred, "USA",
         "United States", "Remote, US", etc.) the row is allowed — even
         if a foreign-country token also collides ("Vienna VA", "Paris
         TX", "New Mexico", "Naples FL", "Indianapolis IN" all match
         both lists; US wins so we keep them).
      2. Otherwise, a foreign-country / region token kills it.
      3. If neither US nor foreign matches and the row is plain Remote,
         remote_must_be_us decides — true (default) drops bare Remote
         since we can't prove it's US.
    """
    low = (job.location or "").lower()

    preferred  = [p.lower() for p in locs.get("preferred", [])]
    states     = [s.lower() for s in locs.get("allowed_states", [])]
    us_signals = [s.lower() for s in locs.get("us_signals", [])]
    is_preferred = any(_has_token(low, p) for p in preferred)
    in_us = (
        is_preferred
        or any(_has_token(low, s) for s in states)
        or any(_has_token(low, s) for s in us_signals)
    )

    is_remote = bool(job.remote) or "remote" in low

    # 1) US-positive — keep, even if a foreign name collides (Vienna VA).
    if in_us:
        if is_remote and not bool(locs.get("allow_remote", True)):
            return False, is_preferred
        return True, is_preferred

    # 2) Not US-positive: foreign mention kills it.
    for c in locs.get("exclude_countries", []) or []:
        if _has_token(low, c):
            return False, False

    # 3) Bare Remote with no country evidence either way.
    if is_remote and bool(locs.get("allow_remote", True)):
        if bool(locs.get("remote_must_be_us", True)):
            return False, False
        return True, False

    # 4) No US signal, no foreign signal, not remote — drop.
    return False, False


_SENIOR_TITLE_RES = [
    # Plain seniority words. Word-boundary, so "Vpn" / "Leader's" /
    # "Director's" etc. don't false-positive, AND "Lead", "Lead,"
    # "Lead." all match regardless of trailing punctuation.
    re.compile(
        r"\b(?:senior|sr\.?|staff|principal|lead|leader|architect|director"
        r"|vp|vice\s+president|svp|evp|head\s+of|chief|cto|cio|ceo|coo|cfo"
        r"|distinguished|fellow|expert)\b",
        re.IGNORECASE,
    ),
    # Numbered seniority following a job-noun: "Engineer 3", "Engineer
    # IV", "Manager 4", "Scientist III", with optional - or / between
    # the noun and the numeral.
    re.compile(
        r"\b(?:engineer|developer|programmer|scientist|analyst|architect"
        r"|manager|consultant|specialist|administrator|designer)\s*[-_/]?\s*"
        r"(?:iii|iv|vi|vii|viii|ix|x|3|4|5|6|7|8|9|10)\b",
        re.IGNORECASE,
    ),
    # Standalone Roman numerals III/IV/VI/VII at any token boundary —
    # picks up typos like "Solutions Integration Enginer III" where the
    # role-noun anchor doesn't match.
    re.compile(r"\b(?:iii|iv|vi|vii)\b", re.IGNORECASE),
    # Levels / grades: "Level 3", "L3", "Grade 4", "Tier 5".
    re.compile(r"\b(?:l|lvl|level|grade|tier|band)\s*-?\s*[3-9]\b", re.IGNORECASE),
]


def excluded(job: Job, rules: dict) -> bool:
    blob = f"{job.company} {job.title} {job.description}".lower()
    for term in rules.get("companies", []):
        if term.lower() in (job.company or "").lower():
            return True
    for term in rules.get("companies_early_stage", []) or []:
        if term.lower() in (job.company or "").lower() or term.lower() in blob:
            return True
    title_low = (job.title or "").lower()
    # Configured substring titles (admin-tunable safety net).
    for term in rules.get("titles", []):
        if term.lower() in title_low:
            return True
    # Regex-based seniority signals — catches "Vice President", "Lead"
    # at end-of-title / before a comma, and numbered grades like
    # "Engineer 3" / "Engineer IV" / "Manager 4" that the substring
    # list can't express cleanly.
    for pat in _SENIOR_TITLE_RES:
        if pat.search(title_low):
            return True
    # Work-authorization gate — citizenship, clearance, no-sponsorship.
    # Checked against company + title + description so phrases like the
    # user-reported "US CITIZEN OR GREEN CARD only" in the title and
    # "unable to sponsor" buried in the description both get caught.
    for term in rules.get("work_auth", []) or []:
        if term.lower() in blob:
            return True
    # Employment-type gate — drop part-time, intern, co-op, apprentice,
    # seasonal. Full-time and contract roles are kept (they're not on
    # the exclusion list).
    for term in rules.get("employment", []) or []:
        if term.lower() in blob:
            return True
    return False


def fresh(job: Job, max_age_days: int, strict: bool = False) -> bool:
    if job.posted_at is None:
        # Unknown date — many ATS feeds don't expose one. Under strict
        # mode we drop these so only provably-recent jobs make the cut.
        return not strict
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return job.posted_at >= cutoff


def score(job: Job, matched_groups: list[str], is_preferred_loc: bool) -> int:
    """Data-only scoring. Boosts data-engineering signals in the title,
    preferred DFW locations, junior hints, and freshness.
    """
    s = 0
    if is_preferred_loc:
        s += 50
    if job.remote or "remote" in (job.location or "").lower():
        s += 10
    if "data" in matched_groups:
        s += 30
    title = (job.title or "").lower()
    blob = f"{title}\n{job.description}".lower()
    # Title-level boosts: prefer roles whose title actually says
    # "data engineer" / "data analyst" / etc. over jobs that only mention
    # data tools deep in the description.
    for tok in ("data engineer", "data analyst", "analytics engineer",
                "data scientist", "data platform", "data warehouse",
                "bi developer", "etl developer"):
        if tok in title:
            s += 15
            break
    # Bonus for data-engineering tooling in the title or description.
    for tok in ("snowflake", "databricks", "spark", "airflow", "dbt",
                "redshift", "bigquery", "kafka", "informatica"):
        if tok in blob:
            s += 5
            break
    # Junior / entry-level boost. Used to live in a "junior" keyword
    # group; moved here so junior-only matches can't gate-pass non-data
    # roles, while junior-data roles still float to the top.
    for tok in (" i ", " ii ", "associate", "entry", "new grad", "graduate", "junior"):
        if tok in blob:
            s += 25
            break
    # Graduated freshness decay over the 7-day window. Truly fresh
    # postings float to the top; week-old ones get a penalty so the
    # daily feed prefers the latest.
    if job.posted_at is not None:
        age_h = (datetime.now(timezone.utc) - job.posted_at).total_seconds() / 3600
        if age_h < 24:
            s += 30
        elif age_h < 48:
            s += 20
        elif age_h < 72:
            s += 10
        elif age_h < 120:
            s += 0
        else:  # 120-168h (5-7 days)
            s -= 10
    # Salary boost — postings that publish a strong floor get a small
    # nudge above otherwise-equivalent silent postings.
    sal_min = getattr(job, "_salary_min", None)
    if sal_min:
        if sal_min >= 150_000:
            s += 15
        elif sal_min >= 120_000:
            s += 10
        elif sal_min >= 90_000:
            s += 5
    return s


def apply_all(
    jobs: list[Job],
    cfg: dict,
    *,
    require_location: bool = True,
) -> list[dict]:
    """Filter, score, and dedup. Returns list of dicts ready for serialization."""
    kw = cfg.get("keywords", {})
    locs = cfg.get("locations", {})
    exc = cfg.get("exclude", {})
    max_age = int(cfg.get("max_age_days", 7))
    strict_fresh = bool(cfg.get("strict_freshness", False))
    cand_yoe = int(cfg.get("candidate_experience_years", 2))
    max_yoe = int(cfg.get("max_experience_years", cand_yoe + 2))
    # Strict experience mode: drop any posting whose description we can't
    # actually scan (LinkedIn/Workday etc. return empty descriptions on
    # their public list endpoints). Combined with an empty description,
    # the YoE regex has no text to match and a "5+ years" requirement can
    # slip through silently.
    strict_exp = bool(cfg.get("strict_experience_filter", False))
    min_desc_chars = int(cfg.get("min_description_chars", 80))
    # Keyword scope: "title" requires the role's TITLE to mention a data
    # keyword. The default "blob" also accepts description matches but
    # leaks heavily on single-token keywords (sql/snowflake/tableau show
    # up in non-data job descriptions).
    kw_scope = str(cfg.get("keyword_match_scope", "blob")).lower()

    seen: dict[str, dict] = {}
    kept = 0
    dropped_loc = 0
    dropped_kw = 0
    dropped_exc = 0
    dropped_old = 0
    dropped_yoe = 0
    dropped_nodesc = 0

    for j in jobs:
        if excluded(j, exc):
            dropped_exc += 1
            continue
        if not fresh(j, max_age, strict=strict_fresh):
            dropped_old += 1
            continue
        hits = matches_keywords(j, kw, scope=kw_scope)
        if not hits:
            dropped_kw += 1
            continue
        # Under strict mode, we must actually be able to read the posting's
        # full text before trusting it. Short/empty descriptions come from
        # list-only endpoints (LinkedIn, Workday, Workable, SmartRecruiters)
        # where a "5+ years" requirement hides until the user clicks Apply.
        desc_len = len(j.description or "")
        if strict_exp and desc_len < min_desc_chars:
            dropped_nodesc += 1
            continue
        req_yoe = _required_years(f"{j.title}\n{j.description}")
        if req_yoe > max_yoe:
            dropped_yoe += 1
            continue
        allowed, preferred = location_ok(j, locs)
        if require_location and not allowed:
            dropped_loc += 1
            continue
        # Even when the strict location filter is dropped (widen pass),
        # we still want to bin jobs that are explicitly located in a
        # foreign country — the user is on F-1/OPT and US-only.
        if not require_location and not allowed:
            low = (j.location or "").lower()
            if any(_has_token(low, c) for c in (locs.get("exclude_countries") or [])):
                dropped_loc += 1
                continue
        # Salary + tech tags. Both scan title + description.
        sal_blob = f"{j.title}\n{j.description}"
        sal_min, sal_max = _extract_salary(sal_blob)
        # Stash on the job so score() can read it for the salary boost.
        j._salary_min = sal_min  # type: ignore[attr-defined]
        tech_tags = _detect_tech_tags(sal_blob)

        row = j.to_dict()
        row["matched_groups"] = hits
        row["preferred_location"] = preferred
        row["required_years"] = req_yoe
        row["salary_min"] = sal_min
        row["salary_max"] = sal_max
        row["tech_tags"] = tech_tags
        row["score"] = score(j, hits, preferred)
        row["_fp"] = j.fingerprint()
        row["directness"] = j.directness()
        fp = j.fingerprint()
        prev = seen.get(fp)
        if prev is None:
            seen[fp] = row
            kept += 1
        else:
            # Same job seen on a prior source — pick whichever has the
            # most-direct apply path (Greenhouse/Lever/Workday/etc. beat
            # LinkedIn/Indeed redirects). Score breaks ties.
            cur_d = prev.get("directness", 50)
            new_d = row["directness"]
            replace = (
                new_d > cur_d
                or (new_d == cur_d and row["score"] > prev.get("score", 0))
            )
            # Track every source/url we've seen for this job so the
            # dashboard can show fallback links if the primary 404s.
            alts = prev.get("alt_sources") or []
            existing_urls = {prev.get("url")} | {a.get("url") for a in alts}
            payload = {"source": row.get("source"), "url": row.get("url"),
                       "directness": new_d}
            if replace:
                # Demote the previous entry into alt_sources.
                demoted = {"source": prev.get("source"), "url": prev.get("url"),
                           "directness": cur_d}
                merged_alts = [a for a in alts if a.get("url") not in (row.get("url"),)]
                merged_alts.append(demoted)
                row["alt_sources"] = merged_alts
                seen[fp] = row
            else:
                if payload["url"] and payload["url"] not in existing_urls:
                    alts.append(payload)
                    prev["alt_sources"] = alts

    log.info(
        "filter: kept=%d unique=%d dropped(exc=%d,kw=%d,loc=%d,old=%d,yoe=%d,nodesc=%d)",
        kept, len(seen), dropped_exc, dropped_kw, dropped_loc, dropped_old,
        dropped_yoe, dropped_nodesc,
    )
    out = list(seen.values())
    out.sort(key=lambda r: r["score"], reverse=True)
    return out
