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
    get_tier_models,
    list_models_by_tier,
    load_allowed_models,
    resolve_quantity,
    run_bulk_translate,
    validate_batch_size,
    validate_isolated_catalog,
    validate_model,
    validate_total_entries,
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

    def test_validate_model_accepts_opencode_go_economic_model(self):
        model, tier = validate_model("opencode-go/deepseek-v4-flash")
        self.assertEqual(model, "opencode-go/deepseek-v4-flash")
        self.assertEqual(tier, "economic")

    def test_validate_model_rejects_unknown_model(self):
        with self.assertRaisesRegex(ValueError, "modelo no permitido"):
            validate_model("opencode/nonexistent-model")

    def test_validate_model_rejects_empty_string(self):
        with self.assertRaisesRegex(ValueError, "modelo no permitido"):
            validate_model("")

    def test_validate_model_rejects_none(self):
        with self.assertRaisesRegex(ValueError, "modelo no permitido"):
            validate_model(None)

    def test_validate_model_sol_rejected_without_confirmed(self):
        """Premium model with require_confirmation is rejected by default."""
        with self.assertRaisesRegex(ValueError, "requiere confirmación"):
            validate_model("opencode/sol-ultra")

    def test_validate_model_sol_accepted_with_confirmed(self):
        """Sol is accepted when confirmed=True (explicit user confirmation)."""
        model, tier = validate_model("opencode/sol-ultra", confirmed=True)
        self.assertEqual(model, "opencode/sol-ultra")
        self.assertEqual(tier, "premium")

    def test_validate_model_free_ignores_confirmed_flag(self):
        """Free models are accepted regardless of confirmed flag."""
        model1, tier1 = validate_model("opencode/mimo-v2.5-free", confirmed=False)
        model2, tier2 = validate_model("opencode/mimo-v2.5-free", confirmed=True)
        self.assertEqual((model1, tier1), ("opencode/mimo-v2.5-free", "free"))
        self.assertEqual((model2, tier2), ("opencode/mimo-v2.5-free", "free"))

    def test_validate_model_economic_ignores_confirmed_flag(self):
        """Economic models are accepted regardless of confirmed flag."""
        model1, tier1 = validate_model("opencode/deepseek-v4-flash", confirmed=False)
        model2, tier2 = validate_model("opencode/deepseek-v4-flash", confirmed=True)
        self.assertEqual((model1, tier1), ("opencode/deepseek-v4-flash", "economic"))
        self.assertEqual((model2, tier2), ("opencode/deepseek-v4-flash", "economic"))

    def test_validate_model_rejects_premium_without_confirmation(self):
        registry = load_allowed_models()
        premium_models = [
            k for k, v in registry["models"].items()
            if v.get("tier") == "premium"
        ]
        self.assertGreater(len(premium_models), 0, "registry must have premium models")
        for model in premium_models:
            with self.assertRaisesRegex(ValueError, "requiere confirmación"):
                validate_model(model)

    def test_validate_model_accepts_premium_with_confirmed(self):
        """All premium models are accepted when confirmed=True."""
        registry = load_allowed_models()
        premium_models = [
            k for k, v in registry["models"].items()
            if v.get("tier") == "premium"
        ]
        for model in premium_models:
            result_model, result_tier = validate_model(model, confirmed=True)
            self.assertEqual(result_model, model)
            self.assertEqual(result_tier, "premium")


class GandalfTierQueryTests(unittest.TestCase):
    """Tests for deterministic tier-based model querying."""

    def test_list_models_by_tier_returns_all_tiers(self):
        grouped = list_models_by_tier()
        self.assertIn("free", grouped)
        self.assertIn("economic", grouped)
        self.assertIn("premium", grouped)

    def test_list_models_by_tier_tiers_are_sorted_lists(self):
        grouped = list_models_by_tier()
        for tier, models in grouped.items():
            self.assertIsInstance(models, list)
            self.assertEqual(models, sorted(models), f"tier {tier} not sorted")

    def test_list_models_by_tier_deterministic_order(self):
        """Calling twice returns the same structure."""
        first = list_models_by_tier()
        second = list_models_by_tier()
        self.assertEqual(first, second)

    def test_list_models_by_tier_free_tier_has_models(self):
        grouped = list_models_by_tier()
        self.assertGreater(len(grouped["free"]), 0)

    def test_list_models_by_tier_economic_tier_has_models(self):
        grouped = list_models_by_tier()
        self.assertGreater(len(grouped["economic"]), 0)

    def test_list_models_by_tier_premium_tier_has_models(self):
        grouped = list_models_by_tier()
        self.assertGreater(len(grouped["premium"]), 0)

    def test_list_models_by_tier_all_registry_models_appear(self):
        registry = load_allowed_models()
        grouped = list_models_by_tier()
        all_grouped = set()
        for models in grouped.values():
            all_grouped.update(models)
        all_registry = set(registry["models"].keys())
        self.assertEqual(all_grouped, all_registry)

    def test_list_models_by_tier_sol_in_premium(self):
        grouped = list_models_by_tier()
        self.assertIn("opencode/sol-ultra", grouped["premium"])

    def test_list_models_by_tier_mimo_free_in_free(self):
        grouped = list_models_by_tier()
        self.assertIn("opencode/mimo-v2.5-free", grouped["free"])

    def test_get_tier_models_returns_free(self):
        models = get_tier_models("free")
        self.assertIsInstance(models, list)
        self.assertIn("opencode/mimo-v2.5-free", models)
        self.assertEqual(models, sorted(models))

    def test_get_tier_models_returns_economic(self):
        models = get_tier_models("economic")
        self.assertIsInstance(models, list)
        self.assertIn("opencode/deepseek-v4-flash", models)
        self.assertEqual(models, sorted(models))

    def test_get_tier_models_returns_premium(self):
        models = get_tier_models("premium")
        self.assertIsInstance(models, list)
        self.assertIn("opencode/sol-ultra", models)
        self.assertEqual(models, sorted(models))

    def test_get_tier_models_rejects_unknown_tier(self):
        with self.assertRaisesRegex(ValueError, "tier no válido"):
            get_tier_models("unknown")

    def test_get_tier_models_rejects_empty_string(self):
        with self.assertRaisesRegex(ValueError, "tier no válido"):
            get_tier_models("")

    def test_get_tier_models_matches_list_models_by_tier(self):
        """get_tier_models(tier) returns the same list as list_models_by_tier()[tier]."""
        grouped = list_models_by_tier()
        for tier in ("free", "economic", "premium"):
            self.assertEqual(get_tier_models(tier), grouped[tier])


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
            validate_batch_size(0)

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
                "--per-worker-count", "0",
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
                "--per-worker-count", "0",
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
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 0
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


class GandalfTotalEntriesValidationTests(unittest.TestCase):
    """Tests for validate_total_entries."""

    def test_validate_total_entries_accepts_minimum(self):
        self.assertEqual(validate_total_entries(BATCH_SIZE_MIN), BATCH_SIZE_MIN)

    def test_validate_total_entries_accepts_maximum(self):
        self.assertEqual(validate_total_entries(BATCH_SIZE_MAX), BATCH_SIZE_MAX)

    def test_validate_total_entries_accepts_midrange(self):
        self.assertEqual(validate_total_entries(50), 50)

    def test_validate_total_entries_rejects_below_minimum(self):
        with self.assertRaisesRegex(ValueError, "total-entries debe estar entre"):
            validate_total_entries(0)

    def test_validate_total_entries_rejects_above_maximum(self):
        with self.assertRaisesRegex(ValueError, "total-entries debe estar entre"):
            validate_total_entries(101)

    def test_validate_total_entries_rejects_non_integer(self):
        with self.assertRaisesRegex(ValueError, "total-entries debe estar entre"):
            validate_total_entries("50")

    def test_validate_total_entries_rejects_zero(self):
        with self.assertRaisesRegex(ValueError, "total-entries debe estar entre"):
            validate_total_entries(0)

    def test_validate_total_entries_rejects_negative(self):
        with self.assertRaisesRegex(ValueError, "total-entries debe estar entre"):
            validate_total_entries(-10)


class GandalfResolveQuantityTests(unittest.TestCase):
    """Tests for resolve_quantity function."""

    def test_resolve_quantity_per_worker_count_mode(self):
        result = resolve_quantity(workers=4, per_worker_count=20)
        self.assertEqual(result["total_entries"], 80)
        self.assertEqual(result["per_worker_count"], 20)
        self.assertIsNone(result["requested_total"])
        self.assertFalse(result["full_catalog"])

    def test_resolve_quantity_total_entries_mode(self):
        result = resolve_quantity(workers=4, total_entries=50)
        self.assertEqual(result["total_entries"], 50)
        self.assertEqual(result["per_worker_count"], 13)  # ceil(50/4) = 13
        self.assertEqual(result["requested_total"], 50)
        self.assertFalse(result["full_catalog"])

    def test_resolve_quantity_total_entries_exact_division(self):
        result = resolve_quantity(workers=4, total_entries=80)
        self.assertEqual(result["total_entries"], 80)
        self.assertEqual(result["per_worker_count"], 20)

    def test_resolve_quantity_total_entries_minimum(self):
        result = resolve_quantity(workers=4, total_entries=20)
        self.assertEqual(result["total_entries"], 20)
        self.assertEqual(result["per_worker_count"], 5)

    def test_resolve_quantity_total_entries_maximum(self):
        result = resolve_quantity(workers=8, total_entries=100)
        self.assertEqual(result["total_entries"], 100)
        self.assertEqual(result["per_worker_count"], 13)

    def test_resolve_quantity_rejects_no_mode(self):
        with self.assertRaisesRegex(ValueError, "indique exactamente uno"):
            resolve_quantity(workers=4)

    def test_resolve_quantity_rejects_multiple_modes(self):
        with self.assertRaisesRegex(ValueError, "indique exactamente uno"):
            resolve_quantity(workers=4, per_worker_count=20, total_entries=50)

    def test_resolve_quantity_rejects_per_worker_and_full_catalog(self):
        with self.assertRaisesRegex(ValueError, "indique exactamente uno"):
            resolve_quantity(workers=4, per_worker_count=20, full_catalog=True)

    def test_resolve_quantity_full_catalog_requires_path(self):
        with self.assertRaisesRegex(ValueError, "full-catalog requiere la ruta"):
            resolve_quantity(workers=4, full_catalog=True)

    def test_resolve_quantity_full_catalog_reads_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            catalog_path.write_text(json.dumps({
                "entries": [
                    {"id": "A", "status": "pending"},
                    {"id": "B", "status": "translated"},
                    {"id": "C", "status": "pending"},
                    {"id": "D", "status": "preserved"},
                    {"id": "E", "status": "pending"},
                ]
            }), encoding="utf-8")

            result = resolve_quantity(
                workers=4, full_catalog=True, catalog_path=catalog_path,
            )
            self.assertEqual(result["total_entries"], 3)  # 3 pending
            self.assertEqual(result["per_worker_count"], 1)  # ceil(3/4) = 1
            self.assertTrue(result["full_catalog"])
            self.assertIsNone(result["requested_total"])

    def test_resolve_quantity_full_catalog_no_pending_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            catalog_path.write_text(json.dumps({
                "entries": [
                    {"id": "A", "status": "translated"},
                    {"id": "B", "status": "preserved"},
                ]
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "no contiene entradas pendientes"):
                resolve_quantity(
                    workers=4, full_catalog=True, catalog_path=catalog_path,
                )

    def test_resolve_quantity_full_catalog_unreadable_raises(self):
        with self.assertRaisesRegex(ValueError, "no se pudo leer el catálogo"):
            resolve_quantity(
                workers=4, full_catalog=True,
                catalog_path=Path("/nonexistent/catalog.json"),
            )

    def test_resolve_quantity_total_entries_invalid_rejects(self):
        with self.assertRaisesRegex(ValueError, "total-entries debe estar entre"):
            resolve_quantity(workers=4, total_entries=0)


class GandalfQuantityPlannerPlanTests(unittest.TestCase):
    """Tests for plan structure with new quantity modes."""

    def test_plan_with_total_entries_has_requested_total(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                total_entries=50,
            )

            self.assertEqual(plan["requested_total"], 50)
            self.assertEqual(plan["total_entries"], 50)
            self.assertEqual(plan["per_worker_count"], 13)
            self.assertFalse(plan["full_catalog"])

    def test_plan_with_full_catalog_has_full_catalog_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = [
                {"id": f"TEST:Entry{i}", "source": f"Source{i}",
                 "translation": "", "status": "pending"}
                for i in range(10)
            ]
            project_file, _catalog = create_project_fixture(directory, entries)

            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                full_catalog=True,
            )

            self.assertTrue(plan["full_catalog"])
            self.assertEqual(plan["total_entries"], 10)
            self.assertEqual(plan["per_worker_count"], 3)  # ceil(10/4) = 3
            self.assertIsNone(plan["requested_total"])

    def test_plan_legacy_mode_has_no_requested_total(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20,
            )

            self.assertIsNone(plan["requested_total"])
            self.assertFalse(plan["full_catalog"])
            self.assertEqual(plan["total_entries"], 80)
            self.assertEqual(plan["per_worker_count"], 20)

    def test_plan_separates_total_from_distribution(self):
        """Verify total_entries and per_worker_count are clearly distinct."""
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                total_entries=30,
            )

            # total_entries is what was requested
            self.assertEqual(plan["total_entries"], 30)
            # per_worker_count is the distribution (ceil(30/4) = 8)
            self.assertEqual(plan["per_worker_count"], 8)
            # requested_total tracks the original request
            self.assertEqual(plan["requested_total"], 30)
            # They are different values
            self.assertNotEqual(plan["total_entries"], plan["per_worker_count"])

    def test_plan_total_entries_boundary_20(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                total_entries=20,
            )

            self.assertEqual(plan["total_entries"], 20)
            self.assertEqual(plan["per_worker_count"], 5)

    def test_plan_total_entries_boundary_100(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                total_entries=100,
            )

            self.assertEqual(plan["total_entries"], 100)
            self.assertEqual(plan["per_worker_count"], 25)

    def test_plan_total_entries_rejects_0(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with self.assertRaisesRegex(ValueError, "total-entries debe estar entre"):
                build_translate_plan(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                    total_entries=0,
                )

    def test_plan_total_entries_rejects_101(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with self.assertRaisesRegex(ValueError, "total-entries debe estar entre"):
                build_translate_plan(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                    total_entries=101,
                )

    def test_plan_rejects_multiple_quantity_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with self.assertRaisesRegex(ValueError, "indique exactamente uno"):
                build_translate_plan(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 20,
                    total_entries=50,
                )


class GandalfQuantityPlannerCLITests(unittest.TestCase):
    """CLI tests for --total-entries and --full-catalog options."""

    def test_help_exposes_new_options(self):
        result = run_gandalf("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--total-entries", result.stdout)
        self.assertIn("--full-catalog", result.stdout)

    def test_dry_run_with_total_entries(self):
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
                "--total-entries", "50",
                "--dry-run",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Entradas solicitadas: 50", result.stdout)
            self.assertIn("Capacidad total: 50", result.stdout)

    def test_dry_run_with_full_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = [
                {"id": f"TEST:Entry{i}", "source": f"Source{i}",
                 "translation": "", "status": "pending"}
                for i in range(8)
            ]
            project_file, _catalog = create_project_fixture(directory, entries)
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--full-catalog",
                "--dry-run",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("full-catalog", result.stdout)
            self.assertIn("Capacidad total: 8", result.stdout)

    def test_rejects_multiple_quantity_options(self):
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
                "--total-entries", "50",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("solo puede indicar uno de", result.stderr)

    def test_total_entries_invalid_below_minimum(self):
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
                "--total-entries", "0",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("total-entries debe estar entre", result.stderr)

    def test_total_entries_invalid_above_maximum(self):
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
                "--total-entries", "150",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("total-entries debe estar entre", result.stderr)

    def test_full_catalog_no_pending_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = [
                {"id": "TEST:One", "source": "One",
                 "translation": "Uno", "status": "translated"},
            ]
            project_file, _catalog = create_project_fixture(directory, entries)
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--full-catalog",
                "--dry-run",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no contiene entradas pendientes", result.stderr)


class GandalfSmallQuantityTests(unittest.TestCase):
    """Tests for small quantity handling (1 to BATCH_SIZE_MIN-1)."""

    def test_validate_batch_size_accepts_one(self):
        self.assertEqual(validate_batch_size(1), 1)

    def test_validate_batch_size_accepts_small_values(self):
        for count in (1, 5, 10, 15, 19):
            self.assertEqual(validate_batch_size(count), count)

    def test_validate_total_entries_accepts_one(self):
        self.assertEqual(validate_total_entries(1), 1)

    def test_validate_total_entries_accepts_small_values(self):
        for count in (1, 5, 10, 15, 19):
            self.assertEqual(validate_total_entries(count), count)

    def test_resolve_quantity_per_worker_count_one(self):
        result = resolve_quantity(workers=4, per_worker_count=1)
        self.assertEqual(result["total_entries"], 4)
        self.assertEqual(result["per_worker_count"], 1)
        self.assertIsNone(result["requested_total"])
        self.assertFalse(result["full_catalog"])

    def test_resolve_quantity_total_entries_one(self):
        result = resolve_quantity(workers=4, total_entries=1)
        self.assertEqual(result["total_entries"], 1)
        self.assertEqual(result["per_worker_count"], 1)  # ceil(1/4) = 1
        self.assertEqual(result["requested_total"], 1)
        self.assertFalse(result["full_catalog"])

    def test_resolve_quantity_total_entries_small(self):
        result = resolve_quantity(workers=4, total_entries=5)
        self.assertEqual(result["total_entries"], 5)
        self.assertEqual(result["per_worker_count"], 2)  # ceil(5/4) = 2
        self.assertEqual(result["requested_total"], 5)

    def test_resolve_quantity_total_entries_less_than_workers(self):
        result = resolve_quantity(workers=8, total_entries=3)
        self.assertEqual(result["total_entries"], 3)
        self.assertEqual(result["per_worker_count"], 1)  # ceil(3/8) = 1
        self.assertEqual(result["requested_total"], 3)

    def test_resolve_quantity_full_catalog_single_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            catalog_path.write_text(json.dumps({
                "entries": [
                    {"id": "A", "status": "pending"},
                    {"id": "B", "status": "translated"},
                ]
            }), encoding="utf-8")

            result = resolve_quantity(
                workers=4, full_catalog=True, catalog_path=catalog_path,
            )
            self.assertEqual(result["total_entries"], 1)
            self.assertEqual(result["per_worker_count"], 1)  # ceil(1/4) = 1
            self.assertTrue(result["full_catalog"])

    def test_plan_with_per_worker_count_one(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4, 1,
            )

            self.assertEqual(plan["total_entries"], 4)
            self.assertEqual(plan["per_worker_count"], 1)
            self.assertIsNone(plan["requested_total"])
            self.assertFalse(plan["full_catalog"])

    def test_plan_with_total_entries_one(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                total_entries=1,
            )

            self.assertEqual(plan["total_entries"], 1)
            self.assertEqual(plan["per_worker_count"], 1)
            self.assertEqual(plan["requested_total"], 1)
            self.assertFalse(plan["full_catalog"])

    def test_plan_with_full_catalog_single_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [
                {"id": "TEST:One", "source": "One", "translation": "", "status": "pending"},
                {"id": "TEST:Two", "source": "Two", "translation": "Dos", "status": "translated"},
            ])
            farm_file = create_farm_profile(directory, project_file)

            plan = build_translate_plan(
                project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                full_catalog=True,
            )

            self.assertTrue(plan["full_catalog"])
            self.assertEqual(plan["total_entries"], 1)
            self.assertEqual(plan["per_worker_count"], 1)
            self.assertIsNone(plan["requested_total"])

    def test_dry_run_with_per_worker_count_one(self):
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
                "--per-worker-count", "1",
                "--dry-run",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Entradas por worker: 1", result.stdout)
            self.assertIn("Capacidad total: 4", result.stdout)

    def test_dry_run_with_total_entries_one(self):
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
                "--total-entries", "1",
                "--dry-run",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Entradas solicitadas: 1", result.stdout)
            self.assertIn("Entradas por worker: 1", result.stdout)
            self.assertIn("Capacidad total: 1", result.stdout)

    def test_dry_run_with_full_catalog_single_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [
                {"id": "TEST:One", "source": "One", "translation": "", "status": "pending"},
                {"id": "TEST:Two", "source": "Two", "translation": "Dos", "status": "translated"},
            ])
            farm_file = create_farm_profile(directory, project_file)

            result = run_gandalf(
                "--translate",
                "--project", str(project_file),
                "--farm-profile", str(farm_file),
                "--model", "opencode/mimo-v2.5-free",
                "--workers", "4",
                "--full-catalog",
                "--dry-run",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("full-catalog", result.stdout)
            self.assertIn("Capacidad total: 1", result.stdout)

    def test_derive_bulk_profile_small_count(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            real_profile = {"coordinators": [{"prefix": "real", "model": "real-model"}]}
            profile_path = derive_bulk_profile(
                real_profile, temp_dir, "run-small",
                "opencode/mimo-v2.5-free", 4, 1
            )

            data = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(data["workers"], 4)
            self.assertEqual(data["count"], 1)

    def test_derive_bulk_profile_zero_rejected_by_farm(self):
        """count=0 would be rejected by farm validation, but gandalf accepts count=1."""
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            real_profile = {"coordinators": [{"prefix": "real", "model": "real-model"}]}
            profile_path = derive_bulk_profile(
                real_profile, temp_dir, "run-ok",
                "opencode/mimo-v2.5-free", 4, 1
            )
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(data["count"], 1)

    def test_no_save_with_small_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                exit_code = execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 1
                )

            self.assertEqual(exit_code, 0)

    def test_yes_with_small_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                exit_code = execute_translate_yes(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4, 1
                )

            self.assertEqual(exit_code, 0)

    def test_no_save_with_total_entries_one(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                exit_code = execute_translate_no_save(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                    total_entries=1,
                )

            self.assertEqual(exit_code, 0)

    def test_yes_with_total_entries_one(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file, _catalog = create_project_fixture(directory, [{
                "id": "TEST:One", "source": "One", "translation": "", "status": "pending",
            }])
            farm_file = create_farm_profile(directory, project_file)

            with patch("gandalf.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                exit_code = execute_translate_yes(
                    project_file, farm_file, "opencode/mimo-v2.5-free", 4,
                    total_entries=1,
                )

            self.assertEqual(exit_code, 0)

    def test_multiple_workers_small_total_entries(self):
        """total_entries < workers should give per_worker=1 for each."""
        result = resolve_quantity(workers=8, total_entries=3)
        self.assertEqual(result["total_entries"], 3)
        self.assertEqual(result["per_worker_count"], 1)
        self.assertEqual(result["requested_total"], 3)

    def test_multiple_workers_exact_division_small(self):
        result = resolve_quantity(workers=4, total_entries=4)
        self.assertEqual(result["total_entries"], 4)
        self.assertEqual(result["per_worker_count"], 1)
        self.assertEqual(result["requested_total"], 4)

    def test_boundary_per_worker_count_100(self):
        self.assertEqual(validate_batch_size(100), 100)

    def test_boundary_total_entries_100(self):
        self.assertEqual(validate_total_entries(100), 100)

    def test_boundary_total_entries_1(self):
        self.assertEqual(validate_total_entries(1), 1)

    def test_boundary_batch_size_1(self):
        self.assertEqual(validate_batch_size(1), 1)

    def test_full_catalog_small_catalog_varied_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            catalog_path.write_text(json.dumps({
                "entries": [
                    {"id": "A", "status": "pending"},
                    {"id": "B", "status": "translated"},
                    {"id": "C", "status": "preserved"},
                    {"id": "D", "status": "pending"},
                ]
            }), encoding="utf-8")

            result = resolve_quantity(
                workers=4, full_catalog=True, catalog_path=catalog_path,
            )
            self.assertEqual(result["total_entries"], 2)
            self.assertEqual(result["per_worker_count"], 1)  # ceil(2/4) = 1
            self.assertTrue(result["full_catalog"])

    def test_full_catalog_many_pending_large_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = [
                {"id": f"E{i}", "status": "pending"}
                for i in range(5)
            ]
            catalog_path = Path(directory) / "catalog.json"
            catalog_path.write_text(json.dumps({"entries": entries}), encoding="utf-8")

            result = resolve_quantity(
                workers=8, full_catalog=True, catalog_path=catalog_path,
            )
            self.assertEqual(result["total_entries"], 5)
            self.assertEqual(result["per_worker_count"], 1)  # ceil(5/8) = 1
            self.assertTrue(result["full_catalog"])


if __name__ == "__main__":
    unittest.main()
