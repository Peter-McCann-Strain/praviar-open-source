from research.tools.benchmarks.check_evidence_quarantine import (
    DEFAULT_MANIFEST,
    validate_manifest,
)


def test_quarantined_research_artifacts_are_machine_rejected_as_release_evidence() -> None:
    assert validate_manifest(DEFAULT_MANIFEST) == []
