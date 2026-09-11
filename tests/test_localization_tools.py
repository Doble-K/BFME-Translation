#!/usr/bin/env python3

import os
import json
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "localization"
sys.path.insert(0, str(TOOLS))
from project import (
    PROJECT_SCOPE_PATH_ENV,
    PROJECT_SCOPE_REVISION_ENV,
    load_project,
    project_revision,
    resolve_project_path,
)
from ai_translate import (
    choose_model,
    mask_protected_tokens,
    order_entries_by_model,
    remove_hotkeys,
    restore_hotkeys,
    restore_protected_tokens,
    select_entries,
)
from watch_progress import activity_state, calculate_recent_rate, render_snapshot
from opencode_farm import (
    FarmSupervisor,
    active_state_process_groups,
    bind_runtime_paths,
    build_opencode_command,
    drain_farm,
    farm_status,
    load_control,
    load_farm_config,
    load_farm_config_with_runtime_fallback,
    load_state,
    release_farm_leases,
    resume_farm,
    save_control,
    start_detached_locked,
    stop_farm,
    supervisor_is_alive,
)
from agent_batch import release_catalog_workers
from catalog_edit import (
    CatalogEditError,
    EntryConflictError,
    EntryReservedError,
    commit_entry,
    search_entries,
)
from gandalf import (
    farm_button_states,
    gandalf_farm_command,
    read_log_tail,
    resolve_workspace_path,
    start_gandalf_worker,
)


def run_tool(name, *args, env=None):
    return subprocess.run(
        [sys.executable, str(TOOLS / name), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def fill_agent_response(batch_path, translations):
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    response_path = Path(batch["response_file"])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    for item in response["translations"]:
        if item["id"] in translations:
            item["translation"] = translations[item["id"]]
    response_path.write_text(json.dumps(response), encoding="utf-8")
    return response_path


def create_project_fixture(directory, entries, name="catalog-edit-test"):
    directory = Path(directory)
    catalog = directory / "catalog.json"
    project_file = directory / "project.json"
    catalog.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    project_file.write_text(json.dumps({
        "name": name,
        "source_archive": str(directory / "source.big"),
        "string_directory": str(directory),
        "string_files": ["data/strings.str"],
        "catalog": str(catalog),
        "output_string_file": str(directory / "strings.str"),
        "output_package": str(directory / "output.big"),
        "language": "es-419",
        "encoding": "cp1252",
    }), encoding="utf-8")
    return project_file, catalog


class LocalizationToolTests(unittest.TestCase):
    def test_rotwk_project_configuration(self):
        project = load_project(ROOT / "config" / "project.json")
        self.assertEqual(project["name"], "bfme2-rotwk-2.02")
        self.assertEqual(project["encoding"], "cp1252")
        self.assertEqual(project["string_header"], "// String file for Lord of the Rings")
        self.assertEqual(project["debug_marker"], "DEBUGING")
        self.assertEqual(project["language"], "es-ES")
        self.assertEqual(
            resolve_project_path(project, "output_package"),
            ROOT / "releases" / "spanishpatch202_es-ES.big",
        )

    def test_rotwk_project_es419_configuration(self):
        project_es419 = ROOT / "config" / "project_es-419.json"
        if not project_es419.exists():
            self.skipTest("es-419 project config not present")
        project = load_project(project_es419)
        self.assertEqual(project["name"], "bfme2-rotwk-2.02")
        self.assertEqual(project["encoding"], "cp1252")
        self.assertEqual(project["language"], "es-419")
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

    def test_extended_format_tokens_and_hotkeys_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({
                "entries": [{
                    "id": "CONTROLBAR:Hotkey",
                    "source": "Use &Aragorn Coger arma [&Y] Ataca [&é] %ls %hs %S %g",
                    "translation": "Usar [&A]ragorn Coger arma [&Y] Ataca [&é] %ls %hs %S %g",
                    "status": "translated",
                }]
            }), encoding="utf-8")
            valid = run_tool("validate_translation.py", catalog)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            data = json.loads(catalog.read_text(encoding="utf-8"))
            data["entries"][0]["translation"] = "Usar &Aragorn Coger arma &Y Ataca [&é] %ls %hs %S %d"
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

    def test_normalize_hotkeys_moves_marker_to_trailing_brackets(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            catalog.write_text(json.dumps({
                "entries": [{
                    "id": "CONTROLBAR:Hotkey",
                    "source": "Build &Farm",
                    "translation": "Construir Granja",
                    "status": "translated",
                    "flags": [],
                }, {
                    "id": "CONTROLBAR:Existing",
                    "source": "Grab [&Y]",
                    "translation": "Coger arma [&Y]",
                    "status": "translated",
                    "flags": [],
                }]
            }), encoding="utf-8")
            preview = run_tool("normalize_hotkeys.py", catalog)
            self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
            before = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(before["entries"][0]["translation"], "Construir Granja")
            result = run_tool("normalize_hotkeys.py", catalog, "--write")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entries = json.loads(catalog.read_text(encoding="utf-8"))["entries"]
            self.assertEqual(entries[0]["translation"], "Construir Granja [&F]")
            self.assertEqual(entries[1]["translation"], "Coger arma [&Y]")
            self.assertEqual(entries[0]["history"][0]["action"], "hotkey_normalized")

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
                "--checkpoint",
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

    def test_ai_selection_keeps_last_duplicate_id_once(self):
        entries = [
            {"id": "TEST:Duplicate", "source": "Old", "status": "pending"},
            {"id": "TEST:Other", "source": "Other", "status": "pending"},
            {"id": "TEST:Duplicate", "source": "Last", "status": "pending"},
        ]
        selected = select_entries({"entries": entries}, "translate", 10)
        self.assertEqual([entry["id"] for entry in selected], ["TEST:Other", "TEST:Duplicate"])
        self.assertEqual(selected[-1]["source"], "Last")

    def test_ai_selection_excludes_system_version_entries(self):
        data = {"entries": [
            {"id": "Version:BuildMachine", "source": "Build machine: %ls", "status": "pending"},
            {"id": "TEST:Normal", "source": "Hello", "status": "pending"},
        ]}
        selected = select_entries(data, "translate", 10)
        self.assertEqual([entry["id"] for entry in selected], ["TEST:Normal"])

    def test_ai_auto_routing_groups_small_model_before_large_model(self):
        rules = {"format_specifiers": [], "control_characters": [], "sage_tags": [], "regex_patterns": []}
        entries = [
            {"id": "OBJECT:LongDescription", "source": "x" * 200},
            {"id": "TIME:Second", "source": "1 Second"},
        ]
        ordered = order_entries_by_model(
            entries, "auto", "llama3.2:3b", "qwen2.5:7b", 180, rules
        )
        self.assertEqual([entry["id"] for entry in ordered], ["TIME:Second", "OBJECT:LongDescription"])

    def test_ai_protected_tokens_are_masked_and_restored(self):
        rules = {"format_specifiers": [], "control_characters": [r"\n"], "sage_tags": [], "regex_patterns": []}
        masked, replacements = mask_protected_tokens(r"Damage \n\n", rules)
        self.assertEqual(masked, "Damage __SAGE_TOKEN_0____SAGE_TOKEN_1__")
        self.assertEqual(
            restore_protected_tokens(masked, replacements), r"Damage \n\n"
        )

    def test_ai_hotkeys_are_removed_for_model_and_restored_at_end(self):
        source, hotkeys = remove_hotkeys("Al&ternate Weapon")
        self.assertEqual(source, "Alternate Weapon")
        self.assertEqual(hotkeys, ["&t"])
        self.assertEqual(restore_hotkeys("Arma alternativa", hotkeys), "Arma alternativa &t")

    def test_agent_batch_exports_only_bounded_translation_data_and_applies_it(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            batch_file = directory / "batch.json"
            catalog.write_text(json.dumps({
                "private_metadata": "must not be exported",
                "entries": [
                    {"id": "TEST:One", "source": "One", "translation": "", "status": "pending"},
                    {
                        "id": "TEST:Two",
                        "source": "%d Days",
                        "translation": "%d Days",
                        "status": "translated",
                        "translation_meta": {"origin": "source_placeholder"},
                    },
                ],
            }), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "agent-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")

            exported = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--output", batch_file, "--count", "1",
            )

            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            batch = json.loads(batch_file.read_text(encoding="utf-8"))
            self.assertEqual(len(batch["entries"]), 1)
            self.assertEqual(batch["mode"], "incomplete")
            self.assertEqual(batch["entries"][0]["id"], "TEST:Two")
            self.assertNotIn("private_metadata", batch)
            self.assertEqual(batch["entries"][0]["protected_tokens"], ["%d"])
            self.assertNotIn("translation", batch["entries"][0])
            batch_before = batch_file.read_bytes()
            fill_agent_response(batch_file, {"TEST:Two": "%d Días"})

            applied = run_tool(
                "agent_batch.py", "apply", "--project", project_file,
                "--input", batch_file, "--model", "test-agent",
            )

            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertEqual(batch_file.read_bytes(), batch_before)
            entries = json.loads(catalog.read_text(encoding="utf-8"))["entries"]
            self.assertEqual(entries[0]["status"], "pending")
            self.assertEqual(entries[1]["translation"], "%d Días")
            self.assertEqual(entries[1]["status"], "translated")
            self.assertIn("needs_review", entries[1]["flags"])
            self.assertEqual(entries[1]["translation_meta"]["origin"], "agent")

    def test_agent_batch_rejects_invalid_tokens_without_partial_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            batch_file = directory / "batch.json"
            catalog.write_text(json.dumps({"entries": [
                {"id": "TEST:One", "source": "One", "translation": "", "status": "pending"},
                {"id": "TEST:Two", "source": "%d Days", "translation": "", "status": "pending"},
            ]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "agent-atomic-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            exported = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--output", batch_file, "--count", "2",
            )
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            batch = json.loads(batch_file.read_text(encoding="utf-8"))
            fill_agent_response(batch_file, {
                batch["entries"][0]["id"]: "Uno",
                batch["entries"][1]["id"]: "Días",
            })
            before = catalog.read_bytes()

            applied = run_tool(
                "agent_batch.py", "apply", "--project", project_file, "--input", batch_file,
            )

            self.assertNotEqual(applied.returncode, 0)
            self.assertIn("tokens inválidos", applied.stderr)
            self.assertEqual(catalog.read_bytes(), before)

    def test_agent_batch_rejects_truncated_response_and_can_reset_it(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            batch_file = directory / "batch.json"
            catalog.write_text(json.dumps({"entries": [
                {"id": "TEST:One", "source": "One", "translation": "", "status": "pending"},
                {"id": "TEST:Two", "source": "Two", "translation": "", "status": "pending"},
            ]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "response-reset-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            exported = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "response-worker", "--count", "2", "--output", batch_file,
            )
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            batch_before = batch_file.read_bytes()
            batch = json.loads(batch_before)
            response_path = Path(batch["response_file"])
            response = json.loads(response_path.read_text(encoding="utf-8"))
            response["translations"] = response["translations"][:1]
            response_path.write_text(json.dumps(response), encoding="utf-8")

            applied = run_tool(
                "agent_batch.py", "apply", "--project", project_file, "--input", batch_file,
            )
            self.assertNotEqual(applied.returncode, 0)
            self.assertIn("IDs de la respuesta no coinciden", applied.stderr)
            self.assertEqual(batch_file.read_bytes(), batch_before)

            reset = run_tool(
                "agent_batch.py", "reset-response", "--project", project_file,
                "--input", batch_file,
            )
            self.assertEqual(reset.returncode, 0, reset.stdout + reset.stderr)
            restored = json.loads(response_path.read_text(encoding="utf-8"))
            self.assertEqual(len(restored["translations"]), 2)
            self.assertTrue(all(not item["translation"] for item in restored["translations"]))
            restored["translations"][0]["actor"] = "not-allowed"
            response_path.write_text(json.dumps(restored), encoding="utf-8")
            extra_field = run_tool(
                "agent_batch.py", "apply", "--project", project_file, "--input", batch_file,
            )
            self.assertNotEqual(extra_field.returncode, 0)
            self.assertIn("solo id y translation", extra_field.stderr)

    def test_agent_batches_reserve_disjoint_work_for_multiple_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            batch_a = directory / "worker-a.json"
            batch_b = directory / "worker-b.json"
            catalog.write_text(json.dumps({"entries": [
                {"id": f"TEST:{index}", "source": f"Source {index}", "translation": "", "status": "pending"}
                for index in range(1, 5)
            ]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "multi-agent-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")

            commands = [
                [sys.executable, str(TOOLS / "agent_batch.py"), "export",
                 "--project", str(project_file), "--worker", worker,
                 "--count", "2", "--output", str(batch_path)]
                for worker, batch_path in (("worker-a", batch_a), ("worker-b", batch_b))
            ]
            processes = [
                subprocess.Popen(
                    command, cwd=ROOT, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True,
                )
                for command in commands
            ]
            results = [process.communicate(timeout=30) for process in processes]
            for process, (stdout, stderr) in zip(processes, results):
                self.assertEqual(process.returncode, 0, stdout + stderr)
            data_a = json.loads(batch_a.read_text(encoding="utf-8"))
            data_b = json.loads(batch_b.read_text(encoding="utf-8"))
            ids_a = {entry["id"] for entry in data_a["entries"]}
            ids_b = {entry["id"] for entry in data_b["entries"]}
            self.assertFalse(ids_a & ids_b)
            self.assertEqual(len(ids_a | ids_b), 4)

            status_result = run_tool(
                "agent_batch.py", "status", "--project", project_file, "--json",
            )
            self.assertEqual(status_result.returncode, 0, status_result.stdout + status_result.stderr)
            queue = json.loads(status_result.stdout)
            self.assertEqual(queue["eligible"], 4)
            self.assertEqual(queue["reserved"], 4)
            self.assertEqual(queue["available"], 0)
            self.assertEqual(len(queue["active_batches"]), 2)

            apply_commands = []
            for batch_path, batch_data, worker in (
                (batch_a, data_a, "worker-a"),
                (batch_b, data_b, "worker-b"),
            ):
                fill_agent_response(batch_path, {
                    entry["id"]: f"Traducción {entry['id']}"
                    for entry in batch_data["entries"]
                })
                apply_commands.append([
                    sys.executable, str(TOOLS / "agent_batch.py"), "apply",
                    "--project", str(project_file), "--input", str(batch_path),
                    "--actor", worker,
                ])
            apply_processes = [
                subprocess.Popen(
                    command, cwd=ROOT, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True,
                )
                for command in apply_commands
            ]
            apply_results = [process.communicate(timeout=30) for process in apply_processes]
            for process, (stdout, stderr) in zip(apply_processes, apply_results):
                self.assertEqual(process.returncode, 0, stdout + stderr)

            final_entries = json.loads(catalog.read_text(encoding="utf-8"))["entries"]
            self.assertTrue(all(entry["status"] == "translated" for entry in final_entries))
            final_status = run_tool(
                "agent_batch.py", "status", "--project", project_file, "--json",
            )
            queue = json.loads(final_status.stdout)
            self.assertEqual(queue["eligible"], 0)
            self.assertEqual(queue["active_batches"], [])

    def test_watch_progress_reports_effective_queue_percentage(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            catalog.write_text(json.dumps({"entries": [
                {
                    "id": "TEST:Pending",
                    "source": "Pending",
                    "translation": "",
                    "status": "pending",
                },
                {
                    "id": "TEST:Translated",
                    "source": "Translated",
                    "translation": "Traducido",
                    "status": "translated",
                },
                {
                    "id": "TEST:Placeholder",
                    "source": "Placeholder",
                    "translation": "Placeholder",
                    "status": "translated",
                    "translation_meta": {"origin": "source_placeholder"},
                },
                {
                    "id": "TEST:Preserved",
                    "source": "Preserved",
                    "translation": "Preserved",
                    "status": "preserved",
                },
                {
                    "id": "Version:BuildMachine",
                    "source": "Build machine",
                    "translation": "",
                    "status": "pending",
                },
            ]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "progress-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")

            result = run_tool(
                "watch_progress.py", "--project", project_file,
                "--once", "--no-clear",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("33,33%", result.stdout)
            self.assertIn("Traducciones completadas: 1 / 3", result.stdout)
            self.assertIn("Entradas incompletas: 2", result.stdout)
            self.assertIn("Estado: DETENIDO", result.stdout)
            self.assertIn("Ritmo reciente (últimos 5 min): 0,00 entradas/min", result.stdout)
            self.assertNotIn("Tiempo restante estimado:", result.stdout)
            self.assertIn("Lotes activos: 0", result.stdout)
            self.assertNotIn("\033", result.stdout)

    def test_watch_progress_recent_rate_expires_after_five_minutes(self):
        samples = [
            (0.0, 100),
            (60.0, 125),
            (300.0, 125),
        ]
        self.assertEqual(calculate_recent_rate(samples), 5.0)

        samples = [
            (60.0, 125),
            (300.0, 125),
            (361.0, 125),
        ]
        self.assertEqual(calculate_recent_rate(samples), 0.0)

    def test_watch_progress_distinguishes_activity_states(self):
        snapshot = {"eligible": 100, "active_batches": [{"worker": "worker-1"}]}
        self.assertEqual(activity_state(snapshot, 5.0, 600.0, 300.0), "AVANZANDO")
        self.assertEqual(
            activity_state(snapshot, 0.0, 120.0, 300.0),
            "ESPERANDO APLICACIÓN",
        )
        self.assertEqual(
            activity_state(snapshot, 0.0, 301.0, 300.0),
            "SIN AVANCE RECIENTE",
        )
        snapshot["active_batches"] = []
        self.assertEqual(
            activity_state(snapshot, 10.0, 600.0, 300.0),
            "DETENIDO (sin lotes activos)",
        )
        snapshot["eligible"] = 0
        self.assertEqual(activity_state(snapshot, 0.0, 600.0, 300.0), "COMPLETADO")

    def test_watch_progress_eta_uses_only_recent_activity(self):
        snapshot = {
            "project": "progress-test",
            "language": "es-419",
            "completed": 100,
            "total": 200,
            "progress_percent": 50.0,
            "eligible": 100,
            "reserved": 25,
            "available": 75,
            "active_batches": [{
                "worker": "worker-1",
                "entries": 25,
                "expires_at": "2099-01-01T00:00:00+00:00",
            }],
        }

        stalled = render_snapshot(
            snapshot, 50, 100, 301.0, 10.0, 0.0, 5.0, 301.0
        )
        advancing = render_snapshot(
            snapshot, 50, 75, 301.0, 10.0, 20.0, 5.0, 10.0
        )

        self.assertIn("Estado: SIN AVANCE RECIENTE", stalled)
        self.assertNotIn("Tiempo restante estimado:", stalled)
        self.assertIn("Estado: AVANZANDO", advancing)
        self.assertIn("Tiempo restante estimado: 5m", advancing)

    def test_agent_batch_release_returns_reserved_entries_to_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            batch_file = directory / "worker.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Reserved",
                "source": "Reserved",
                "translation": "",
                "status": "pending",
            }]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "lease-release-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            exported = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "worker-release", "--output", batch_file,
            )
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)

            released = run_tool(
                "agent_batch.py", "release", "--project", project_file,
                "--input", batch_file,
            )

            self.assertEqual(released.returncode, 0, released.stdout + released.stderr)
            status_result = run_tool(
                "agent_batch.py", "status", "--project", project_file, "--json",
            )
            queue = json.loads(status_result.stdout)
            self.assertEqual(queue["eligible"], 1)
            self.assertEqual(queue["reserved"], 0)
            self.assertEqual(queue["available"], 1)

    def test_agent_batch_release_prefix_keeps_unrelated_leases(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            catalog.write_text(json.dumps({"entries": [
                {
                    "id": f"TEST:{index}",
                    "source": f"Source {index}",
                    "translation": "",
                    "status": "pending",
                }
                for index in range(4)
            ]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "release-prefix-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")

            for worker in ("farm-a-1", "farm-b-1"):
                result = run_tool(
                    "agent_batch.py", "export", "--project", project_file,
                    "--worker", worker, "--count", "2",
                    "--output", directory / f"{worker}.json",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            released = run_tool(
                "agent_batch.py", "release-prefix", "--project", project_file,
                "--prefix", "farm-a",
            )
            status_result = run_tool(
                "agent_batch.py", "status", "--project", project_file, "--json",
            )
            queue = json.loads(status_result.stdout)

            self.assertEqual(released.returncode, 0, released.stdout + released.stderr)
            self.assertIn("Reservas liberadas para farm-a: 1", released.stdout)
            self.assertEqual(queue["reserved"], 2)
            self.assertEqual(queue["available"], 2)
            self.assertEqual(
                [batch["worker"] for batch in queue["active_batches"]],
                ["farm-b-1"],
            )

    def test_agent_batch_enforces_supervisor_worker_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Scoped",
                "source": "Scoped",
                "translation": "",
                "status": "pending",
            }]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "worker-scope-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            environment = os.environ.copy()
            environment.update({
                "BFME_TRANSLATION_WORKER_PREFIX": "farm-safe",
                "BFME_TRANSLATION_WORKER_COUNT": "4",
            })

            rejected = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "farm", "--output", directory / "rejected.json",
                env=environment,
            )
            accepted = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "farm-safe-1", "--output", directory / "accepted.json",
                env=environment,
            )

            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("worker fuera del ámbito", rejected.stderr)
            self.assertFalse((directory / "rejected.json").exists())
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

    def test_catalog_edit_rejects_reserved_entry_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:Reserved",
                "source": "Reserved",
                "translation": "",
                "status": "pending",
                "flags": [],
            }])
            snapshot = search_entries(project_path=project_file)[0]
            self.assertEqual(len(snapshot["entry_revision"]), 32)
            exported = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "reservation-test", "--count", "1",
                "--output", directory / "batch.json",
            )
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            before = catalog.read_bytes()

            with self.assertRaisesRegex(EntryReservedError, "reservada por"):
                commit_entry(
                    snapshot["id"],
                    snapshot["entry_revision"],
                    "save",
                    project_path=project_file,
                    translation="Reservado",
                )

            self.assertEqual(catalog.read_bytes(), before)

    def test_catalog_edit_merges_with_unrelated_agent_application(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, catalog = create_project_fixture(directory, [
                {
                    "id": "TEST:Manual",
                    "source": "Manual",
                    "translation": "",
                    "status": "pending",
                    "flags": [],
                },
                {
                    "id": "TEST:Agent",
                    "source": "Agent",
                    "translation": "",
                    "status": "pending",
                    "flags": [],
                },
            ])
            manual_snapshot = next(
                item for item in search_entries(project_path=project_file)
                if item["id"] == "TEST:Manual"
            )
            batch_file = directory / "agent.json"
            exported = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "agent-worker", "--count", "1",
                "--output", batch_file,
            )
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            fill_agent_response(batch_file, {"TEST:Agent": "Agente"})
            applied = run_tool(
                "agent_batch.py", "apply", "--project", project_file,
                "--input", batch_file, "--actor", "agent-worker",
            )
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)

            commit_entry(
                manual_snapshot["id"],
                manual_snapshot["entry_revision"],
                "save",
                project_path=project_file,
                translation="Manual corregido",
            )

            entries = {
                item["id"]: item
                for item in json.loads(catalog.read_text(encoding="utf-8"))["entries"]
            }
            self.assertEqual(entries["TEST:Agent"]["translation"], "Agente")
            self.assertEqual(
                entries["TEST:Manual"]["translation"], "Manual corregido"
            )

    def test_catalog_edit_rejects_stale_entry_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:Conflict",
                "source": "One",
                "translation": "",
                "status": "pending",
                "flags": [],
            }])
            snapshot = search_entries(project_path=project_file)[0]
            commit_entry(
                snapshot["id"], snapshot["entry_revision"], "save",
                project_path=project_file, translation="Uno",
            )

            with self.assertRaisesRegex(EntryConflictError, "cambió"):
                commit_entry(
                    snapshot["id"], snapshot["entry_revision"], "save",
                    project_path=project_file, translation="Uno corregido",
                )

    def test_catalog_edit_validates_tokens_and_requires_explicit_preserve(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:Tokens",
                "source": "%d Days",
                "translation": "",
                "status": "pending",
                "flags": [],
            }])
            snapshot = search_entries(project_path=project_file)[0]

            with self.assertRaisesRegex(CatalogEditError, "tokens inválidos"):
                commit_entry(
                    snapshot["id"], snapshot["entry_revision"], "save",
                    project_path=project_file, translation="Días",
                )
            with self.assertRaisesRegex(CatalogEditError, "use la acción preserve"):
                commit_entry(
                    snapshot["id"], snapshot["entry_revision"], "save",
                    project_path=project_file, translation="%d Days",
                )

            preserved = commit_entry(
                snapshot["id"], snapshot["entry_revision"], "preserve",
                project_path=project_file,
            )
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(preserved["status"], "preserved")
            self.assertEqual(entry["translation"], "%d Days")
            self.assertIn("source_preserved", entry["flags"])

    def test_catalog_edit_review_and_requeue_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:Review",
                "source": "Hello",
                "translation": "Hola",
                "status": "translated",
                "flags": ["needs_review"],
            }])
            snapshot = search_entries(project_path=project_file)[0]
            reviewed = commit_entry(
                snapshot["id"], snapshot["entry_revision"], "review",
                project_path=project_file,
            )
            self.assertEqual(reviewed["status"], "reviewed")
            self.assertNotIn("needs_review", reviewed["flags"])

            requeued = commit_entry(
                reviewed["id"], reviewed["entry_revision"], "requeue",
                project_path=project_file,
            )
            entry = json.loads(catalog.read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual(requeued["status"], "pending")
            self.assertEqual(entry["translation"], "")
            self.assertIn("manual_requeue", entry["flags"])

    def test_opencode_farm_uses_explicit_models_for_every_coordinator(self):
        config_path = ROOT / "config" / "opencode_farm.json"
        config = load_farm_config(config_path)

        self.assertEqual(config["workers"], 4)
        self.assertEqual(config["count"], 25)
        self.assertEqual(len(config["coordinators"]), 5)
        self.assertEqual(
            [item["model"] for item in config["coordinators"]],
            [
                "opencode/ling-3.0-flash-free",
                "opencode-go/deepseek-v4-flash",
                "opencode/mimo-v2.5-free",
                "opencode/nemotron-3-ultra-free",
                "opencode/laguna-s-2.1-free",
            ],
        )
        for coordinator in config["coordinators"]:
            command = build_opencode_command(
                coordinator, config["project"], 4, 25
            )
            self.assertEqual(
                command[command.index("--agent") + 1],
                "translation-coordinator",
            )
            self.assertEqual(command[command.index("--model") + 1], coordinator["model"])
            arguments = json.loads(command[-1])
            self.assertEqual(arguments, {
                "project": str(config["project"]),
                "prefix": coordinator["prefix"],
                "workers": 4,
                "count": 25,
            })
            self.assertNotIn("gemma", " ".join(command).lower())

        dry_run = run_tool(
            "opencode_farm.py", "start", "--config", config_path, "--dry-run"
        )
        self.assertEqual(dry_run.returncode, 0, dry_run.stdout + dry_run.stderr)
        self.assertEqual(len(dry_run.stdout.strip().splitlines()), 5)

    def test_opencode_farm_passes_exact_worker_scope_to_child(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file = directory / "project.json"
            project_file.write_text("{}", encoding="utf-8")
            config = {
                "config_path": directory / "farm.json",
                "project": project_file,
                "project_revision": "project-revision",
                "workers": 4,
                "count": 25,
                "max_restarts": 1,
                "poll_seconds": 1.0,
                "state_file": directory / "state.json",
                "control_file": directory / "control.json",
                "log_directory": directory / "logs",
                "coordinators": [{
                    "prefix": "farm-safe",
                    "model": "provider/model",
                }],
            }
            supervisor = FarmSupervisor(config)
            process = Mock(pid=12345)

            with (
                patch("opencode_farm.subprocess.Popen", return_value=process) as popen,
                patch.object(supervisor, "save_state"),
            ):
                supervisor.launch(supervisor.slots[0])

            environment = popen.call_args.kwargs["env"]
            self.assertEqual(
                environment["BFME_TRANSLATION_WORKER_PREFIX"], "farm-safe"
            )
            self.assertEqual(environment["BFME_TRANSLATION_WORKER_COUNT"], "4")
            self.assertEqual(
                environment[PROJECT_SCOPE_PATH_ENV], str(directory / "project.json")
            )
            self.assertEqual(
                environment[PROJECT_SCOPE_REVISION_ENV], "project-revision"
            )
            supervisor.slots[0]["log"].close()

    def test_supervised_project_scope_rejects_other_or_changed_project(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)

            def create_project(name):
                project_directory = directory / name
                project_directory.mkdir()
                catalog = project_directory / "catalog.json"
                project_file = project_directory / "project.json"
                catalog.write_text(json.dumps({"entries": [{
                    "id": f"TEST:{name}",
                    "source": name,
                    "translation": "",
                    "status": "pending",
                }]}), encoding="utf-8")
                project_file.write_text(json.dumps({
                    "name": name,
                    "source_archive": str(project_directory / "source.big"),
                    "string_directory": str(project_directory),
                    "string_files": ["data/strings.str"],
                    "catalog": str(catalog),
                    "output_string_file": str(project_directory / "strings.str"),
                    "output_package": str(project_directory / "output.big"),
                    "language": "es-419",
                    "encoding": "cp1252",
                }), encoding="utf-8")
                return project_file, catalog

            project_a, catalog_a = create_project("project-a")
            project_b, _catalog_b = create_project("project with spaces")
            environment = os.environ.copy()
            environment.update({
                PROJECT_SCOPE_PATH_ENV: str(project_b.resolve()),
                PROJECT_SCOPE_REVISION_ENV: project_revision(project_b),
            })
            self.assertEqual(len(environment[PROJECT_SCOPE_REVISION_ENV]), 32)
            before_a = catalog_a.read_bytes()

            wrong_project = run_tool(
                "agent_batch.py", "status", "--project", project_a,
                "--mode", "incomplete", "--json", env=environment,
            )
            correct_project = run_tool(
                "agent_batch.py", "status", "--project", project_b,
                "--mode", "incomplete", "--json", env=environment,
            )

            self.assertNotEqual(wrong_project.returncode, 0)
            self.assertIn("fuera del ámbito supervisado", wrong_project.stderr)
            self.assertEqual(catalog_a.read_bytes(), before_a)
            self.assertEqual(
                correct_project.returncode,
                0,
                correct_project.stdout + correct_project.stderr,
            )

            project_b.write_text(
                project_b.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            changed_project = run_tool(
                "agent_batch.py", "status", "--project", project_b,
                "--mode", "incomplete", "--json", env=environment,
            )
            self.assertNotEqual(changed_project.returncode, 0)
            self.assertIn("cambió durante la ejecución", changed_project.stderr)

    def test_opencode_farm_cleans_up_after_unexpected_error(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = {
                "config_path": directory / "farm.json",
                "project": directory / "project.json",
                "project_revision": "project-revision",
                "project_name": "farm-test",
                "language": "es-419",
                "catalog": directory / "catalog.json",
                "workers": 4,
                "count": 25,
                "max_restarts": 1,
                "poll_seconds": 1.0,
                "state_file": directory / "state.json",
                "control_file": directory / "control.json",
                "log_directory": directory / "logs",
                "coordinators": [{
                    "prefix": "farm-test",
                    "model": "provider/model",
                }],
            }
            supervisor = FarmSupervisor(config)

            with (
                patch("opencode_farm.signal.signal"),
                patch.object(supervisor, "save_state"),
                patch(
                    "opencode_farm.catalog_progress_snapshot",
                    side_effect=RuntimeError("snapshot failed"),
                ),
                patch("opencode_farm.project_revision", return_value="project-revision"),
                patch.object(supervisor, "cleanup") as cleanup,
            ):
                with self.assertRaisesRegex(RuntimeError, "snapshot failed"):
                    supervisor.run()

            cleanup.assert_called_once_with()

    def test_opencode_farm_stop_keeps_leases_if_supervisor_will_not_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            state_file = directory / "state.json"
            state_file.write_text(json.dumps({
                "schema_version": 3,
                "config": str(directory / "farm.json"),
                "project": str(directory / "project.json"),
                "project_revision": "project-revision",
                "supervisor_pid": 12345,
                "mode": "running",
                "children": [],
            }), encoding="utf-8")
            config = {
                "config_path": directory / "farm.json",
                "state_file": state_file,
                "control_file": directory / "control.json",
                "project": directory / "project.json",
                "project_revision": "project-revision",
                "coordinators": [],
            }

            with (
                patch("opencode_farm.supervisor_is_alive", return_value=True),
                patch("opencode_farm.wait_for_process_exit", return_value=False),
                patch("opencode_farm.os.kill"),
                patch("opencode_farm.release_farm_leases") as release_leases,
            ):
                with self.assertRaisesRegex(RuntimeError, "no se detuvo"):
                    stop_farm(config)

            release_leases.assert_not_called()
            self.assertTrue(state_file.exists())

    def test_opencode_farm_drain_and_resume_write_control(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            state_file = directory / "state.json"
            control_file = directory / "control.json"
            state_file.write_text(json.dumps({
                "schema_version": 3,
                "config": str(directory / "farm.json"),
                "project": str(directory / "project.json"),
                "project_revision": "project-revision",
                "supervisor_pid": 12345,
                "mode": "running",
                "children": [],
            }), encoding="utf-8")
            config = {
                "config_path": directory / "farm.json",
                "state_file": state_file,
                "control_file": control_file,
                "project": directory / "project.json",
                "project_revision": "project-revision",
                "coordinators": [],
            }

            with (
                patch("opencode_farm.supervisor_is_alive", return_value=True),
                patch("opencode_farm.wait_for_control_ack", return_value=True),
            ):
                self.assertEqual(drain_farm(config), 0)
                self.assertEqual(
                    json.loads(control_file.read_text(encoding="utf-8"))["action"],
                    "drain",
                )
                self.assertEqual(resume_farm(config), 0)
                self.assertEqual(
                    json.loads(control_file.read_text(encoding="utf-8"))["action"],
                    "resume",
                )

    def test_opencode_farm_draining_does_not_launch_new_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = {
                "config_path": directory / "farm.json",
                "project": directory / "project.json",
                "project_revision": "project-revision",
                "project_name": "farm-test",
                "language": "es-419",
                "catalog": directory / "catalog.json",
                "workers": 4,
                "count": 25,
                "max_restarts": 1,
                "poll_seconds": 1.0,
                "state_file": directory / "state.json",
                "control_file": directory / "control.json",
                "log_directory": directory / "logs",
                "coordinators": [{
                    "prefix": "farm-test",
                    "model": "provider/model",
                }],
            }
            supervisor = FarmSupervisor(config)

            def request_drain():
                supervisor.draining = True

            with (
                patch("opencode_farm.signal.signal"),
                patch.object(supervisor, "save_state"),
                patch.object(supervisor, "apply_control", side_effect=request_drain),
                patch("opencode_farm.catalog_progress_snapshot", return_value={
                    "eligible": 10,
                    "available": 10,
                    "active_batches": [],
                }),
                patch("opencode_farm.project_revision", return_value="project-revision"),
                patch.object(supervisor, "launch") as launch,
                patch.object(supervisor, "cleanup") as cleanup,
            ):
                result = supervisor.run()

            self.assertEqual(result, 0)
            launch.assert_not_called()
            cleanup.assert_called_once_with()

    def test_opencode_farm_resume_restarts_inactive_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = {
                "state_file": directory / "state.json",
                "control_file": directory / "control.json",
            }
            with patch("opencode_farm.start_detached_locked", return_value=0) as start:
                self.assertEqual(resume_farm(config), 0)
            start.assert_called_once_with(config)

    def test_opencode_farm_status_returns_structured_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:Pending",
                "source": "Pending",
                "translation": "",
                "status": "pending",
            }], name="farm-status-test")
            config = {
                "state_file": directory / "state.json",
                "project": project_file,
                "project_name": "farm-status-test",
                "language": "es-419",
                "catalog": _catalog,
            }

            result = farm_status(config)

            self.assertFalse(result["supervisor"]["active"])
            self.assertEqual(result["supervisor"]["mode"], "stopped")
            self.assertEqual(result["queue"]["eligible"], 1)

    def test_opencode_farm_loads_legacy_state_for_safe_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            for schema_version in (1, 2):
                state_file.write_text(json.dumps({
                    "schema_version": schema_version,
                    "config": str(Path(directory) / "farm.json"),
                    "project": str(Path(directory) / "project.json"),
                    "project_revision": "legacy-revision",
                    "supervisor_pid": 12345,
                    "children": [],
                }), encoding="utf-8")

                state = load_state(state_file)

                self.assertEqual(state["schema_version"], schema_version)
                self.assertEqual(state["mode"], "running")
                self.assertIsNone(state["last_control_id"])

    def test_opencode_farm_stops_legacy_state_when_identity_is_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            catalog.write_text('{"entries": []}', encoding="utf-8")
            state_file = directory / "state.json"
            state_file.write_text(json.dumps({
                "schema_version": 1,
                "config": str(directory / "farm.json"),
                "project": str(directory / "project.json"),
                "project_revision": "legacy-revision",
                "supervisor_pid": 12345,
                "children": [{"prefix": "farm-legacy", "pid": None}],
            }), encoding="utf-8")
            config = {
                "config_path": directory / "farm.json",
                "project": directory / "project.json",
                "project_revision": "legacy-revision",
                "catalog": catalog,
                "state_file": state_file,
                "control_file": directory / "control.json",
                "workers": 2,
                "coordinators": [{"prefix": "farm-legacy"}],
            }

            with (
                patch("opencode_farm.supervisor_is_alive", return_value=True),
                patch("opencode_farm.wait_for_process_exit", return_value=True),
                patch("opencode_farm.os.kill") as kill,
                patch("opencode_farm.release_catalog_workers") as release,
            ):
                self.assertEqual(stop_farm(config), 0)

            kill.assert_called_once_with(12345, signal.SIGTERM)
            release.assert_called_once_with(
                catalog, {"farm-legacy-1", "farm-legacy-2"}
            )
            self.assertFalse(state_file.exists())

    def test_opencode_farm_does_not_signal_reused_supervisor_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            catalog.write_text('{"entries": []}', encoding="utf-8")
            state_file = directory / "state.json"
            state_file.write_text(json.dumps({
                "schema_version": 3,
                "config": str(directory / "farm.json"),
                "project": str(directory / "project.json"),
                "project_revision": "project-revision",
                "catalog": str(catalog),
                "supervisor_pid": 12345,
                "supervisor_identity": "old-process",
                "children": [],
            }), encoding="utf-8")
            config = {
                "config_path": directory / "farm.json",
                "project": directory / "project.json",
                "project_revision": "project-revision",
                "catalog": catalog,
                "state_file": state_file,
                "control_file": directory / "control.json",
                "workers": 2,
                "coordinators": [],
            }

            with (
                patch("opencode_farm.process_is_alive", return_value=True),
                patch("opencode_farm.process_identity", return_value="new-process"),
                patch("opencode_farm.os.kill") as kill,
                patch("opencode_farm.release_farm_leases"),
            ):
                self.assertFalse(supervisor_is_alive(load_state(state_file)))
                self.assertEqual(stop_farm(config), 0)

            self.assertNotIn(
                ((12345, signal.SIGTERM), {}),
                [(call.args, call.kwargs) for call in kill.call_args_list],
            )

    def test_opencode_farm_runtime_paths_survive_profile_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:Pending",
                "source": "Pending",
                "translation": "",
                "status": "pending",
            }], name="farm-anchor-test")
            farm_file = directory / "farm.json"
            runtime_directory = directory / ".agent"
            profile = {
                "project": str(project_file),
                "workers": 2,
                "count": 1,
                "state_file": str(runtime_directory / "state-a.json"),
                "control_file": str(runtime_directory / "control-a.json"),
                "coordinators": [{
                    "prefix": "farm-anchor",
                    "model": "provider/model",
                }],
            }
            farm_file.write_text(json.dumps(profile), encoding="utf-8")
            first = load_farm_config(farm_file)
            bind_runtime_paths(first, create=True)

            profile["state_file"] = str(runtime_directory / "state-b.json")
            profile["control_file"] = str(runtime_directory / "control-b.json")
            farm_file.write_text(json.dumps(profile), encoding="utf-8")
            second = load_farm_config(farm_file)

            self.assertEqual(
                second["state_file"], runtime_directory / "state-a.json"
            )
            self.assertEqual(
                second["control_file"], runtime_directory / "control-a.json"
            )

    def test_opencode_farm_rejects_unsafe_or_aliased_runtime_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:Pending",
                "source": "Pending",
                "translation": "",
                "status": "pending",
            }], name="farm-path-test")
            farm_file = directory / "farm.json"
            profile = {
                "project": str(project_file),
                "workers": 2,
                "count": 1,
                "state_file": str(directory / "unsafe-state.json"),
                "coordinators": [{
                    "prefix": "farm-path",
                    "model": "provider/model",
                }],
            }
            farm_file.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "directorio .agent"):
                load_farm_config(farm_file)

            shared_path = directory / ".agent" / "shared.json"
            profile["state_file"] = str(shared_path)
            profile["control_file"] = str(shared_path)
            farm_file.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "deben ser distintas"):
                load_farm_config(farm_file)

    def test_opencode_farm_runtime_fallback_survives_deleted_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:Pending",
                "source": "Pending",
                "translation": "",
                "status": "pending",
            }], name="farm-fallback-test")
            farm_file = directory / "farm.json"
            runtime_directory = directory / ".agent"
            farm_file.write_text(json.dumps({
                "project": str(project_file),
                "workers": 2,
                "count": 1,
                "state_file": str(runtime_directory / "state.json"),
                "log_directory": str(runtime_directory / "logs"),
                "coordinators": [{
                    "prefix": "farm-fallback",
                    "model": "provider/model",
                }],
            }), encoding="utf-8")
            config = load_farm_config(farm_file)
            bind_runtime_paths(config, create=True)
            farm_file.unlink()

            recovered = load_farm_config_with_runtime_fallback(farm_file)

            self.assertTrue(recovered["runtime_fallback"])
            self.assertEqual(recovered["project"], project_file.resolve())
            status = run_tool(
                "opencode_farm.py", "status", "--config", farm_file, "--json"
            )
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertFalse(
                json.loads(status.stdout)["supervisor"]["profile_available"]
            )

    def test_opencode_farm_requires_identity_and_tokens_in_current_state(self):
        state = {
            "schema_version": 3,
            "supervisor_pid": 12345,
            "children": [{"prefix": "farm-current", "pid": 23456}],
        }
        with (
            patch("opencode_farm.process_is_alive", return_value=True),
            self.assertRaisesRegex(RuntimeError, "no identifica al supervisor"),
        ):
            supervisor_is_alive(state)
        with (
            patch("opencode_farm.process_group_is_alive", return_value=True),
            self.assertRaisesRegex(RuntimeError, "no identifica el grupo"),
        ):
            active_state_process_groups(state)

    def test_opencode_farm_rejects_overlapping_prefixes(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:Pending",
                "source": "Pending",
                "translation": "",
                "status": "pending",
            }], name="farm-prefix-test")
            farm_file = directory / "farm.json"
            farm_file.write_text(json.dumps({
                "project": str(project_file),
                "workers": 2,
                "count": 1,
                "coordinators": [
                    {"prefix": "farm", "model": "provider/model"},
                    {"prefix": "farm-1", "model": "provider/model"},
                ],
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "no pueden solaparse"):
                load_farm_config(farm_file)

    def test_agent_batch_releases_only_exact_worker_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, catalog = create_project_fixture(directory, [
                {
                    "id": "TEST:One",
                    "source": "One",
                    "translation": "",
                    "status": "pending",
                },
                {
                    "id": "TEST:Two",
                    "source": "Two",
                    "translation": "",
                    "status": "pending",
                },
            ], name="exact-release-test")
            for worker in ("farm-1", "farm-10"):
                exported = run_tool(
                    "agent_batch.py", "export", "--project", project_file,
                    "--worker", worker, "--count", "1",
                    "--output", directory / f"{worker}.json",
                )
                self.assertEqual(
                    exported.returncode, 0, exported.stdout + exported.stderr
                )

            release_catalog_workers(catalog, {"farm-1"})
            queue = json.loads(run_tool(
                "agent_batch.py", "status", "--project", project_file, "--json"
            ).stdout)

            self.assertEqual(
                [batch["worker"] for batch in queue["active_batches"]],
                ["farm-10"],
            )

    def test_opencode_farm_reports_orphaned_coordinators_as_active(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:Pending",
                "source": "Pending",
                "translation": "",
                "status": "pending",
            }], name="farm-orphan-test")
            state_file = directory / "state.json"
            state_file.write_text(json.dumps({
                "schema_version": 3,
                "config": str(directory / "farm.json"),
                "project": str(project_file),
                "project_revision": project_revision(project_file),
                "project_name": "farm-orphan-test",
                "language": "es-419",
                "catalog": str(catalog),
                "supervisor_pid": 111,
                "children": [{"prefix": "farm-orphan", "pid": 222}],
            }), encoding="utf-8")
            config = {
                "config_path": directory / "farm.json",
                "project": project_file,
                "project_revision": project_revision(project_file),
                "project_name": "farm-orphan-test",
                "language": "es-419",
                "catalog": catalog,
                "state_file": state_file,
            }

            with (
                patch("opencode_farm.supervisor_is_alive", return_value=False),
                patch("opencode_farm.active_state_process_groups", return_value=[222]),
            ):
                result = farm_status(config)

            self.assertTrue(result["supervisor"]["active"])
            self.assertTrue(result["supervisor"]["orphaned"])
            self.assertEqual(result["supervisor"]["mode"], "orphaned")
            self.assertFalse(result["supervisor"]["control_supported"])
            self.assertTrue(result["children"][0]["active"])

    def test_opencode_farm_control_claim_does_not_delete_newer_command(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = {
                "control_file": directory / "control.json",
                "project": directory / "project.json",
                "project_revision": "project-revision",
            }
            state = {
                "supervisor_pid": 12345,
                "project": str(config["project"]),
                "project_revision": config["project_revision"],
            }
            first_control_id = save_control(config, state, "drain")
            real_json_loads = json.loads
            replacement = {}

            def replace_while_reading(value):
                replacement["id"] = save_control(config, state, "resume")
                return real_json_loads(value)

            with patch("opencode_farm.json.loads", side_effect=replace_while_reading):
                claimed = load_control(config, 12345)

            queued = real_json_loads(
                config["control_file"].read_text(encoding="utf-8")
            )
            self.assertEqual(claimed["control_id"], first_control_id)
            self.assertEqual(queued["control_id"], replacement["id"])
            self.assertEqual(queued["action"], "resume")

    def test_opencode_farm_acknowledges_control_in_state(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = {
                "config_path": directory / "farm.json",
                "project": directory / "project.json",
                "project_revision": "project-revision",
                "project_name": "farm-control-test",
                "language": "es-419",
                "catalog": directory / "catalog.json",
                "state_file": directory / "state.json",
                "control_file": directory / "control.json",
                "workers": 2,
                "coordinators": [],
            }
            supervisor = FarmSupervisor(config)
            supervisor.prepare()
            state = load_state(config["state_file"])
            control_id = save_control(config, state, "drain")

            supervisor.apply_control()

            acknowledged = load_state(config["state_file"])
            self.assertTrue(supervisor.draining)
            self.assertEqual(acknowledged["mode"], "draining")
            self.assertEqual(acknowledged["last_control_id"], control_id)

    def test_opencode_farm_releases_frozen_catalog_and_prefixes(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            old_catalog = directory / "old.json"
            new_catalog = directory / "new.json"
            old_catalog.write_text('{"entries": []}', encoding="utf-8")
            new_catalog.write_text('{"entries": []}', encoding="utf-8")
            config = {
                "project": directory / "project.json",
                "project_revision": "new-revision",
                "catalog": new_catalog,
                "coordinators": [{"prefix": "farm-new"}],
            }
            state = {
                "project": str(config["project"]),
                "project_revision": "old-revision",
                "catalog": str(old_catalog),
                "workers": 2,
                "children": [{"prefix": "farm-old"}],
            }

            with patch("opencode_farm.release_catalog_workers") as release:
                release_farm_leases(config, state)

            release.assert_called_once_with(
                old_catalog.resolve(), {"farm-old-1", "farm-old-2"}
            )

    def test_opencode_farm_stop_uses_recorded_state_after_project_change(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            old_catalog = directory / "old.json"
            new_catalog = directory / "new.json"
            old_catalog.write_text('{"entries": []}', encoding="utf-8")
            new_catalog.write_text('{"entries": []}', encoding="utf-8")
            state_file = directory / "state.json"
            state_file.write_text(json.dumps({
                "schema_version": 3,
                "config": str(directory / "farm.json"),
                "project": str(directory / "project.json"),
                "project_revision": "old-revision",
                "catalog": str(old_catalog),
                "workers": 2,
                "supervisor_pid": 12345,
                "mode": "running",
                "children": [{"prefix": "farm-old", "pid": None}],
            }), encoding="utf-8")
            config = {
                "config_path": directory / "farm.json",
                "project": directory / "project.json",
                "project_revision": "new-revision",
                "catalog": new_catalog,
                "state_file": state_file,
                "control_file": directory / "control.json",
                "workers": 2,
                "coordinators": [{"prefix": "farm-new"}],
            }

            with (
                patch("opencode_farm.supervisor_is_alive", return_value=False),
                patch("opencode_farm.process_group_is_alive", return_value=False),
                patch("opencode_farm.release_catalog_workers") as release,
            ):
                self.assertEqual(stop_farm(config), 0)

            release.assert_called_once_with(
                old_catalog.resolve(), {"farm-old-1", "farm-old-2"}
            )
            self.assertFalse(state_file.exists())

    def test_opencode_farm_keeps_exited_leader_until_group_finishes(self):
        supervisor = FarmSupervisor({
            "coordinators": [{"prefix": "farm-tree", "model": "provider/model"}],
        })
        process = Mock(pid=12345, returncode=0)
        process.poll.return_value = 0
        supervisor.slots[0]["process"] = process

        with patch("opencode_farm.process_group_is_alive", return_value=True):
            supervisor.close_finished_slot(supervisor.slots[0])

        self.assertIs(supervisor.slots[0]["process"], process)

    def test_opencode_farm_cleans_up_when_detached_handshake_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = {
                "config_path": directory / "farm.json",
                "project": directory / "project.json",
                "project_revision": "project-revision",
                "state_file": directory / "state.json",
                "control_file": directory / "control.json",
                "log_directory": directory / "logs",
            }
            process = Mock(pid=12345)

            with (
                patch("opencode_farm.shutil.which", return_value="/bin/opencode"),
                patch("opencode_farm.subprocess.Popen", return_value=process),
                patch("opencode_farm.load_state", side_effect=ValueError("bad state")),
                patch("opencode_farm.cleanup_failed_detached_start") as cleanup,
            ):
                with self.assertRaisesRegex(ValueError, "bad state"):
                    start_detached_locked(config)

            cleanup.assert_called_once_with(config, process)

    def test_opencode_farm_rejects_excessive_poll_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:Pending",
                "source": "Pending",
                "translation": "",
                "status": "pending",
            }], name="farm-poll-test")
            farm_file = directory / "farm.json"
            farm_file.write_text(json.dumps({
                "project": str(project_file),
                "workers": 2,
                "count": 1,
                "poll_seconds": 11,
                "coordinators": [{
                    "prefix": "farm-poll",
                    "model": "provider/model",
                }],
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "entre 1 y 10"):
                load_farm_config(farm_file)

    def test_opencode_farm_detached_lifecycle_smoke(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:Pending",
                "source": "Pending",
                "translation": "",
                "status": "pending",
            }], name="farm-lifecycle-test")
            fake_bin = directory / "bin"
            fake_bin.mkdir()
            fake_opencode = fake_bin / "opencode"
            fake_opencode.write_text(
                "#!/bin/sh\n"
                f'"{sys.executable}" "{TOOLS / "agent_batch.py"}" export '
                '--project "$SAGE_LOCALIZATION_PROJECT" '
                '--worker "${BFME_TRANSLATION_WORKER_PREFIX}-1" '
                f'--count 1 --output "{directory}/batch-$$.json" >/dev/null\n'
                "sleep 1.5\n",
                encoding="utf-8",
            )
            fake_opencode.chmod(0o755)
            runtime_directory = directory / ".agent"
            state_file = runtime_directory / "state.json"
            farm_file = directory / "farm.json"
            second_farm_file = directory / "farm-second.json"
            farm_profile = {
                "project": str(project_file),
                "workers": 2,
                "count": 1,
                "max_restarts": 0,
                "poll_seconds": 1,
                "state_file": str(state_file),
                "log_directory": str(runtime_directory / "logs"),
                "coordinators": [{
                    "prefix": "farm-smoke",
                    "model": "provider/model",
                }],
            }
            farm_file.write_text(json.dumps(farm_profile), encoding="utf-8")
            second_farm_file.write_text(json.dumps(farm_profile), encoding="utf-8")
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            active_farm_file = farm_file

            def farm_command(command, *extra):
                return run_tool(
                    "opencode_farm.py",
                    command,
                    "--config",
                    active_farm_file,
                    *extra,
                    env=environment,
                )

            try:
                starts = [
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(TOOLS / "opencode_farm.py"),
                            "start",
                            "--config",
                            str(profile_path),
                            "--detach",
                        ],
                        cwd=ROOT,
                        env=environment,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    for profile_path in (farm_file, second_farm_file)
                ]
                start_results = []
                for process in starts:
                    stdout, stderr = process.communicate(timeout=15)
                    start_results.append((process.returncode, stdout, stderr))
                self.assertEqual(
                    sorted(result[0] for result in start_results), [0, 1]
                )
                self.assertIn(
                    "ya está activa",
                    "".join(result[2] for result in start_results),
                )
                active_farm_file = (
                    farm_file if start_results[0][0] == 0 else second_farm_file
                )
                deadline = time.monotonic() + 5
                active_child = None
                while time.monotonic() < deadline:
                    payload = json.loads(farm_command("status", "--json").stdout)
                    active_child = next(
                        (
                            child for child in payload["children"]
                            if child["active"]
                        ),
                        None,
                    )
                    if active_child and payload["queue"]["reserved"] == 1:
                        break
                    time.sleep(0.1)
                self.assertIsNotNone(active_child, "no coordinator became active")
                self.assertEqual(payload["queue"]["reserved"], 1)
                drained = farm_command("drain")
                self.assertEqual(
                    drained.returncode, 0, drained.stdout + drained.stderr
                )
                deadline = time.monotonic() + 8
                while state_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertFalse(state_file.exists(), "the drained farm did not exit")
                drained_status = json.loads(farm_command("status", "--json").stdout)
                self.assertEqual(drained_status["queue"]["reserved"], 0)

                resumed = farm_command("resume")
                self.assertEqual(
                    resumed.returncode, 0, resumed.stdout + resumed.stderr
                )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    payload = json.loads(farm_command("status", "--json").stdout)
                    if (
                        any(child["active"] for child in payload["children"])
                        and payload["queue"]["reserved"] == 1
                    ):
                        break
                    time.sleep(0.1)
                self.assertTrue(
                    any(child["active"] for child in payload["children"]),
                    "no coordinator became active after resume",
                )
                self.assertEqual(payload["queue"]["reserved"], 1)
                stopped = farm_command("stop")
                self.assertEqual(
                    stopped.returncode, 0, stopped.stdout + stopped.stderr
                )
            finally:
                if state_file.exists():
                    farm_command("stop")

            status = farm_command("status", "--json")
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            payload = json.loads(status.stdout)
            self.assertFalse(payload["supervisor"]["active"])
            self.assertEqual(payload["queue"]["reserved"], 0)

    def test_agent_batch_reuses_active_lease_for_same_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            first_batch = directory / "first.json"
            unused_batch = directory / "unused.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "lease-reuse-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            first = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "same-worker", "--output", first_batch,
            )
            repeated = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "same-worker", "--output", unused_batch,
            )

            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
            self.assertIn(str(first_batch.resolve()), repeated.stdout)
            self.assertFalse(unused_batch.exists())

    def test_agent_batch_can_release_corrupt_file_by_batch_id(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            batch_file = directory / "worker.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Corrupt", "source": "Corrupt", "translation": "", "status": "pending",
            }]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "corrupt-release-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            exported = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "worker-corrupt", "--output", batch_file,
            )
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            batch_id = json.loads(batch_file.read_text(encoding="utf-8"))["batch_id"]
            batch_file.write_text("{broken", encoding="utf-8")

            released = run_tool(
                "agent_batch.py", "release", "--project", project_file,
                "--batch-id", batch_id, "--worker", "worker-corrupt",
            )

            self.assertEqual(released.returncode, 0, released.stdout + released.stderr)
            queue = json.loads(run_tool(
                "agent_batch.py", "status", "--project", project_file, "--json",
            ).stdout)
            self.assertEqual(queue["available"], 1)
            self.assertEqual(queue["active_batches"], [])

    def test_agent_batch_rejects_expired_lease_and_renew_extends_it(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog = directory / "catalog.json"
            project_file = directory / "project.json"
            batch_file = directory / "worker.json"
            catalog.write_text(json.dumps({"entries": [{
                "id": "TEST:Lease", "source": "Lease", "translation": "", "status": "pending",
            }]}), encoding="utf-8")
            project_file.write_text(json.dumps({
                "name": "lease-expiry-test",
                "source_archive": str(directory / "source.big"),
                "string_directory": str(directory),
                "string_files": ["data/strings.str"],
                "catalog": str(catalog),
                "output_string_file": str(directory / "strings.str"),
                "output_package": str(directory / "output.big"),
                "language": "es-419",
                "encoding": "cp1252",
            }), encoding="utf-8")
            exported = run_tool(
                "agent_batch.py", "export", "--project", project_file,
                "--worker", "worker-lease", "--output", batch_file,
                "--lease-seconds", "60",
            )
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            registry_path = directory / ".catalog.json.agent-leases.json"
            before_renew = json.loads(
                registry_path.read_text(encoding="utf-8")
            )["leases"][0]["expires_at"]
            renewed = run_tool(
                "agent_batch.py", "renew", "--project", project_file,
                "--input", batch_file, "--lease-seconds", "120",
            )
            self.assertEqual(renewed.returncode, 0, renewed.stdout + renewed.stderr)
            after_renew = json.loads(
                registry_path.read_text(encoding="utf-8")
            )["leases"][0]["expires_at"]
            self.assertGreater(after_renew, before_renew)

            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["leases"][0]["expires_at"] = 0
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            fill_agent_response(batch_file, {"TEST:Lease": "Reserva"})
            before_apply = catalog.read_bytes()

            applied = run_tool(
                "agent_batch.py", "apply", "--project", project_file, "--input", batch_file,
            )

            self.assertNotEqual(applied.returncode, 0)
            self.assertIn("reserva del lote venció", applied.stderr)
            self.assertEqual(catalog.read_bytes(), before_apply)

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
        self.assertIn("--gui", result.stdout)
        self.assertIn("--cli", result.stdout)
        self.assertIn("--avanced", result.stdout)

    def test_gandalf_builds_exact_farm_control_commands(self):
        config_path = ROOT / "config" / "opencode_farm.json"
        start = gandalf_farm_command("start", config_path)
        drain = gandalf_farm_command("drain", config_path)
        relative = gandalf_farm_command(
            "stop", Path("config") / "opencode_farm.json"
        )

        self.assertEqual(start[-1], "--detach")
        self.assertEqual(start[-4:-1], ["start", "--config", str(config_path)])
        self.assertEqual(drain[-3:], ["drain", "--config", str(config_path)])
        self.assertEqual(relative[-1], str(config_path))
        self.assertEqual(
            resolve_workspace_path("config/opencode_farm.json"), config_path
        )
        with self.assertRaisesRegex(ValueError, "acción de granja inválida"):
            gandalf_farm_command("invalid", config_path)

    def test_gandalf_farm_button_policy_covers_safe_states(self):
        self.assertEqual(
            farm_button_states(True, "orphaned", control_supported=False),
            ("disabled", "disabled", "disabled", "normal"),
        )
        self.assertEqual(
            farm_button_states(False, "stopped"),
            ("normal", "disabled", "normal", "disabled"),
        )
        self.assertEqual(
            farm_button_states(True, "draining"),
            ("disabled", "disabled", "normal", "normal"),
        )
        self.assertEqual(
            farm_button_states(True, "running", project_changed=True),
            ("disabled", "disabled", "disabled", "normal"),
        )
        self.assertEqual(
            farm_button_states(True, "running", profile_available=False),
            ("disabled", "disabled", "disabled", "normal"),
        )
        self.assertEqual(
            farm_button_states(
                True, "running", enabled=False, action_running=True
            ),
            ("disabled", "disabled", "disabled", "disabled"),
        )

    def test_gandalf_reads_only_the_requested_log_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "farm.log"
            log_path.write_text(
                "\n".join(f"line-{index}" for index in range(250)) + "\n",
                encoding="utf-8",
            )

            lines = read_log_tail(log_path, line_count=20).splitlines()

            self.assertEqual(lines[0], "line-230")
            self.assertEqual(lines[-1], "line-249")
            self.assertEqual(len(lines), 20)

            log_path.write_text(
                "must-not-be-read-" + ("x" * 2048) + "\nlast-line\n",
                encoding="utf-8",
            )
            bounded = read_log_tail(log_path, max_bytes=64)
            self.assertNotIn("must-not-be-read", bounded)
            self.assertLessEqual(len(bounded.encode("utf-8")), 64)

    def test_gandalf_worker_runs_work_off_the_initiating_thread(self):
        initiating_thread = threading.get_ident()
        work_threads = []
        callback_threads = []
        result = []

        def work():
            work_threads.append(threading.get_ident())
            return "catalog result"

        def callback(value, error):
            callback_threads.append(threading.get_ident())
            result.append((value, error))

        worker = start_gandalf_worker(work, callback, "gandalf-test-worker")
        worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [("catalog result", None)])
        self.assertEqual(len(work_threads), 1)
        self.assertEqual(work_threads, callback_threads)
        self.assertNotEqual(work_threads[0], initiating_thread)

    def test_opencode_farm_help_exposes_lifecycle_controls(self):
        result = run_tool("opencode_farm.py", "--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for command in ("start", "status", "drain", "resume", "stop"):
            self.assertIn(command, result.stdout)

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
