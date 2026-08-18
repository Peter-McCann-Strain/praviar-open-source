"""Tests for Fix 6: Cost calculation accuracy.

Tests:
- Correct Haiku pricing ($1.00/$5.00 per M tokens)
- Correct Opus pricing ($5.00/$25.00 per M tokens)
- model_name → pricing tier derivation
- Role-based fallback when model_name is empty
- Actual cost computation for realistic token counts
"""

from __future__ import annotations

import pytest

from praviar_pipeline.models.audit import StepTokenUsage
from praviar_pipeline.pipeline.step8_report import _compute_cost, _model_name_to_pricing_key


class TestModelNameToPricingKey:
    """Test deriving pricing tier from actual model names."""

    def test_haiku(self):
        assert _model_name_to_pricing_key("claude-haiku-4-5-20251001") == "haiku"

    def test_sonnet(self):
        assert _model_name_to_pricing_key("claude-sonnet-4-6") == "sonnet"

    def test_opus(self):
        assert _model_name_to_pricing_key("claude-opus-4-6") == "opus"

    def test_case_insensitive(self):
        assert _model_name_to_pricing_key("Claude-HAIKU-3-5") == "haiku"

    def test_unknown_model(self):
        assert _model_name_to_pricing_key("gpt-4o") == ""

    def test_empty_string(self):
        assert _model_name_to_pricing_key("") == ""


class TestComputeCost:
    """Test the cost computation function with realistic token usage."""

    @pytest.fixture(autouse=True)
    def _use_mock_settings(self, mock_settings):
        pass

    def test_haiku_pricing_correct(self):
        """Haiku should use $1.00/$5.00 per M tokens."""
        usage = [
            StepTokenUsage(
                step_name="step3_triage",
                model_role="triage",
                model_name="claude-haiku-4-5-20251001",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            ),
        ]
        cost = _compute_cost(usage)
        # $1.00 input + $5.00 output = $6.00
        assert cost == pytest.approx(6.00, abs=0.01)

    def test_sonnet_pricing(self):
        usage = [
            StepTokenUsage(
                step_name="step8_report",
                model_role="analysis",
                model_name="claude-sonnet-4-6",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            ),
        ]
        cost = _compute_cost(usage)
        # $3.00 input + $15.00 output = $18.00
        assert cost == pytest.approx(18.00, abs=0.01)

    def test_opus_pricing(self):
        usage = [
            StepTokenUsage(
                step_name="step4_analyze",
                model_role="deep",
                model_name="claude-opus-4-6",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            ),
        ]
        cost = _compute_cost(usage)
        # $5.00 input + $25.00 output = $30.00
        assert cost == pytest.approx(30.00, abs=0.01)

    def test_model_name_takes_priority_over_role(self):
        """If model_name says haiku but role says 'deep', use haiku pricing."""
        usage = [
            StepTokenUsage(
                step_name="step4_analyze",
                model_role="deep",  # Would normally use opus pricing
                model_name="claude-haiku-4-5-20251001",  # But model is actually haiku
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            ),
        ]
        cost = _compute_cost(usage)
        # Should use haiku pricing: $1.00 + $5.00 = $6.00
        assert cost == pytest.approx(6.00, abs=0.01)

    def test_fallback_to_role_when_no_model_name(self):
        """When model_name is empty, fall back to role-based pricing."""
        usage = [
            StepTokenUsage(
                step_name="step3_triage",
                model_role="triage",
                model_name="",  # No model name — use role
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            ),
        ]
        cost = _compute_cost(usage)
        # Role "triage" → haiku pricing: $1.00 + $5.00 = $6.00
        assert cost == pytest.approx(6.00, abs=0.01)

    def test_empty_usage_is_zero(self):
        cost = _compute_cost([])
        assert cost == 0.0

    def test_realistic_pipeline_cost(self):
        """Realistic pipeline with all three model tiers."""
        usage = [
            StepTokenUsage(
                step_name="step3_triage",
                model_role="triage",
                model_name="claude-haiku-4-5-20251001",
                input_tokens=50_000,
                output_tokens=10_000,
            ),
            StepTokenUsage(
                step_name="step4_analyze",
                model_role="deep",
                model_name="claude-haiku-4-5-20251001",  # Dev mode: using haiku as deep
                input_tokens=500_000,
                output_tokens=200_000,
            ),
            StepTokenUsage(
                step_name="step8_report",
                model_role="analysis",
                model_name="claude-haiku-4-5-20251001",  # Dev mode: using haiku
                input_tokens=100_000,
                output_tokens=50_000,
            ),
        ]
        cost = _compute_cost(usage)
        # All haiku: input total = 650K, output total = 260K
        # Cost = (650K/1M * 1.00) + (260K/1M * 5.00)
        #      = 0.65 + 1.30 = 1.95
        assert cost == pytest.approx(1.95, abs=0.01)


class TestStepTokenUsageModelName:
    """Test the new model_name field on StepTokenUsage."""

    def test_model_name_default_empty(self):
        usage = StepTokenUsage(step_name="test", model_role="triage")
        assert usage.model_name == ""

    def test_model_name_set(self):
        usage = StepTokenUsage(
            step_name="test",
            model_role="triage",
            model_name="claude-haiku-4-5-20251001",
        )
        assert usage.model_name == "claude-haiku-4-5-20251001"

    def test_serialization_includes_model_name(self):
        usage = StepTokenUsage(
            step_name="test",
            model_role="triage",
            model_name="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )
        data = usage.model_dump()
        assert "model_name" in data
        assert data["model_name"] == "claude-haiku-4-5-20251001"
