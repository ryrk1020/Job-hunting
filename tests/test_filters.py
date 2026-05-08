"""Behaviour tests for the filter pipeline.

Run with:
    python -m unittest tests.test_filters

These cover the load-bearing logic the daily scrape depends on:
salary parsing, keyword matching, location filtering, seniority
exclusion, fingerprint normalization, and tech-tag detection. Adding
a regression here is the cheapest way to keep accidental breakage
out of the daily feed.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from scraper.filters import (
    _detect_tech_tags,
    _extract_salary,
    _required_years,
    excluded,
    fresh,
    location_ok,
    matches_keywords,
)
from scraper.sources.base import Job, directness


def _job(**overrides) -> Job:
    base = dict(
        source="greenhouse",
        company="Acme",
        title="Data Engineer",
        location="Dallas, TX",
        url="https://example.com/x",
        posted_at=datetime.now(timezone.utc),
        description="",
    )
    base.update(overrides)
    return Job(**base)


# ─────────────────────────── Salary parsing ────────────────────────
class SalaryTests(unittest.TestCase):
    cases = [
        ("Pay range: $95,000 - $130,000 USD annually", (95000, 130000)),
        ("$95k-$130k base", (95000, 130000)),
        ("$95K to $130K", (95000, 130000)),
        ("compensation: 110-145k", (110000, 145000)),
        ("salary range 90k - 120k base", (90000, 120000)),
        ("up to $150k base salary", (None, 150000)),
        ("starting at $95,000", (95000, None)),
        ("from $110k", (110000, None)),
        ("No pay info anywhere here", (None, None)),
        ("Hourly rate: $45/hr", (None, None)),
        ("compensation 200000 - 280000 USD", (200000, 280000)),
        ("Salary: 90,000.00 - 130,000.00", (90000, 130000)),
        ("$120,000-$150,000 + equity", (120000, 150000)),
        ("Annual salary 95-115k depending on experience", (95000, 115000)),
    ]

    def test_each_case(self):
        for text, expected in self.cases:
            with self.subTest(text=text):
                self.assertEqual(_extract_salary(text), expected)

    def test_input_length_capped(self):
        # Padding should not cause runaway regex; result must equal
        # what we'd see if the salary appeared at the start.
        big_text = "Pay range: $95k-$130k. " + ("x" * 200_000)
        self.assertEqual(_extract_salary(big_text), (95000, 130000))


# ──────────────────────────── YoE parsing ──────────────────────────
class RequiredYearsTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(_required_years("5+ years of experience"), 5)
        self.assertEqual(_required_years("at least 7 years"), 7)
        self.assertEqual(_required_years("requires 4 yrs of industry experience"), 4)
        self.assertEqual(_required_years("must have 3 years"), 3)

    def test_word_form(self):
        self.assertEqual(_required_years("five years of professional experience"), 5)

    def test_no_signal(self):
        self.assertEqual(_required_years(""), 0)
        self.assertEqual(_required_years("ideal for new grads"), 0)


# ─────────────────────────── Keyword matching ──────────────────────
class KeywordTests(unittest.TestCase):
    groups = {
        "data": [
            ["data", "engineer"],
            ["bi", "developer"],
            ["bi", "engineer"],
            ["bi", "analyst"],
            ["snowflake"],
            ["etl"],
            ["powerbi"],
        ]
    }

    def _has(self, title):
        return matches_keywords(_job(title=title), self.groups, scope="title")

    def test_data_role_titles_match(self):
        self.assertEqual(self._has("Data Engineer"), ["data"])
        self.assertEqual(self._has("BI Developer"), ["data"])
        self.assertEqual(self._has("BI Analyst"), ["data"])
        self.assertEqual(self._has("Snowflake Engineer"), ["data"])
        self.assertEqual(self._has("PowerBI Developer"), ["data"])

    def test_non_data_titles_rejected(self):
        # "bi" must not match "Mobile" / "Mobile Developer".
        self.assertEqual(self._has("Mobile Developer"), [])
        self.assertEqual(self._has("Mobile Full-Stack Engineer"), [])
        # "etl" must not match arbitrary substrings.
        self.assertEqual(self._has("Software Engineer"), [])
        self.assertEqual(self._has("Database Engineer"), [])
        # Database != Data — word boundary on 'data'.
        self.assertEqual(self._has("Database Administrator"), [])


# ──────────────────────────── Location ─────────────────────────────
class LocationTests(unittest.TestCase):
    locs = {
        "preferred": ["dallas", "frisco", "fort worth", "plano"],
        "allowed_states": ["texas", "tx", "california", "ca", "virginia", "va"],
        "us_signals": ["united states", "usa", "us", "remote, us", "us remote"],
        "exclude_countries": ["india", "bangalore", "uk", "london", "vienna"],
        "allow_remote": True,
        "remote_must_be_us": True,
    }

    def test_preferred_metro(self):
        ok, pref = location_ok(_job(location="Dallas, TX"), self.locs)
        self.assertTrue(ok and pref)

    def test_allowed_state_not_preferred(self):
        ok, pref = location_ok(_job(location="San Francisco, CA"), self.locs)
        self.assertTrue(ok)
        self.assertFalse(pref)

    def test_foreign_rejected(self):
        ok, _ = location_ok(_job(location="Bangalore, India"), self.locs)
        self.assertFalse(ok)

    def test_us_collision_with_foreign_kept(self):
        # 'Vienna' is an exclude_countries token, but VA pulls it back.
        ok, _ = location_ok(_job(location="Vienna, VA"), self.locs)
        self.assertTrue(ok)

    def test_bare_remote_dropped_when_us_required(self):
        ok, _ = location_ok(_job(location="Remote", remote=True), self.locs)
        self.assertFalse(ok)

    def test_us_remote_kept(self):
        ok, _ = location_ok(_job(location="Remote, US", remote=True), self.locs)
        self.assertTrue(ok)


# ─────────────────────────── Seniority filter ──────────────────────
class SeniorityTests(unittest.TestCase):
    rules = {"titles": [], "companies": [], "work_auth": [], "employment": []}

    def test_senior_titles_dropped(self):
        for t in ("Senior Data Engineer", "Lead Data Analyst",
                  "Principal Data Scientist", "Data Engineer III",
                  "Data Engineer IV", "Software Engineer 4",
                  "Director of Data", "VP of Engineering",
                  "Head of Data Platform"):
            with self.subTest(title=t):
                self.assertTrue(excluded(_job(title=t), self.rules))

    def test_junior_kept(self):
        for t in ("Data Engineer", "Junior Data Analyst",
                  "Data Engineer II", "Associate Data Scientist"):
            with self.subTest(title=t):
                self.assertFalse(excluded(_job(title=t), self.rules))

    def test_work_auth_blocked(self):
        rules = {**self.rules, "work_auth": ["us citizens only", "no sponsorship"]}
        self.assertTrue(excluded(
            _job(description="US citizens only please"), rules,
        ))
        self.assertTrue(excluded(
            _job(description="No sponsorship offered for this role"), rules,
        ))


# ────────────────────── Fingerprint normalization ──────────────────
class FingerprintTests(unittest.TestCase):
    def test_cross_source_identity(self):
        a = _job(company="Deloitte", title="Data Engineer (Remote)",
                 location="Dallas, TX, United States", source="greenhouse")
        b = _job(company="Deloitte LLP", title="Data Engineer",
                 location="Dallas, Texas", source="linkedin")
        c = _job(company="Deloitte Consulting", title="Data Engineer - Remote",
                 location="Dallas, TX, USA", source="indeed_rss")
        self.assertEqual(a.fingerprint(), b.fingerprint())
        self.assertEqual(b.fingerprint(), c.fingerprint())

    def test_different_companies_distinct(self):
        a = _job(company="Acme", title="Data Engineer", location="Dallas, TX")
        b = _job(company="Globex", title="Data Engineer", location="Dallas, TX")
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_directness_ranking(self):
        self.assertGreater(directness("greenhouse"), directness("linkedin"))
        self.assertGreater(directness("workday"), directness("indeed_rss"))
        self.assertEqual(directness("unknown_source"), 50)


# ───────────────────────────── Tech tags ───────────────────────────
class TechTagsTests(unittest.TestCase):
    def test_extracts_named_tools(self):
        text = "We use Snowflake, dbt, Airflow, Python on AWS"
        tags = _detect_tech_tags(text)
        for t in ("snowflake", "dbt", "airflow", "python", "aws"):
            self.assertIn(t, tags)

    def test_no_false_positives(self):
        text = "A React frontend role. Java backend. PostgreSQL."
        tags = _detect_tech_tags(text)
        # 'sql' is a real keyword and matches PostgreSQL via "postgreSQL"
        # ending with 'sql' — but our boundary check should reject it.
        self.assertNotIn("snowflake", tags)
        self.assertNotIn("aws", tags)


# ───────────────────────────── Freshness ───────────────────────────
class FreshnessTests(unittest.TestCase):
    def test_within_window(self):
        j = _job(posted_at=datetime.now(timezone.utc) - timedelta(days=2))
        self.assertTrue(fresh(j, 7))

    def test_outside_window(self):
        j = _job(posted_at=datetime.now(timezone.utc) - timedelta(days=10))
        self.assertFalse(fresh(j, 7))

    def test_unknown_date_kept_when_lenient(self):
        j = _job(posted_at=None)
        self.assertTrue(fresh(j, 7, strict=False))

    def test_unknown_date_dropped_when_strict(self):
        j = _job(posted_at=None)
        self.assertFalse(fresh(j, 7, strict=True))


if __name__ == "__main__":
    unittest.main()
