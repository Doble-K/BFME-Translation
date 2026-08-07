#!/usr/bin/env python3
"""Focused tests for Gandalf model selector pure functions.

These tests exercise the UI-agnostic selection logic without requiring a
display or tkinter.  The full GUI is not tested here; only the pure
functions extracted for the model selector are covered.
"""

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gandalf import (
    _TIER_ORDER,
    format_model_status,
    get_models_for_tier,
    get_tier_models,
    is_premium_tier,
    list_models_by_tier,
    select_model,
    tier_label,
    tier_menu_key,
    validate_model,
)


class TierLabelTests(unittest.TestCase):
    """Tests for tier_label() and tier_menu_key()."""

    def test_tier_label_free(self):
        result = tier_label("free")
        self.assertIn("Free", result)

    def test_tier_label_economic(self):
        result = tier_label("economic")
        self.assertIn("Económico", result)

    def test_tier_label_premium(self):
        result = tier_label("premium")
        self.assertIn("Premium", result)

    def test_tier_label_unknown_returns_raw(self):
        result = tier_label("unknown_tier")
        self.assertEqual(result, "unknown_tier")

    def test_tier_menu_key_returns_string(self):
        for tier in _TIER_ORDER:
            key = tier_menu_key(tier)
            self.assertIsInstance(key, str)
            self.assertTrue(key.isdigit())

    def test_tier_menu_keys_are_distinct(self):
        keys = [tier_menu_key(t) for t in _TIER_ORDER]
        self.assertEqual(len(keys), len(set(keys)))


class IsPremiumTierTests(unittest.TestCase):
    """Tests for is_premium_tier()."""

    def test_free_is_not_premium(self):
        self.assertFalse(is_premium_tier("free"))

    def test_economic_is_not_premium(self):
        self.assertFalse(is_premium_tier("economic"))

    def test_premium_is_premium(self):
        self.assertTrue(is_premium_tier("premium"))


class GetModelsForTierTests(unittest.TestCase):
    """Tests for get_models_for_tier() wrapper."""

    def test_returns_list_for_free(self):
        models = get_models_for_tier("free")
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)

    def test_returns_list_for_economic(self):
        models = get_models_for_tier("economic")
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)

    def test_returns_list_for_premium(self):
        models = get_models_for_tier("premium")
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)

    def test_matches_get_tier_models(self):
        for tier in _TIER_ORDER:
            self.assertEqual(get_models_for_tier(tier), get_tier_models(tier))

    def test_rejects_invalid_tier(self):
        with self.assertRaises(ValueError):
            get_models_for_tier("invalid")


class SelectModelTests(unittest.TestCase):
    """Tests for select_model() — the core UI-agnostic selector."""

    def test_select_free_model(self):
        models = get_tier_models("free")
        model_id, tier = select_model("free", models[0])
        self.assertEqual(model_id, models[0])
        self.assertEqual(tier, "free")

    def test_select_economic_model(self):
        models = get_tier_models("economic")
        model_id, tier = select_model("economic", models[0])
        self.assertEqual(model_id, models[0])
        self.assertEqual(tier, "economic")

    def test_select_premium_model_without_confirmation_fails(self):
        models = get_tier_models("premium")
        with self.assertRaisesRegex(ValueError, "confirmación"):
            select_model("premium", models[0], confirmed=False)

    def test_select_premium_model_with_confirmation(self):
        models = get_tier_models("premium")
        model_id, tier = select_model("premium", models[0], confirmed=True)
        self.assertEqual(model_id, models[0])
        self.assertEqual(tier, "premium")

    def test_select_model_not_in_tier_fails(self):
        free_models = get_tier_models("free")
        economic_models = get_tier_models("economic")
        if free_models and economic_models:
            with self.assertRaisesRegex(ValueError, "no pertenece al tier"):
                select_model("free", economic_models[0])

    def test_select_model_invalid_tier_fails(self):
        models = get_tier_models("free")
        if models:
            with self.assertRaisesRegex(ValueError, "tier no válido"):
                select_model("invalid_tier", models[0])

    def test_select_model_empty_model_id_fails(self):
        with self.assertRaises(ValueError):
            select_model("free", "")

    def test_select_model_none_model_id_fails(self):
        with self.assertRaises((ValueError, TypeError)):
            select_model("free", None)

    def test_select_model_returns_validate_model_result(self):
        """select_model should delegate to validate_model for confirmation logic."""
        models = get_tier_models("free")
        model_id, tier = select_model("free", models[0])
        v_model, v_tier = validate_model(models[0])
        self.assertEqual((model_id, tier), (v_model, v_tier))


class FormatModelStatusTests(unittest.TestCase):
    """Tests for format_model_status()."""

    def test_format_with_model(self):
        result = format_model_status("free", "opencode/mimo-v2.5-free")
        self.assertIn("Free", result)
        self.assertIn("opencode/mimo-v2.5-free", result)

    def test_format_without_model(self):
        result = format_model_status("economic", "")
        self.assertIn("Económico", result)
        self.assertIn("sin modelo", result)

    def test_format_premium_tier(self):
        result = format_model_status("premium", "opencode/sol-ultra")
        self.assertIn("Premium", result)
        self.assertIn("opencode/sol-ultra", result)


class ModelSelectorIntegrationTests(unittest.TestCase):
    """Integration tests combining tier selection and model validation."""

    def test_full_selection_free_tier(self):
        """Simulate user selecting free tier and first model."""
        tiers = list_models_by_tier()
        tier = "free"
        models = tiers[tier]
        self.assertGreater(len(models), 0)
        model_id, result_tier = select_model(tier, models[0])
        self.assertEqual(result_tier, "free")
        self.assertEqual(model_id, models[0])

    def test_full_selection_economic_tier(self):
        """Simulate user selecting economic tier and first model."""
        tiers = list_models_by_tier()
        tier = "economic"
        models = tiers[tier]
        self.assertGreater(len(models), 0)
        model_id, result_tier = select_model(tier, models[0])
        self.assertEqual(result_tier, "economic")
        self.assertEqual(model_id, models[0])

    def test_full_selection_premium_tier_with_confirmation(self):
        """Simulate user selecting premium tier, model, and confirming."""
        tiers = list_models_by_tier()
        tier = "premium"
        models = tiers[tier]
        self.assertGreater(len(models), 0)
        model_id, result_tier = select_model(tier, models[0], confirmed=True)
        self.assertEqual(result_tier, "premium")
        self.assertEqual(model_id, models[0])

    def test_full_selection_premium_tier_without_confirmation_blocked(self):
        """Premium tier without confirmation should be blocked."""
        tiers = list_models_by_tier()
        tier = "premium"
        models = tiers[tier]
        self.assertGreater(len(models), 0)
        with self.assertRaises(ValueError):
            select_model(tier, models[0], confirmed=False)

    def test_tier_models_match_list_models_by_tier(self):
        """get_models_for_tier returns same result as list_models_by_tier."""
        grouped = list_models_by_tier()
        for tier in _TIER_ORDER:
            self.assertEqual(get_models_for_tier(tier), grouped[tier])

    def test_all_models_selectable_in_own_tier(self):
        """Every model in the registry should be selectable in its own tier."""
        grouped = list_models_by_tier()
        for tier, models in grouped.items():
            for model_id in models:
                if is_premium_tier(tier):
                    result_model, result_tier = select_model(
                        tier, model_id, confirmed=True
                    )
                else:
                    result_model, result_tier = select_model(tier, model_id)
                self.assertEqual(result_model, model_id)
                self.assertEqual(result_tier, tier)


if __name__ == "__main__":
    unittest.main()
