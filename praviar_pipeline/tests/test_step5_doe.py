from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from praviar_pipeline.errors import DoEAssessmentError
from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.equivalents import (
    ChemicalEquivalenceContext,
    ClaimAmendment,
    EstoppelResult,
    FWRAssessment,
    ProsecutionHistory,
    RejectionRecord,
)
from praviar_pipeline.pipeline import assess_equivalents
from praviar_pipeline.pipeline.doe.candidates import (
    find_doe_candidates,
    rank_and_limit_candidates,
)
from praviar_pipeline.pipeline.doe.estoppel import check_estoppel
from praviar_pipeline.pipeline.doe.fwr import (
    build_fwr_user_prompt,
    build_prosecution_context_summary,
    derive_fwr_confidence,
    map_confidence_band,
)
from praviar_pipeline.pipeline.step5_doe import _build_prosecution_summaries


def _make_analysis(
    patent_id: str,
    risk_level: RiskLevel,
    statuses: list[ElementStatus],
) -> PatentAnalysis:
    return PatentAnalysis(
        patent_id=patent_id,
        title=f"Patent {patent_id}",
        assignee="Test Assignee",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[
                    ClaimElement(
                        element_number=index + 1,
                        element_text=f"Element {index + 1}",
                        status=status,
                        reasoning=f"Reason {index + 1}",
                        confidence=0.9,
                    )
                    for index, status in enumerate(statuses)
                ],
                overall_status=ElementStatus.NOT_MET,
                overall_confidence=0.8,
            )
        ],
        risk_level=risk_level,
        risk_summary="summary",
    )


@pytest.mark.asyncio
async def test_candidate_failure_aborts_doe_step_without_partial_output(monkeypatch) -> None:
    analyses = [_make_analysis("US-FAIL", RiskLevel.HIGH, [ElementStatus.NOT_MET])]
    settings = SimpleNamespace(
        max_doe_candidates=10,
        doe_concurrency=1,
        doe_fwr_scale=0.8,
        doe_fwr_boost=0.1,
        doe_fwr_fallback=0.3,
        doe_fwr_cap=0.8,
        doe_confidence_high=0.65,
        doe_confidence_moderate=0.4,
    )

    async def fake_check_estoppel(_patent_id: str) -> EstoppelResult:
        return EstoppelResult(estoppel_applies=False)

    async def fail_fwr(*_args, **_kwargs):
        raise RuntimeError("provider-secret-and-customer-claim")

    class FakeClaudeClient:
        def load_prompt(self, _name: str) -> str:
            return "system prompt"

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe.get_settings", lambda: settings)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe._check_estoppel", fake_check_estoppel)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe._assess_fwr", fail_fwr)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe.ClaudeClient", FakeClaudeClient)

    with pytest.raises(DoEAssessmentError) as exc_info:
        await assess_equivalents(
            analyses,
            SimpleNamespace(name="test", canonical_smiles="", molecular_formula=""),
        )

    assert exc_info.value.failure_types == ("RuntimeError",)
    assert "provider-secret" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_find_doe_candidates_includes_low_risk_near_misses() -> None:
    high = _make_analysis(
        "US-HIGH",
        RiskLevel.HIGH,
        [ElementStatus.MET, ElementStatus.NOT_MET, ElementStatus.PARTIALLY_MET],
    )
    low = _make_analysis("US-LOW", RiskLevel.LOW, [ElementStatus.NOT_MET])

    candidates = find_doe_candidates([high, low])

    assert candidates == [
        {
            "patent_id": "US-HIGH",
            "claim_number": 1,
            "element_number": 2,
            "element_text": "Element 2",
            "element_reasoning": "Reason 2",
        },
        {
            "patent_id": "US-HIGH",
            "claim_number": 1,
            "element_number": 3,
            "element_text": "Element 3",
            "element_reasoning": "Reason 3",
        },
        {
            "patent_id": "US-LOW",
            "claim_number": 1,
            "element_number": 1,
            "element_text": "Element 1",
            "element_reasoning": "Reason 1",
        },
    ]


def test_rank_and_limit_candidates_prioritizes_high_risk() -> None:
    analyses = [
        _make_analysis("US-MED", RiskLevel.MEDIUM, [ElementStatus.NOT_MET]),
        _make_analysis("US-HIGH", RiskLevel.HIGH, [ElementStatus.NOT_MET]),
    ]
    candidates = find_doe_candidates(analyses)

    ranked = rank_and_limit_candidates(candidates, analyses, max_candidates=1)

    assert [candidate["patent_id"] for candidate in ranked] == ["US-HIGH"]


@pytest.mark.asyncio
async def test_check_estoppel_detects_narrowing_amendments(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(_: str) -> ProsecutionHistory:
        return ProsecutionHistory(
            patent_id="US123",
            application_number="123/456",
            amendments=[
                ClaimAmendment(
                    claim_number=1,
                    amendment_date=date(2020, 1, 2),
                    narrowing=True,
                    response_to_rejection=True,
                    patentability_related=True,
                    surrendered_scope="microorganisms outside the amended genus",
                    festo_rebuttal="not_established",
                )
            ],
            rejections=[
                RejectionRecord(rejection_type="103"),
                RejectionRecord(rejection_type="103"),
            ],
            prosecution_complete=True,
        )

    monkeypatch.setattr(
        "praviar_pipeline.pipeline.doe.estoppel.fetch_prosecution_history",
        fake_fetch,
    )

    result = await check_estoppel("US123")

    assert result.estoppel_applies is True
    assert result.prosecution_narrowing_count == 1
    assert result.rejections_found == ["103"]
    assert "microorganisms outside the amended genus" in result.surrendered_scope


def test_build_fwr_user_prompt_includes_best_structure(succinic_acid) -> None:
    candidate = {
        "patent_id": "US123",
        "claim_number": 1,
        "element_number": 2,
        "element_text": "fermenting Mannheimia",
        "element_reasoning": "Target process uses E. coli",
    }

    class StubDrawingEvidence:
        def has_structures(self, patent_id: str) -> bool:
            return patent_id == "US123"

        def get_structures(self, patent_id: str, min_tanimoto: float) -> list[SimpleNamespace]:
            assert patent_id == "US123"
            assert min_tanimoto == 0.2
            return [
                SimpleNamespace(
                    canonical_smiles="CCO",
                    tanimoto_to_target=0.51,
                    is_substructure_of_target=False,
                    target_is_substructure=False,
                ),
                SimpleNamespace(
                    canonical_smiles="CCC",
                    tanimoto_to_target=0.88,
                    is_substructure_of_target=True,
                    target_is_substructure=False,
                ),
            ]

    prompt = build_fwr_user_prompt(candidate, succinic_acid, StubDrawingEvidence())

    assert "STRUCTURAL SIMILARITY EVIDENCE" in prompt
    assert "SMILES: CCC" in prompt
    assert "0.880" in prompt
    assert "substructure relationship exists" in prompt


def test_confidence_mapping_applies_boosts(mock_settings) -> None:
    from praviar_pipeline.config import get_settings

    settings = get_settings()
    fwr = FWRAssessment(
        same_function=True,
        function_reasoning="same function",
        same_way=True,
        way_reasoning="same way",
        same_result=True,
        result_reasoning="same result",
        equivalent=True,
        chemical_context=ChemicalEquivalenceContext(
            structural_relationship="salt_form",
            known_interchangeability=True,
        ),
    )

    confidence = derive_fwr_confidence(fwr, settings)

    assert confidence == settings.doe_fwr_cap
    assert map_confidence_band(confidence, settings) == "HIGH"


@pytest.mark.asyncio
async def test_assess_equivalents_dedupes_estoppel_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    analyses = [
        _make_analysis(
            "US123",
            RiskLevel.HIGH,
            [ElementStatus.NOT_MET, ElementStatus.PARTIALLY_MET],
        )
    ]
    settings = SimpleNamespace(
        max_doe_candidates=10,
        doe_concurrency=2,
        doe_fwr_scale=0.8,
        doe_fwr_boost=0.1,
        doe_fwr_fallback=0.3,
        doe_fwr_cap=0.8,
        doe_confidence_high=0.65,
        doe_confidence_moderate=0.4,
    )
    seen_patents: list[str] = []

    async def fake_check_estoppel(patent_id: str):
        seen_patents.append(patent_id)
        return EstoppelResult(
            estoppel_applies=True,
            amendments_found=[],
            surrendered_scope="",
            file_wrapper_available=True,
            rejections_found=[],
            prosecution_narrowing_count=1,
        )

    async def fake_assess_fwr(*args, **kwargs):
        raise AssertionError("FWR should not run when estoppel applies")

    class FakeClaudeClient:
        def load_prompt(self, _: str) -> str:
            return "system prompt"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe.get_settings", lambda: settings)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe._check_estoppel", fake_check_estoppel)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe._assess_fwr", fake_assess_fwr)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe.ClaudeClient", FakeClaudeClient)

    assessments, input_tokens, output_tokens = await assess_equivalents(
        analyses,
        SimpleNamespace(name="test", canonical_smiles="CCO", molecular_formula="C2H6O"),
    )

    assert len(assessments) == 2
    assert input_tokens == 0
    assert output_tokens == 0
    assert seen_patents == ["US123"]
    assert all(not assessment.overall_equivalent for assessment in assessments)


def test_build_prosecution_context_summary_renders_festo_signals() -> None:
    """SG-121: the dossier helper must expose narrowing amendments for Festo."""
    context = {
        "office_action_count": 2,
        "amendment_entry_count": 1,
        "rejection_bases": ["103", "112"],
        "estoppel_risk_flags": [
            "prior_art_rejection_history",
            "amendment_after_office_action_history",
        ],
        "narrowing_claim_numbers": [1, 4],
        "rejected_claim_numbers": [1, 2, 3],
        "amendments": "- 2007-08-15 RESPONSE: Amendment narrowed 'antifolate' to 'pemetrexed disodium'",
        "office_actions": "- 2007-05-01 NON_FINAL: 103 rejection over Akimoto",
    }

    rendered = build_prosecution_context_summary(context)

    assert "Office actions: 2" in rendered
    assert "103" in rendered and "112" in rendered
    assert "narrowed claims: 1, 4" in rendered
    assert "prior_art_rejection_history" in rendered
    assert "pemetrexed disodium" in rendered
    assert build_prosecution_context_summary(None) == ""
    assert build_prosecution_context_summary({}) == ""


def test_build_prosecution_summaries_is_us_only() -> None:
    cache = {
        "US-7772209": {
            "office_action_count": 1,
            "amendment_entry_count": 1,
            "narrowing_claim_numbers": [1],
            "amendments": "- narrowed antifolate to pemetrexed disodium",
        },
        "EP-123": {
            "office_action_count": 5,
            "amendments": "- EP amendment — out of scope",
        },
    }

    summaries = _build_prosecution_summaries(["US-7772209", "EP-123", "US-NOCACHE"], cache)

    assert "US-7772209" in summaries
    assert "EP-123" not in summaries, "non-US patents must not receive a dossier"
    assert "US-NOCACHE" not in summaries
    assert "pemetrexed disodium" in summaries["US-7772209"]


@pytest.mark.asyncio
async def test_assess_equivalents_passes_prosecution_dossier_to_fwr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SG-121 regression: DoE must wire the US file-wrapper dossier into the FWR call.

    Mirrors the pemetrexed / Eli Lilly v. Hospira scenario: a narrowing amendment
    from 'antifolate' to 'pemetrexed disodium' is in the prosecution cache; the
    DoE step must hand that context to the FWR prompt and mark the assessment
    reasoning so auditors can see the dossier was consulted.
    """
    analyses = [
        _make_analysis(
            "US-7772209",  # the Eli Lilly v. Hospira pemetrexed patent
            RiskLevel.HIGH,
            [ElementStatus.NOT_MET],
        )
    ]

    prosecution_cache = {
        "US-7772209": {
            "office_action_count": 1,
            "amendment_entry_count": 1,
            "rejection_bases": ["103"],
            "estoppel_risk_flags": ["prior_art_rejection_history"],
            "narrowing_claim_numbers": [1],
            "amendments": "- 2007-08-15 RESPONSE: narrowed 'antifolate' to 'pemetrexed disodium'",
            "office_actions": "- 2007-05-01 NON_FINAL: 103 rejection over Akimoto",
        }
    }

    settings = SimpleNamespace(
        max_doe_candidates=10,
        doe_concurrency=2,
        doe_fwr_scale=0.8,
        doe_fwr_boost=0.1,
        doe_fwr_fallback=0.3,
        doe_fwr_cap=0.8,
        doe_confidence_high=0.65,
        doe_confidence_moderate=0.4,
    )

    async def fake_check_estoppel(patent_id: str) -> EstoppelResult:
        # Estoppel fetch returned no narrowing amendments — exercise the path
        # where FWR *still runs* and must receive the dossier context.
        return EstoppelResult(
            estoppel_applies=False,
            file_wrapper_available=True,
        )

    captured_kwargs: dict = {}

    async def fake_assess_fwr(claude, candidate, compound, system_prompt, **kwargs):
        captured_kwargs.update(kwargs)
        captured_kwargs["patent_id"] = candidate["patent_id"]
        fwr = FWRAssessment(
            same_function=True,
            function_reasoning="same active moiety",
            same_way=True,
            way_reasoning="dissociates to pemetrexed anions",
            same_result=True,
            result_reasoning="same therapeutic outcome",
            equivalent=True,
        )
        return fwr, {"input_tokens": 10, "output_tokens": 5}

    class FakeClaudeClient:
        def load_prompt(self, _: str) -> str:
            return "system prompt"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe.get_settings", lambda: settings)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe._check_estoppel", fake_check_estoppel)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe._assess_fwr", fake_assess_fwr)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe.ClaudeClient", FakeClaudeClient)

    assessments, input_tokens, output_tokens = await assess_equivalents(
        analyses,
        SimpleNamespace(
            name="pemetrexed",
            canonical_smiles="N[C@@H](CCc1[nH]c2nc(N)[nH]c(=O)c2c1C)C(=O)O",
            molecular_formula="C20H21N5O6",
        ),
        prosecution_cache=prosecution_cache,
    )

    assert len(assessments) == 1
    # The dossier summary must have been passed to the FWR call.
    prosecution_context = captured_kwargs.get("prosecution_context")
    assert prosecution_context, "prosecution_context missing from FWR call"
    assert "pemetrexed disodium" in prosecution_context
    assert "narrowed claims: 1" in prosecution_context
    # The assessment reasoning carries an audit marker so downstream audit
    # trails (checkpoints, report) can confirm the file wrapper was consulted.
    assert "[prosecution_dossier=consulted]" in assessments[0].reasoning
    assert input_tokens == 10
    assert output_tokens == 5


@pytest.mark.asyncio
async def test_assess_equivalents_continues_without_dossier_for_non_us_and_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-US patents and cache misses must not receive a dossier; DoE proceeds."""
    analyses = [
        _make_analysis("EP-123", RiskLevel.HIGH, [ElementStatus.NOT_MET]),
        _make_analysis("US-9999999", RiskLevel.HIGH, [ElementStatus.NOT_MET]),
    ]

    settings = SimpleNamespace(
        max_doe_candidates=10,
        doe_concurrency=2,
        doe_fwr_scale=0.8,
        doe_fwr_boost=0.1,
        doe_fwr_fallback=0.3,
        doe_fwr_cap=0.8,
        doe_confidence_high=0.65,
        doe_confidence_moderate=0.4,
    )

    async def fake_check_estoppel(patent_id: str) -> EstoppelResult:
        return EstoppelResult(estoppel_applies=False, file_wrapper_available=False)

    captured_contexts: dict[str, str | None] = {}

    async def fake_assess_fwr(claude, candidate, compound, system_prompt, **kwargs):
        captured_contexts[candidate["patent_id"]] = kwargs.get("prosecution_context")
        fwr = FWRAssessment(
            same_function=False,
            function_reasoning="-",
            same_way=False,
            way_reasoning="-",
            same_result=False,
            result_reasoning="-",
            equivalent=False,
        )
        return fwr, {"input_tokens": 0, "output_tokens": 0}

    class FakeClaudeClient:
        def load_prompt(self, _: str) -> str:
            return "system prompt"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe.get_settings", lambda: settings)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe._check_estoppel", fake_check_estoppel)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe._assess_fwr", fake_assess_fwr)
    monkeypatch.setattr("praviar_pipeline.pipeline.step5_doe.ClaudeClient", FakeClaudeClient)

    # No prosecution cache passed (or empty) — flow must continue safely.
    assessments, _inp, _out = await assess_equivalents(
        analyses,
        SimpleNamespace(name="x", canonical_smiles="CCO", molecular_formula="C2H6O"),
        prosecution_cache=None,
    )

    assert len(assessments) == 2
    assert captured_contexts == {"EP-123": None, "US-9999999": None}
    # Without a dossier, the audit marker is absent.
    assert all("[prosecution_dossier=consulted]" not in a.reasoning for a in assessments)
