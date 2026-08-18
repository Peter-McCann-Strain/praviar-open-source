"""Tests for pipeline checkpoint save/load/restore."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from praviar_pipeline.checkpoint import (
    CheckpointIntegrityKeyRing,
    PipelineCheckpoint,
    build_checkpoint,
    restore_from_checkpoint,
)
from praviar_pipeline.checkpoint import (
    load_latest_checkpoint as _load_latest_checkpoint,
)
from praviar_pipeline.checkpoint import (
    save_checkpoint as _save_checkpoint,
)
from praviar_pipeline.models.patent import (
    LegalStatus,
    PatentHit,
    PatentSource,
    has_trusted_legal_status_provenance,
    trusted_legal_status_conflict,
    trusted_legal_status_observations,
)
from tests.legal_status_test_helpers import (
    trusted_ops_provenance,
    trusted_register_provenance,
)

TEST_INTEGRITY_KEYS = CheckpointIntegrityKeyRing(
    active_key_id="test-v1",
    _keys={"test-v1": b"test-pipeline-checkpoint-hmac-key-00000001"},
)


def save_checkpoint(checkpoint, checkpoint_dir, *, integrity_keys=TEST_INTEGRITY_KEYS):
    return _save_checkpoint(checkpoint, checkpoint_dir, integrity_keys=integrity_keys)


def load_latest_checkpoint(checkpoint_dir, *, integrity_keys=TEST_INTEGRITY_KEYS):
    return _load_latest_checkpoint(checkpoint_dir, integrity_keys=integrity_keys)


def _trusted_checkpoint_hit() -> PatentHit:
    patent_id = "EP1234567B1"
    provenance = trusted_register_provenance(
        patent_id=patent_id,
        artifact={"status": "revoked"},
    )
    return PatentHit(
        patent_id=patent_id,
        sources=[PatentSource.EPO_SEARCH],
        legal_status=LegalStatus.REVOKED,
        legal_status_provenance=provenance,
    )


def _conflicted_checkpoint_hit() -> PatentHit:
    patent_id = "EP7654321B1"
    active = trusted_ops_provenance(
        patent_id=patent_id,
        legal_status=LegalStatus.ACTIVE,
        artifact=[
            {
                "event_code": "B1",
                "event_description": "Patent granted",
            }
        ],
    )
    revoked = trusted_register_provenance(
        patent_id=patent_id,
        artifact={"status": "revoked"},
    )
    return PatentHit(
        patent_id=patent_id,
        sources=[PatentSource.EPO_SEARCH],
        legal_status=LegalStatus.UNKNOWN,
        legal_status_observations=[active, revoked],
    )


class TestPipelineCheckpoint:
    """Tests for PipelineCheckpoint model."""

    def test_minimal_checkpoint(self):
        ckpt = PipelineCheckpoint(
            run_id="test-001",
            completed_step=1,
            compound_input="succinic acid",
        )
        assert ckpt.run_id == "test-001"
        assert ckpt.completed_step == 1
        assert ckpt.execution_profile == "world_class_adaptive"
        assert ckpt.analysis_escalation_reasons == []
        assert ckpt.compound is None


class TestCheckpointLegacyModeHardBreak:
    """Legacy mode/depth checkpoint metadata is intentionally rejected."""

    def test_legacy_lite_checkpoint_is_rejected(self):
        legacy_json = json.dumps(
            {
                "run_id": "legacy-001",
                "completed_step": 6,
                "compound_input": "aspirin",
                "pipeline_mode": "lite",
            }
        )
        with pytest.raises(ValidationError, match="pipeline_mode"):
            PipelineCheckpoint.model_validate_json(legacy_json)

    def test_legacy_advanced_checkpoint_is_rejected(self):
        legacy_json = json.dumps(
            {
                "run_id": "legacy-002",
                "completed_step": 6,
                "compound_input": "ibuprofen",
                "pipeline_mode": "advanced",
            }
        )
        with pytest.raises(ValidationError, match="pipeline_mode"):
            PipelineCheckpoint.model_validate_json(legacy_json)

    def test_explicit_execution_profile_is_preserved(self):
        ckpt = PipelineCheckpoint(
            run_id="new-001",
            completed_step=1,
            compound_input="aspirin",
            execution_profile="world_class_adaptive",
            analysis_escalation_reasons=["high_risk_triage"],
        )
        assert ckpt.execution_profile == "world_class_adaptive"
        assert ckpt.analysis_escalation_reasons == ["high_risk_triage"]

    def test_round_trip_preserves_execution_profile(self):
        original = build_checkpoint(
            run_id="rt-001",
            completed_step=3,
            compound_input="aspirin",
            execution_profile="world_class_adaptive",
            analysis_escalation_reasons=["dense_relevant_landscape"],
        )
        restored = PipelineCheckpoint.model_validate_json(original.model_dump_json())
        assert restored.execution_profile == "world_class_adaptive"
        assert restored.analysis_escalation_reasons == ["dense_relevant_landscape"]

    def test_full_checkpoint_serialization(self):
        ckpt = PipelineCheckpoint(
            run_id="test-002",
            completed_step=6,
            compound_input="ibuprofen",
            execution_profile="world_class_adaptive",
            analysis_escalation_reasons=["complex_matter_type"],
            compound={"name": "ibuprofen", "pubchem_cid": 3672},
            patent_hits=[{"patent_id": "US123", "title": "Test"}],
            matter_graph={"nodes": [{"node_id": "compound:ibuprofen"}], "edges": []},
            matter_graph_summary={"node_count": 1, "root_compound": "ibuprofen"},
            matter_store={"matter_graph_summary": {"node_count": 1, "root_compound": "ibuprofen"}},
            evidence_artifacts=[{"artifact_id": "artifact-1", "artifact_type": "search_hit"}],
            evidence_adapter_results=[{"adapter_name": "patentsview", "status": "ok"}],
            collector_runs=[{"definition": {"collector_name": "patentsview"}}],
            analyses=[{"patent_id": "US123", "risk_level": "low"}],
            triage_input_tokens=5000,
            triage_output_tokens=1000,
        )
        data = json.loads(ckpt.model_dump_json())
        assert data["execution_profile"] == "world_class_adaptive"
        assert data["analysis_escalation_reasons"] == ["complex_matter_type"]
        assert len(data["patent_hits"]) == 1
        assert data["matter_graph"]["nodes"][0]["node_id"] == "compound:ibuprofen"
        assert data["matter_graph_summary"]["root_compound"] == "ibuprofen"
        assert data["matter_store"]["matter_graph_summary"]["root_compound"] == "ibuprofen"
        assert data["evidence_artifacts"][0]["artifact_id"] == "artifact-1"
        assert data["evidence_adapter_results"][0]["adapter_name"] == "patentsview"
        assert data["collector_runs"][0]["definition"]["collector_name"] == "patentsview"
        assert data["triage_input_tokens"] == 5000


class TestSaveLoadCheckpoint:
    """Tests for save and load functions."""

    def test_save_and_load_roundtrip(self, tmp_path):
        ckpt = PipelineCheckpoint(
            run_id="roundtrip-test",
            completed_step=3,
            compound_input="benzene",
            compound={"name": "benzene", "pubchem_cid": 241},
            patent_hits=[{"patent_id": "US456", "title": "Benzene patent"}],
        )
        save_checkpoint(ckpt, tmp_path)
        loaded = load_latest_checkpoint(tmp_path)
        assert loaded is not None
        assert loaded.run_id == "roundtrip-test"
        assert loaded.completed_step == 3
        assert loaded.compound["name"] == "benzene"
        assert len(loaded.patent_hits) == 1

    def test_load_latest_picks_highest_step(self, tmp_path):
        for step in [1, 3, 5]:
            ckpt = PipelineCheckpoint(
                run_id="multi-step",
                completed_step=step,
                compound_input="test",
            )
            save_checkpoint(ckpt, tmp_path)
        loaded = load_latest_checkpoint(tmp_path)
        assert loaded.completed_step == 5

    def test_load_from_empty_dir(self, tmp_path):
        assert load_latest_checkpoint(tmp_path) is None

    def test_load_from_nonexistent_dir(self, tmp_path):
        assert load_latest_checkpoint(tmp_path / "nonexistent") is None

    def test_checkpoint_payload_tampering_fails_integrity_validation(self, tmp_path):
        checkpoint = build_checkpoint(
            run_id="tamper-payload",
            completed_step=3,
            compound_input="test",
            patent_hits=[_trusted_checkpoint_hit()],
        )
        save_checkpoint(checkpoint, tmp_path)
        path = tmp_path / "step_3.json"
        path.write_text(path.read_text().replace("EP1234567B1", "EP7654321B1"))

        with pytest.raises(ValueError, match="integrity authentication failed"):
            load_latest_checkpoint(tmp_path)

    def test_checkpoint_manifest_identity_tampering_fails_closed(self, tmp_path):
        checkpoint = build_checkpoint(
            run_id="tamper-manifest",
            completed_step=3,
            compound_input="test",
        )
        save_checkpoint(checkpoint, tmp_path)
        path = tmp_path / "step_3.manifest.json"
        manifest = json.loads(path.read_text())
        manifest["run_id"] = "other-run"
        path.write_text(json.dumps(manifest))

        with pytest.raises(ValueError, match="integrity authentication failed"):
            load_latest_checkpoint(tmp_path)

    def test_checkpoint_wrong_key_fails_constant_time_authentication(
        self,
        tmp_path,
        monkeypatch,
    ):
        import praviar_pipeline.checkpoint as checkpoint_module

        checkpoint = build_checkpoint(
            run_id="wrong-key",
            completed_step=3,
            compound_input="test",
        )
        save_checkpoint(checkpoint, tmp_path)
        wrong_keys = CheckpointIntegrityKeyRing(
            active_key_id="test-v1",
            _keys={"test-v1": b"different-pipeline-checkpoint-hmac-key-0001"},
        )
        compared = []
        original_compare = checkpoint_module.hmac.compare_digest

        def recording_compare(left, right):
            compared.append((left, right))
            return original_compare(left, right)

        monkeypatch.setattr(checkpoint_module.hmac, "compare_digest", recording_compare)

        with pytest.raises(ValueError, match="integrity authentication failed"):
            load_latest_checkpoint(tmp_path, integrity_keys=wrong_keys)

        assert len(compared) == 1

    @pytest.mark.parametrize(
        ("field_name", "replacement"),
        [
            ("run_id", "other-run"),
            ("completed_step", 4),
            ("checkpoint_sha256", "0" * 64),
            ("patent_hits_sha256", "1" * 64),
            ("trusted_legal_status_cassette_sha256", ["2" * 64]),
        ],
    )
    def test_checkpoint_manifest_field_tampering_fails_authentication(
        self,
        tmp_path,
        field_name,
        replacement,
    ):
        checkpoint = build_checkpoint(
            run_id="tamper-fields",
            completed_step=3,
            compound_input="test",
            patent_hits=[_trusted_checkpoint_hit()],
        )
        save_checkpoint(checkpoint, tmp_path)
        path = tmp_path / "step_3.manifest.json"
        manifest = json.loads(path.read_text())
        manifest[field_name] = replacement
        path.write_text(json.dumps(manifest))

        with pytest.raises(ValueError, match="integrity authentication failed"):
            load_latest_checkpoint(tmp_path)

    def test_checkpoint_key_id_tampering_fails_before_restore_capability(self, tmp_path):
        checkpoint = build_checkpoint(
            run_id="tamper-key-id",
            completed_step=3,
            compound_input="test",
        )
        save_checkpoint(checkpoint, tmp_path)
        path = tmp_path / "step_3.manifest.json"
        manifest = json.loads(path.read_text())
        manifest["key_id"] = "unknown-v9"
        path.write_text(json.dumps(manifest))

        with pytest.raises(ValueError, match="key id is unavailable"):
            load_latest_checkpoint(tmp_path)

    def test_checkpoint_key_rotation_verifies_old_and_signs_new(self, tmp_path):
        old_only = CheckpointIntegrityKeyRing(
            active_key_id="rotation-old",
            _keys={"rotation-old": b"old-pipeline-checkpoint-hmac-key-0000001"},
        )
        checkpoint = build_checkpoint(
            run_id="rotation",
            completed_step=3,
            compound_input="test",
        )
        save_checkpoint(checkpoint, tmp_path, integrity_keys=old_only)

        rotating = CheckpointIntegrityKeyRing(
            active_key_id="rotation-new",
            _keys={
                "rotation-old": b"old-pipeline-checkpoint-hmac-key-0000001",
                "rotation-new": b"new-pipeline-checkpoint-hmac-key-0000001",
            },
        )
        loaded = load_latest_checkpoint(tmp_path, integrity_keys=rotating)
        assert loaded is not None

        loaded.completed_step = 4
        save_checkpoint(loaded, tmp_path, integrity_keys=rotating)
        new_manifest = json.loads((tmp_path / "step_4.manifest.json").read_text())
        assert new_manifest["key_id"] == "rotation-new"

    def test_checkpoint_key_ring_missing_or_short_key_fails_closed(self):
        with pytest.raises(ValueError, match="integrity key is required"):
            CheckpointIntegrityKeyRing.from_secret("")
        with pytest.raises(ValueError, match="at least 32 bytes"):
            CheckpointIntegrityKeyRing.from_secret(
                '{"active_key_id":"short","keys":{"short":"too-short"}}'
            )


class TestBuildCheckpoint:
    """Tests for build_checkpoint helper."""

    def test_build_with_none_values(self):
        ckpt = build_checkpoint(
            run_id="build-test",
            completed_step=1,
            compound_input="test",
        )
        assert ckpt.compound is None
        assert ckpt.patent_hits is None

    def test_build_serializes_pydantic_models(self):
        """Verify Pydantic models are serialized to dicts."""
        from datetime import UTC, datetime

        from praviar_pipeline.models.audit import StepTiming

        timing = StepTiming(
            step_name="step1_resolve",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            duration_seconds=2.5,
            items_processed=1,
            items_output=1,
        )
        ckpt = build_checkpoint(
            run_id="pydantic-test",
            completed_step=1,
            compound_input="test",
            timing_data=[timing],
        )
        assert isinstance(ckpt.timing_data, list)
        assert isinstance(ckpt.timing_data[0], dict)
        assert ckpt.timing_data[0]["step_name"] == "step1_resolve"

    def test_build_serializes_list_of_models(self):
        """Verify lists of Pydantic models are serialized."""
        from praviar_pipeline.models.triage import TriageResult

        results = [
            TriageResult(
                patent_id="US123",
                relevance="relevant",
                reason="Important patent",
                blocking_potential="high",
                key_claims=[1, 2],
                confidence=0.9,
            ),
        ]
        ckpt = build_checkpoint(
            run_id="list-test",
            completed_step=5,
            compound_input="test",
            triage_results=results,
        )
        assert isinstance(ckpt.triage_results[0], dict)
        assert ckpt.triage_results[0]["patent_id"] == "US123"

    def test_build_serializes_full_triage_and_critic_state(self):
        """Verify checkpoint payload keeps non-final triage and critic metadata."""
        from praviar_pipeline.models.critic import CriticReport
        from praviar_pipeline.models.triage import TriageResult

        triage_results = [
            TriageResult(
                patent_id="US123",
                relevance="relevant",
                reason="Blocking composition claim",
                blocking_potential="high",
                key_claims=[1],
                confidence=0.9,
            ),
            TriageResult(
                patent_id="US456",
                relevance="not_relevant",
                reason="Different scaffold",
                blocking_potential="low",
                key_claims=[],
                confidence=0.2,
            ),
        ]
        critic_report = CriticReport(
            overall_quality_score=0.8, patents_flagged_for_revision=["US123"]
        )

        ckpt = build_checkpoint(
            run_id="critic-state",
            completed_step=7,
            compound_input="test",
            triage_results=[triage_results[0]],
            all_triage_results=triage_results,
            critic_report=critic_report,
            critic_input_tokens=123,
            critic_output_tokens=45,
        )

        assert len(ckpt.all_triage_results) == 2
        assert ckpt.critic_report["overall_quality_score"] == 0.8
        assert ckpt.critic_input_tokens == 123
        assert ckpt.critic_output_tokens == 45


class TestRestoreFromCheckpoint:
    """Tests for restore_from_checkpoint."""

    def test_restore_empty_checkpoint(self):
        ckpt = PipelineCheckpoint(
            run_id="empty",
            completed_step=0,
            compound_input="test",
        )
        state = restore_from_checkpoint(ckpt)
        assert state["compound"] is None
        assert state["patent_hits"] == []
        assert state["analyses"] == []
        assert state["triage_input_tokens"] == 0

    def test_restore_with_triage_data(self):
        ckpt = PipelineCheckpoint(
            run_id="triage-restore",
            completed_step=5,
            compound_input="test",
            triage_results=[
                {
                    "patent_id": "US789",
                    "relevance": "relevant",
                    "reason": "test reason",
                    "blocking_potential": "medium",
                    "key_claims": [1],
                    "confidence": 0.85,
                }
            ],
            triage_input_tokens=3000,
            triage_output_tokens=800,
        )
        state = restore_from_checkpoint(ckpt)
        assert len(state["triage_results"]) == 1
        assert state["triage_results"][0].patent_id == "US789"
        assert state["triage_input_tokens"] == 3000

    def test_restore_with_full_triage_and_critic_state(self):
        ckpt = PipelineCheckpoint(
            run_id="critic-restore",
            completed_step=7,
            compound_input="test",
            triage_results=[
                {
                    "patent_id": "US789",
                    "relevance": "relevant",
                    "reason": "Primary blocking patent",
                    "blocking_potential": "high",
                    "key_claims": [1],
                    "confidence": 0.85,
                }
            ],
            all_triage_results=[
                {
                    "patent_id": "US789",
                    "relevance": "relevant",
                    "reason": "Primary blocking patent",
                    "blocking_potential": "high",
                    "key_claims": [1],
                    "confidence": 0.85,
                },
                {
                    "patent_id": "US999",
                    "relevance": "not_relevant",
                    "reason": "No overlapping limitations",
                    "blocking_potential": "low",
                    "key_claims": [],
                    "confidence": 0.1,
                },
            ],
            critic_report={
                "findings": [],
                "patents_reviewed": 1,
                "patents_flagged_for_revision": ["US789"],
                "overall_quality_score": 0.75,
                "portfolio_level_observations": ["Needs stronger claim support"],
                "input_tokens": 111,
                "output_tokens": 22,
            },
            critic_input_tokens=111,
            critic_output_tokens=22,
        )

        state = restore_from_checkpoint(ckpt)

        assert len(state["triage_results"]) == 1
        assert len(state["all_triage_results"]) == 2
        assert state["critic_report"] is not None
        assert state["critic_report"].overall_quality_score == 0.75
        assert state["critic_input_tokens"] == 111
        assert state["critic_output_tokens"] == 22

    def test_full_save_restore_roundtrip(self, tmp_path):
        """Build → save → load → restore roundtrip."""
        from praviar_pipeline.models.triage import TriageResult

        tr = TriageResult(
            patent_id="US100",
            relevance="possibly_relevant",
            reason="Might be relevant",
            blocking_potential="low",
            key_claims=[3],
            confidence=0.6,
        )
        ckpt = build_checkpoint(
            run_id="full-roundtrip",
            completed_step=5,
            compound_input="aspirin",
            execution_profile="world_class_adaptive",
            triage_results=[tr],
            triage_input_tokens=2000,
            matter_graph={
                "nodes": [
                    {
                        "node_id": "compound:aspirin",
                        "node_type": "compound_variant",
                        "label": "aspirin",
                    }
                ],
                "edges": [],
            },
            matter_graph_summary={"root_compound": "aspirin", "node_count": 1},
            evidence_artifacts=[
                {
                    "artifact_id": "artifact-1",
                    "artifact_type": "verification",
                    "source_name": "step7_verification",
                }
            ],
            evidence_adapter_results=[
                {
                    "adapter_name": "step7_verification",
                    "adapter_kind": "pipeline",
                    "authority_tier": "supporting",
                    "status": "ok",
                    "artifacts": [],
                }
            ],
        )
        save_checkpoint(ckpt, tmp_path)
        loaded = load_latest_checkpoint(tmp_path)
        state = restore_from_checkpoint(loaded)
        assert len(state["triage_results"]) == 1
        assert state["triage_results"][0].patent_id == "US100"
        assert state["triage_results"][0].confidence == 0.6
        assert state["matter_graph"].nodes[0].node_id == "compound:aspirin"
        assert state["matter_graph_summary"].root_compound == "aspirin"
        assert state["evidence_artifacts"][0].artifact_id == "artifact-1"
        assert state["evidence_adapter_results"][0].adapter_name == "step7_verification"

    def test_direct_patent_hit_roundtrip_remains_untrusted(self):
        hit = _trusted_checkpoint_hit()
        assert has_trusted_legal_status_provenance(hit)

        restored = PatentHit.model_validate_json(hit.model_dump_json())

        assert not has_trusted_legal_status_provenance(restored)

    def test_integrity_validated_save_load_restore_rehydrates_trust(self, tmp_path):
        hit = _trusted_checkpoint_hit()
        checkpoint = build_checkpoint(
            run_id="trusted-restore",
            completed_step=3,
            compound_input="test",
            patent_hits=[hit],
        )
        save_checkpoint(checkpoint, tmp_path)

        loaded = load_latest_checkpoint(tmp_path)
        assert loaded is not None
        restored_hit = restore_from_checkpoint(loaded)["patent_hits"][0]

        assert has_trusted_legal_status_provenance(restored_hit)

    def test_signed_checkpoint_rehydrates_conflicting_status_observations(
        self,
        tmp_path,
    ):
        hit = _conflicted_checkpoint_hit()
        assert len(trusted_legal_status_observations(hit)) == 2
        checkpoint = build_checkpoint(
            run_id="trusted-conflict-restore",
            completed_step=3,
            compound_input="test",
            patent_hits=[hit],
        )
        save_checkpoint(checkpoint, tmp_path)

        loaded = load_latest_checkpoint(tmp_path)
        assert loaded is not None
        restored_hit = restore_from_checkpoint(loaded)["patent_hits"][0]

        assert len(trusted_legal_status_observations(restored_hit)) == 2
        assert trusted_legal_status_conflict(restored_hit) == (
            LegalStatus.ACTIVE,
            LegalStatus.REVOKED,
        )
        assert restored_hit.legal_status == LegalStatus.UNKNOWN
        assert restored_hit.legal_status_provenance is None

    def test_checkpoint_cannot_promote_preexisting_untrusted_provenance(self, tmp_path):
        untrusted_hit = PatentHit.model_validate_json(_trusted_checkpoint_hit().model_dump_json())
        assert not has_trusted_legal_status_provenance(untrusted_hit)
        checkpoint = build_checkpoint(
            run_id="untrusted-cassette",
            completed_step=3,
            compound_input="test",
            patent_hits=[untrusted_hit],
        )
        save_checkpoint(checkpoint, tmp_path)

        loaded = load_latest_checkpoint(tmp_path)
        assert loaded is not None
        restored_hit = restore_from_checkpoint(loaded)["patent_hits"][0]

        assert not has_trusted_legal_status_provenance(restored_hit)

    def test_manifest_cannot_promote_deserialized_provenance(self, tmp_path):
        untrusted_hit = PatentHit.model_validate_json(_trusted_checkpoint_hit().model_dump_json())
        assert not has_trusted_legal_status_provenance(untrusted_hit)
        checkpoint = build_checkpoint(
            run_id="untrusted-manifest-cassette",
            completed_step=3,
            compound_input="test",
            patent_hits=[untrusted_hit],
        )
        save_checkpoint(checkpoint, tmp_path)
        manifest_path = tmp_path / "step_3.manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["trusted_legal_status_cassette_sha256"] = [
            untrusted_hit.legal_status_provenance.cassette_sha256
        ]
        manifest_path.write_text(json.dumps(manifest))

        with pytest.raises(ValueError, match="integrity authentication failed"):
            load_latest_checkpoint(tmp_path)

    def test_loaded_checkpoint_mutation_invalidates_restore_capability(self, tmp_path):
        checkpoint = build_checkpoint(
            run_id="mutated-after-load",
            completed_step=3,
            compound_input="test",
            patent_hits=[_trusted_checkpoint_hit()],
        )
        save_checkpoint(checkpoint, tmp_path)
        loaded = load_latest_checkpoint(tmp_path)
        assert loaded is not None
        loaded.patent_hits[0]["title"] = "mutated after integrity validation"

        with pytest.raises(PermissionError, match="capability is invalid"):
            restore_from_checkpoint(loaded)

    @pytest.mark.parametrize(
        ("field_name", "replacement", "message"),
        [
            ("artifact_payload", {"status": "active"}, "retained artifact hash mismatch"),
            ("collector_version", "forged-version", "collector version is not trusted"),
            (
                "retrieved_at",
                (datetime.now(UTC) - timedelta(days=31)).isoformat(),
                "provenance is stale",
            ),
        ],
    )
    def test_manifest_valid_but_invalid_provenance_fails_restore(
        self,
        tmp_path,
        field_name,
        replacement,
        message,
    ):
        checkpoint = build_checkpoint(
            run_id=f"invalid-{field_name}",
            completed_step=3,
            compound_input="test",
            patent_hits=[_trusted_checkpoint_hit()],
        )
        checkpoint.patent_hits[0]["legal_status_provenance"][field_name] = replacement
        save_checkpoint(checkpoint, tmp_path)
        loaded = load_latest_checkpoint(tmp_path)
        assert loaded is not None

        with pytest.raises(ValueError, match=message):
            restore_from_checkpoint(loaded)

    def test_checkpoint_restore_capability_and_reattestation_are_callsite_confined(self):
        from praviar_pipeline.models.patent import (
            _issue_checkpoint_restore_capability,
            _restore_checkpoint_legal_status_attestation,
        )

        checkpoint = build_checkpoint(
            run_id="confined",
            completed_step=3,
            compound_input="test",
            patent_hits=[_trusted_checkpoint_hit()],
        )
        with pytest.raises(PermissionError, match="loader-private"):
            _issue_checkpoint_restore_capability(
                checkpoint,
                checkpoint_sha256="0" * 64,
                patent_hits_sha256="0" * 64,
                trusted_claim_text_cassette_sha256=frozenset(),
                trusted_legal_status_cassette_sha256=frozenset(),
            )
        with pytest.raises(PermissionError, match="callsite-private"):
            _restore_checkpoint_legal_status_attestation(
                _trusted_checkpoint_hit(),
                checkpoint=checkpoint,
                checkpoint_restore_capability=object(),
            )
