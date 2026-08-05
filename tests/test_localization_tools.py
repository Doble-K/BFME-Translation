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
from ai_translate import choose_model


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
        self.assertEqual(project["string_header"], "// String file for Lord of the Rings")
        self.assertEqual(project["debug_marker"], "DEBUGING")
        self.assertEqual(
            resolve_project_path(project, "output_package"),
            ROOT / "releases" / "spanishpatch202.big",
        )

    def test_build_uses_generic_project_paths_and_header(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "french.json"
            output = directory / "translations" / "french" / "data" / "strings.str"
            project_file = directory / "project.json"
            catalog.write_text(
                json.dumps({
                    "entries": [{
                        "id": "TEST:Bonjour",
                        "source": "Hello",
                        "translation": "Bonjour",
                        "status": "translated",
                    }]
                }),
                encoding="utf-8",
            )
            project_file.write_text(
                json.dumps({
                    "name": "custom-french-test",
                    "source_archive": str(directory / "source.big"),
                    "string_directory": str(output.parent),
                    "string_files": ["data/strings.str"],
                    "catalog": str(catalog),
                    "output_string_file": str(output),
                    "output_package": str(directory / "french.big"),
                    "language": "fr",
                    "encoding": "cp1252",
                    "string_header": "// French test string file",
                }),
                encoding="utf-8",
            )

            result = run_tool("build.py", "--project", project_file)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                output.read_bytes().decode("cp1252"),
                '// French test string file\r\n\r\n'
                'TEST:Bonjour\r\n"Bonjour"\r\nEND\r\n\r\n',
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

    def test_preserved_entries_are_validated_as_system_text(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({
                "entries": [{
                    "id": "LETTER:G",
                    "source": "%d <COL:RED>",
                    "translation": "%d <COL:RED>",
                    "status": "preserved",
                }]
            }), encoding="utf-8")

            structural = run_tool("validate.py", catalog)
            tokens = run_tool("validate_translation.py", catalog)

            self.assertEqual(structural.returncode, 0, structural.stdout + structural.stderr)
            self.assertEqual(tokens.returncode, 0, tokens.stdout + tokens.stderr)

    def test_extract_handles_crlf_and_rejects_incomplete_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "source.str"
            output = directory / "source.json"
            source.write_bytes(
                b"// header\r\nTEST:One\r\n\"A \\n line\"\r\nEND \r\n"
                b"TEST:Two\r\n\"Name with \"quote\" inside\" // context\r\nEnd\r\n"
                b"TEST:Empty\r\nEND\r\n"
            )
            result = run_tool("extract.py", source, output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            extracted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(extracted["entries"][0]["text"], "A \\n line")
            self.assertEqual(extracted["entries"][1]["text"], 'Name with "quote" inside')
            self.assertEqual(extracted["entries"][2]["text"], "")

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

    def test_build_blocks_unapproved_suggestions(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            output = directory / "output.str"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Suggested",
                "source": "English",
                "translation": "Propuesta",
                "status": "suggested",
            }]}), encoding="utf-8")

            strict = run_tool("build.py", catalog, output)
            self.assertNotEqual(strict.returncode, 0)
            self.assertIn("no aprobadas", strict.stderr)

            partial = run_tool("build.py", catalog, output, "--allow-source-fallback")
            self.assertEqual(partial.returncode, 0, partial.stdout + partial.stderr)
            self.assertIn('"English"', output.read_text(encoding="cp1252"))

    def test_approve_promotes_suggestion_after_token_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Suggested",
                "source": "%d Days",
                "translation": "%d Días",
                "status": "suggested",
                "history": [],
            }]}), encoding="utf-8")

            result = run_tool("review.py", "approve", catalog, "--id", "TEST:Suggested")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(entry["status"], "translated")
            self.assertEqual(entry["history"][0]["action"], "approved")
            self.assertEqual(entry["translation_meta"]["approved_by"], "human")

    def test_review_reject_preserves_suggestion_and_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Rejected",
                "source": "English",
                "translation": "Propuesta",
                "status": "suggested",
                "history": [],
            }]}), encoding="utf-8")

            result = run_tool(
                "review.py",
                "reject",
                catalog,
                "--id",
                "TEST:Rejected",
                "--reason",
                "Needs context",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(entry["status"], "rejected")
            self.assertEqual(entry["translation"], "Propuesta")
            self.assertEqual(entry["translation_meta"]["rejection_reason"], "Needs context")
            self.assertEqual(entry["history"][0]["action"], "rejected")

    def test_review_marks_translation_as_human_reviewed(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Reviewed",
                "source": "%d Days",
                "translation": "%d Días",
                "status": "translated",
                "flags": ["needs_review"],
                "history": [],
            }]}), encoding="utf-8")

            result = run_tool("review.py", "review", catalog, "--id", "TEST:Reviewed")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(entry["status"], "reviewed")
            self.assertNotIn("needs_review", entry["flags"])
            self.assertEqual(entry["history"][0]["action"], "reviewed")

    def test_ai_translate_fixture_dry_run_and_write(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            fixture = directory / "fixture.json"
            glossary = directory / "GLOSSARY.md"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Bulk",
                "source": "%d Days",
                "translation": "",
                "status": "pending",
            }]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "bulk-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            fixture.write_text(json.dumps({
                "translations": {"TEST:Bulk": "%d Días"}
            }), encoding="utf-8")
            glossary.write_text("Glossary", encoding="utf-8")

            dry_run = run_tool(
                "ai_translate.py",
                "--project", project_file,
                "--mode", "translate",
                "--fixture", fixture,
                "--glossary", glossary,
            )
            self.assertEqual(dry_run.returncode, 0, dry_run.stdout + dry_run.stderr)
            self.assertEqual(
                json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]["status"],
                "pending",
            )

            written = run_tool(
                "ai_translate.py",
                "--project", project_file,
                "--mode", "translate",
                "--fixture", fixture,
                "--glossary", glossary,
                "--write",
            )
            self.assertEqual(written.returncode, 0, written.stdout + written.stderr)
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(entry["status"], "translated")
            self.assertIn("needs_review", entry["flags"])
            self.assertEqual(entry["translation_meta"]["origin"], "ai")

    def test_ai_review_fixture_writes_review_context_only(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            fixture = directory / "fixture.json"
            glossary = directory / "GLOSSARY.md"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:ReviewAI",
                "source": "Build the fortress",
                "translation": "Construir la fortaleza",
                "status": "translated",
                "flags": ["needs_review"],
            }]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "review-ai-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            fixture.write_text(json.dumps({
                "reviews": {"TEST:ReviewAI": {
                    "issues": ["Check terminology"],
                    "suggestion": "Construir la fortaleza",
                    "confidence": 0.9,
                }}
            }), encoding="utf-8")
            glossary.write_text("Glossary", encoding="utf-8")

            result = run_tool(
                "ai_translate.py",
                "--project", project_file,
                "--mode", "review",
                "--fixture", fixture,
                "--glossary", glossary,
                "--write",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(entry["translation"], "Construir la fortaleza")
            self.assertEqual(entry["review"]["ai"]["issues"], ["Check terminology"])
            self.assertIn("needs_review", entry["flags"])

    def test_ai_bulk_skips_failed_entry_and_keeps_following_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            fixture = directory / "fixture.json"
            glossary = directory / "GLOSSARY.md"
            catalog.write_text(json.dumps({"entries": [
                {"id": "TEST:Missing", "source": "One", "translation": "", "status": "pending"},
                {"id": "TEST:Good", "source": "Two", "translation": "", "status": "pending"},
            ]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "bulk-skip-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            fixture.write_text(json.dumps({
                "translations": {"TEST:Good": "Dos"}
            }), encoding="utf-8")
            glossary.write_text("Glossary", encoding="utf-8")

            result = run_tool(
                "ai_translate.py",
                "--project", project_file,
                "--mode", "translate",
                "--fixture", fixture,
                "--glossary", glossary,
                "--retries", "2",
                "--write",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entries = json.loads(catalog.read_text(encoding="utf-8"))["entries"]
            self.assertEqual(entries[0]["status"], "pending")
            self.assertEqual(entries[1]["translation"], "Dos")

    def test_ai_auto_routing_uses_large_model_for_complex_entries(self):
        rules = {"format_specifiers": [], "control_characters": [], "sage_tags": [], "regex_patterns": []}
        short = {"id": "TIME:Second", "source": "1 Second"}
        long = {
            "id": "OBJECT:RohanFarmDescription",
            "source": "Reduces the Cost of Cavalry \\n 2 Farms: 10%\\n 3 Farms: 15%\\n 4 Farms: 20%",
        }
        self.assertEqual(
            choose_model(long, "auto", "llama3.2:3b", "qwen2.5:7b", 180, rules),
            "qwen2.5:7b",
        )
        self.assertEqual(
            choose_model(short, "auto", "llama3.2:3b", "qwen2.5:7b", 180, rules),
            "llama3.2:3b",
        )

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
        self.assertIn("--avanced", result.stdout)

    def test_pack_help_exposes_debug_controls(self):
        result = run_tool("pack.py", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--exclude-orphan-ids", result.stdout)
        self.assertIn("--dedupe-ids", result.stdout)

    def test_pack_requires_project_configuration(self):
        result = run_tool("pack.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requiere --project", result.stderr)

    def test_validate_requires_catalog_or_project(self):
        result = run_tool("validate.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("indique catalog o use --project", result.stderr)

        configured = run_tool("validate.py", "--project", ROOT / "config" / "project.json")
        self.assertEqual(configured.returncode, 0, configured.stdout + configured.stderr)

    def test_validate_translation_requires_catalog_or_project(self):
        result = run_tool("validate_translation.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("indique catalog o use --project", result.stderr)

        configured = run_tool(
            "validate_translation.py",
            "--project",
            ROOT / "config" / "project.json",
        )
        self.assertEqual(configured.returncode, 0, configured.stdout + configured.stderr)

    def test_normalize_uses_project_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            catalog.write_text(json.dumps({
                "entries": [{
                    "id": "TEST:Normalize",
                    "source": "  Hello\r\n",
                    "translation": "  Hola\r\n",
                    "status": "translated",
                }]
            }), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "normalize-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "fr",
                "encoding": "cp1252",
            }), encoding="utf-8")

            result = run_tool("normalize.py", "--project", project_file)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(data["entries"][0]["source"], "Hello")
            self.assertEqual(data["entries"][0]["translation"], "Hola")

    def test_preprocess_marks_system_entries_as_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({
                "entries": [{
                    "id": "LETTER:G",
                    "source": "G",
                    "translation": "",
                    "status": "pending",
                }]
            }), encoding="utf-8")

            preview = run_tool("preprocess.py", catalog)
            self.assertNotEqual(preview.returncode, 0)
            self.assertEqual(
                json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]["status"],
                "pending",
            )

            result = run_tool("preprocess.py", catalog, "--write")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(entry["status"], "preserved")
            self.assertIn("system_preserved", entry["flags"])
            self.assertEqual(entry["history"][0]["action"], "auto_preserved")

    def test_normalize_escapes_uses_project_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            catalog.write_text(json.dumps({
                "entries": [{
                    "id": "TEST:Escapes",
                    "source": "Line 1\\nLine 2",
                    "translation": "Línea 1\nLínea 2",
                    "status": "preserved",
                }]
            }), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "escapes-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "fr",
                "encoding": "cp1252",
            }), encoding="utf-8")

            result = run_tool(
                "normalize_escapes.py",
                "--project",
                project_file,
                "--write",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(data["entries"][0]["translation"], r"Línea 1\nLínea 2")

    def test_migrate_uses_project_catalog_and_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            catalog.write_text(json.dumps({
                "entries": [{
                    "id": "TEST:Migrate",
                    "source": "Hello",
                    "translation": "Bonjour",
                    "status": "translated",
                }, {
                    "id": "LETTER:G",
                    "source": "G",
                    "translation": "G",
                    "status": "preserved",
                }]
            }), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "migrate-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "fr",
                "encoding": "cp1252",
            }), encoding="utf-8")

            result = run_tool("migrate_catalog.py", "--project", project_file)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(catalog.read_text(encoding="utf-8"))
            entry = data["entries"][0]
            self.assertEqual(entry["translation_meta"]["origin"], "ai")
            self.assertIn("review", entry)
            self.assertEqual(entry["history"][0]["action"], "translated")
            preserved = data["entries"][1]
            self.assertEqual(preserved["translation_meta"]["origin"], "system")
            self.assertEqual(preserved["history"][0]["action"], "auto_preserved")

    def test_compare_creates_generic_report(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            reference = directory / "reference.json"
            target = directory / "target.json"
            report = directory / "reports" / "comparison.json"
            reference.write_text(json.dumps({
                "source": "reference.str",
                "entries": [
                    {"id": "TEST:Same", "text": "Same"},
                    {"id": "TEST:Missing", "text": "Missing"},
                    {"id": "TEST:Duplicate", "text": "First"},
                    {"id": "TEST:Duplicate", "text": "Last"},
                ],
            }), encoding="utf-8")
            target.write_text(json.dumps({
                "source": "target.str",
                "entries": [
                    {"id": "TEST:Same", "text": "Same"},
                    {"id": "TEST:Duplicate", "text": "Translated"},
                    {"id": "TEST:Empty", "text": ""},
                ],
            }), encoding="utf-8")

            result = run_tool(
                "compare.py",
                reference,
                target,
                "--output",
                report,
                "--reference-name",
                "English",
                "--target-name",
                "French",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["reference"]["name"], "English")
            self.assertEqual(data["target"]["name"], "French")
            self.assertEqual(data["missing_in_target"], ["TEST:Missing"])
            self.assertEqual(data["empty_in_target"], [])
            self.assertEqual(data["reference"]["duplicate_ids"], ["TEST:Duplicate"])

    def test_translate_help_exposes_review_mode(self):
        result = run_tool("translate.py", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--review", result.stdout)
        self.assertIn("--advanced", result.stdout)
        self.assertIn("--project", result.stdout)

    def test_translate_uses_project_language_and_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "french.json"
            project_file = directory / "project.json"
            catalog.write_text(json.dumps({
                "entries": [{
                    "id": "TEST:Bonjour",
                    "source": "Hello",
                    "translation": "",
                    "status": "pending",
                }]
            }), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "french-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "french.big"),
                "language": "fr",
                "encoding": "cp1252",
            }), encoding="utf-8")

            result = run_tool("translate.py", "--project", project_file, "--count", "1")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("fr:", result.stdout)
            self.assertIn("Hello", result.stdout)

    def test_translate_review_clears_needs_review_after_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Review",
                "source": "%d Days",
                "translation": "%d Jornadas",
                "status": "translated",
                "flags": ["needs_review"],
                "history": [],
            }]}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "translate.py"),
                    str(catalog),
                    "--review",
                    "--edit",
                    "--count",
                    "1",
                ],
                cwd=ROOT,
                input="%d Días\n",
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(entry["translation"], "%d Días")
            self.assertNotIn("needs_review", entry["flags"])
            self.assertTrue(entry["review"]["human"]["checked"])

    def test_translate_review_keep_clears_needs_review_without_editing(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:KeepReview",
                "source": "Hello",
                "translation": "Hola",
                "status": "translated",
                "flags": ["needs_review"],
            }]}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "translate.py"),
                    str(catalog),
                    "--review",
                    "--edit",
                    "--count",
                    "1",
                ],
                cwd=ROOT,
                input=":keep\n",
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(entry["translation"], "Hola")
            self.assertNotIn("needs_review", entry["flags"])

    def test_translate_retries_after_token_error(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Percent",
                "source": "%d Days",
                "translation": "",
                "status": "pending",
                "flags": [],
                "history": [],
            }]}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOLS / "translate.py"), catalog, "--count", "1", "--edit"],
                cwd=ROOT,
                input="Dias\n%d dias\n",
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(data["entries"][0]["translation"], "%d dias")

    def test_translate_can_go_back_in_a_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({"entries": [
                {"id": "TEST:One", "source": "One", "translation": "", "status": "pending"},
                {"id": "TEST:Two", "source": "Two", "translation": "", "status": "pending"},
            ]}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOLS / "translate.py"), catalog, "--count", "2", "--edit"],
                cwd=ROOT,
                input="Uno\n:back\nUno corregido\nDos\n",
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(data["entries"][0]["translation"], "Uno corregido")
            self.assertEqual(data["entries"][1]["translation"], "Dos")


if __name__ == "__main__":
    unittest.main()
