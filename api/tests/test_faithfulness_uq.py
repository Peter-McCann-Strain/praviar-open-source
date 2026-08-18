"""Tests for the Faithfulness-Aware UQ shadow scorer (T3-02).

Source paper: arXiv:2505.21072 (Vashurin, Fadeeva et al., May 2025) -
"Faithfulness-Aware Uncertainty Quantification for Fact-Checking the Output
of Retrieval Augmented Generation".

The unit test mocks the Anthropic client and verifies the scoring function
classifies a known ENTAILED pair correctly. The optional diagnostic runs the
real Claude Haiku model against five deterministic synthetic pairs; it checks
only that the configured integration can execute and emit well-formed verdicts.
The sample is not an accuracy, performance, or product-effect benchmark. It is
skipped unless ``PRAVIAR_FAITHFULNESS_UQ_ENABLED`` is set in the environment.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from conftest import bind_report_data, valid_report_data

from api.db.models import AnalysisStatus
from api.services.faithfulness_uq import (
    FAITHFULNESS_MODEL_ID,
    is_feature_enabled,
    iter_evidence_pairs,
    score_pair,
    score_report,
)


def _make_fake_anthropic_response(payload: dict) -> SimpleNamespace:
    """Mimic the shape of ``anthropic.Anthropic().messages.create`` output."""
    block = SimpleNamespace(text=json.dumps(payload))
    return SimpleNamespace(content=[block])


def _make_mock_client(responses: list[dict]) -> MagicMock:
    """Return a MagicMock client whose messages.create returns each payload
    from ``responses`` in order."""
    client = MagicMock()
    client.messages.create.side_effect = [
        _make_fake_anthropic_response(payload) for payload in responses
    ]
    return client


def test_is_feature_enabled_defaults_to_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the env var, the feature flag is off and no behaviour changes."""
    monkeypatch.delenv("PRAVIAR_FAITHFULNESS_UQ_ENABLED", raising=False)
    assert is_feature_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_is_feature_enabled_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("PRAVIAR_FAITHFULNESS_UQ_ENABLED", value)
    assert is_feature_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_is_feature_enabled_falsey_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("PRAVIAR_FAITHFULNESS_UQ_ENABLED", value)
    assert is_feature_enabled() is False


def test_score_pair_entailed_known_case() -> None:
    """Mocked Claude Haiku returns ENTAILED; verify the parsed verdict."""
    client = _make_mock_client([{"verdict": "ENTAILED", "confidence": 0.92}])
    result = score_pair(
        claim_sentence=(
            "The compound aspirin is acetylsalicylic acid, a salicylate "
            "derivative used as an anti-inflammatory."
        ),
        evidence_span=(
            "Aspirin (acetylsalicylic acid) is the prototype of a class of "
            "drugs known as the salicylates and is widely used for its "
            "anti-inflammatory properties."
        ),
        client=client,
    )
    assert result.verdict == "ENTAILED"
    assert 0.0 <= result.confidence <= 1.0
    assert result.confidence == pytest.approx(0.92)
    assert result.model_id == FAITHFULNESS_MODEL_ID

    # The classifier must have been invoked once with the expected model id.
    client.messages.create.assert_called_once()
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == FAITHFULNESS_MODEL_ID


def test_score_pair_contradicted_case() -> None:
    """Mocked classifier returns CONTRADICTS; verify normalisation passes."""
    client = _make_mock_client([{"verdict": "CONTRADICTS", "confidence": 0.81}])
    result = score_pair(
        claim_sentence="The patent expressly covers all aryl-substituted variants.",
        evidence_span=(
            "The patent's claim 1 explicitly disclaims aryl substituents and "
            "restricts the scope to alkyl substituents only."
        ),
        client=client,
    )
    assert result.verdict == "CONTRADICTS"
    assert result.confidence == pytest.approx(0.81)


def test_score_pair_handles_garbled_response_as_neutral() -> None:
    """If the model returns non-JSON, fall back to NEUTRAL with low confidence."""
    block = SimpleNamespace(text="I am not sure about this pair.")
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(content=[block])
    result = score_pair(
        claim_sentence="The compound is a salt.",
        evidence_span="No data.",
        client=client,
    )
    assert result.verdict == "NEUTRAL"
    assert result.confidence == 0.0


def test_score_pair_handles_client_exception_as_neutral() -> None:
    """Shadow-mode passes never abort the pipeline on a single bad call."""
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("network down")
    result = score_pair(
        claim_sentence="The compound is a salt.",
        evidence_span="Sodium chloride is a salt.",
        client=client,
    )
    assert result.verdict == "NEUTRAL"
    assert result.confidence == 0.0


def test_iter_evidence_pairs_extracts_from_report_data() -> None:
    """Walk a realistic report_data shape and yield only non-empty pairs."""
    report_data = {
        "patent_analyses": [
            {
                "patent_id": "US12345678A1",
                "claims_analyzed": [
                    {
                        "claim_number": 1,
                        "elements": [
                            {
                                "element_number": 1,
                                "element_text": "A compound of formula I.",
                                "evidence": (
                                    "Claim 1: A compound of formula I, "
                                    "comprising at least one aryl substituent."
                                ),
                                "reasoning": (
                                    "Compound aspirin matches formula I via "
                                    "its salicylate backbone."
                                ),
                            },
                            {
                                "element_number": 2,
                                "element_text": "Said compound being a salt.",
                                "evidence": "",  # skipped: empty evidence
                                "reasoning": "",
                            },
                        ],
                    }
                ],
            }
        ]
    }
    pairs = list(iter_evidence_pairs(report_data))
    assert len(pairs) == 1
    assert pairs[0].finding_index == 0
    assert pairs[0].evidence_index == 0
    assert "aspirin matches formula I" in pairs[0].claim_sentence
    assert "comprising at least one aryl substituent" in pairs[0].evidence_span


def test_iter_evidence_pairs_handles_missing_fields() -> None:
    """Malformed report_data must not raise."""
    assert list(iter_evidence_pairs(None)) == []
    assert list(iter_evidence_pairs({})) == []
    assert list(iter_evidence_pairs({"patent_analyses": [None, {}]})) == []


def test_score_report_caps_pairs() -> None:
    """``max_pairs`` should limit the number of model calls."""
    report_data = {
        "patent_analyses": [
            {
                "claims_analyzed": [
                    {
                        "elements": [
                            {
                                "element_text": f"claim {i}",
                                "evidence": f"evidence {i}",
                                "reasoning": f"reasoning {i}",
                            }
                            for i in range(5)
                        ]
                    }
                ]
            }
        ]
    }
    client = _make_mock_client([{"verdict": "ENTAILED", "confidence": 0.7} for _ in range(2)])
    results = score_report(report_data=report_data, client=client, max_pairs=2)
    assert len(results) == 2
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Worker persistence path — compute_faithfulness_scores_impl.
#
# faithfulness_scores carries an org_isolation RLS policy whose WITH CHECK
# clause rejects any INSERT made while app.current_org_id is unset. The worker
# must therefore bind the tenant context before persisting. This test asserts
# the transaction-local setting is issued and precedes the row INSERTs.
#
# The advisory lock is now held on a dedicated engine connection (lock_conn)
# separate from the main Session.  _make_lock_engine() produces a mock sync
# engine whose .connect() context manager yields a lock_conn that returns the
# desired pg_try_advisory_lock scalar.
# ---------------------------------------------------------------------------


def _make_lock_engine(lock_acquired: bool) -> MagicMock:
    """Return a mock sync engine whose .connect() yields the given lock result."""
    lock_result = MagicMock()
    lock_result.scalar.return_value = lock_acquired
    lock_conn = MagicMock()
    lock_conn.execute.return_value = lock_result
    conn_ctx = MagicMock()
    conn_ctx.__enter__.return_value = lock_conn
    conn_ctx.__exit__.return_value = False
    engine = MagicMock()
    engine.connect.return_value = conn_ctx
    return engine


def test_compute_faithfulness_scores_binds_supplied_org_before_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the advisory lock is busy, the Session must never be opened.

    The lock is acquired on a dedicated connection before opening the main
    Session.  If the lock is not available the worker returns early without
    touching the regular DB session at all.
    """
    import uuid

    from api.workers import task_faithfulness

    analysis_id = uuid.uuid4()
    session_calls: list[str] = []

    def _session_factory(_engine: object) -> MagicMock:
        session_calls.append("opened")
        return MagicMock()

    monkeypatch.setattr(task_faithfulness, "Session", _session_factory)
    monkeypatch.setenv("PRAVIAR_FAITHFULNESS_UQ_ENABLED", "1")

    result = task_faithfulness.compute_faithfulness_scores_impl(
        engine=_make_lock_engine(lock_acquired=False),
        analysis_id=str(analysis_id),
        org_id=str(uuid.uuid4()),
    )

    assert result["status"] == "already_running"
    assert not session_calls, "Session must not be opened when the advisory lock is busy"


def test_compute_faithfulness_scores_binds_org_context_before_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker binds app.current_org_id before adding faithfulness rows."""
    import uuid

    from api.workers import task_faithfulness

    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    report_data = valid_report_data()
    bind_report_data(report_data, analysis_id=analysis_id, org_id=org_id)
    fake_analysis = SimpleNamespace(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report_data,
    )

    # Record every execute / commit on the mocked session, in order.
    calls: list[tuple[str, str]] = []
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    def _execute(stmt, *args, **kwargs):  # noqa: ARG001
        statement = str(stmt)
        calls.append(("execute", statement))
        if "count" in statement.lower():
            return count_result
        return MagicMock()

    db = MagicMock()
    db.get.return_value = fake_analysis
    db.execute.side_effect = _execute
    db.commit.side_effect = lambda: calls.append(("commit", ""))

    session_cm = MagicMock()
    session_cm.__enter__.return_value = db
    session_cm.__exit__.return_value = False
    monkeypatch.setattr(task_faithfulness, "Session", lambda _engine: session_cm)

    monkeypatch.setenv("PRAVIAR_FAITHFULNESS_UQ_ENABLED", "1")

    pair = SimpleNamespace(
        finding_index=0,
        evidence_index=0,
        claim_sentence="The compound is a salicylate.",
        evidence_span="Aspirin is a salicylate.",
    )
    verdict = SimpleNamespace(verdict="ENTAILED", confidence=0.9, model_id=FAITHFULNESS_MODEL_ID)
    score_report_mock = MagicMock(return_value=[(pair, verdict)])
    monkeypatch.setattr("api.services.faithfulness_uq.score_report", score_report_mock)

    result = task_faithfulness.compute_faithfulness_scores_impl(
        engine=_make_lock_engine(lock_acquired=True),
        analysis_id=str(analysis_id),
        org_id=str(org_id),
        client_factory=lambda _key: MagicMock(),
        settings_factory=lambda: SimpleNamespace(anthropic_api_key="test-key"),
    )

    assert result["status"] == "completed"
    assert result["scored"] == 1
    assert score_report_mock.call_args.kwargs["report_data"] is fake_analysis.report_data

    # Rows are now inserted via pg_insert(...).on_conflict_do_nothing() rather than
    # db.add(), so verify ordering via the execute call that contains "INSERT".
    set_local_idx = next(
        i
        for i, (kind, payload) in enumerate(calls)
        if kind == "execute" and "set_config" in payload
    )
    first_insert_idx = next(
        i
        for i, (kind, payload) in enumerate(calls)
        if kind == "execute" and "INSERT" in payload.upper()
    )
    assert set_local_idx < first_insert_idx, "RLS binding must precede the row INSERTs"


def test_compute_faithfulness_scores_skips_when_duplicate_task_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A concurrent worker must not duplicate paid faithfulness model calls."""
    import uuid

    from api.workers import task_faithfulness

    analysis_id = uuid.uuid4()
    db = MagicMock()
    session_cm = MagicMock()
    session_cm.__enter__.return_value = db
    session_cm.__exit__.return_value = False
    monkeypatch.setattr(task_faithfulness, "Session", lambda _engine: session_cm)
    monkeypatch.setenv("PRAVIAR_FAITHFULNESS_UQ_ENABLED", "1")
    score_report = MagicMock()
    client_factory = MagicMock()
    monkeypatch.setattr("api.services.faithfulness_uq.score_report", score_report)

    result = task_faithfulness.compute_faithfulness_scores_impl(
        engine=_make_lock_engine(lock_acquired=False),
        analysis_id=str(analysis_id),
        org_id=str(uuid.uuid4()),
        client_factory=client_factory,
        settings_factory=lambda: SimpleNamespace(anthropic_api_key="test-key"),
    )

    assert result == {
        "status": "already_running",
        "analysis_id": str(analysis_id),
        "scored": 0,
    }
    db.get.assert_not_called()
    client_factory.assert_not_called()
    score_report.assert_not_called()


def test_compute_faithfulness_scores_skips_when_model_scores_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate delivery should reuse persisted scores instead of calling the model."""
    import uuid

    from api.workers import task_faithfulness

    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    fake_analysis = SimpleNamespace(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=valid_report_data(),
    )
    count_result = MagicMock()
    count_result.scalar.return_value = 7

    def _execute(stmt, *args, **kwargs):  # noqa: ARG001
        statement = str(stmt)
        if "count" in statement.lower():
            return count_result
        return MagicMock()

    db = MagicMock()
    db.get.return_value = fake_analysis
    db.execute.side_effect = _execute
    session_cm = MagicMock()
    session_cm.__enter__.return_value = db
    session_cm.__exit__.return_value = False
    monkeypatch.setattr(task_faithfulness, "Session", lambda _engine: session_cm)
    monkeypatch.setenv("PRAVIAR_FAITHFULNESS_UQ_ENABLED", "1")
    score_report = MagicMock()
    client_factory = MagicMock()
    monkeypatch.setattr("api.services.faithfulness_uq.score_report", score_report)

    result = task_faithfulness.compute_faithfulness_scores_impl(
        engine=_make_lock_engine(lock_acquired=True),
        analysis_id=str(analysis_id),
        org_id=str(org_id),
        client_factory=client_factory,
        settings_factory=lambda: SimpleNamespace(anthropic_api_key="test-key"),
    )

    assert result == {
        "status": "already_scored",
        "analysis_id": str(analysis_id),
        "scored": 7,
    }
    client_factory.assert_not_called()
    score_report.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_compute_faithfulness_scores_skips_unpublishable_report_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shadow scoring must not derive model inputs from unsafe report payloads."""
    import uuid

    from api.workers import task_faithfulness

    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    report = valid_report_data()
    report["verification_summary"]["claims_incorrect"] = 1
    fake_analysis = SimpleNamespace(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    def _execute(stmt, *args, **kwargs):  # noqa: ARG001
        statement = str(stmt)
        if "count" in statement.lower():
            return count_result
        return MagicMock()

    db = MagicMock()
    db.get.return_value = fake_analysis
    db.execute.side_effect = _execute
    session_cm = MagicMock()
    session_cm.__enter__.return_value = db
    session_cm.__exit__.return_value = False
    monkeypatch.setattr(task_faithfulness, "Session", lambda _engine: session_cm)
    monkeypatch.setenv("PRAVIAR_FAITHFULNESS_UQ_ENABLED", "1")
    score_report_mock = MagicMock()
    client_factory = MagicMock()
    monkeypatch.setattr("api.services.faithfulness_uq.score_report", score_report_mock)

    result = task_faithfulness.compute_faithfulness_scores_impl(
        engine=_make_lock_engine(lock_acquired=True),
        analysis_id=str(analysis_id),
        org_id=str(org_id),
        client_factory=client_factory,
        settings_factory=lambda: SimpleNamespace(anthropic_api_key="test-key"),
    )

    assert result == {
        "status": "unpublishable_report",
        "analysis_id": str(analysis_id),
        "scored": 0,
    }
    client_factory.assert_not_called()
    score_report_mock.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Real-model diagnostic — only runs when the flag is set.
#
# Synthetic Praviar-shaped sample of five (claim, evidence) pairs: three
# unambiguously ENTAILED, two unambiguously CONTRADICTS. This smoke fixture is
# deliberately too small and synthetic to support an accuracy or effect claim.
#
# Skipping rules:
#   - ``PRAVIAR_FAITHFULNESS_UQ_ENABLED`` must be set (matches the production
#     gate; CI runs the mock-based tests above but never burns real tokens).
#   - ``ANTHROPIC_API_KEY`` must be present in the settings.
# ---------------------------------------------------------------------------


SYNTHETIC_PAIRS: list[tuple[str, str, str]] = [
    (
        "ENTAILED",
        "Aspirin is acetylsalicylic acid, a salicylate used for its "
        "anti-inflammatory and antiplatelet effects.",
        "Aspirin (acetylsalicylic acid) is the prototype of the salicylate "
        "drug class and is widely used for its anti-inflammatory and "
        "antiplatelet activity.",
    ),
    (
        "ENTAILED",
        "Claim 1 of US12345678 covers any pharmaceutical composition "
        "comprising the compound of formula I in a unit dosage form.",
        "Claim 1: A pharmaceutical composition comprising a compound of "
        "formula I, formulated as a unit dosage form.",
    ),
    (
        "ENTAILED",
        "The patent application has a priority date of 2018-03-15.",
        "Application US12/345,678 was filed on 15 March 2018 claiming priority "
        "from provisional 61/987,654 filed 16 March 2017.",
    ),
    (
        "CONTRADICTS",
        "The patent expressly covers all aryl-substituted variants of the compound of formula I.",
        "Claim 1 explicitly disclaims aryl substituents and restricts the "
        "scope to alkyl substituents only.",
    ),
    (
        "CONTRADICTS",
        "The compound is described as a stable solid at room temperature.",
        "The compound was found to decompose rapidly above 0 degrees Celsius, "
        "rendering room-temperature storage impossible without refrigeration.",
    ),
]


def _real_anthropic_available() -> bool:
    if not is_feature_enabled():
        return False
    try:
        from api.config import get_settings
    except Exception:  # noqa: BLE001
        return False
    api_key = getattr(get_settings(), "anthropic_api_key", "") or ""
    return bool(api_key)


@pytest.mark.skipif(
    not _real_anthropic_available(),
    reason=(
        "Real Claude Haiku benchmark only runs when "
        "PRAVIAR_FAITHFULNESS_UQ_ENABLED is set and ANTHROPIC_API_KEY is "
        "configured."
    ),
)
def test_faithfulness_uq_real_model_diagnostic() -> None:
    """Exercise the real-model integration without claiming measured quality."""
    import anthropic

    from api.config import get_settings

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

    correct = 0
    results = []
    for expected, claim, evidence in SYNTHETIC_PAIRS:
        verdict = score_pair(claim_sentence=claim, evidence_span=evidence, client=client)
        results.append((expected, verdict.verdict, verdict.confidence))
        if verdict.verdict == expected:
            correct += 1

    assert len(results) == len(SYNTHETIC_PAIRS)
    assert all(verdict in {"ENTAILED", "CONTRADICTS", "UNCERTAIN"} for _, verdict, _ in results)
    assert all(0.0 <= confidence <= 1.0 for _, _, confidence in results)
    # Retain the match count only as diagnostic output on failure. It is not a
    # release threshold or evidence that the paper's reported effect transfers.
    assert 0 <= correct <= len(SYNTHETIC_PAIRS)
