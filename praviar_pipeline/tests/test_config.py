"""Tests for settings and configuration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from praviar_pipeline.config import (
    ClaudeModels,
    Settings,
    clear_settings_cache,
    get_settings,
    runtime_settings_context,
)
from praviar_pipeline.config_execution_sections import PipelineExecutionSettingsMixin
from praviar_pipeline.errors import ConfigurationError


class TestSettings:
    def test_missing_anthropic_key_raises(self):
        """Settings without anthropic_api_key should raise ConfigurationError."""
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False),
            pytest.raises(ConfigurationError, match="anthropic_api_key"),
        ):
            Settings()

    def test_valid_keys_pass(self):
        """Settings with real (non-placeholder) API keys should construct fine."""
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "sk-ant-real-key",
                "PATENTSVIEW_API_KEY": "real-pv-key",
                "USPTO_ODP_API_KEY": "real-odp-key",
            },
        ):
            s = Settings()
            assert s.anthropic_api_key == "sk-ant-real-key"
            assert s.patentsview_api_key == "real-pv-key"
            assert s.uspto_odp_api_key == "real-odp-key"

    def test_claude_models_property(self):
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "sk-ant-real-key",
                "PATENTSVIEW_API_KEY": "real-pv-key",
                "USPTO_ODP_API_KEY": "real-odp-key",
                "CLAUDE_TRIAGE_MODEL": "claude-haiku-4-5-20251001",
                "CLAUDE_ANALYSIS_MODEL": "claude-sonnet-4-6",
                "CLAUDE_DEEP_MODEL": "claude-opus-4-6",
            },
        ):
            s = Settings()
            models = s.claude_models
            assert isinstance(models, ClaudeModels)
            assert "haiku" in models.triage
            assert "sonnet" in models.analysis
            assert "opus" in models.deep

    def test_get_settings_cached(self):
        """get_settings() should return the same instance (lru_cache)."""
        clear_settings_cache()

    def test_runtime_settings_context_is_scoped_and_restored(self):
        """Per-analysis overrides reach deep clients without leaking afterward."""
        clear_settings_cache()
        base = get_settings()
        overridden = base.model_copy(
            update={
                "trust_mode": "counsel",
                "search_allowed_jurisdictions": ["US", "WO"],
            }
        )

        with runtime_settings_context(overridden):
            assert get_settings() is overridden
            assert get_settings().trust_mode == "counsel"
            assert get_settings().search_allowed_jurisdictions == ["US", "WO"]

        assert get_settings() is base
        clear_settings_cache()
        with patch.dict(
            "os.environ",
            {"ANTHROPIC_API_KEY": "sk-ant-test-key"},
        ):
            s1 = get_settings()
            s2 = get_settings()
            assert s1 is s2
        clear_settings_cache()

    def test_env_override(self):
        """Environment variables should override defaults."""
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "sk-ant-real-key",
                "PATENTSVIEW_API_KEY": "real-pv-key",
                "USPTO_ODP_API_KEY": "real-odp-key",
                "LOG_LEVEL": "DEBUG",
            },
        ):
            s = Settings()
            assert s.anthropic_api_key == "sk-ant-real-key"
            assert s.log_level == "DEBUG"

    @pytest.mark.parametrize(
        "contact_email",
        [
            "not-an-email",
            "missing-domain@",
            "two words@example.com",
            "x)@example.org",
            "x(@example.org",
            "x\\@example.org",
            "x\x00@example.org",
            "x@example..org",
            "x@-example.org",
            "x@example-.org",
            "x@exam_ple.org",
            "x@localhost",
            f"{'a' * 65}@example.org",
            " opérateur@example.org",
        ],
    )
    def test_source_contact_email_rejects_invalid_operator_identity(
        self,
        contact_email: str,
    ) -> None:
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}),
            pytest.raises(ValueError, match="source_contact_email"),
        ):
            Settings(source_contact_email=contact_email)

    def test_source_contact_email_is_optional_and_explicit(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            assert Settings().source_contact_email == ""
            assert Settings(source_contact_email="operator@example.org").source_contact_email == (
                "operator@example.org"
            )


def test_hybrid_retrieval_enabled_default_is_false():
    """hybrid_retrieval_enabled must default to False (gate: benchmark smoke first).

    PipelineExecutionSettingsMixin is a plain Python class (not a BaseModel), so its
    Field defaults are only evaluated when composed into Settings. We therefore test
    via Settings with the required API-key env vars patched in.
    """
    with patch.dict(
        "os.environ",
        {"ANTHROPIC_API_KEY": "sk-ant-test-key"},
    ):
        s = Settings()
    assert s.hybrid_retrieval_enabled is False
    # Sanity-check the mixin is the source of the field via the class annotation.
    assert "hybrid_retrieval_enabled" in PipelineExecutionSettingsMixin.__dict__


def test_hybrid_retrieval_requires_bigquery_source_enabled():
    with (
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}),
        pytest.raises(ValueError, match="search_enable_bigquery"),
    ):
        Settings(
            hybrid_retrieval_enabled=True,
            search_enable_bigquery=False,
            bigquery_project_id="project-1",
        )


def test_hybrid_retrieval_requires_explicit_project():
    with (
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}),
        pytest.raises(ValueError, match="bigquery_project_id"),
    ):
        Settings(
            hybrid_retrieval_enabled=True,
            bigquery_project_id="",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bigquery_dataset", "bad-dataset"),
        ("bigquery_table", "bad.table"),
    ],
)
def test_hybrid_retrieval_rejects_invalid_table_identifiers(
    field: str,
    value: str,
):
    with (
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}),
        pytest.raises(ValueError, match=field),
    ):
        Settings(
            hybrid_retrieval_enabled=True,
            bigquery_project_id="project-1",
            **{field: value},
        )


def test_hybrid_retrieval_accepts_complete_prerequisites():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
        settings = Settings(
            hybrid_retrieval_enabled=True,
            search_enable_bigquery=True,
            bigquery_project_id="project-1",
            bigquery_dataset="patents",
            bigquery_table="hybrid_index",
        )

    assert settings.hybrid_retrieval_enabled is True


def test_drawing_preprocessing_typo_fails_during_settings_validation():
    """Configured preprocessing operations are a closed enum, not best-effort strings."""
    with (
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}),
        pytest.raises(ValueError, match="drawing_preprocessing"),
    ):
        Settings(drawing_preprocessing=["clhae"])


def test_all_supported_drawing_preprocessing_steps_validate():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
        settings = Settings(
            drawing_preprocessing=[
                "denoise",
                "clahe",
                "binarize",
                "sauvola",
                "connected_components",
                "deskew",
                "sharpen",
                "pad",
                "resize_512",
            ]
        )

    assert [str(step) for step in settings.drawing_preprocessing] == [
        "denoise",
        "clahe",
        "binarize",
        "sauvola",
        "connected_components",
        "deskew",
        "sharpen",
        "pad",
        "resize_512",
    ]


def test_drawing_resource_limits_cannot_exceed_hard_ceilings():
    with (
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}),
        pytest.raises(ValueError, match="drawing_pdf_max_bytes"),
    ):
        Settings(drawing_pdf_max_bytes=100 * 1024 * 1024 + 1)
