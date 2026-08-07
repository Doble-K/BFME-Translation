#!/usr/bin/env python3
"""Focused tests for the Gandalf translation/debug window helpers.

These tests exercise the UI-agnostic helper functions used by the
independent A/B translation window (source language A vs translation
language B).  No display or tkinter is required; only the pure helpers
extracted for the window are covered.
"""

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gandalf import format_entry_header, translation_pane_labels


def make_record(**overrides):
    """Build a minimal entry_view-style record dict."""
    record = {
        "id": "LETTER:1",
        "source": "Attack",
        "translation": "Atacar",
        "status": "translated",
        "flags": [],
        "notes": "",
        "entry_revision": "rev1",
        "reserved": False,
        "reservations": [],
    }
    record.update(overrides)
    return record


class FormatEntryHeaderTests(unittest.TestCase):
    """Tests for format_entry_header()."""

    def test_plain_record_uses_sin_flags(self):
        result = format_entry_header(make_record())
        self.assertEqual(result, "LETTER:1 | estado=translated | sin flags")

    def test_record_with_flags(self):
        record = make_record(flags=["needs_review"])
        result = format_entry_header(record)
        self.assertIn("LETTER:1", result)
        self.assertIn("estado=translated", result)
        self.assertIn("needs_review", result)

    def test_record_with_multiple_flags(self):
        record = make_record(flags=["needs_review", "missing"])
        result = format_entry_header(record)
        self.assertIn("needs_review, missing", result)

    def test_pending_status_visible(self):
        record = make_record(status="pending", flags=["incomplete"])
        result = format_entry_header(record)
        self.assertIn("estado=pending", result)

    def test_reserved_record_lists_workers(self):
        record = make_record(
            reserved=True,
            reservations=[
                {"worker": "worker-a", "batch_id": "b1", "expires_at": "x"},
                {"worker": "worker-b", "batch_id": "b2", "expires_at": "y"},
            ],
        )
        result = format_entry_header(record)
        self.assertIn("RESERVADA por worker-a, worker-b", result)

    def test_reserved_record_without_workers_is_defensive(self):
        record = make_record(reserved=True, reservations=[])
        result = format_entry_header(record)
        self.assertNotIn("RESERVADA", result)

    def test_reserved_record_unknown_worker(self):
        record = make_record(
            reserved=True,
            reservations=[{"batch_id": "b1", "expires_at": "x"}],
        )
        result = format_entry_header(record)
        self.assertIn("RESERVADA por desconocido", result)

    def test_does_not_mutate_input(self):
        record = make_record(
            reserved=True,
            reservations=[{"worker": "worker-a", "batch_id": "b1"}],
        )
        original_flags = list(record["flags"])
        original_reservations = list(record["reservations"])
        format_entry_header(record)
        self.assertEqual(record["flags"], original_flags)
        self.assertEqual(record["reservations"], original_reservations)
        self.assertEqual(record["status"], "translated")


class TranslationPaneLabelsTests(unittest.TestCase):
    """Tests for translation_pane_labels()."""

    def test_returns_source_and_target_titles(self):
        source, target = translation_pane_labels("English", "Español")
        self.assertEqual(source, "Idioma A - origen (English)")
        self.assertEqual(target, "Idioma B - destino (Español)")

    def test_titles_are_distinct(self):
        source, target = translation_pane_labels("English", "Español")
        self.assertNotEqual(source, target)

    def test_titles_include_language_names(self):
        source, target = translation_pane_labels("English", "Español")
        self.assertIn("English", source)
        self.assertIn("Español", target)

    def test_titles_mark_language_roles(self):
        source, target = translation_pane_labels("English", "Español")
        self.assertIn("origen", source)
        self.assertIn("destino", target)


if __name__ == "__main__":
    unittest.main()
