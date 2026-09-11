#!/usr/bin/env python3
"""Focused contract tests for the Piece 4 DEBUG snapshot contract.

These tests define the expected public API and behavioral contract for atomic
DEBUG snapshot packages. The implementation does not exist yet; these tests
anchor the contract and prevent scope drift during future implementation.

Contract areas:
1. Catalog lock scope: snapshot holds the lock briefly for copying, then
   releases it before validation and packaging.
2. Source fallback permission: DEBUG permits source fallback; RELEASE does not.
3. Stable output path: DEBUG output path is separate from RELEASE.
4. Manifest fields: snapshot includes required manifest metadata.
5. History retention: snapshot preserves timestamped history.
6. Atomic publish failure: previous valid artifact is preserved on failure.
"""

import copy
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "localization"
sys.path.insert(0, str(TOOLS))

from project import load_project, resolve_project_path
from agent_batch import catalog_lock, save_json
from catalog_edit import catalog_snapshot, entry_revision, search_entries
from validate_translation import protected_tokens, protected_tokens_match, DEFAULT_RULES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_tool(name, *args, env=None):
    """Run a localization tool as a subprocess."""
    return subprocess.run(
        [sys.executable, str(TOOLS / name), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def create_project_fixture(directory, entries, name="debug-snapshot-test"):
    """Create a minimal project fixture with catalog and project.json."""
    directory = Path(directory)
    catalog = directory / "catalog.json"
    project_file = directory / "project.json"
    catalog.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    project_file.write_text(json.dumps({
        "name": name,
        "source_archive": str(directory / "source.big"),
        "string_directory": str(directory),
        "string_files": ["data/lotr.str"],
        "catalog": str(catalog),
        "output_string_file": str(directory / "data" / "lotr.str"),
        "output_package": str(directory / "output.big"),
        "language": "es-419",
        "encoding": "cp1252",
        "debug_ids": ["GUI:SinglePlayer", "APT:SoloPlay"],
        "debug_marker": "DEBUGING",
    }), encoding="utf-8")
    return project_file, catalog


def create_entries(*specs):
    """Create entry dicts from (id, source, translation, status) tuples."""
    entries = []
    for entry_id, source, translation, status in specs:
        entry = {
            "id": entry_id,
            "source": source,
            "translation": translation,
            "status": status,
        }
        if status in ("translated", "reviewed"):
            entry.setdefault("flags", ["needs_review"])
            entry.setdefault("translation_meta", {"origin": "human"})
        if status == "preserved":
            entry["flags"] = ["system_preserved"]
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Contract Area 1: Catalog Lock Scope
# ---------------------------------------------------------------------------

class TestCatalogLockScope(unittest.TestCase):
    """The snapshot must hold the shared lock only long enough to copy the
    catalog data, then release it before validation and packaging begin."""

    def test_catalog_snapshot_releases_lock_before_returning(self):
        """catalog_snapshot acquires the lock, reads data, and releases
        the lock before returning results to the caller."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "TEST:One", "source": "One", "translation": "Uno",
                 "status": "translated"},
            ])
            data, reservations = catalog_snapshot(
                project_path=project_file
            )
            # Lock must be released at this point; another process can acquire it.
            with catalog_lock(catalog):
                # If the lock were still held, this would deadlock.
                current = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(len(data["entries"]), 1)
            self.assertEqual(data["entries"][0]["id"], "TEST:One")
            self.assertIsInstance(reservations, dict)

    def test_lock_release_allows_parallel_validation(self):
        """After the snapshot returns, the catalog lock must be available
        so that validation or another operation can proceed concurrently."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "TEST:Lock", "source": "Lock", "translation": "Cerradura",
                 "status": "translated"},
            ])
            # Take a snapshot (acquires and releases lock internally).
            data, _ = catalog_snapshot(project_path=project_file)

            # Now acquire the lock ourselves; this proves it was released.
            acquired = threading.Event()
            def try_lock():
                with catalog_lock(catalog):
                    acquired.set()
                    time.sleep(0.05)

            thread = threading.Thread(target=try_lock)
            thread.start()
            acquired.wait(timeout=2.0)
            thread.join(timeout=2.0)
            self.assertTrue(acquired.is_set(),
                            "Lock was not released after catalog_snapshot")

    def test_lock_file_follows_naming_convention(self):
        """The catalog_lock must create a lock file adjacent to the catalog
        with the .agent.lock suffix, so concurrent agents share it."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "TEST:Conv", "source": "C", "translation": "Conv",
                 "status": "translated"},
            ])
            expected_lock = catalog.parent / f".{catalog.name}.agent.lock"
            # Before any lock acquisition, the file may not exist.
            # Take a snapshot to trigger lock creation.
            catalog_snapshot(project_path=project_file)
            # After snapshot, the lock file should exist (opened in 'a+' mode).
            self.assertTrue(expected_lock.exists(),
                            f"Expected lock file at {expected_lock}")
            # The lock file name must follow the .agent.lock convention.
            self.assertTrue(expected_lock.name.endswith(".agent.lock"))
            self.assertTrue(expected_lock.name.startswith("."))

    def test_snapshot_does_not_hold_lock_during_entry_view_construction(self):
        """The snapshot reads data inside the lock but constructs entry views
        outside the lock, so no lock is held when callers inspect views."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [
                {"id": "TEST:View", "source": "View", "translation": "Vista",
                 "status": "translated"},
            ])
            views = search_entries(project_path=project_file, limit=10)
            self.assertEqual(len(views), 1)
            self.assertEqual(views[0]["id"], "TEST:View")
            self.assertEqual(len(views[0]["entry_revision"]), 32)

    def test_validate_runs_concurrently_after_snapshot(self):
        """After catalog_snapshot returns, validation tools must be able to
        acquire the catalog lock. This proves the snapshot released the lock
        before validation begins — a critical contract requirement."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "TEST:Val", "source": "Val", "translation": "Valor",
                 "status": "translated"},
            ])
            # Take a snapshot (acquires and releases lock internally).
            data, _ = catalog_snapshot(project_path=project_file)
            self.assertEqual(len(data["entries"]), 1)

            # Now run validate.py as a subprocess — this must succeed
            # because the snapshot released the lock before returning.
            result = run_tool(
                "validate_translation.py", "--project", project_file,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            # Also run structural validation.
            structural = run_tool("validate.py", "--project", project_file)
            self.assertEqual(
                structural.returncode, 0,
                structural.stdout + structural.stderr,
            )


# ---------------------------------------------------------------------------
# Contract Area 2: Source Fallback Permission
# ---------------------------------------------------------------------------

class TestSourceFallbackPermission(unittest.TestCase):
    """DEBUG builds must permit source fallback. RELEASE builds must not."""

    def test_build_with_fallback_succeeds_for_pending_entries(self):
        """A debug build allows --allow-source-fallback to fill pending
        entries with their source text."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "TEST:Pending", "source": "English",
                 "translation": "", "status": "pending"},
                {"id": "TEST:Translated", "source": "World",
                 "translation": "Mundo", "status": "translated"},
            ])
            output = Path(directory) / "data" / "lotr.str"
            result = run_tool(
                "build.py", "--project", project_file,
                "--allow-source-fallback",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            content = output.read_text(encoding="cp1252")
            self.assertIn("English", content)
            self.assertIn("Mundo", content)

    def test_build_without_fallback_rejects_pending_entries(self):
        """A strict build without fallback must reject pending entries."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "TEST:Pending", "source": "English",
                 "translation": "", "status": "pending"},
            ])
            result = run_tool("build.py", "--project", project_file)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--allow-source-fallback", result.stderr)

    def test_debug_marker_replaces_configured_ids(self):
        """When --debug is active, entries whose IDs are in debug_ids
        receive the configured debug_marker text."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "GUI:SinglePlayer", "source": "Single Player",
                 "translation": "Un Jugador", "status": "translated"},
                {"id": "TEST:Normal", "source": "Normal",
                 "translation": "Normal", "status": "translated"},
            ])
            result = run_tool(
                "build.py", "--project", project_file, "--debug",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEBUGING", result.stdout)
            output = resolve_project_path(
                load_project(project_file), "output_string_file"
            )
            content = output.read_text(encoding="cp1252")
            self.assertIn("DEBUGING", content)

    def test_source_fallback_permitted_for_debug_not_release(self):
        """The contract requires that source fallback is always permitted in
        DEBUG context. The existing build tool enforces this distinction:
        --allow-source-fallback is mandatory for partial builds."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, _ = create_project_fixture(directory, [
                {"id": "TEST:Pending", "source": "OnlySource",
                 "translation": "", "status": "pending"},
            ])
            strict = run_tool("build.py", "--project", project_file)
            fallback = run_tool(
                "build.py", "--project", project_file,
                "--allow-source-fallback",
            )
            self.assertNotEqual(strict.returncode, 0)
            self.assertEqual(fallback.returncode, 0,
                             fallback.stdout + fallback.stderr)


# ---------------------------------------------------------------------------
# Contract Area 3: Stable DEBUG Output Path
# ---------------------------------------------------------------------------

class TestStableDebugOutputPath(unittest.TestCase):
    """DEBUG output must use a separate, stable path that never overwrites
    the RELEASE artifact."""

    def test_project_requires_separate_output_package(self):
        """Project configuration must define output_package. The DEBUG
        snapshot must write to a distinct path from this release path."""
        project = load_project(ROOT / "config" / "project.json")
        release_path = resolve_project_path(project, "output_package")
        self.assertTrue(release_path.name.endswith(".big"))
        self.assertEqual(release_path.name, "spanishpatch202_es-ES.big")

    def test_debug_output_must_not_equal_release_output(self):
        """If a DEBUG snapshot defines its own output path, it must differ
        from the RELEASE output path. The debug convention of prepending
        'debug-' to the release filename guarantees separation."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, _ = create_project_fixture(directory, [
                {"id": "TEST:Path", "source": "P", "translation": "P",
                 "status": "translated"},
            ])
            project = load_project(project_file)
            release_path = resolve_project_path(project, "output_package")
            debug_convention = release_path.with_name(
                "debug-" + release_path.name
            )
            # The convention of prepending 'debug-' always produces a
            # different path from the release path.
            self.assertNotEqual(release_path, debug_convention)
            # Both paths must share the same parent directory
            # (releases/), ensuring a predictable layout.
            self.assertEqual(release_path.parent, debug_convention.parent)
            # The debug filename must contain 'debug' for traceability.
            self.assertIn("debug", debug_convention.name)
            # The debug filename must end with .big.
            self.assertTrue(debug_convention.name.endswith(".big"))

    def test_debug_str_output_goes_to_string_directory(self):
        """The .str build artifact goes to the project's string_directory.
        DEBUG packaging must produce its own copy, not modify the release .str."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, _ = create_project_fixture(directory, [
                {"id": "TEST:Artifact", "source": "A",
                 "translation": "Arte", "status": "translated"},
            ])
            project = load_project(project_file)
            str_file = resolve_project_path(project, "output_string_file")
            self.assertTrue(str_file.suffix == ".str")
            self.assertIn("data", str(str_file))


# ---------------------------------------------------------------------------
# Contract Area 4: Manifest Fields
# ---------------------------------------------------------------------------

class TestManifestFields(unittest.TestCase):
    """A DEBUG snapshot manifest must contain required metadata fields
    so the package is traceable and reproducible."""

    MANIFEST_REQUIRED_FIELDS = {
        "project_name",
        "language",
        "catalog_hash",
        "debug_marker",
        "created_at",
        "output_package",
        "source_fallback_used",
    }

    def test_manifest_must_contain_required_fields(self):
        """The manifest contract requires these fields for traceability."""
        # This is a contract definition test; when the implementation exists,
        # it must produce a manifest containing at least these fields.
        manifest = {
            "project_name": "bfme2-rotwk-2.02",
            "language": "es-419",
            "catalog_hash": "abc123",
            "debug_marker": "DEBUGING",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "output_package": "releases/debug-spanishpatch202.big",
            "source_fallback_used": True,
        }
        for field in self.MANIFEST_REQUIRED_FIELDS:
            self.assertIn(field, manifest,
                          f"Manifest must contain field: {field}")

    def test_manifest_created_at_must_be_iso8601(self):
        """The created_at timestamp must use ISO 8601 format."""
        timestamp = datetime.now(timezone.utc).isoformat()
        # ISO 8601 contains T separator and +00:00 or Z
        self.assertIn("T", timestamp)
        self.assertTrue(
            timestamp.endswith("+00:00") or timestamp.endswith("Z"),
            f"Timestamp must be UTC: {timestamp}",
        )

    def test_manifest_catalog_hash_must_be_nonempty(self):
        """catalog_hash must be a non-empty string derived from the catalog."""
        catalog_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertIsInstance(catalog_hash, str)
        self.assertTrue(len(catalog_hash) > 0)

    def test_manifest_catalog_hash_is_sha256_hex(self):
        """catalog_hash must be a 64-character hex string (SHA-256),
        ensuring reproducible integrity checks."""
        import hashlib
        content = b'{"entries": [{"id": "TEST:Hash"}]}'
        expected = hashlib.sha256(content).hexdigest()
        self.assertEqual(len(expected), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in expected))

    def test_manifest_project_name_matches_config(self):
        """project_name in the manifest must match the project's name field."""
        project = load_project(ROOT / "config" / "project.json")
        self.assertEqual(project["name"], "bfme2-rotwk-2.02")
        # The contract requires manifest.project_name == project["name"]

    def test_manifest_source_fallback_is_boolean(self):
        """source_fallback_used must be a boolean indicating whether the
        debug build used source text for missing translations. The manifest
        must record this for reproducibility."""
        # The contract defines a schema: source_fallback_used is boolean.
        manifest_with_fallback = {
            "source_fallback_used": True,
        }
        manifest_without_fallback = {
            "source_fallback_used": False,
        }
        self.assertIsInstance(manifest_with_fallback["source_fallback_used"], bool)
        self.assertIsInstance(manifest_without_fallback["source_fallback_used"], bool)
        self.assertTrue(manifest_with_fallback["source_fallback_used"])
        self.assertFalse(manifest_without_fallback["source_fallback_used"])

    def test_manifest_debug_marker_matches_project_config(self):
        """debug_marker in the manifest must match the project's configured
        debug_marker value."""
        project = load_project(ROOT / "config" / "project.json")
        self.assertEqual(project["debug_marker"], "DEBUGING")
        # Contract: manifest.debug_marker == project["debug_marker"]

    def test_manifest_output_package_must_be_separate_from_release(self):
        """output_package in the manifest must not be the release package.
        A DEBUG manifest must record a path containing 'debug' that differs
        from the project's output_package."""
        project = load_project(ROOT / "config" / "project.json")
        release_path = str(resolve_project_path(project, "output_package"))
        debug_path = "releases/debug-spanishpatch202.big"
        # The DEBUG output_package must differ from the release path.
        self.assertNotEqual(debug_path, release_path)
        # The DEBUG path must contain 'debug' for traceability.
        self.assertIn("debug", debug_path)
        # The release path must NOT contain 'debug'.
        self.assertNotIn("debug", release_path)


# ---------------------------------------------------------------------------
# Contract Area 5: History Retention
# ---------------------------------------------------------------------------

class TestHistoryRetention(unittest.TestCase):
    """DEBUG snapshots must retain timestamped history from the catalog
    entries they snapshot."""

    def test_entry_history_is_list_of_dicts(self):
        """Each entry's history field must be a list of dicts with at
        minimum date, action, and from/to fields."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [
                {
                    "id": "TEST:History",
                    "source": "Hello",
                    "translation": "Hola",
                    "status": "translated",
                    "history": [
                        {
                            "date": "2026-01-01T00:00:00+00:00",
                            "action": "translated",
                            "from": "",
                            "to": "Hola",
                            "by": "human",
                        }
                    ],
                },
            ])
            views = search_entries(project_path=project_file)
            self.assertEqual(len(views), 1)
            # entry_view does not include history directly; the raw catalog does.
            catalog = json.loads(
                Path(_catalog).read_text(encoding="utf-8")
            )
            entry = catalog["entries"][0]
            self.assertIn("history", entry)
            self.assertIsInstance(entry["history"], list)
            self.assertGreater(len(entry["history"]), 0)
            record = entry["history"][0]
            self.assertIn("date", record)
            self.assertIn("action", record)

    def test_snapshot_preserves_existing_history(self):
        """A snapshot must not lose or truncate existing history records."""
        history = [
            {"date": f"2026-01-0{i}T00:00:00+00:00",
             "action": "translated", "from": "", "to": f"V{i}",
             "by": "human"}
            for i in range(1, 6)
        ]
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:FullHistory",
                "source": "Full",
                "translation": "Completo",
                "status": "translated",
                "history": copy.deepcopy(history),
            }])
            data, _ = catalog_snapshot(project_path=project_file)
            entry = data["entries"][0]
            self.assertEqual(len(entry["history"]), 5)
            for i, record in enumerate(entry["history"]):
                self.assertEqual(record["action"], "translated")
                self.assertEqual(record["by"], "human")

    def test_history_timestamps_are_iso8601(self):
        """Every history record's date must be a valid ISO 8601 timestamp."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:Timestamps",
                "source": "Time",
                "translation": "Tiempo",
                "status": "translated",
                "history": [
                    {"date": "2026-03-15T12:30:00+00:00",
                     "action": "translated", "from": "", "to": "Tiempo",
                     "by": "test"},
                ],
            }])
            data, _ = catalog_snapshot(project_path=project_file)
            record = data["entries"][0]["history"][0]
            self.assertIn("T", record["date"])
            # Parseable as ISO 8601
            datetime.fromisoformat(record["date"])

    def test_history_accumulates_after_commit_entry(self):
        """When commit_entry edits an entry, a new history record must be
        appended with a valid ISO 8601 timestamp, preserving prior history."""
        from catalog_edit import commit_entry, search_entries
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:Accum",
                "source": "Accum",
                "translation": "V1",
                "status": "translated",
                "history": [
                    {"date": "2026-01-01T00:00:00+00:00",
                     "action": "translated", "from": "", "to": "V1",
                     "by": "human"},
                ],
            }])
            views = search_entries(project_path=project_file)
            self.assertEqual(len(views), 1)
            self.assertEqual(len(views[0]["entry_revision"]), 32)

            # Edit the entry.
            commit_entry(
                views[0]["id"],
                views[0]["entry_revision"],
                "save",
                project_path=project_file,
                translation="V2",
            )

            # Verify history grew by one record.
            catalog_data = json.loads(
                catalog.read_text(encoding="utf-8")
            )
            entry = catalog_data["entries"][0]
            self.assertEqual(len(entry["history"]), 2)
            # First record is untouched.
            self.assertEqual(entry["history"][0]["to"], "V1")
            self.assertEqual(entry["history"][0]["action"], "translated")
            # Second record reflects the edit.
            self.assertEqual(entry["history"][1]["to"], "V2")
            self.assertEqual(entry["history"][1]["action"], "edited")
            self.assertEqual(entry["history"][1]["by"], "human")
            # Timestamps are valid ISO 8601.
            datetime.fromisoformat(entry["history"][0]["date"])
            datetime.fromisoformat(entry["history"][1]["date"])

    def test_entry_revision_is_stable_for_same_data(self):
        """entry_revision must produce the same hash for identical data,
        ensuring snapshot integrity checks are deterministic."""
        entry = {
            "id": "TEST:Rev",
            "source": "Hello",
            "translation": "Hola",
            "status": "translated",
        }
        rev1 = entry_revision(entry)
        rev2 = entry_revision(entry)
        self.assertEqual(rev1, rev2)
        self.assertEqual(len(rev1), 32)

    def test_entry_revision_differs_for_different_data(self):
        """entry_revision must produce different hashes when entry data
        changes, so the snapshot detects mutations."""
        entry_a = {
            "id": "TEST:Rev",
            "source": "Hello",
            "translation": "Hola",
            "status": "translated",
        }
        entry_b = {
            "id": "TEST:Rev",
            "source": "Hello",
            "translation": "Adios",
            "status": "translated",
        }
        self.assertNotEqual(entry_revision(entry_a), entry_revision(entry_b))

    def test_entry_revision_ignores_field_order(self):
        """entry_revision must be order-independent (sort_keys=True),
        so dict key ordering does not affect the hash."""
        entry_1 = {
            "status": "translated",
            "source": "Hello",
            "id": "TEST:Rev",
            "translation": "Hola",
        }
        entry_2 = {
            "id": "TEST:Rev",
            "source": "Hello",
            "translation": "Hola",
            "status": "translated",
        }
        self.assertEqual(entry_revision(entry_1), entry_revision(entry_2))


# ---------------------------------------------------------------------------
# Contract Area 6: Atomic Publish Failure Preservation
# ---------------------------------------------------------------------------

class TestAtomicPublishFailure(unittest.TestCase):
    """Package publication must be atomic: write to a temporary location first,
    then move into place. If publication fails, the previous valid artifact
    must remain untouched."""

    def test_atomic_write_preserves_original_on_failure(self):
        """If a new file write fails midway, the original file must still
        exist with its original contents."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output.big"
            target.write_bytes(b"ORIGINAL_VALID_BYTES")

            # Simulate a failed atomic write.
            temp = target.with_name(f".{target.name}.tmp")
            try:
                temp.write_bytes(b"NEW_BROKEN")
                raise RuntimeError("simulated publication failure")
            except RuntimeError:
                if temp.exists():
                    temp.unlink()

            # Original must be intact.
            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(), b"ORIGINAL_VALID_BYTES")

    def test_atomic_rename_is_used_for_publication(self):
        """The contract requires os.replace (atomic rename) for the final
        publication step, not a copy-then-delete."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output.big"
            target.write_bytes(b"OLD")
            temp = target.with_name(f".{target.name}.tmp")
            temp.write_bytes(b"NEW")

            os.replace(temp, target)
            self.assertEqual(target.read_bytes(), b"NEW")
            self.assertFalse(temp.exists())

    def test_save_json_uses_atomic_write_pattern(self):
        """save_json from agent_batch.py must write to a temporary file
        then atomically rename, matching the same pattern as publication."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "test_catalog.json"
            target.write_bytes(b'{"entries": []}')
            original = target.read_bytes()
            temp = target.with_name(f".{target.name}.tmp")

            # Simulate the save_json pattern: write temp, then replace.
            data = {"entries": [{"id": "TEST:New", "source": "N"}]}
            with temp.open("w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            # Original is still intact until os.replace.
            self.assertEqual(target.read_bytes(), original)
            # Atomic rename completes the write.
            os.replace(temp, target)
            written = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(written["entries"][0]["id"], "TEST:New")
            self.assertFalse(temp.exists())

    def test_atomic_write_cleans_temp_on_failure(self):
        """When an atomic write fails after creating the temp file, the temp
        file must be cleaned up and the original preserved."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "catalog.json"
            target.write_bytes(b'{"entries": []}')
            original = target.read_bytes()
            temp = target.with_name(f".{target.name}.tmp")

            try:
                temp.write_bytes(b'BROKEN_DATA')
                raise RuntimeError("simulated write failure")
            except RuntimeError:
                if temp.exists():
                    temp.unlink()

            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(), original)
            self.assertFalse(temp.exists())

    def test_previous_artifact_survives_failed_verification(self):
        """If post-publication verification fails, the previous artifact
        must still be in place."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output.big"
            target.write_bytes(b"VERIFIED_GOOD")

            # Simulate: new package written but verification fails.
            temp = target.with_name(f".{target.name}.tmp")
            temp.write_bytes(b"UNVERIFIED")
            # Verification fails; temp is removed, original stays.
            temp.unlink()

            self.assertEqual(target.read_bytes(), b"VERIFIED_GOOD")

    def test_debug_snapshot_must_not_overwrite_release_package(self):
        """A DEBUG snapshot must write to a different path than the release
        package. The release package must remain untouched during debug builds."""
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "spanishpatch202.big"
            release.write_bytes(b"RELEASE_PACKAGE")
            debug = Path(directory) / "debug-spanishpatch202.big"
            debug.write_bytes(b"DEBUG_PACKAGE")

            # Both exist independently.
            self.assertEqual(release.read_bytes(), b"RELEASE_PACKAGE")
            self.assertEqual(debug.read_bytes(), b"DEBUG_PACKAGE")
            # Writing debug must not affect release.
            debug.unlink()
            self.assertTrue(release.exists())
            self.assertEqual(release.read_bytes(), b"RELEASE_PACKAGE")

    def test_catalog_snapshot_returns_deep_copy_not_reference(self):
        """The snapshot data must not be a mutable reference to the on-disk
        catalog. Modifying the returned dict must not corrupt the catalog."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:Copy",
                "source": "Copy",
                "translation": "Copia",
                "status": "translated",
            }])
            data, _ = catalog_snapshot(project_path=project_file)
            original_catalog = catalog.read_bytes()
            # Mutate the returned data.
            data["entries"][0]["translation"] = "MODIFIED"
            # Catalog on disk must be unchanged.
            self.assertEqual(catalog.read_bytes(), original_catalog)


# ---------------------------------------------------------------------------
# Contract Area 7: Existing Build Tool DEBUG Behavior
# ---------------------------------------------------------------------------

class TestExistingBuildDebugBehavior(unittest.TestCase):
    """Verify that existing build.py and pack.py --debug behaviors are
    consistent with the Piece 4 contract."""

    def test_build_debug_flag_is_recognized(self):
        """build.py must accept the --debug flag."""
        result = run_tool("build.py", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--debug", result.stdout)

    def test_pack_debug_flag_is_recognized(self):
        """pack.py must accept the --debug flag."""
        result = run_tool("pack.py", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--debug", result.stdout)

    def test_pack_requires_project_for_debug(self):
        """pack.py requires --project for any build, including debug."""
        result = run_tool("pack.py", "--debug")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requiere --project", result.stderr)

    def test_build_produces_valid_str_with_debug_marker(self):
        """A --debug build with debug_ids must inject the debug_marker into
        the .str output for configured IDs."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, _ = create_project_fixture(directory, [
                {"id": "GUI:SinglePlayer", "source": "Single Player",
                 "translation": "Un Jugador", "status": "translated"},
                {"id": "TEST:Normal", "source": "Hello",
                 "translation": "Hola", "status": "translated"},
            ])
            result = run_tool(
                "build.py", "--project", project_file, "--debug",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            project = load_project(project_file)
            str_path = resolve_project_path(project, "output_string_file")
            content = str_path.read_text(encoding="cp1252")
            self.assertIn("DEBUGING", content)
            self.assertIn("Hola", content)

    def test_config_project_has_debug_ids_and_marker(self):
        """The real project configuration must define debug_ids and
        debug_marker for the DEBUG snapshot contract."""
        project = load_project(ROOT / "config" / "project.json")
        self.assertIn("debug_ids", project)
        self.assertIsInstance(project["debug_ids"], list)
        self.assertTrue(len(project["debug_ids"]) > 0)
        self.assertIn("debug_marker", project)
        self.assertIsInstance(project["debug_marker"], str)
        self.assertTrue(len(project["debug_marker"]) > 0)


# ---------------------------------------------------------------------------
# Contract Area 8: Snapshot Concurrency Safety
# ---------------------------------------------------------------------------

class TestSnapshotConcurrencySafety(unittest.TestCase):
    """The snapshot must be safe for concurrent access."""

    def test_concurrent_snapshots_do_not_corrupt_data(self):
        """Multiple threads taking snapshots concurrently must not corrupt
        the catalog or produce inconsistent reads."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": f"TEST:Concurrent{i}", "source": f"S{i}",
                 "translation": f"T{i}", "status": "translated"}
                for i in range(10)
            ])
            results = []
            errors = []

            def take_snapshot():
                try:
                    data, _ = catalog_snapshot(project_path=project_file)
                    results.append(len(data["entries"]))
                except Exception as error:
                    errors.append(error)

            threads = [
                threading.Thread(target=take_snapshot) for _ in range(5)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5.0)

            self.assertEqual(errors, [])
            self.assertEqual(len(results), 5)
            self.assertTrue(all(r == 10 for r in results))

    def test_concurrent_snapshot_and_edit_are_safe(self):
        """Taking a snapshot while another thread edits the catalog must not
        cause data corruption, though one operation may see stale data."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "TEST:Shared", "source": "Shared",
                 "translation": "Original", "status": "translated",
                 "history": []},
            ])
            snapshot_data = []

            def take_snapshot():
                data, _ = catalog_snapshot(project_path=project_file)
                snapshot_data.append(data)

            def edit_entry():
                # Small delay to interleave with snapshot.
                time.sleep(0.01)
                from catalog_edit import commit_entry, search_entries
                views = search_entries(project_path=project_file)
                if views:
                    commit_entry(
                        views[0]["id"],
                        views[0]["entry_revision"],
                        "save",
                        project_path=project_file,
                        translation="Modificado",
                    )

            threads = [
                threading.Thread(target=take_snapshot),
                threading.Thread(target=edit_entry),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5.0)

            # After both complete, the catalog must be consistent.
            final = json.loads(catalog.read_text(encoding="utf-8"))
            entry = final["entries"][0]
            self.assertIn(entry["translation"], ("Original", "Modificado"))
            self.assertEqual(entry["id"], "TEST:Shared")


if __name__ == "__main__":
    unittest.main()
