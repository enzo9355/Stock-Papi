import os
import unittest
from unittest.mock import patch

from stock_papi.config.capabilities import PredictionCapabilityState


class PredictionCapabilityStateTests(unittest.TestCase):
    def test_defaults_to_observation_enabled_research_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            state = PredictionCapabilityState.from_environment()

        self.assertEqual(state.mode, "research")
        self.assertTrue(state.observation_enabled)
        self.assertFalse(state.probability_allowed)
        self.assertFalse(state.ranking_allowed)
        self.assertFalse(state.strong_action_allowed)
        self.assertFalse(state.performance_endorsement_allowed)
        self.assertIsNone(state.preview_candidate_prefix)
        self.assertEqual(state.warnings, ())

    def test_research_mode_ignores_prediction_enable_flags(self):
        environment = {
            "ABSORB_PREDICTION_MODE": "research",
            "ABSORB_PREDICTION_PROBABILITY_ENABLED": "true",
            "ABSORB_PREDICTION_RANKING_ENABLED": "1",
            "ABSORB_PREDICTION_STRONG_ACTIONS_ENABLED": "yes",
            "ABSORB_PREDICTION_PERFORMANCE_ENDORSEMENT_ENABLED": "on",
        }
        with patch.dict(os.environ, environment, clear=True):
            state = PredictionCapabilityState.from_environment()

        self.assertFalse(state.probability_allowed)
        self.assertFalse(state.ranking_allowed)
        self.assertFalse(state.strong_action_allowed)
        self.assertFalse(state.performance_endorsement_allowed)
        self.assertEqual(
            set(state.warnings),
            {
                "probability_disabled_in_research",
                "ranking_disabled_in_research",
                "strong_actions_disabled_in_research",
                "performance_endorsement_disabled_in_research",
            },
        )

    def test_validated_preview_requires_prefix_and_never_allows_strong_actions(self):
        environment = {
            "ABSORB_PREDICTION_MODE": "validated_preview",
            "ABSORB_PREVIEW_CANDIDATE_PREFIX": "previews/2026-07-17-abc123",
            "ABSORB_PREDICTION_PROBABILITY_ENABLED": "true",
            "ABSORB_PREDICTION_RANKING_ENABLED": "true",
            "ABSORB_PREDICTION_STRONG_ACTIONS_ENABLED": "true",
            "ABSORB_PREDICTION_PERFORMANCE_ENDORSEMENT_ENABLED": "true",
        }
        with patch.dict(os.environ, environment, clear=True):
            state = PredictionCapabilityState.from_environment()

        self.assertEqual(state.mode, "validated_preview")
        self.assertEqual(
            state.preview_candidate_prefix, "previews/2026-07-17-abc123"
        )
        self.assertTrue(state.probability_allowed)
        self.assertTrue(state.ranking_allowed)
        self.assertFalse(state.strong_action_allowed)
        self.assertFalse(state.performance_endorsement_allowed)
        self.assertEqual(
            set(state.warnings),
            {
                "strong_actions_require_production_mode",
                "performance_endorsement_requires_production_mode",
            },
        )

    def test_invalid_mode_and_prefix_fail_closed(self):
        environment = {
            "ABSORB_PREDICTION_MODE": "enabled",
            "ABSORB_OBSERVATION_ENABLED": "false",
            "ABSORB_PREVIEW_CANDIDATE_PREFIX": "../preview",
            "ABSORB_PREDICTION_PROBABILITY_ENABLED": "true",
        }
        with patch.dict(os.environ, environment, clear=True):
            state = PredictionCapabilityState.from_environment()

        self.assertEqual(state.mode, "research")
        self.assertFalse(state.observation_enabled)
        self.assertIsNone(state.preview_candidate_prefix)
        self.assertFalse(state.probability_allowed)
        self.assertIn("invalid_prediction_mode", state.warnings)
        self.assertIn("invalid_preview_candidate_prefix", state.warnings)

    def test_public_document_exposes_only_capability_contract(self):
        with patch.dict(os.environ, {}, clear=True):
            document = PredictionCapabilityState.from_environment().to_document()

        self.assertEqual(
            document,
            {
                "mode": "research",
                "observation_enabled": True,
                "probability_allowed": False,
                "ranking_allowed": False,
                "strong_action_allowed": False,
                "performance_endorsement_allowed": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
