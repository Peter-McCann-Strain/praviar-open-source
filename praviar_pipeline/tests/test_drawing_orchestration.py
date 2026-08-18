from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.errors import DrawingAcquisitionError, DrawingAnalysisError
from praviar_pipeline.models.drawing import PatentDrawingAnalysis
from praviar_pipeline.pipeline.drawings.orchestration import (
    build_patent_text,
    run_drawing_analysis,
    run_patent_analyses,
    select_patents_to_process,
)


def test_select_patents_to_process_honors_limit() -> None:
    patents = [SimpleNamespace(patent_id=f"US{i}") for i in range(3)]

    limited = select_patents_to_process(patents, max_patents=2)
    unlimited = select_patents_to_process(patents, max_patents=0)

    assert [patent.patent_id for patent in limited] == ["US0", "US1"]
    assert [patent.patent_id for patent in unlimited] == ["US0", "US1", "US2"]


def test_build_patent_text_appends_claims_text() -> None:
    patent = SimpleNamespace(abstract="Abstract", claims_text="Claim 1")

    assert build_patent_text(patent) == "Abstract\nClaim 1"


@pytest.mark.asyncio
async def test_run_patent_analyses_fails_closed_without_partial_results() -> None:
    patents = [
        SimpleNamespace(patent_id="US1", abstract="A", claims_text="C1"),
        SimpleNamespace(patent_id="US2", abstract="B", claims_text="C2"),
    ]
    settings = SimpleNamespace(drawing_concurrency=2, drawing_timeout_per_patent_s=1)

    async def fake_analyze_single_patent(**kwargs):
        if kwargs["patent_id"] == "US1":
            return PatentDrawingAnalysis(patent_id="US1", drawing_summary="ok")
        raise RuntimeError("boom")

    with pytest.raises(DrawingAnalysisError) as exc_info:
        await run_patent_analyses(
            patents,
            epo_client=None,
            seg_runner=None,
            all_runners={},
            compound_smiles="CCO",
            settings=settings,
            work_dir=SimpleNamespace(),
            analyze_single_patent_fn=fake_analyze_single_patent,
        )

    assert exc_info.value.failure_types == ("RuntimeError",)
    assert "boom" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_patent_analyses_preserves_typed_stage_failure_metadata() -> None:
    settings = SimpleNamespace(drawing_concurrency=1, drawing_timeout_per_patent_s=1)

    async def fake_analyze_single_patent(**_kwargs):
        raise DrawingAcquisitionError(failure_types=("ReadTimeout", "RuntimeError"))

    with pytest.raises(DrawingAnalysisError) as exc_info:
        await run_patent_analyses(
            [SimpleNamespace(patent_id="US1")],
            epo_client=None,
            seg_runner=None,
            all_runners={},
            compound_smiles="CCO",
            settings=settings,
            work_dir=SimpleNamespace(),
            analyze_single_patent_fn=fake_analyze_single_patent,
        )

    assert exc_info.value.failure_types == (
        "DrawingAcquisitionError",
        "ReadTimeout",
        "RuntimeError",
    )


@pytest.mark.asyncio
async def test_run_drawing_analysis_returns_empty_when_disabled() -> None:
    settings = SimpleNamespace(drawing_analysis_enabled=False)

    result = await run_drawing_analysis(
        [],
        compound_smiles="CCO",
        settings=settings,
        get_runners_fn=lambda *_args: {"molscribe": object()},
        get_segmentation_runner_fn=lambda: object(),
        create_epo_client_fn=lambda: object(),
        resolve_work_dir_fn=lambda _settings: SimpleNamespace(),
        select_patents_to_process_fn=lambda patent_hits, *, max_patents: list(patent_hits),
        run_patent_analyses_fn=lambda *args, **kwargs: [],
        close_epo_client_fn=lambda _client: None,
        build_results_fn=lambda _results: SimpleNamespace(total_patents_with_images=0),
    )

    assert result.total_patents_with_images == 0


@pytest.mark.asyncio
async def test_run_drawing_analysis_returns_empty_when_no_runners() -> None:
    settings = SimpleNamespace(
        drawing_analysis_enabled=True,
        drawing_ensemble_tools=["missing"],
    )

    result = await run_drawing_analysis(
        [],
        compound_smiles="CCO",
        settings=settings,
        get_runners_fn=lambda *_args: {},
        get_segmentation_runner_fn=lambda: object(),
        create_epo_client_fn=lambda: object(),
        resolve_work_dir_fn=lambda _settings: SimpleNamespace(),
        select_patents_to_process_fn=lambda patent_hits, *, max_patents: list(patent_hits),
        run_patent_analyses_fn=lambda *args, **kwargs: [],
        close_epo_client_fn=lambda _client: None,
        build_results_fn=lambda _results: SimpleNamespace(total_patents_with_images=0),
    )

    assert result.total_patents_with_images == 0


@pytest.mark.asyncio
async def test_run_drawing_analysis_orchestrates_selected_patents() -> None:
    patents = [SimpleNamespace(patent_id="US1"), SimpleNamespace(patent_id="US2")]
    settings = SimpleNamespace(
        drawing_analysis_enabled=True,
        drawing_analysis_jurisdictions=["US"],
        drawing_ensemble_tools=["molscribe"],
        drawing_cascade_enabled=True,
        drawing_classifier_enabled=True,
        drawing_text_validation_enabled=True,
        drawing_max_patents=1,
        drawing_markush_scope_agent_enabled=False,
    )
    selected: list[SimpleNamespace] = []
    closed: list[object] = []

    async def _create_epo_client():
        return object()

    async def _run_patent_analyses(
        patent_hits,
        *,
        epo_client,
        seg_runner,
        all_runners,
        compound_smiles,
        settings,
        work_dir,
    ):
        selected.extend(patent_hits)
        assert epo_client is not None
        assert seg_runner == "seg"
        assert all_runners == {"molscribe": "runner"}
        assert compound_smiles == "CCO"
        return [PatentDrawingAnalysis(patent_id="US1", drawing_summary="ok")]

    async def _close_epo_client(client):
        closed.append(client)

    aggregate = SimpleNamespace(
        total_patents_with_images=1,
        total_structures_extracted=2,
        total_high_risk_structures=1,
        total_time_s=3.2,
    )

    result = await run_drawing_analysis(
        patents,
        compound_smiles="CCO",
        settings=settings,
        get_runners_fn=lambda *_args: {"molscribe": "runner"},
        get_segmentation_runner_fn=lambda: "seg",
        create_epo_client_fn=_create_epo_client,
        resolve_work_dir_fn=lambda _settings: "/tmp/work",
        select_patents_to_process_fn=lambda patent_hits, *, max_patents: list(
            patent_hits[:max_patents]
        ),
        run_patent_analyses_fn=_run_patent_analyses,
        close_epo_client_fn=_close_epo_client,
        build_results_fn=lambda results: aggregate,
    )

    assert selected == [patents[0]]
    assert len(closed) == 1
    assert result is aggregate


@pytest.mark.asyncio
async def test_run_drawing_analysis_closes_client_when_analysis_fails() -> None:
    settings = SimpleNamespace(
        drawing_analysis_enabled=True,
        drawing_analysis_jurisdictions=["US"],
        drawing_ensemble_tools=["molscribe"],
        drawing_cascade_enabled=True,
        drawing_classifier_enabled=True,
        drawing_text_validation_enabled=True,
        drawing_max_patents=1,
        drawing_markush_scope_agent_enabled=False,
    )
    client = object()
    closed: list[object] = []

    async def _raise_analysis_failure(*_args, **_kwargs):
        raise DrawingAnalysisError(failure_types=("RuntimeError",))

    async def _create_epo_client():
        return client

    async def _close_epo_client(value):
        closed.append(value)

    with pytest.raises(DrawingAnalysisError):
        await run_drawing_analysis(
            [SimpleNamespace(patent_id="US1")],
            compound_smiles="CCO",
            settings=settings,
            get_runners_fn=lambda *_args: {"molscribe": "runner"},
            get_segmentation_runner_fn=lambda: "seg",
            create_epo_client_fn=_create_epo_client,
            resolve_work_dir_fn=lambda _settings: "/tmp/work",
            select_patents_to_process_fn=lambda patent_hits, *, max_patents: list(
                patent_hits[:max_patents]
            ),
            run_patent_analyses_fn=_raise_analysis_failure,
            close_epo_client_fn=_close_epo_client,
            build_results_fn=lambda _results: None,
        )

    assert closed == [client]


@pytest.mark.asyncio
async def test_run_drawing_analysis_applies_jurisdiction_allowlist() -> None:
    patents = [
        SimpleNamespace(patent_id="US1"),
        SimpleNamespace(patent_id="EP2"),
        SimpleNamespace(patent_id="JP3"),
    ]
    settings = SimpleNamespace(
        drawing_analysis_enabled=True,
        drawing_ensemble_tools=["molscribe"],
        drawing_cascade_enabled=False,
        drawing_classifier_enabled=True,
        drawing_text_validation_enabled=False,
        drawing_max_patents=0,
        drawing_analysis_jurisdictions=["US", "JP"],
        drawing_markush_scope_agent_enabled=False,
    )
    selected: list[str] = []

    async def _create_epo_client():
        return object()

    async def _run_patent_analyses(
        patent_hits,
        *,
        epo_client,
        seg_runner,
        all_runners,
        compound_smiles,
        settings,
        work_dir,
    ):
        selected.extend(patent.patent_id for patent in patent_hits)
        return [PatentDrawingAnalysis(patent_id=patent.patent_id) for patent in patent_hits]

    async def _close_epo_client(_client):
        return None

    result = await run_drawing_analysis(
        patents,
        compound_smiles="CCO",
        settings=settings,
        get_runners_fn=lambda *_args: {"molscribe": "runner"},
        get_segmentation_runner_fn=lambda: "seg",
        create_epo_client_fn=_create_epo_client,
        resolve_work_dir_fn=lambda _settings: "/tmp/work",
        select_patents_to_process_fn=lambda patent_hits, *, max_patents: list(patent_hits),
        run_patent_analyses_fn=_run_patent_analyses,
        close_epo_client_fn=_close_epo_client,
        build_results_fn=lambda results: SimpleNamespace(
            patent_analyses=results,
            total_patents_with_images=len(results),
            total_structures_extracted=0,
            total_high_risk_structures=0,
            total_time_s=0.0,
        ),
    )

    assert selected == ["US1", "JP3"]
    assert len(result.patent_analyses) == 2
