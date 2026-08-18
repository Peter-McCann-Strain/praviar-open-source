"""Regression tests for the credential-free triage settings boundary."""

from praviar_pipeline.config import Settings
from praviar_pipeline.triage_local_settings import TriageLocalSettings


def test_triage_local_defaults_match_full_runtime_settings() -> None:
    """Shared fields must not drift while the settings modules stay acyclic."""
    full_fields = Settings.model_fields

    for name, local_field in TriageLocalSettings.model_fields.items():
        full_field = full_fields[name]
        local_default = local_field.get_default(call_default_factory=True)
        full_default = full_field.get_default(call_default_factory=True)

        assert local_default == full_default, name
