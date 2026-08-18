"""Tests for the agentic search loop (wrapping Steps 2-3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from praviar_pipeline.models.patent import (
    PatentFamily,
    PatentFamilyMember,
    PatentHit,
    PatentSource,
)
from praviar_pipeline.models.report_common import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.models.search_loop import (
    CoverageAssessment,
    CoverageGap,
    SearchIterationLog,
    SearchLoopResult,
)
from praviar_pipeline.models.triage import Relevance, TriageResult

# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------


class TestCoverageGap:
    def test_basic_creation(self):
        gap = CoverageGap(
            gap_type="missing_assignee",
            description="Major pharma company not found",
            suggested_action="Search for Pfizer patents",
        )
        assert gap.gap_type == "missing_assignee"

    def test_gap_type_normalization(self):
        gap = CoverageGap(gap_type="Missing Assignee", description="test")
        assert gap.gap_type == "missing_assignee"

    def test_empty_gap(self):
        gap = CoverageGap()
        assert gap.gap_type == ""
        assert gap.description == ""


class TestCoverageAssessment:
    def test_basic_creation(self):
        assessment = CoverageAssessment(
            coverage_adequate=True,
            confidence=0.85,
            iteration_summary="Good coverage",
        )
        assert assessment.coverage_adequate is True
        assert assessment.confidence == 0.85


class TestCoverageContext:
    def test_build_coverage_context_includes_clearance_policy(self):
        from praviar_pipeline.models.report import (
            EvidenceCollectionDirective,
            EvidenceDirectivePriority,
        )
        from praviar_pipeline.pipeline.search_loop import build_coverage_context

        compound = MagicMock()
        compound.name = "aspirin"
        compound.canonical_smiles = "CC(=O)OC1=CC=CC=C1C(=O)O"
        compound.inchi = "InChI=1S/C9H8O4"
        compound.molecular_weight = 180.16
        queries = ExpandedSearchQueries(patent_synonyms=["aspirin"])
        source_health = MagicMock()
        source_health.entries = []

        context = build_coverage_context(
            compound,
            queries,
            source_health,
            1,
            search_stats="search stats",
            triage_stats="triage stats",
            clearance_policy={
                "matter_type": "small_molecule",
                "jurisdiction_policy": "us_ep_core",
                "clearance_threshold_profile": "world_class_us_ep",
                "source_authority_policy": "official_plus_licensed",
                "required_record_components": ["claims_text", "family_context"],
            },
            known_record_gaps=["missing family coverage"],
            collection_directives=[
                EvidenceCollectionDirective(
                    directive_id="expand_family_context:US1234567B2",
                    directive_type="expand_family_context",
                    priority=EvidenceDirectivePriority.HIGH,
                    target_patent_ids=["US1234567B2"],
                    recommended_adapters=["epo_register"],
                    summary="Expand family coverage.",
                    rationale="Family context matters.",
                )
            ],
            matter_graph_summary={
                "root_compound": "aspirin",
                "node_count": 4,
                "edge_count": 3,
                "node_counts_by_type": {"compound_variant": 1, "patent": 2, "family": 1},
                "edge_counts_by_type": {"roots": 2, "belongs_to_family": 1},
                "patent_node_ids": ["patent:US1234567B2", "patent:EP2345678B1"],
                "family_node_ids": ["family:fam-1"],
            },
            matter_store={
                "matter_graph_summary": {
                    "root_compound": "aspirin",
                    "node_count": 4,
                    "edge_count": 3,
                    "node_counts_by_type": {
                        "compound_variant": 1,
                        "patent": 2,
                        "family": 1,
                    },
                    "edge_counts_by_type": {"roots": 2, "belongs_to_family": 1},
                    "patent_node_ids": ["patent:US1234567B2", "patent:EP2345678B1"],
                    "family_node_ids": ["family:fam-1"],
                },
                "record_completeness": {
                    "required_components": ["claims_text", "family_context"],
                    "missing_components": ["family_context"],
                },
                "run_observability": {
                    "false_clear_risk_flags": ["record_incomplete"],
                },
                "collector_runs": [
                    {
                        "definition": {"collector_name": "epo_register"},
                        "collection_state": "missing",
                        "missing_patent_ids": ["EP2345678B1"],
                    }
                ],
                "record_contradictions": [
                    {
                        "summary": "Search loop stopped while required evidence-collection directives were still open."
                    }
                ],
            },
        )

        assert "world_class_us_ep" in context["clearance_policy"]
        assert "claims_text, family_context" in context["clearance_policy"]
        assert context["known_record_gaps"] == ["missing family coverage"]
        assert "expand_family_context" in context["evidence_collection_directives"]
        assert "Node count: 4" in context["matter_graph_summary"]
        assert "patent:US1234567B2" in context["matter_graph_summary"]
        assert "Required components: claims_text, family_context" in context["matter_store_summary"]
        assert "epo_register=missing" in context["matter_store_summary"]
        assert "record_incomplete" in context["matter_store_summary"]

    def test_confidence_clamping(self):
        assessment = CoverageAssessment(confidence=1.5)
        assert assessment.confidence == 1.0
        assessment2 = CoverageAssessment(confidence=-0.5)
        assert assessment2.confidence == 0.0

    def test_with_gaps(self):
        gaps = [
            CoverageGap(gap_type="missing_cpc", description="C12P not searched"),
            CoverageGap(gap_type="search_bias", description="80% from one assignee"),
        ]
        assessment = CoverageAssessment(
            coverage_adequate=False,
            gaps_identified=gaps,
            confidence=0.3,
        )
        assert len(assessment.gaps_identified) == 2
        assert not assessment.coverage_adequate

    def test_with_suggested_queries(self):
        queries = ExpandedSearchQueries(
            patent_synonyms=["new term"],
            cpc_codes=["C12P7/46"],
            key_assignees=["Pfizer"],
            process_keywords=["fermentation"],
            compound_class_terms=["dicarboxylic acid"],
        )
        assessment = CoverageAssessment(
            coverage_adequate=False,
            suggested_queries=queries,
        )
        assert assessment.suggested_queries is not None
        assert "C12P7/46" in assessment.suggested_queries.cpc_codes

    def test_extra_fields_ignored(self):
        assessment = CoverageAssessment(
            coverage_adequate=True,
            confidence=0.9,
            unknown_field="should be ignored",
        )
        assert assessment.coverage_adequate is True

    def test_derive_known_record_gaps_uses_effective_policy_and_material_patents(self):
        from praviar_pipeline.pipeline.search_loop import derive_known_record_gaps

        settings = MagicMock()
        settings.required_record_components = []
        settings.clearance_threshold_profile = "world_class_us_ep"

        patent_hits = [
            PatentHit(
                patent_id="US1234567B2",
                jurisdiction="US",
                claims_text="",
                sources=[PatentSource.PUBCHEM],
                application_number="",
                transactions=[],
            ),
            PatentHit(
                patent_id="EP2345678B1",
                jurisdiction="EP",
                claims_text="Claim 1. Example text.",
                sources=[PatentSource.EPO_SEARCH],
                family=PatentFamily(
                    family_id="fam-ep",
                    members=[PatentFamilyMember(country="EP", doc_number="2345678", kind="B1")],
                ),
                designated_states=[],
                priority_claims=[],
                opposition_events=[],
                legal_events=[],
            ),
        ]
        triage = [
            TriageResult(
                patent_id="US1234567B2",
                relevance=Relevance.RELEVANT,
                reason="Core structure overlap.",
            ),
            TriageResult(
                patent_id="EP2345678B1",
                relevance=Relevance.NOT_RELEVANT,
                reason="Unrelated dosage form.",
            ),
        ]
        source_health = SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.FAILED),
                SourceHealthEntry(source="epo_search", status=SourceStatus.OK),
            ]
        )

        required_components, gaps = derive_known_record_gaps(
            patent_hits,
            triage,
            source_health,
            settings=settings,
        )

        assert required_components == [
            "claims_text",
            "claim_level_analysis",
            "authoritative_records",
            "family_context",
            "us_file_wrapper_dossier",
            "verification",
        ]
        assert "1/1 material patents are missing full claims text." in gaps
        assert "1/1 material patents are missing patent-family context." in gaps
        assert (
            "1/1 material patents lack authoritative-source support from PatentsView or EPO search."
            in gaps
        )
        assert "Authoritative sources failed this iteration: patentsview." in gaps
        assert "1/1 material US patents are missing dossier-grade file-wrapper history." in gaps

    def test_derive_known_record_gaps_tracks_ep_register_context(self):
        from praviar_pipeline.pipeline.search_loop import derive_known_record_gaps

        settings = MagicMock()
        settings.required_record_components = []
        settings.clearance_threshold_profile = "world_class_us_ep"

        patent_hits = [
            PatentHit(
                patent_id="EP2345678B1",
                jurisdiction="EP",
                claims_text="Claim text",
                sources=[PatentSource.EPO_SEARCH],
                family=PatentFamily(
                    family_id="fam-ep",
                    members=[PatentFamilyMember(country="EP", doc_number="2345678", kind="B1")],
                ),
            )
        ]
        triage = [
            TriageResult(
                patent_id="EP2345678B1",
                relevance=Relevance.POSSIBLY_RELEVANT,
                reason="Potential overlap.",
            )
        ]
        source_health = SourceHealth(
            entries=[SourceHealthEntry(source="epo_search", status=SourceStatus.OK)]
        )

        required_components, gaps = derive_known_record_gaps(
            patent_hits,
            triage,
            source_health,
            settings=settings,
        )

        assert "ep_register_context" in required_components
        assert "1/1 material EP patents are missing EPO register or opposition context." in gaps

    def test_apply_record_gap_guard_blocks_adequate_assessment(self):
        from praviar_pipeline.pipeline.search_loop import apply_record_gap_guard

        assessment = CoverageAssessment(
            coverage_adequate=True,
            confidence=0.91,
            iteration_summary="Looks complete.",
        )

        guarded = apply_record_gap_guard(
            assessment,
            ["1/1 material US patents are missing dossier-grade file-wrapper history."],
        )

        assert guarded.coverage_adequate is False
        assert guarded.gaps_identified[-1].gap_type == "record_gap"
        assert (
            guarded.gaps_identified[-1].description
            == "1/1 material US patents are missing dossier-grade file-wrapper history."
        )

    def test_build_search_collection_directives_emits_policy_actions(self):
        from praviar_pipeline.pipeline.search_loop import (
            build_search_collection_directives,
            build_search_gap_plan,
        )

        settings = MagicMock()
        settings.required_record_components = []
        settings.clearance_threshold_profile = "world_class_us_ep"

        patent_hits = [
            PatentHit(
                patent_id="US1234567B2",
                jurisdiction="US",
                claims_text="",
                sources=[PatentSource.PUBCHEM],
                application_number="",
                transactions=[],
            )
        ]
        triage = [
            TriageResult(
                patent_id="US1234567B2",
                relevance=Relevance.RELEVANT,
                reason="Core overlap.",
            )
        ]
        source_health = SourceHealth(
            entries=[SourceHealthEntry(source="patentsview", status=SourceStatus.FAILED)]
        )

        gap_plan = build_search_gap_plan(
            patent_hits,
            triage,
            source_health,
            settings=settings,
        )
        directives = build_search_collection_directives(gap_plan)

        assert [directive.directive_type for directive in directives] == [
            "collect_claims_text",
            "collect_authoritative_records",
            "expand_family_context",
            "collect_us_file_wrapper_dossier",
            "retry_authoritative_adapters",
        ]
        assert directives[1].recommended_adapters == [
            "patentsview",
            "epo_search",
            "uspto_odp",
            "epo_register",
        ]

    def test_synthesize_search_queries_from_directives_uses_target_patent_metadata(self):
        from praviar_pipeline.models.report import (
            EvidenceCollectionDirective,
            EvidenceDirectivePriority,
        )
        from praviar_pipeline.pipeline.search_loop import (
            synthesize_search_queries_from_directives,
        )

        directives = [
            EvidenceCollectionDirective(
                directive_id="collect_authoritative_records:US1234567B2",
                directive_type="collect_authoritative_records",
                priority=EvidenceDirectivePriority.CRITICAL,
                target_patent_ids=["US1234567B2"],
                recommended_adapters=["patentsview"],
                summary="Collect authoritative records.",
                rationale="Needed before clear.",
            )
        ]
        patent_hits = [
            PatentHit(
                patent_id="US1234567B2",
                jurisdiction="US",
                claims_text="Claim 1...",
                sources=[PatentSource.PUBCHEM],
                assignees=["Example Pharma", "Second Pharma"],
                cpc_codes=["A61K31/00", "C07D401/12"],
            )
        ]
        accumulated = ExpandedSearchQueries(
            patent_synonyms=["aspirin"],
            cpc_codes=["A61K31/00"],
            key_assignees=["Example Pharma"],
        )

        synthesized = synthesize_search_queries_from_directives(
            directives,
            patent_hits,
            accumulated,
        )

        assert synthesized is not None
        assert synthesized.key_assignees == ["Second Pharma"]
        assert synthesized.cpc_codes == ["C07D401/12"]


class TestSearchIterationLog:
    def test_basic_creation(self):
        log = SearchIterationLog(
            iteration_number=1,
            patents_found_new=50,
            patents_found_total=50,
            triage_relevant_new=10,
        )
        assert log.iteration_number == 1
        assert log.patents_found_new == 50

    def test_with_assessment(self):
        assessment = CoverageAssessment(coverage_adequate=True, confidence=0.9)
        log = SearchIterationLog(
            iteration_number=2,
            patents_found_new=20,
            patents_found_total=70,
            assessment=assessment,
        )
        assert log.assessment is not None
        assert log.assessment.coverage_adequate


class TestSearchLoopResult:
    def test_basic_creation(self):
        result = SearchLoopResult(iterations_completed=1)
        assert result.iterations_completed == 1
        assert result.iteration_logs == []
        assert result.pending_collection_directives == []
        assert result.termination_reason == ""

    def test_with_logs(self):
        logs = [
            SearchIterationLog(iteration_number=1, patents_found_new=50, patents_found_total=50),
            SearchIterationLog(iteration_number=2, patents_found_new=20, patents_found_total=70),
        ]
        result = SearchLoopResult(
            iterations_completed=2,
            iteration_logs=logs,
            total_input_tokens=1000,
            total_output_tokens=500,
        )
        assert result.iterations_completed == 2
        assert len(result.iteration_logs) == 2


# ---------------------------------------------------------------------------
# _merge_queries tests
# ---------------------------------------------------------------------------


class TestMergeQueries:
    def test_merge_deduplicates(self):
        from praviar_pipeline.pipeline.search_loop import _merge_queries

        base = ExpandedSearchQueries(
            patent_synonyms=["aspirin", "acetylsalicylic acid"],
            cpc_codes=["C07C"],
            key_assignees=["Bayer"],
            process_keywords=["synthesis"],
            compound_class_terms=["NSAID"],
        )
        new = ExpandedSearchQueries(
            patent_synonyms=["aspirin", "ASA"],  # "aspirin" is duplicate
            cpc_codes=["C07C", "A61K"],  # "C07C" is duplicate
            key_assignees=["Pfizer"],
            process_keywords=["synthesis", "acetylation"],  # "synthesis" is duplicate
            compound_class_terms=["analgesic"],
        )
        merged = _merge_queries(base, new)
        assert merged.patent_synonyms == ["aspirin", "acetylsalicylic acid", "ASA"]
        assert merged.cpc_codes == ["C07C", "A61K"]
        assert merged.key_assignees == ["Bayer", "Pfizer"]
        assert merged.process_keywords == ["synthesis", "acetylation"]
        assert merged.compound_class_terms == ["NSAID", "analgesic"]

    def test_merge_empty(self):
        from praviar_pipeline.pipeline.search_loop import _merge_queries

        base = ExpandedSearchQueries()
        new = ExpandedSearchQueries(patent_synonyms=["test"])
        merged = _merge_queries(base, new)
        assert merged.patent_synonyms == ["test"]

    def test_merge_preserves_order(self):
        from praviar_pipeline.pipeline.search_loop import _merge_queries

        base = ExpandedSearchQueries(cpc_codes=["A", "B", "C"])
        new = ExpandedSearchQueries(cpc_codes=["B", "D", "A"])
        merged = _merge_queries(base, new)
        assert merged.cpc_codes == ["A", "B", "C", "D"]


# ---------------------------------------------------------------------------
# run_search_loop tests
# ---------------------------------------------------------------------------


class TestRunSearchLoop:
    @pytest.fixture
    def mock_settings(self):
        with patch("praviar_pipeline.pipeline.search_loop.get_settings") as mock:
            settings = MagicMock()
            settings.search_loop_enabled = False
            settings.search_loop_max_iterations = 3
            settings.search_loop_coverage_threshold = 0.7
            mock.return_value = settings
            yield settings

    @pytest.fixture
    def sample_queries(self):
        return ExpandedSearchQueries(
            patent_synonyms=["succinic acid"],
            cpc_codes=["C12P7/46"],
            key_assignees=[],
            process_keywords=["fermentation"],
            compound_class_terms=["dicarboxylic acid"],
        )

    @pytest.fixture
    def mock_patent_hit(self):
        hit = MagicMock()
        hit.patent_id = "US1234567B2"
        hit.assignees = ["Test Corp"]
        hit.cpc_codes = ["C12P7/46"]
        hit.sources = [MagicMock(value="pubchem")]
        hit.filing_date = None
        hit.confidence_score = 0.8
        return hit

    @pytest.fixture
    def mock_triage_result(self):
        result = MagicMock()
        result.patent_id = "US1234567B2"
        result.relevance = MagicMock(value="relevant")
        result.confidence = 0.85
        return result

    @pytest.fixture
    def mock_compound(self):
        compound = MagicMock()
        compound.name = "succinic acid"
        compound.canonical_smiles = "OC(=O)CCC(O)=O"
        return compound

    @pytest.mark.asyncio
    async def test_single_iteration_when_loop_disabled(
        self,
        mock_settings,
        sample_queries,
        mock_compound,
        mock_patent_hit,
        mock_triage_result,
    ):
        """When search_loop_enabled=False, runs exactly one iteration."""
        from praviar_pipeline.pipeline.search_loop import run_search_loop

        mock_source_health = MagicMock()
        mock_source_health.entries = []

        with (
            patch("praviar_pipeline.pipeline.search_loop.search_patents") as mock_search,
            patch("praviar_pipeline.pipeline.search_loop.triage_patents") as mock_triage,
        ):
            mock_search.return_value = ([mock_patent_hit], mock_source_health, [])
            mock_triage.return_value = (
                [mock_triage_result],
                100,
                50,
                0,
                [mock_triage_result],
            )

            result = await run_search_loop(mock_compound, sample_queries)

        hits, *_unused, loop = result
        assert len(hits) == 1
        assert loop.iterations_completed == 1
        mock_search.assert_called_once()
        mock_triage.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_iteration_with_coverage_assessment(
        self,
        mock_settings,
        sample_queries,
        mock_compound,
    ):
        """When loop is enabled, runs multiple iterations until coverage is adequate."""
        from praviar_pipeline.pipeline.search_loop import run_search_loop

        mock_settings.search_loop_enabled = True
        mock_settings.search_loop_max_iterations = 3

        hit1 = MagicMock()
        hit1.patent_id = "US001"
        hit1.assignees = ["Corp A"]
        hit1.cpc_codes = ["C12P"]
        hit1.sources = [MagicMock(value="pubchem")]
        hit1.filing_date = None
        hit1.confidence_score = 0.7

        hit2 = MagicMock()
        hit2.patent_id = "US002"
        hit2.assignees = ["Corp B"]
        hit2.cpc_codes = ["A61K"]
        hit2.sources = [MagicMock(value="lens")]
        hit2.filing_date = None
        hit2.confidence_score = 0.8

        triage1 = MagicMock()
        triage1.patent_id = "US001"
        triage2 = MagicMock()
        triage2.patent_id = "US002"

        mock_source_health = MagicMock()
        mock_source_health.entries = []

        # First iteration finds hit1, second finds hit2
        search_calls = [
            ([hit1], mock_source_health, []),
            ([hit2], mock_source_health, []),
        ]
        triage_calls = [
            ([triage1], 100, 50, 0, [triage1]),
            ([triage2], 100, 50, 0, [triage2]),
        ]

        # Coverage assessment: first says not adequate, second says adequate
        assessment_not_adequate = CoverageAssessment(
            coverage_adequate=False,
            confidence=0.4,
            suggested_queries=ExpandedSearchQueries(
                patent_synonyms=["new term"],
                cpc_codes=["A61K"],
                key_assignees=["Corp B"],
                process_keywords=[],
                compound_class_terms=[],
            ),
        )
        assessment_adequate = CoverageAssessment(
            coverage_adequate=True,
            confidence=0.85,
        )

        with (
            patch("praviar_pipeline.pipeline.search_loop.search_patents") as mock_search,
            patch("praviar_pipeline.pipeline.search_loop.triage_patents") as mock_triage,
            patch("praviar_pipeline.pipeline.search_loop._assess_coverage") as mock_assess,
        ):
            mock_search.side_effect = search_calls
            mock_triage.side_effect = triage_calls
            mock_assess.side_effect = [
                (assessment_not_adequate, 200, 100),
                (assessment_adequate, 200, 100),
            ]

            result = await run_search_loop(mock_compound, sample_queries)

        hits, *_unused, loop = result
        assert len(hits) == 2  # Both hits found
        assert loop.iterations_completed == 2
        assert mock_search.call_count == 2
        assert mock_assess.call_count == 2

    @pytest.mark.asyncio
    async def test_deduplication_across_iterations(
        self,
        mock_settings,
        sample_queries,
        mock_compound,
    ):
        """Same patent found in two iterations should appear only once."""
        from praviar_pipeline.pipeline.search_loop import run_search_loop

        mock_settings.search_loop_enabled = True

        hit = MagicMock()
        hit.patent_id = "US001"
        hit.assignees = ["Corp"]
        hit.cpc_codes = []
        hit.sources = [MagicMock(value="pubchem")]
        hit.filing_date = None
        hit.confidence_score = 0.8

        mock_source_health = MagicMock()
        mock_source_health.entries = []

        # Both iterations return the same patent
        search_calls = [
            ([hit], mock_source_health, []),
            ([hit], mock_source_health, []),  # duplicate
        ]

        assessment_not = CoverageAssessment(
            coverage_adequate=False,
            confidence=0.3,
            suggested_queries=ExpandedSearchQueries(
                patent_synonyms=["retry"],
                cpc_codes=[],
                key_assignees=[],
                process_keywords=[],
                compound_class_terms=[],
            ),
        )
        assessment_ok = CoverageAssessment(coverage_adequate=True, confidence=0.9)

        triage_result = MagicMock()
        triage_result.patent_id = "US001"

        with (
            patch("praviar_pipeline.pipeline.search_loop.search_patents") as mock_search,
            patch("praviar_pipeline.pipeline.search_loop.triage_patents") as mock_triage,
            patch("praviar_pipeline.pipeline.search_loop._assess_coverage") as mock_assess,
        ):
            mock_search.side_effect = search_calls
            # Only first iteration gets triaged (second has no truly new patents)
            mock_triage.return_value = ([triage_result], 100, 50, 0, [triage_result])
            mock_assess.side_effect = [
                (assessment_not, 200, 100),
                (assessment_ok, 200, 100),
            ]

            result = await run_search_loop(mock_compound, sample_queries)

        hits, *_ = result
        assert len(hits) == 1  # Deduplicated
        # Triage only called once (second iteration had no new patents)
        mock_triage.assert_called_once()

    @pytest.mark.asyncio
    async def test_early_exit_on_adequate_coverage(
        self,
        mock_settings,
        sample_queries,
        mock_compound,
        mock_patent_hit,
        mock_triage_result,
    ):
        """Loop exits early when coverage is adequate."""
        from praviar_pipeline.pipeline.search_loop import run_search_loop

        mock_settings.search_loop_enabled = True
        mock_settings.search_loop_max_iterations = 5

        mock_source_health = MagicMock()
        mock_source_health.entries = []

        assessment = CoverageAssessment(coverage_adequate=True, confidence=0.9)

        with (
            patch("praviar_pipeline.pipeline.search_loop.search_patents") as mock_search,
            patch("praviar_pipeline.pipeline.search_loop.triage_patents") as mock_triage,
            patch("praviar_pipeline.pipeline.search_loop._assess_coverage") as mock_assess,
        ):
            mock_search.return_value = ([mock_patent_hit], mock_source_health, [])
            mock_triage.return_value = ([mock_triage_result], 100, 50, 0, [mock_triage_result])
            mock_assess.return_value = (assessment, 200, 100)

            result = await run_search_loop(mock_compound, sample_queries)

        *_, loop = result
        assert loop.iterations_completed == 1  # Exited after first iteration
        mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_exits_when_no_suggested_queries(
        self,
        mock_settings,
        sample_queries,
        mock_compound,
        mock_patent_hit,
        mock_triage_result,
    ):
        """Loop stops when coverage assessment has no suggested_queries."""
        from praviar_pipeline.pipeline.search_loop import run_search_loop

        mock_settings.search_loop_enabled = True

        mock_source_health = MagicMock()
        mock_source_health.entries = []

        assessment = CoverageAssessment(
            coverage_adequate=False,
            confidence=0.3,
            suggested_queries=None,  # No suggestions
        )

        with (
            patch("praviar_pipeline.pipeline.search_loop.search_patents") as mock_search,
            patch("praviar_pipeline.pipeline.search_loop.triage_patents") as mock_triage,
            patch("praviar_pipeline.pipeline.search_loop._assess_coverage") as mock_assess,
        ):
            mock_search.return_value = ([mock_patent_hit], mock_source_health, [])
            mock_triage.return_value = ([mock_triage_result], 100, 50, 0, [mock_triage_result])
            mock_assess.return_value = (assessment, 200, 100)

            result = await run_search_loop(mock_compound, sample_queries)

        *_, loop = result
        assert loop.iterations_completed == 1

    @pytest.mark.asyncio
    async def test_coverage_assessment_failure_is_nonfatal(
        self,
        mock_settings,
        sample_queries,
        mock_compound,
        mock_patent_hit,
        mock_triage_result,
    ):
        """If coverage assessment fails, loop stops gracefully."""
        from praviar_pipeline.pipeline.search_loop import run_search_loop

        mock_settings.search_loop_enabled = True

        mock_source_health = MagicMock()
        mock_source_health.entries = []

        with (
            patch("praviar_pipeline.pipeline.search_loop.search_patents") as mock_search,
            patch("praviar_pipeline.pipeline.search_loop.triage_patents") as mock_triage,
            patch("praviar_pipeline.pipeline.search_loop._assess_coverage") as mock_assess,
        ):
            mock_search.return_value = ([mock_patent_hit], mock_source_health, [])
            mock_triage.return_value = ([mock_triage_result], 100, 50, 0, [mock_triage_result])
            mock_assess.side_effect = RuntimeError("Coverage agent crashed")

            result = await run_search_loop(mock_compound, sample_queries)

        hits, *_, loop = result
        assert len(hits) == 1  # Still got results from first iteration
        assert loop.iterations_completed == 1

    @pytest.mark.asyncio
    async def test_max_iterations_respected(
        self,
        mock_settings,
        sample_queries,
        mock_compound,
    ):
        """Loop does not exceed max_iterations."""
        from praviar_pipeline.pipeline.search_loop import run_search_loop

        mock_settings.search_loop_enabled = True
        mock_settings.search_loop_max_iterations = 2

        def make_hit(pid):
            h = MagicMock()
            h.patent_id = pid
            h.assignees = []
            h.cpc_codes = []
            h.sources = [MagicMock(value="pubchem")]
            h.filing_date = None
            h.confidence_score = 0.5
            return h

        mock_source_health = MagicMock()
        mock_source_health.entries = []

        # Coverage never adequate but limited to 2 iterations
        not_adequate = CoverageAssessment(
            coverage_adequate=False,
            confidence=0.2,
            suggested_queries=ExpandedSearchQueries(
                patent_synonyms=["more"],
                cpc_codes=[],
                key_assignees=[],
                process_keywords=[],
                compound_class_terms=[],
            ),
        )

        call_count = 0

        def search_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return ([make_hit(f"US{call_count:03d}")], mock_source_health, [])

        triage_result = MagicMock()
        triage_result.patent_id = "USxxx"

        with (
            patch("praviar_pipeline.pipeline.search_loop.search_patents") as mock_search,
            patch("praviar_pipeline.pipeline.search_loop.triage_patents") as mock_triage,
            patch("praviar_pipeline.pipeline.search_loop._assess_coverage") as mock_assess,
        ):
            mock_search.side_effect = search_side_effect
            mock_triage.return_value = ([triage_result], 50, 25, 0, [triage_result])
            mock_assess.return_value = (not_adequate, 100, 50)

            result = await run_search_loop(mock_compound, sample_queries)

        *_, loop = result
        assert loop.iterations_completed == 2
        assert mock_search.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_search_results(
        self,
        mock_settings,
        sample_queries,
        mock_compound,
    ):
        """Handle case where search returns no results."""
        from praviar_pipeline.pipeline.search_loop import run_search_loop

        mock_source_health = MagicMock()
        mock_source_health.entries = []

        with (
            patch("praviar_pipeline.pipeline.search_loop.search_patents") as mock_search,
            patch("praviar_pipeline.pipeline.search_loop.triage_patents") as mock_triage,
        ):
            mock_search.return_value = ([], mock_source_health, [])
            # Triage should not be called if no patents found

            result = await run_search_loop(mock_compound, sample_queries)

        hits, *_, loop = result
        assert len(hits) == 0
        assert loop.iterations_completed == 1
        mock_triage.assert_not_called()
