"""Tests for the atomic file writer + SeenStore robustness."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scraper.dedup import SeenStore
from scraper.io_utils import atomic_write_text


class AtomicWriteTests(unittest.TestCase):
    def test_writes_content(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a.txt"
            atomic_write_text(path, "hello world")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello world")

    def test_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a.txt"
            path.write_text("old")
            atomic_write_text(path, "new")
            self.assertEqual(path.read_text(encoding="utf-8"), "new")

    def test_creates_parent_dir(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "deep" / "nested" / "file.json"
            atomic_write_text(path, "{}")
            self.assertTrue(path.exists())

    def test_no_tmp_files_left_on_success(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            atomic_write_text(d / "a.json", '{"ok": true}')
            tmp_left = list(d.glob(".*.tmp"))
            self.assertEqual(tmp_left, [])


class SeenStoreTests(unittest.TestCase):
    def test_load_save_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "seen.json"
            store = SeenStore(path)
            store.add("https://example.com/x", "fp123", "2026-05-08")
            store.save()

            other = SeenStore(path)
            self.assertTrue(other.has("https://example.com/x", ""))
            self.assertTrue(other.has("", "fp123"))

    def test_malformed_json_starts_fresh(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "seen.json"
            path.write_text("{not valid json")
            store = SeenStore(path)
            self.assertEqual(store.urls, {})
            self.assertEqual(store.fingerprints, {})

    def test_non_dict_root_starts_fresh(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "seen.json"
            path.write_text(json.dumps([1, 2, 3]))
            store = SeenStore(path)
            self.assertEqual(store.urls, {})
            self.assertEqual(store.fingerprints, {})

    def test_partial_dict_tolerated(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "seen.json"
            path.write_text(json.dumps({"urls": "not a dict"}))
            store = SeenStore(path)
            self.assertEqual(store.urls, {})
            self.assertEqual(store.fingerprints, {})


if __name__ == "__main__":
    unittest.main()
