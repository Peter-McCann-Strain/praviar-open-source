from __future__ import annotations

import base64
import io
import struct
import zipfile
import zlib
from datetime import UTC, datetime, timedelta

import pytest
from praviar_pipeline.checkpoint import (
    DEV_CHECKPOINT_HMAC_KEYRING_SECRET,
    CheckpointIntegrityKeyRing,
)

from api.schemas.analyses import AnalysisConfigSchema
from api.schemas.markush_evidence import (
    MarkushEvidenceImportRequest,
    MarkushEvidenceVerifyRequest,
)
from api.services.markush_evidence import (
    build_analyst_markush_draft,
    verify_analyst_markush_draft,
)


def _xlsx_fixture() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as workbook:
        workbook.writestr("[Content_Types].xml", "<Types/>")
        workbook.writestr("xl/workbook.xml", "<workbook/>")
    return buffer.getvalue()


def _png_fixture(*, width: int = 640, height: int = 360) -> bytes:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + name
            + payload
            + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rows = b"".join(b"\x00" + (b"\xff\xff\xff\xff" * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


_ARTIFACT = _xlsx_fixture()
_CONTROLS = _png_fixture()
_QUERY = "CC(=O)OC1=CC=CC=C1C(=O)O"
_ORG_ID = "00000000-0000-4000-8000-000000000001"
_INTEGRITY_KEYS = CheckpointIntegrityKeyRing.from_secret(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)


def _import_request() -> MarkushEvidenceImportRequest:
    return MarkushEvidenceImportRequest(
        query_structure=_QUERY,
        target_structure=_QUERY,
        query_role="target_compound",
        chemical_search_mode="substructure",
        markush_method="formula_matching",
        markush_match_mode="substructure",
        wipo_query_field=None,
        family_grouping_enabled=True,
        executed_at=datetime.now(UTC) - timedelta(minutes=5),
        artifact_base64=base64.b64encode(_ARTIFACT).decode(),
        artifact_filename="patentscope-results.xlsx",
        artifact_media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        controls_artifact_base64=base64.b64encode(_CONTROLS).decode(),
        controls_artifact_filename="patentscope-controls.png",
        controls_artifact_media_type="image/png",
        result_count=2,
        selected_publication_ids=["WO-2020123456-A1", "EP-1234567-B1"],
        limitations=["PATENTSCOPE does not document a stable chemical-search workbook schema."],
    )


def _verify_request(
    draft,
) -> MarkushEvidenceVerifyRequest:
    assert draft.executed_at is not None
    assert draft.artifact_filename is not None
    assert draft.artifact_media_type is not None
    assert draft.controls_artifact_filename is not None
    assert draft.controls_artifact_media_type is not None
    assert draft.result_count is not None
    return MarkushEvidenceVerifyRequest(
        draft_receipt=draft,
        query_structure=_QUERY,
        target_structure=_QUERY,
        query_role=draft.query_role,
        chemical_search_mode=draft.chemical_search_mode,
        markush_method=draft.markush_method,
        markush_match_mode=draft.markush_match_mode,
        wipo_query_field=draft.wipo_query_field,
        family_grouping_enabled=draft.family_grouping_enabled,
        executed_at=draft.executed_at,
        artifact_base64=base64.b64encode(_ARTIFACT).decode(),
        artifact_filename=draft.artifact_filename,
        artifact_media_type=draft.artifact_media_type,
        controls_artifact_base64=base64.b64encode(_CONTROLS).decode(),
        controls_artifact_filename=draft.controls_artifact_filename,
        controls_artifact_media_type=draft.controls_artifact_media_type,
        result_count=draft.result_count,
        selected_publication_ids=draft.selected_publication_ids,
    )


def test_two_actor_workflow_rehashes_and_verifies_original_evidence() -> None:
    draft = build_analyst_markush_draft(
        _import_request(),
        analyst_user_id="analyst-1",
        analyst_org_id=_ORG_ID,
        integrity_keys=_INTEGRITY_KEYS,
    )

    assert draft.status == "incomplete"
    assert draft.analyst_identity == "user:analyst-1"
    assert draft.reviewer_identity is None
    assert draft.chemical_search_mode == "substructure"
    assert draft.markush_method == "formula_matching"
    assert draft.markush_match_mode == "substructure"
    assert draft.wipo_query_field is None

    verified = verify_analyst_markush_draft(
        _verify_request(draft),
        reviewer_user_id="reviewer-2",
        reviewer_org_id=_ORG_ID,
        integrity_keys=_INTEGRITY_KEYS,
    )

    assert verified.status == "verified_manual"
    assert verified.analyst_identity == "user:analyst-1"
    assert verified.reviewer_identity == "user:reviewer-2"
    assert verified.imported_artifact_sha256 == draft.imported_artifact_sha256
    assert verified.query_structure_sha256 == draft.query_structure_sha256
    assert verified.selected_publication_ids_sha256 == draft.selected_publication_ids_sha256


def test_workflow_rejects_same_actor_artifact_change_and_query_change() -> None:
    draft = build_analyst_markush_draft(
        _import_request(),
        analyst_user_id="analyst-1",
        analyst_org_id=_ORG_ID,
        integrity_keys=_INTEGRITY_KEYS,
    )
    same_actor = _verify_request(draft)
    with pytest.raises(ValueError, match="must be distinct"):
        verify_analyst_markush_draft(
            same_actor,
            reviewer_user_id="analyst-1",
            reviewer_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )

    changed_artifact = same_actor.model_copy(
        update={"artifact_base64": base64.b64encode(b"changed").decode()}
    )
    with pytest.raises(ValueError, match="artifact digest"):
        verify_analyst_markush_draft(
            changed_artifact,
            reviewer_user_id="reviewer-2",
            reviewer_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )

    forged_draft = draft.model_copy(update={"attestation_hmac_sha256": "0" * 64})
    with pytest.raises(ValueError, match="attestation is invalid"):
        verify_analyst_markush_draft(
            same_actor.model_copy(update={"draft_receipt": forged_draft}),
            reviewer_user_id="reviewer-2",
            reviewer_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )

    changed_query = same_actor.model_copy(update={"query_structure": "CCO"})
    with pytest.raises(ValueError, match="query structure"):
        verify_analyst_markush_draft(
            changed_query,
            reviewer_user_id="reviewer-2",
            reviewer_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )

    changed_target = same_actor.model_copy(update={"target_structure": "CCO"})
    with pytest.raises(ValueError, match="target structure"):
        verify_analyst_markush_draft(
            changed_target,
            reviewer_user_id="reviewer-2",
            reviewer_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )

    changed_controls = same_actor.model_copy(
        update={
            "controls_artifact_base64": base64.b64encode(
                b"\x89PNG\r\n\x1a\n" + b"different controls capture"
            ).decode()
        }
    )
    with pytest.raises(ValueError, match="controls artifact digest"):
        verify_analyst_markush_draft(
            changed_controls,
            reviewer_user_id="reviewer-2",
            reviewer_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )

    with pytest.raises(ValueError, match="organization boundaries"):
        verify_analyst_markush_draft(
            same_actor,
            reviewer_user_id="reviewer-2",
            reviewer_org_id="00000000-0000-4000-8000-000000000099",
            integrity_keys=_INTEGRITY_KEYS,
        )

    changed_affirmation = same_actor.model_copy(update={"family_grouping_enabled": False})
    with pytest.raises(ValueError, match="search-control affirmation"):
        verify_analyst_markush_draft(
            changed_affirmation,
            reviewer_user_id="reviewer-2",
            reviewer_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )


def test_import_rejects_malformed_or_oversized_base64() -> None:
    malformed = _import_request().model_copy(update={"artifact_base64": "not-base64!"})
    with pytest.raises(ValueError, match="malformed"):
        build_analyst_markush_draft(
            malformed,
            analyst_user_id="analyst-1",
            analyst_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )

    oversized = _import_request().model_copy(
        update={"artifact_base64": base64.b64encode(b"x" * (25 * 1024 * 1024 + 1)).decode()}
    )
    with pytest.raises(ValueError, match="exceeds 25 MiB"):
        build_analyst_markush_draft(
            oversized,
            analyst_user_id="analyst-1",
            analyst_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )


def test_import_rejects_arbitrary_files_and_stale_redating_attempts() -> None:
    arbitrary_text = _import_request().model_copy(
        update={
            "artifact_base64": base64.b64encode(b"ordinary search fabricated fixture").decode(),
            "artifact_filename": "ordinary.txt",
            "artifact_media_type": "text/plain",
        }
    )
    with pytest.raises(ValueError, match="must be an XLSX export"):
        build_analyst_markush_draft(
            arbitrary_text,
            analyst_user_id="analyst-1",
            analyst_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )

    fake_controls = _import_request().model_copy(
        update={
            "controls_artifact_base64": base64.b64encode(
                b"not a screenshot of the search controls"
            ).decode()
        }
    )
    with pytest.raises(ValueError, match="must be a valid PNG"):
        build_analyst_markush_draft(
            fake_controls,
            analyst_user_id="analyst-1",
            analyst_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )

    stale = _import_request().model_copy(
        update={"executed_at": datetime.now(UTC) - timedelta(hours=25)}
    )
    with pytest.raises(ValueError, match="imported within 24 hours"):
        build_analyst_markush_draft(
            stale,
            analyst_user_id="analyst-1",
            analyst_org_id=_ORG_ID,
            integrity_keys=_INTEGRITY_KEYS,
        )


def test_analysis_clients_cannot_disable_or_age_extend_markush_gate() -> None:
    with pytest.raises(ValueError):
        AnalysisConfigSchema(require_verified_manual_markush=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        AnalysisConfigSchema(markush_evidence_max_age_days=180)  # type: ignore[arg-type]
