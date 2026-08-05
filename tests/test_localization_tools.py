#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "localization"
sys.path.insert(0, str(TOOLS))
from project import load_project, resolve_project_path


def run_tool(name, *args):
    return subprocess.run(
        [sys.executable, str(TOOLS / name), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class LocalizationToolTests(unittest.TestCase):
    def test_rotwk_project_configuration(self):
        project = load_project(ROOT / "config" / "project.json")
        self.assertEqual(project["name"], "bfme2-rotwk-2.02")
        self.assertEqual(project["encoding"], "cp1252")
        self.assertEqual(
            resolve_project_path(project, "output_package"),
            ROOT / "releases" / "spanishpatch202.big",
        )

    def test_translation_tokens_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(
                json.dumps({
                    "entries": [{
                        "id": "TEST:Token",
                        "source": "Damage %d <COL:RED> \\n",
                        "translation": "Daño %d <COL:RED> \\n",
                        "status": "translated",
                    }]
                }),
                encoding="utf-8",
            )
            valid = run_tool("validate_translation.py", catalog)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)

            data = json.loads(catalog.read_text(encoding="utf-8"))
            data["entries"][0]["translation"] = "Daño %s <COL:RED> \\n"
            catalog.write_text(json.dumps(data), encoding="utf-8")
            invalid = run_tool("validate_translation.py", catalog)
            self.assertNotEqual(invalid.returncode, 0)

    def test_extract_handles_crlf_and_rejects_incomplete_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "source.str"
            output = directory / "source.json"
            source.write_bytes(
                b"// header\r\nTEST:One\r\n\"A \\n line\"\r\nEND\r\n"
            )
            result = run_tool("extract.py", source, output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            extracted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(extracted["entries"][0]["text"], "A \\n line")

            source.write_text("TEST:Broken\n\"missing end\"\n", encoding="utf-8")
            broken = run_tool("extract.py", source, output)
            self.assertNotEqual(broken.returncode, 0)

    def test_update_retires_and_restores_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source_removed = directory / "source-removed.json"
            source_restored = directory / "source-restored.json"
            catalog = directory / "catalog.json"
            source_removed.write_text(
                json.dumps({"entries": [{"id": "TEST:One", "text": "One", "line": 1}]}),
                encoding="utf-8",
            )
            source_restored.write_text(
                json.dumps({"entries": [
                    {"id": "TEST:One", "text": "One", "line": 1},
                    {"id": "TEST:Two", "text": "Two", "line": 2},
                ]}),
                encoding="utf-8",
            )
            catalog.write_text(json.dumps({"entries": [
                {"id": "TEST:One", "source": "One", "translation": "Uno", "status": "translated"},
                {"id": "TEST:Two", "source": "Two", "translation": "Dos", "status": "translated"},
            ]}), encoding="utf-8")

            removed = run_tool("update.py", source_removed, catalog)
            self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
            retired_data = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(len(retired_data["retired_entries"]), 1)
            self.assertIn("source_removed", retired_data["retired_entries"][0]["flags"])

            restored = run_tool("update.py", source_restored, catalog)
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            restored_data = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(restored_data.get("retired_entries"), [])
            restored_entry = next(e for e in restored_data["entries"] if e["id"] == "TEST:Two")
            self.assertIn("source_restored", restored_entry["flags"])

    def test_update_applies_last_wins_metadata_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "source.json"
            catalog = directory / "catalog.json"
            source.write_text(json.dumps({"entries": [
                {"id": "TEST:Duplicate", "text": "First", "line": 1},
                {"id": "TEST:Duplicate", "text": "Last", "line": 2},
                {"id": " ", "text": "Orphan", "line": 3},
            ]}), encoding="utf-8")
            catalog.write_text(json.dumps({"entries": [
                {"id": "TEST:Duplicate", "source": "Old", "translation": "Viejo", "status": "translated"},
                {"id": " ", "source": "Orphan", "translation": "Huérfana", "status": "translated"},
            ]}), encoding="utf-8")

            first = run_tool("update.py", source, catalog)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            result = json.loads(catalog.read_text(encoding="utf-8"))
            duplicates = [e for e in result["entries"] if e["id"] == "TEST:Duplicate"]
            self.assertEqual(duplicates[-1]["duplicate_meta"]["selected"], True)
            self.assertEqual(duplicates[0]["duplicate_meta"]["selected"], False)
            self.assertIn("orphan_meta", next(e for e in result["entries"] if e["id"] == " "))

            before = catalog.read_bytes()
            second = run_tool("update.py", source, catalog)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(catalog.read_bytes(), before)

    def test_build_requires_explicit_partial_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            output = directory / "output.str"
            catalog.write_text(json.dumps({"entries": [
                {"id": "TEST:Pending", "source": "English", "translation": "", "status": "pending"},
            ]}), encoding="utf-8")
            strict = run_tool("build.py", catalog, output)
            self.assertNotEqual(strict.returncode, 0)
            partial = run_tool("build.py", catalog, output, "--allow-source-fallback")
            self.assertEqual(partial.returncode, 0, partial.stdout + partial.stderr)
            self.assertIn("English", output.read_text(encoding="cp1252"))

    def test_init_refuses_to_overwrite_existing_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "source.json"
            output = directory / "catalog.json"
            source.write_text(json.dumps({"source": "test", "entries": []}), encoding="utf-8")
            output.write_text("keep", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "gandalf.py"), source, output],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")

    def test_gandalf_noninteractive_mode_creates_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "source.json"
            output = directory / "catalog.json"
            source.write_text(json.dumps({"source": "test", "entries": []}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "gandalf.py"), source, output],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["project"]["slug"], "custom")
            self.assertEqual(data["language"], "Spanish")

    def test_gandalf_help_exposes_wizard_mode(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "gandalf.py"), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--wizard", result.stdout)

    def test_pack_help_exposes_debug_controls(self):
        result = run_tool("pack.py", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--exclude-orphan-ids", result.stdout)
        self.assertIn("--dedupe-ids", result.stdout)


if __name__ == "__main__":
    unittest.main()
