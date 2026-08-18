"""Tests for SG-123 deterministic post-LLM integrity checks.

Covers every check's happy path + failure path, plus an aggregated
integration test and a verification-flow test that confirms block-severity
violations raise ``ReportIntegrityError``.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.errors import ReportIntegrityError
from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.report_sections import (
    DeterministicCheckResult,
    ReportSection,
    VerificationReport,
)
from praviar_pipeline.models.verification import VerificationResult
from praviar_pipeline.pipeline.report.deterministic_checks import (
    VALID_JURISDICTION_CODES,
    _check_assignee_non_empty,
    _check_chemical_formula_parses,
    _check_citation_existence,
    _check_claim_count_sanity,
    _check_claim_verbatim,
    _check_date_in_term,
    _check_element_count_sum,
    _check_jurisdiction_code_valid,
    _check_patent_id_format,
    _check_risk_level_monotonic,
    _Context,
    run_deterministic_checks,
)
from praviar_pipeline.pipeline.report_data_store import ReportDataStore

# ── Fixtures ─────────────────────────────────────────────────────────────


def _compound() -> ResolvedCompound:
    return ResolvedCompound(
        name="aspirin",
        canonical_smiles="CC(=O)OC1=CC=CC=C1C(=O)O",
        cas_numbers=["50-78-2"],
        original_input="aspirin",
        input_type="name",
    )


def _analysis(
    patent_id: str = "US10000001B2",
    risk: RiskLevel = RiskLevel.HIGH,
    assignee: str = "Acme Corp",
    expiry: date | None = date(2030, 6, 15),
    elements: list[tuple[int, ElementStatus]] | None = None,
) -> PatentAnalysis:
    if elements is None:
        elements = [(1, ElementStatus.MET), (2, ElementStatus.NOT_MET)]
    statuses = {status for _, status in elements}
    if ElementStatus.NOT_MET in statuses:
        overall_status = ElementStatus.NOT_MET
    elif ElementStatus.UNCLEAR in statuses:
        overall_status = ElementStatus.UNCLEAR
    elif ElementStatus.PARTIALLY_MET in statuses:
        overall_status = ElementStatus.PARTIALLY_MET
    else:
        overall_status = ElementStatus.MET
    return PatentAnalysis(
        patent_id=patent_id,
        title="Test Patent",
        assignee=assignee,
        expiry_date=expiry,
        risk_level=risk,
        risk_summary=f"{risk.value} risk",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                overall_status=overall_status,
                preamble="A compound",
                elements=[
                    ClaimElement(
                        element_number=n,
                        element_text=f"element {n}",
                        status=s,
                        reasoning="x",
                    )
                    for n, s in elements
                ],
            ),
        ],
    )


def _store(
    analyses: list[PatentAnalysis] | None = None,
    overall_risk: RiskLevel = RiskLevel.HIGH,
    patent_hits: list | None = None,
) -> ReportDataStore:
    store = ReportDataStore(
        compound=_compound(),
        analyses=analyses or [_analysis()],
        doe_assessments=[],
        invalidity_assessments=[],
        verification=VerificationResult(),
        patent_hits=patent_hits,
        overall_risk=overall_risk,
    )
    return store


def _section(
    content: str, section_id: str = "body", patents: list[str] | None = None
) -> ReportSection:
    return ReportSection(
        section_id=section_id,
        section_title=section_id.title(),
        content=content,
        patents_referenced=patents or [],
        word_count=max(1, len(content.split())),
    )


def _ctx(sections: list[ReportSection], store: ReportDataStore) -> _Context:
    return _Context(
        sections=sections,
        data_store=store,
        full_text="\n\n".join(s.content for s in sections if s.word_count > 0),
    )


# ── Citation existence ───────────────────────────────────────────────────


class TestCitationExistence:
    def test_happy_path(self):
        store = _store()
        sections = [_section("See US10000001B2 for details.")]
        result = _check_citation_existence(_ctx(sections, store))
        assert result.passed
        assert result.violations == []

    def test_unknown_patent_id_redacts(self):
        store = _store()
        sections = [_section("See US10000001B2 and the unknown US9999999B2.")]
        result = _check_citation_existence(_ctx(sections, store))
        assert not result.passed
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.severity == "redact"
        assert "US9999999B2" in v.detail


# ── Claim verbatim ──────────────────────────────────────────────────────


class TestClaimVerbatim:
    def _patent_hit(self, pid: str, claims_text: str):
        from praviar_pipeline.models.patent import PatentHit
        from praviar_pipeline.models.patent_lineage import PatentSource

        return PatentHit(
            patent_id=pid,
            title="T",
            claims_text=claims_text,
            sources=[PatentSource.PUBCHEM],
        )

    def test_happy_path(self):
        pid = "US10000001B2"
        claim_text = "1. A method of treating pain comprising administering aspirin per claim 1 of the preceding."
        store = _store(patent_hits=[self._patent_hit(pid, claim_text)])
        sections = [
            _section(
                'The patent states: "A method of treating pain comprising administering aspirin per claim 1 of the preceding." exactly.',
                patents=[pid],
            )
        ]
        result = _check_claim_verbatim(_ctx(sections, store))
        assert result.passed

    def test_mismatch_redacts(self):
        pid = "US10000001B2"
        claim_text = "1. A method of treating pain comprising administering aspirin per claim 1."
        store = _store(patent_hits=[self._patent_hit(pid, claim_text)])
        sections = [
            _section(
                'The patent states: "A method of treating cancer comprising administering doxorubicin per claim 1 of the invention."',
                patents=[pid],
            )
        ]
        result = _check_claim_verbatim(_ctx(sections, store))
        assert not result.passed
        assert result.violations[0].severity == "redact"


# ── Chemical formula ─────────────────────────────────────────────────────


class TestChemicalFormulaParses:
    def test_happy_path_valid_smiles(self):
        store = _store()
        # Compound canonical SMILES alone should pass.
        sections = [_section("Aspirin is our target.")]
        result = _check_chemical_formula_parses(_ctx(sections, store))
        # Either passes entirely, or only failure would be RDKit-missing warn.
        assert result.passed or all("RDKit not available" in v.detail for v in result.violations)

    def test_invalid_smiles_warns(self):
        store = _store()
        sections = [_section("Invalid token C(=O(XYZ[Q])) appears here.")]
        result = _check_chemical_formula_parses(_ctx(sections, store))
        # If RDKit is available, we should get at least one warn violation.
        try:
            from rdkit import Chem  # noqa: F401

            rdkit_available = True
        except ImportError:
            rdkit_available = False
        if rdkit_available:
            assert any(v.severity == "warn" for v in result.violations)


# ── Date in term ─────────────────────────────────────────────────────────


class TestDateInTerm:
    def _patent_hit(self, pid: str, filing: date, expiry: date):
        from praviar_pipeline.models.patent import PatentHit
        from praviar_pipeline.models.patent_lineage import PatentSource

        return PatentHit(
            patent_id=pid,
            title="T",
            sources=[PatentSource.PUBCHEM],
            filing_date=filing,
            expiry_date=expiry,
        )

    def test_happy_path_in_term(self):
        pid = "US10000001B2"
        store = _store(
            analyses=[_analysis(patent_id=pid, expiry=date(2030, 6, 15))],
            patent_hits=[self._patent_hit(pid, date(2010, 1, 1), date(2030, 6, 15))],
        )
        sections = [_section(f"{pid} was granted 2015-03-01 and expires 2030-06-15.")]
        result = _check_date_in_term(_ctx(sections, store))
        assert result.passed

    def test_out_of_term_warns(self):
        pid = "US10000001B2"
        store = _store(
            analyses=[_analysis(patent_id=pid, expiry=date(2030, 6, 15))],
            patent_hits=[self._patent_hit(pid, date(2010, 1, 1), date(2030, 6, 15))],
        )
        sections = [_section(f"{pid} was mentioned for 2099-12-31 in the filing.")]
        result = _check_date_in_term(_ctx(sections, store))
        assert not result.passed
        assert result.violations[0].severity == "warn"


# ── Jurisdiction code ────────────────────────────────────────────────────


class TestJurisdictionCode:
    def test_happy_path(self):
        store = _store()
        sections = [_section("The application was filed in: US and granted in: EP.")]
        result = _check_jurisdiction_code_valid(_ctx(sections, store))
        assert result.passed

    def test_unknown_code_warns(self):
        store = _store()
        # Use an unknown country-code-like token that matches the regex.
        sections = [_section("Filed in: XX by the applicant.")]
        result = _check_jurisdiction_code_valid(_ctx(sections, store))
        assert not result.passed
        assert result.violations[0].severity == "warn"
        assert "XX" in result.violations[0].detail

    def test_valid_codes_set_covers_wipo_jurisdictions(self):
        for code in ("US", "EP", "WO", "JP", "KR", "CN"):
            assert code in VALID_JURISDICTION_CODES


# ── Patent ID format ─────────────────────────────────────────────────────


class TestPatentIdFormat:
    def test_happy_path(self):
        store = _store()
        sections = [_section("See US10000001B2 for the canonical grant.")]
        result = _check_patent_id_format(_ctx(sections, store))
        assert result.passed

    def test_malformed_id_warns(self):
        store = _store()
        # EP123456A1 matches mention regex (EP + 6+ digits) but fails the
        # strict EP format regex which requires exactly 7 digits.
        sections = [_section("The application EP123456A1 was cited.")]
        result = _check_patent_id_format(_ctx(sections, store))
        assert any(v.severity == "warn" and v.location.startswith("EP") for v in result.violations)


# ── Assignee non empty ───────────────────────────────────────────────────


class TestAssigneeNonEmpty:
    def test_happy_path(self):
        store = _store()
        result = _check_assignee_non_empty(_ctx([], store))
        assert result.passed

    def test_empty_assignee_warns(self):
        store = _store(analyses=[_analysis(assignee="")])
        result = _check_assignee_non_empty(_ctx([], store))
        assert not result.passed
        assert result.violations[0].severity == "warn"


# ── Claim count sanity ───────────────────────────────────────────────────


class TestClaimCountSanity:
    def _patent_hit(self, pid: str, total_claims: int):
        from praviar_pipeline.models.patent import PatentHit
        from praviar_pipeline.models.patent_lineage import PatentSource

        hit = PatentHit(
            patent_id=pid,
            title="T",
            sources=[PatentSource.PUBCHEM],
        )
        # Inject total_claims via model_dump; PatentHit doesn't have it, so we
        # extend the patent_details dict directly through the data store.
        return hit, total_claims

    def test_happy_path(self):
        pid = "US10000001B2"
        analysis = _analysis(patent_id=pid)
        store = _store(analyses=[analysis])
        # Directly inject a patent detail with total_claims >= analyzed.
        store._patent_details[pid] = {"total_claims": 20}
        result = _check_claim_count_sanity(_ctx([], store))
        assert result.passed

    def test_over_count_blocks(self):
        pid = "US10000001B2"
        analysis = _analysis(patent_id=pid)
        store = _store(analyses=[analysis])
        store._patent_details[pid] = {"total_claims": 0}  # 0 < 1 analyzed
        # _get_total_claims returns None for 0 — inject a realistic small count
        store._patent_details[pid] = {"total_claims": 0, "num_claims": 0}
        # Use a value that the helper WILL accept (positive int).
        store._patent_details[pid] = {"claim_count": 0}
        # None of the above trip; use a legitimate exceed scenario: two claims analyzed vs total=1.
        analysis.claims_analyzed.append(
            ClaimAnalysis(
                claim_number=2,
                claim_type="dependent",
                depends_on=1,
                overall_status=ElementStatus.MET,
                elements=[],
            )
        )
        store._patent_details[pid] = {"total_claims": 1}
        result = _check_claim_count_sanity(_ctx([], store))
        assert not result.passed
        assert result.violations[0].severity == "block"


# ── Element count sum ────────────────────────────────────────────────────


class TestElementCountSum:
    def test_happy_path(self):
        store = _store()
        result = _check_element_count_sum(_ctx([], store))
        assert result.passed

    def test_sum_mismatch_blocks(self):
        # Craft an analysis whose element statuses don't cover all buckets.
        # Since every ElementStatus value is classified, we force a mismatch
        # by mutating the model to include an unknown status enum via
        # bypass. Simpler: patch ElementStatus set. Use monkey-patched
        # elements list with an object that looks like a ClaimElement but
        # has a status not in our bucket sets.
        from praviar_pipeline.pipeline.report import deterministic_checks as dc

        class _FakeElement:
            def __init__(self):
                self.status = "weirdo"  # not in MET/NOT_MET/PARTIAL/UNCLEAR

        class _FakeClaim:
            claim_number = 1

            def __init__(self):
                self.elements = [_FakeElement(), _FakeElement()]

        class _FakeAnalysis:
            patent_id = "US1"

            def __init__(self):
                self.claims_analyzed = [_FakeClaim()]

        class _FakeStore:
            overall_risk = RiskLevel.HIGH
            compound = None

            def all_analyses(self):
                return [_FakeAnalysis()]

            def all_patent_ids(self):
                return set()

            def get_patent_detail(self, pid):
                return None

        ctx = dc._Context(sections=[], data_store=_FakeStore(), full_text="")
        result = dc._check_element_count_sum(ctx)
        assert not result.passed
        assert result.violations[0].severity == "block"


# ── Risk level monotonic ─────────────────────────────────────────────────


class TestRiskLevelMonotonic:
    def test_happy_path(self):
        store = _store(
            analyses=[_analysis(risk=RiskLevel.HIGH), _analysis("US2", risk=RiskLevel.LOW)],
            overall_risk=RiskLevel.HIGH,
        )
        result = _check_risk_level_monotonic(_ctx([], store))
        assert result.passed

    def test_downgraded_overall_blocks(self):
        store = _store(
            analyses=[_analysis(risk=RiskLevel.HIGH)],
            overall_risk=RiskLevel.LOW,
        )
        result = _check_risk_level_monotonic(_ctx([], store))
        assert not result.passed
        assert result.violations[0].severity == "block"


# ── Integration: aggregated results ──────────────────────────────────────


class TestRunDeterministicChecks:
    def test_all_checks_run_and_all_pass_on_clean_report(self):
        store = _store()
        sections = [_section("All systems nominal. US10000001B2 is the primary hit.")]
        results = run_deterministic_checks(sections, store, raise_on_block=False)
        assert len(results) == 10
        names = {r.check_name for r in results}
        assert {
            "citation_existence",
            "claim_verbatim",
            "chemical_formula_parses",
            "date_in_term",
            "jurisdiction_code_valid",
            "patent_id_format",
            "assignee_non_empty",
            "claim_count_sanity",
            "element_count_sum",
            "risk_level_monotonic",
        } == names

    def test_aggregated_violations_distinct_severities_without_raise(self):
        # Empty assignee → warn. Unknown citation → redact. Downgraded overall → block.
        analyses = [
            _analysis(assignee=""),  # warn
        ]
        store = _store(analyses=analyses, overall_risk=RiskLevel.LOW)  # block
        sections = [_section("Ghost citation US9999999B2 appears here.")]  # redact

        results = run_deterministic_checks(sections, store, raise_on_block=False)
        severities = {v.severity for r in results for v in r.violations}
        assert "warn" in severities
        assert "redact" in severities
        assert "block" in severities

    def test_block_violation_raises_by_default(self):
        store = _store(overall_risk=RiskLevel.LOW)  # block: HIGH analysis, LOW overall
        with pytest.raises(ReportIntegrityError) as excinfo:
            run_deterministic_checks([_section("x")], store)
        assert excinfo.value.violations
        assert any(v["severity"] == "block" for v in excinfo.value.violations)

    def test_checker_exception_blocks_by_default(self):
        def crashing_check(_ctx):
            raise RuntimeError("boom")

        with (
            patch(
                "praviar_pipeline.pipeline.report.deterministic_checks._ALL_CHECKS",
                (crashing_check,),
            ),
            pytest.raises(ReportIntegrityError) as excinfo,
        ):
            run_deterministic_checks([_section("x")], _store())

        assert any(
            v["severity"] == "block" and v["detail"] == "check failed: RuntimeError"
            for v in excinfo.value.violations
        )

    def test_checker_exception_collected_as_block_without_raise(self):
        def crashing_check(_ctx):
            raise RuntimeError("boom")

        with patch(
            "praviar_pipeline.pipeline.report.deterministic_checks._ALL_CHECKS",
            (crashing_check,),
        ):
            results = run_deterministic_checks(
                [_section("x")],
                _store(),
                raise_on_block=False,
            )

        assert len(results) == 1
        assert results[0].violations[0].severity == "block"
        assert results[0].violations[0].detail == "check failed: RuntimeError"


# ── Verification flow integration ────────────────────────────────────────


class TestVerificationFlowIntegration:
    @pytest.mark.asyncio
    async def test_block_severity_raises_report_integrity_error_via_flow(self):
        from praviar_pipeline.pipeline.report.verification_flow import (
            _run_report_verification_flow,
        )

        sections = [_section("Some body text mentioning US10000001B2.")]
        store = _store(overall_risk=RiskLevel.LOW)  # triggers risk_level_monotonic block

        fake_report = VerificationReport(
            total_claims_checked=1,
            claims_correct=1,
            overall_assessment="PASS",
            factual_accuracy_rate=1.0,
        )

        with (
            patch(
                "praviar_pipeline.pipeline.report.verification_flow.verify_report",
                new=AsyncMock(return_value=(fake_report, 10, 5)),
            ),
            pytest.raises(ReportIntegrityError),
        ):
            await _run_report_verification_flow(
                claude=object(),
                sections=sections,
                data_store=store,
                total_input=0,
                total_output=0,
            )

    @pytest.mark.asyncio
    async def test_results_attached_when_no_block(self):
        from praviar_pipeline.pipeline.report.verification_flow import (
            _run_report_verification_flow,
        )

        sections = [_section("Body mentioning US10000001B2.")]
        store = _store()  # clean: overall=HIGH, analysis HIGH

        fake_report = VerificationReport(
            total_claims_checked=1,
            claims_correct=1,
            overall_assessment="PASS",
            factual_accuracy_rate=1.0,
        )

        with patch(
            "praviar_pipeline.pipeline.report.verification_flow.verify_report",
            new=AsyncMock(return_value=(fake_report, 10, 5)),
        ):
            result = await _run_report_verification_flow(
                claude=object(),
                sections=sections,
                data_store=store,
                total_input=0,
                total_output=0,
            )
        assert len(result.verification_report.deterministic_check_results) == 10
        assert all(
            isinstance(r, DeterministicCheckResult)
            for r in result.verification_report.deterministic_check_results
        )
