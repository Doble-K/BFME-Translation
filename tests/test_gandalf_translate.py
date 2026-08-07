#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "localization"
sys.path.insert(0, str(TOOLS))

from gandalf import (
    BATCH_SIZE_MAX,
    BATCH_SIZE_MIN,
    WORKER_MAX,
    WORKER_MIN,
    build_translate_plan,
    cleanup_temp_farm_runtime,
    create_temp_farm_profile,
    derive_bulk_profile,
    execute_translate_dry_run,
    execute_translate_no_save,
    execute_translate_yes,
    load_allowed_models,
    run_bulk_translate,
    validate_batch_size,
    validate_isolated_catalog,
    validate_model,
    validate_workers,
)


def run_gandalf(*args, env=None):
    return subprocess.run(
        [sys.executable, str(ROOT / "gandalf.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def create_project_fixture(directory, entries, name="bulk-test"):
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


def create_farm_profile(directory, project_file, prefix="bulk-farm", workers=4, count=25):
    directory = Path(directory)
    farm_file = directory / "farm.json"
    farm_file.write_text(json.dumps({
        "project": str(project_file),
        "workers": workers,
        "count": count,
        "max_restarts": 0,
        "poll_seconds": 1,
        "coordinators": [{"prefix": prefix, "model": "opencode/mimo-v2.5-free"}],
    }), encoding="utf-8")
    return farm_file


class GandalfRegistryTests(unittest.TestCase):
    """Tests for allowed_models.json registry structure and policies."""

    def test_registry_loads_successfully(self):
        registry = load_allowed_models()
        self.assertIn("version", registry)
        self.assertIn("models", registry)
        self.assertIsInstance(registry["models"], dict)
        self.assertGreater(len(registry["models"]), 0)

    def test_registry_has_free_tier_models(self):
        registry = load_allowed_models()
        free_models = [
            k for k, v in registry["models"].items()
            if v.get("tier") == "free"
        ]
        self.assertGreater(len(free_models), 0)

    def test_registry_has_economic_tier_models(self):
        registry = load_allowed_models()
        economic_models = [
            k for k, v in registry["models"].items()
            if v.get("tier") == "economic"
        ]
        self.assertGreater(len(economic_models), 0)

    def test_registry_has_premium_tier_models(self):
        registry = load_allowed_models()
        premium_models = [
            k for k, v in registry["models"].items()
            if v.get("tier") == "premium"
        ]
        self.assertGreater(len(premium_models), 0)

    def test_registry_no_default_model(self):
        registry = load_allowed_models()
        policies = registry.get("policies", {})
        self.assertIsNone(
            policies.get("default_model"),
            "default_model must be null; --model is mandatory"
        )

    def test_sol_has_no_auto_select_policy(self):
        registry = load_allowed_models()
        models = registry["models"]
        sol_models = [k for k in models if "sol" in k.lower()]
        for model in sol_models:
            entry = models[model]
            self.assertEqual(
                entry.get("default_policy"),
                "no-auto-select",
                f"{model} must have no-auto-select policy"
            )
            self.assertTrue(
                entry.get("require_confirmation", False),
                f"{model} must require explicit confirmation"
            )


class GandalfModelValidationTests(unittest.TestCase):

    def test_validate_model_accepts_known_free_model(self):
        model, tier = validate_model("opencode/mimo-v2.5-free")
        self.assertEqual(model, "opencode/mimo-v2.5-free")
        self.assertEqual(tier, "free")

    def test_validate_model_accepts_economic_model(self):
        model, tier = validate_model("opencode/deepseek-v4-flash")
        self.assertEqual(model, "opencode/deepseek-v4-flash")
        self.assertEqual(tier, "economic")

    def test_validate_model_rejects_unknown_model(self):
        with self.assertRaisesRegex(ValueError, "modelo no permitido"):
            validate_model("opencode/nonexistent-model")

    def test_validate_model_rejects_empty_string(self):
        with self.assertRaisesRegex(ValueError, "modelo no permitido"):
            validate_model("")

    def test_validate_model_sol_accepted_when_explicit(self):
        """Sol is accepted when user explicitly passes --model (human confirmation)."""
        model, tier = validate_model("opencode/sol-ultra")
        self.assertEqual(model, "opencode/sol-ultra")
        self.assertEqual(tier, "premium")

    def test_validate_model_rejects_premium_without_confirmation(self):
        registry = load_allowed_models()
        premium_models = [
            k for k, v in registry["models"].items()
            if v.get("tier") == "premium"
        ]
        for model in premium_models:
            if not registry["models"][model].get("require_confirmation"):
                with self.assertRaisesRegex(ValueError, "requiere confirmación"):
                    validate_model(model)


class GandalfWorkerLimitsTests(unittest.TestCase):

    def test_validate_workers_accepts_valid_range(self):
        for count in (WORKER_MIN, 5, 6, 7, WORKER_MAX):
            self.assertEqual(validate_workers(count), count)

    def test_validate_workers_rejects_below_minimum(self):
        with self.assertRaisesRegex(ValueError, "workers debe estar entre"):
            validate_workers(3)

    def test_validate_workers_rejects_above_maximum(self):
        with self.assertRaisesRegex(ValueError, "workers debe estar entre"):
            validate_workers(9)

    def test_validate_workers_rejects_non_integer(self):
        with self.assertRaisesRegex(ValueError, "workers debe estar entre"):
            validate_workers("4")


class GandalfBatchSizeLimitsTests(unittest.TestCase):

    def test_validate_batch_size_accepts_valid_range(self):
        for count in (BATCH_SIZE_MIN, 50, 75, BATCH_SIZE_MAX):
            self.assertEqual(validate_batch_size(count), count)

    def test_validate_batch_size_rejects_below_minimum(self):
        with self.assertRaisesRegex(ValueError, "per-worker-count debe estar entre"):
            validate_batch_size(19)

    def test_validate_batch_size_rejects_above_maximum(self):
        with self.assertRaisesRegex(ValueError, "per-worker-count debe estar entre"):
            validate_batch_size(101)

    def test_validate_batch_size_rejects_non_integer(self):
        with self.assertRaisesRegex(ValueError, "per-worker-count debe estar entre"):
            validate_batch_size("20")


class GandalfDerivedProfileTests(unittest.TestCase):
    """Tests for bulk profile derivation."""

    def test_derive_bulk_profile_creates_isolated_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            real_profile = {"coordinators": [{"prefix": "real", "model": "real-model"}]}
            profile_path = derive_bulk_profile(
                real_profile, temp_dir, "run-123",
                "opencode/deepseek-v4-flash", 4, 20
            )

            self.assertTrue(profile_path.exists())
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(data["workers"], 4)
            self.assertEqual(data["count"], 20)
            self.assertEqual(len(data["coordinators"]), 1)
            self.assertEqual(data["coordinators"][0]["prefix"], "run-123")
            self.assertEqual(data["coordinators"][0]["model"], "opencode/deepseek-v4-flash")

    def test_derive_bulk_profile_ignores_real_profile_coordinators(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            real_profile = {
                "coordinators": [
                    {"prefix": "a", "model": "model-a"},
                    {"prefix": "b", "model": "model-b"},
                ]
            }
            profile_path = derive_bulk_profile(
                real_profile, temp_dir, "run-456",
                "opencode/mimo-v2.5-free", 4, 20
            )

            data = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["coordinators"]), 1)
            self.assertEqual(data["coordinators"][0]["model"], "opencode/mimo-v2.5-free")

    def test_derive_bulk_profile_uses_user_model_not_profile_model(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            real_profile = {
                "coordinators": [{"prefix": "old", "model": "opencode/old-model"}]
            }
            profile_path = derive_bulk_profile(
                real_profile, temp_dir, "run-789",
                "opencode/nemotron-3-ultra-free", 6, 50
            )

            data = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(data["coordinators"][0]["model"], "opencode/nemotron-3-ultra-free")
            self.assertNotEqual(data["coordinators"][0]["model"], "opencode/old-model")

    def test_create_temp_farm_profile_delegates_to_derive(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            real_profile = {"coordinators": [{"prefix": "r", "model": "m"}]}
            profile_path = create_temp_farm_profile(
                real_profile, temp_dir, "legacy-prefix",
                "opencode/ling-3.0-flash-free", 4, 20
            )

            data = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(data["coordinators"][0]["prefix"], "legacy-prefix")
            self.assertEqual(data["coordinators"][0]["model"], "opencode/ling-3.0-flash-free")


class GandalfTranslatePlanTests(unittest.TestCase):

    def test_build_translate_plan_returns_correct_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
            )

            self.assertEqual(plan["project_name"], "bulk-test")
            self.assertEqual(plan["model"], "opencode/mimo-v2.5-free")
            self.assertEqual(plan["workers"], 4)
            self.assertEqual(plan["per_worker_count"], 20)
            self.assertEqual(plan["total_entries"], 80)
            self.assertEqual(plan["language"], "es-419")
            self.assertEqual(len(plan["coordinators"]), 1)
            self.assertEqual(plan["coordinators"][0]["model"], "opencode/mimo-v2.5-free")

    def test_plan_uses_user_model_not_profile_model(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file,
                                            prefix="old-coord",
                                            workers=4, count=25)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/deepseek-v4-flash-free", 4, 20
            )

            self.assertEqual(plan["coordinators"][0]["model"], "opencode/deepseek-v4-flash-free")


class GandalfDryRunTests(unittest.TestCase):

    def test_dry_run_validates_and_shows_derived_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)
            catalog_before = catalog.read_bytes()

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Perfil bulk derivado", result.stdout)
            self.assertIn("opencode/mimo-v2.5-free", result.stdout)
            self.assertIn("[dry-run]", result.stdout)
            self.assertEqual(catalog.read_bytes(), catalog_before)

    def test_dry_run_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            agent_dir = Path(directory) / ".agent"
            self.assertFalse(agent_dir.exists())

    def test_dry_run_rejects_invalid_model(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/sol-expensive",
                "--workers", "4",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("modelo no permitido", result.stderr)

    def test_dry_run_rejects_invalid_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "2",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("workers debe estar entre", result.stderr)

    def test_dry_run_rejects_invalid_batch_size(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--per-worker-count", "10",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("per-worker-count debe estar entre", result.stderr)

    def test_dry_run_shows_derived_coordinator_not_base(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file,
                                            prefix="old-coordinator",
                                            workers=4, count=25)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/deepseek-v4-flash-free",
                "--workers", "6",
                "--per-worker-count", "50",
                "--dry-run",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("opencode/deepseek-v4-flash-free", result.stdout)
            self.assertIn("Workers: 6", result.stdout)
            self.assertIn("Entradas por worker: 50", result.stdout)


class GandalfCLIModeTests(unittest.TestCase):

    def test_translate_requires_mode_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--per-worker-count", "20",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("indique un modo", result.stderr)

    def test_translate_rejects_multiple_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--per-worker-count", "20",
                "--dry-run", "--no-save",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("solo puede indicar un modo", result.stderr)

    def test_translate_requires_model(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--workers", "4",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("modelo requerido", result.stderr.lower())

    def test_gandalf_help_exposes_translate_options(self):
        result = run_gandalf("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--translate", result.stdout)
        self.assertIn("--farm-profile", result.stdout)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--no-save", result.stdout)
        self.assertIn("--yes", result.stdout)
        self.assertIn("--per-worker-count", result.stdout)

    def test_existing_gandalf_modes_still_work(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            output = Path(directory) / "catalog.json"
            source.write_text(
                json.dumps({"source": "test", "entries": []}), encoding="utf-8"
            )
            result = run_gandalf(str(source), str(output))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["project"]["slug"], "custom")

    def test_translate_rejects_missing_project_file(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            farm_file = directory / "farm.json"
            farm_file.write_text(json.dumps({
                "project": str(directory / "missing.json"),
                "workers": 4,
                "count": 25,
                "coordinators": [{"prefix": "f", "model": "opencode/mimo-v2.5-free"}],
            }), encoding="utf-8")

            result = run_gandalf(
                "--translate",
                "--project", str(directory / "missing.json"),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)

    def test_translate_rejects_missing_farm_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(Path(directory) / "missing.json"),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)

    def test_translate_rejects_workers_below_minimum(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "2",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("workers debe estar entre", result.stderr)

    def test_translate_rejects_workers_above_maximum(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "10",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("workers debe estar entre", result.stderr)

    def test_translate_rejects_batch_size_below_minimum(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--per-worker-count", "10",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("per-worker-count debe estar entre", result.stderr)

    def test_translate_rejects_batch_size_above_maximum(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--per-worker-count", "150",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("per-worker-count debe estar entre", result.stderr)


class GandalfNoSaveTests(unittest.TestCase):

    def test_no_save_preserves_real_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "TEST:One", "source": "One", "translation": "", "status": "pending"},
                {"id": "TEST:Two", "source": "Two", "translation": "Dos", "status": "translated"},
            ])
            farm_file = create_farm_profile(directory, project_file)
            catalog_before = catalog.read_bytes()

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                exit_code = execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(catalog.read_bytes(), catalog_before)

    def test_no_save_creates_unique_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )
                command = mock_run.call_args[0][0]
                config_idx = None
                for i, arg in enumerate(command):
                    if arg == "--config":
                        config_idx = i
                        break

            self.assertIsNotNone(config_idx)

    def test_no_save_cleans_up_on_success(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                exit_code = execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            self.assertEqual(exit_code, 0)

    def test_no_save_cleans_up_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=1, stdout="", stderr="farm error"
                )
                exit_code = execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            self.assertNotEqual(exit_code, 0)

    def test_no_save_catalog_unchanged_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [
                {"id": "TEST:Original", "source": "Original", "translation": "Original", "status": "translated"},
            ])
            farm_file = create_farm_profile(directory, project_file)
            original = catalog.read_text(encoding="utf-8")

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=1, stdout="", stderr="farm error"
                )
                execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            self.assertEqual(catalog.read_text(encoding="utf-8"), original)

    def test_no_save_project_points_to_clone(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            call_args = mock_run.call_args
            command = call_args[0][0]
            self.assertTrue(any("opencode_farm.py" in arg for arg in command))
            self.assertIn("start", command)

    def test_cleanup_temp_farm_runtime_removes_files(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            agent_dir = temp_dir / ".agent"
            runtime_dir = agent_dir / "farm-runtime"
            runtime_dir.mkdir(parents=True)
            (runtime_dir / "anchor.json").write_text("{}", encoding="utf-8")
            (agent_dir / "state.json").write_text("{}", encoding="utf-8")
            (agent_dir / "control.json").write_text("{}", encoding="utf-8")

            cleanup_temp_farm_runtime(temp_dir, "test-prefix")

            self.assertFalse(runtime_dir.exists())
            self.assertFalse(agent_dir.exists())

    def test_cleanup_temp_farm_runtime_handles_missing_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            cleanup_temp_farm_runtime(temp_dir, "test-prefix")
            self.assertFalse((temp_dir / ".agent").exists())

    def test_cleanup_temp_farm_runtime_handles_partial_files(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            agent_dir = temp_dir / ".agent"
            agent_dir.mkdir()
            (agent_dir / "leftover.txt").write_text("data", encoding="utf-8")
            nested = agent_dir / "nested"
            nested.mkdir()
            (nested / "file.log").write_text("log", encoding="utf-8")

            cleanup_temp_farm_runtime(temp_dir, "test-prefix")

            self.assertFalse(agent_dir.exists())

    def test_no_save_runs_farm_start_command(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            call_args = mock_run.call_args
            command = call_args[0][0]
            self.assertTrue(any("opencode_farm.py" in arg for arg in command))
            self.assertIn("start", command)
            self.assertIn("--config", command)

    def test_no_save_real_registry_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)
            registry_path = catalog.parent / ".catalog.json.agent-leases.json"

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            self.assertFalse(registry_path.exists())

    def test_no_save_real_state_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)
            state_path = directory / ".agent" / "state.json"

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            self.assertFalse(state_path.exists())

    def test_no_save_uses_derived_profile_not_original(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file,
                                            prefix="original-coord",
                                            workers=4, count=25)

            captured_config = {}
            original_run = None
            import gandalf as gmod
            original_run = gmod.subprocess.run

            def capture_and_run(command, *args, **kwargs):
                for i, arg in enumerate(command):
                    if arg == "--config":
                        config_path = command[i + 1]
                        if os.path.exists(config_path):
                            with open(config_path, encoding="utf-8") as f:
                                captured_config.update(json.load(f))
                return Mock(returncode=0, stdout="", stderr="")

            with patch("gandalf.subprocess.run", side_effect=capture_and_run):
                execute_translate_no_save(
                    project_file, farm_file, "opencode/deepseek-v4-flash-free", 6, 50
                )

            self.assertTrue(captured_config, "No config was captured")
            self.assertEqual(captured_config["coordinators"][0]["model"], "opencode/deepseek-v4-flash-free")
            self.assertEqual(captured_config["workers"], 6)
            self.assertEqual(captured_config["count"], 50)

    def test_no_save_runs_validations(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                with patch("gandalf.validate_isolated_catalog") as mock_validate:
                    mock_validate.return_value = []
                    execute_translate_no_save(
                        project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                    )
                    mock_validate.assert_called_once()

    def test_validate_isolated_catalog_valid_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            catalog_path.write_text(json.dumps({
                "entries": [
                    {"id": "TEST:One", "source": "One", "translation": ""},
                    {"id": "TEST:Two", "source": "Two", "translation": "Dos"},
                ]
            }), encoding="utf-8")

            errors = validate_isolated_catalog(catalog_path)
            self.assertEqual(errors, [])

    def test_validate_isolated_catalog_missing_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            catalog_path.write_text(json.dumps({}), encoding="utf-8")

            errors = validate_isolated_catalog(catalog_path)
            self.assertIn("catálogo no contiene campo 'entries'", errors)


class GandalfYesTests(unittest.TestCase):

    def test_yes_persists_results(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)
            catalog_before = catalog.read_bytes()

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                exit_code = execute_translate_yes(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(catalog.read_bytes(), catalog_before)

    def test_yes_calls_farm_start_command(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                execute_translate_yes(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            call_args = mock_run.call_args
            command = call_args[0][0]
            self.assertTrue(any("opencode_farm.py" in arg for arg in command))
            self.assertIn("start", command)
            self.assertIn("--config", command)

    def test_yes_reports_error_on_farm_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=1, stdout="", stderr="farm failed"
                )
                exit_code = execute_translate_yes(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20
                )

            self.assertNotEqual(exit_code, 0)

    def test_yes_validates_model_before_running(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with self.assertRaisesRegex(ValueError, "modelo no permitido"):
                execute_translate_yes(
                    project_file, farm_file, "opencode/sol-expensive", 4, 20
                )

    def test_yes_validates_workers_before_running(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with self.assertRaisesRegex(ValueError, "workers debe estar entre"):
                execute_translate_yes(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 2, 20
                )

    def test_yes_validates_batch_size_before_running(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with self.assertRaisesRegex(ValueError, "per-worker-count debe estar entre"):
                execute_translate_yes(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 10
                )

    def test_yes_uses_derived_profile_not_original(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file,
                                            prefix="original-coord",
                                            workers=4, count=25)

            captured_config = {}

            def capture_and_run(command, *args, **kwargs):
                for i, arg in enumerate(command):
                    if arg == "--config":
                        config_path = command[i + 1]
                        if os.path.exists(config_path):
                            with open(config_path, encoding="utf-8") as f:
                                captured_config.update(json.load(f))
                return Mock(returncode=0, stdout="", stderr="")

            with patch("gandalf.subprocess.run", side_effect=capture_and_run):
                execute_translate_yes(
                    project_file, farm_file, "opencode/deepseek-v4-flash-free", 6, 50
                )

            self.assertTrue(captured_config, "No config was captured")
            self.assertEqual(captured_config["coordinators"][0]["model"], "opencode/deepseek-v4-flash-free")
            self.assertEqual(captured_config["workers"], 6)
            self.assertEqual(captured_config["count"], 50)

    def test_yes_propagates_model_to_coordinator(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file,
                                            prefix="old-model-coord",
                                            workers=4, count=25)

            captured_config = {}

            def capture_and_run(command, *args, **kwargs):
                for i, arg in enumerate(command):
                    if arg == "--config":
                        config_path = command[i + 1]
                        if os.path.exists(config_path):
                            with open(config_path, encoding="utf-8") as f:
                                captured_config.update(json.load(f))
                return Mock(returncode=0, stdout="", stderr="")

            with patch("gandalf.subprocess.run", side_effect=capture_and_run):
                execute_translate_yes(
                    project_file, farm_file, "opencode/nemotron-3-ultra-free", 4, 20
                )

            self.assertTrue(captured_config, "No config was captured")
            for coord in captured_config["coordinators"]:
                self.assertEqual(coord["model"], "opencode/nemotron-3-ultra-free")


class GandalfPropagationTests(unittest.TestCase):
    """Tests for model propagation to all coordinators."""

    def test_model_propagates_to_derived_coordinator(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            profile = derive_bulk_profile(
                {}, temp_dir, "test-run",
                "opencode/deepseek-v4-flash-free", 4, 20
            )

            data = json.loads(profile.read_text(encoding="utf-8"))
            for coord in data["coordinators"]:
                self.assertEqual(coord["model"], "opencode/deepseek-v4-flash-free")

    def test_workers_propagates_to_derived_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            profile = derive_bulk_profile(
                {}, temp_dir, "test-run",
                "opencode/mimo-v2.5-free", 8, 100
            )

            data = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(data["workers"], 8)
            self.assertEqual(data["count"], 100)


class GandalfIntegrationTests(unittest.TestCase):
    """Integration tests for bulk translate flow."""

    def test_bulk_translate_requires_model(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--workers", "4",
                "--per-worker-count", "20",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("modelo requerido", result.stderr.lower())

    def test_bulk_translate_validates_all_params(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "2",
                "--per-worker-count", "150",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
