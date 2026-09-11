#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "localization"
sys.path.insert(0, str(TOOLS))

from project import (
    DEFAULT_GLOSSARY,
    load_project,
    resolve_glossary_path,
    resolve_project_path,
)


def create_project_file(directory, overrides=None):
    directory = Path(directory)
    data = {
        "name": "test-project",
        "source_archive": str(directory / "source.big"),
        "string_directory": str(directory),
        "string_files": ["data/lotr.str"],
        "catalog": str(directory / "catalog.json"),
        "output_string_file": str(directory / "output.str"),
        "output_package": str(directory / "output.big"),
        "language": "es-419",
        "encoding": "cp1252",
    }
    if overrides:
        data.update(overrides)
    project_file = directory / "project.json"
    project_file.write_text(json.dumps(data), encoding="utf-8")
    return project_file


class ProjectGlossarySelectionTests(unittest.TestCase):
    """Tests for optional project-level glossary resolution."""

    def test_resolve_glossary_falls_back_to_root_when_no_field(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_file = create_project_file(directory)
            project = load_project(project_file)
            result = resolve_glossary_path(project)
            self.assertEqual(result, DEFAULT_GLOSSARY)

    def test_resolve_glossary_uses_project_field_when_present(self):
        """Glossary path is resolved relative to the project ROOT."""
        # Place the file at ROOT so ROOT / "custom_glossary.md" resolves
        glossary = ROOT / "custom_glossary.md"
        glossary.write_text("# Custom Glossary", encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                directory = Path(tmpdir)
                project_file = create_project_file(directory, {"glossary": "custom_glossary.md"})
                project = load_project(project_file)
                result = resolve_glossary_path(project)
                self.assertEqual(result, glossary)
        finally:
            glossary.unlink(missing_ok=True)

    def test_resolve_glossary_falls_back_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_file = create_project_file(directory, {"glossary": "nonexistent.md"})
            project = load_project(project_file)
            result = resolve_glossary_path(project)
            self.assertEqual(result, DEFAULT_GLOSSARY)

    def test_resolve_glossary_accepts_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            glossary = directory / "abs_glossary.md"
            glossary.write_text("# Absolute Glossary", encoding="utf-8")
            project_file = create_project_file(directory, {
                "glossary": str(glossary),
            })
            project = load_project(project_file)
            result = resolve_glossary_path(project)
            self.assertEqual(result, glossary)

    def test_load_project_accepts_glossary_field(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_file = create_project_file(directory, {"glossary": "my_glossary.md"})
            project = load_project(project_file)
            self.assertEqual(project["glossary"], "my_glossary.md")

    def test_load_project_rejects_non_string_glossary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_file = create_project_file(directory, {"glossary": 123})
            with self.assertRaisesRegex(ValueError, "glossary"):
                load_project(project_file)

    def test_project_without_glossary_field_has_no_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_file = create_project_file(directory)
            project = load_project(project_file)
            self.assertNotIn("glossary", project)


class ProjectEsESConfigTests(unittest.TestCase):
    """Tests for es-ES project configuration structure."""

    def test_es_es_config_exists_and_is_valid(self):
        config_path = ROOT / "config" / "project_es-ES.json"
        self.assertTrue(config_path.exists(), "es-ES project config should exist")
        project = load_project(config_path)
        self.assertEqual(project["language"], "es-ES")
        self.assertIn("es-ES", project["catalog"])
        self.assertIn("es-ES", project["output_package"])

    def test_active_project_json_is_es_es(self):
        """config/project.json (the active default) must be es-ES."""
        project = load_project(ROOT / "config" / "project.json")
        self.assertEqual(project["language"], "es-ES")
        self.assertEqual(project["glossary"], "glossaries/es-ES.glossary.md")
        self.assertIn("es-ES", project["catalog"])
        self.assertIn("es-ES", project["output_package"])
        self.assertIn("es-ES", project["string_directory"])

    def test_es419_config_exists_and_is_valid(self):
        """config/project_es-419.json must exist and be es-419."""
        config_path = ROOT / "config" / "project_es-419.json"
        self.assertTrue(config_path.exists(), "es-419 project config should exist")
        project = load_project(config_path)
        self.assertEqual(project["language"], "es-419")
        self.assertEqual(project["glossary"], "GLOSSARY.md")
        self.assertNotIn("es-ES", project["catalog"])
        self.assertNotIn("es-ES", project["output_package"])

    def test_active_project_and_es419_have_distinct_paths(self):
        """The active es-ES config and the preserved es-419 config must use distinct paths."""
        es_es = load_project(ROOT / "config" / "project.json")
        es419 = load_project(ROOT / "config" / "project_es-419.json")
        self.assertNotEqual(es_es["language"], es419["language"])
        self.assertNotEqual(es_es["catalog"], es419["catalog"])
        self.assertNotEqual(es_es["output_package"], es419["output_package"])
        self.assertNotEqual(es_es["string_directory"], es419["string_directory"])
        self.assertNotEqual(es_es["output_string_file"], es419["output_string_file"])
        self.assertNotEqual(es_es["glossary"], es419["glossary"])

    def test_es_es_config_has_separate_paths_from_es419(self):
        es419 = load_project(ROOT / "config" / "project_es-419.json")
        es_es = load_project(ROOT / "config" / "project.json")
        self.assertNotEqual(es419["catalog"], es_es["catalog"])
        self.assertNotEqual(es419["output_package"], es_es["output_package"])
        self.assertNotEqual(es419["string_directory"], es_es["string_directory"])

    def test_es419_config_unchanged(self):
        project = load_project(ROOT / "config" / "project_es-419.json")
        self.assertEqual(project["language"], "es-419")
        self.assertEqual(project["name"], "bfme2-rotwk-2.02")
        self.assertEqual(
            resolve_project_path(project, "output_package"),
            ROOT / "releases" / "spanishpatch202.big",
        )

    def test_es_es_config_shares_engine_settings(self):
        es419 = load_project(ROOT / "config" / "project_es-419.json")
        es_es = load_project(ROOT / "config" / "project.json")
        self.assertEqual(es419["encoding"], es_es["encoding"])
        self.assertEqual(es419["string_files"], es_es["string_files"])
        self.assertEqual(es419["string_header"], es_es["string_header"])
        self.assertEqual(es419["debug_ids"], es_es["debug_ids"])
        self.assertEqual(es419["debug_marker"], es_es["debug_marker"])


class DualLocaleGlossaryPathTests(unittest.TestCase):
    """Tests that each locale resolves to the correct glossary file."""

    def test_es419_resolves_to_root_glossary(self):
        project = load_project(ROOT / "config" / "project_es-419.json")
        self.assertEqual(project.get("glossary"), "GLOSSARY.md")
        resolved = resolve_glossary_path(project)
        self.assertEqual(resolved, ROOT / "GLOSSARY.md")
        self.assertTrue(resolved.is_file(), "root GLOSSARY.md should exist")

    def test_es_es_resolves_to_locale_glossary(self):
        project = load_project(ROOT / "config" / "project.json")
        self.assertEqual(project.get("glossary"), "glossaries/es-ES.glossary.md")
        resolved = resolve_glossary_path(project)
        self.assertEqual(resolved, ROOT / "glossaries" / "es-ES.glossary.md")
        self.assertTrue(resolved.is_file(), "es-ES glossary should exist")

    def test_locales_use_different_glossaries(self):
        es419_project = load_project(ROOT / "config" / "project_es-419.json")
        es_es_project = load_project(ROOT / "config" / "project.json")
        es419_glossary = resolve_glossary_path(es419_project)
        es_es_glossary = resolve_glossary_path(es_es_project)
        self.assertNotEqual(es419_glossary, es_es_glossary)

    def test_opencode_farm_references_es_es_project(self):
        farm_path = ROOT / "config" / "opencode_farm.json"
        self.assertTrue(farm_path.exists(), "opencode_farm.json should exist")
        farm_config = json.loads(farm_path.read_text(encoding="utf-8"))
        self.assertEqual(farm_config["project"], "config/project.json")
        referenced_project = load_project(ROOT / farm_config["project"])
        self.assertEqual(referenced_project["language"], "es-ES")


class GandalfLanguageDetectionTests(unittest.TestCase):
    """Tests for Gandalf language detection with es-ES support."""

    def test_detect_language_es_es_from_filename(self):
        from gandalf import detect_language
        from pathlib import Path

        self.assertEqual(detect_language(Path("castilian_patch.big")), "es-ES")
        self.assertEqual(detect_language(Path("castellano.big")), "es-ES")

    def test_detect_language_es419_from_filename(self):
        from gandalf import detect_language
        from pathlib import Path

        self.assertEqual(detect_language(Path("spanish_patch.big")), "es-419")
        self.assertEqual(detect_language(Path("español.big")), "es-419")

    def test_choose_language_includes_es_es(self):
        from gandalf import choose_language
        import io
        from unittest.mock import patch

        with patch("builtins.input", return_value="2"):
            result = choose_language("de destino", "es-419")
            self.assertEqual(result, "es-ES")

    def test_choose_language_includes_es419(self):
        from gandalf import choose_language
        from unittest.mock import patch

        with patch("builtins.input", return_value="1"):
            result = choose_language("de destino", "es-419")
            self.assertEqual(result, "es-419")


if __name__ == "__main__":
    unittest.main()
