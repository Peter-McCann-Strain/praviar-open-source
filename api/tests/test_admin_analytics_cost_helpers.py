"""Tests for pure admin analytics cost helper functions."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.admin_analytics import (
    build_model_costs,
    build_model_usage_details,
    build_step_costs,
    calculate_cache_hit_rate,
    model_name_from_config,
)


def test_build_step_costs_distributes_total_cost_by_analysis_share():
    step_costs = build_step_costs(
        step_rows=[
            SimpleNamespace(step_name="step4_analyze", analysis_count=3),
            SimpleNamespace(step_name="step6_invalid", analysis_count=1),
        ],
        total_cost=20.0,
    )

    assert step_costs[0].step_name == "step4_analyze"
    assert step_costs[0].total_cost_usd == 15.0
    assert step_costs[1].avg_cost_usd == 5.0


def test_build_model_costs_groups_by_resolved_model_name():
    model_costs = build_model_costs(
        rows=[
            SimpleNamespace(
                config={"analysis_execution_profile": "agentic_escalation"},
                input_tokens=100,
                output_tokens=50,
                total_cost=1.2,
                count=2,
            ),
            SimpleNamespace(
                config={"analysis_execution_profile": "agentic_escalation"},
                input_tokens=30,
                output_tokens=20,
                total_cost=0.4,
                count=1,
            ),
        ],
        model_name_from_config=model_name_from_config,
    )

    assert len(model_costs) == 1
    assert model_costs[0].model_name == "agentic_escalation"
    assert model_costs[0].total_input_tokens == 130
    assert model_costs[0].total_output_tokens == 70
    assert model_costs[0].request_count == 3
    assert model_costs[0].total_cost_usd == 1.6


def test_build_model_usage_details_returns_sorted_models_and_totals():
    models, total_tokens, total_cost = build_model_usage_details(
        rows=[
            SimpleNamespace(
                config={"analysis_execution_profile": "single_pass"},
                input_tokens=50,
                output_tokens=10,
                total_cost=0.5,
                count=1,
            ),
            SimpleNamespace(
                config={"analysis_execution_profile": "agentic_escalation"},
                input_tokens=120,
                output_tokens=30,
                total_cost=2.5,
                count=2,
            ),
        ],
        model_name_from_config=model_name_from_config,
    )

    assert [model.model_name for model in models] == [
        "agentic_escalation",
        "single_pass",
    ]
    assert total_tokens == 210
    assert total_cost == 3.0


def test_calculate_cache_hit_rate_counts_only_cached_rows():
    rate = calculate_cache_hit_rate(
        [
            {"cost": {"cache_creation_input_tokens": 100, "cache_read_input_tokens": 50}},
            {"cost": {"cache_creation_input_tokens": 100, "cache_read_input_tokens": 0}},
            {"cost": {"cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}},
        ]
    )

    assert rate == 50.0


def test_calculate_cache_hit_rate_returns_none_without_cached_rows():
    assert calculate_cache_hit_rate([{"cost": {}}, {}]) is None
