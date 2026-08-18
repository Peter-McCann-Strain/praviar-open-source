from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from praviar_pipeline.errors import DrawingAcquisitionError, DrawingSegmentationError
from praviar_pipeline.models.drawing import (
    DrawingRiskLevel,
    DrawingStructure,
    PatentDrawingAnalysis,
    SegmentationResult,
)
from praviar_pipeline.pipeline.drawings import patent_analysis
from praviar_pipeline.pipeline.drawings.patent_analysis import _maybe_split_oversized_segments
from praviar_pipeline.pipeline.step2d_drawings import (
    _analyze_single_patent,
    analyze_patent_drawings,
)

# OpenCV/numpy are required for the splitter guard tests below; skip those
# tests if the deps are missing (mirrors test_crop_splitter.py's policy).
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.drawing_max_pages_per_patent = 5
    settings.drawing_pdf_max_bytes = 1024 * 1024
    settings.drawing_max_pixels_per_page = 4_000_000
    settings.drawing_max_total_pixels_per_patent = 10_000_000
    settings.drawing_timeout_per_patent_s = 30
    settings.drawing_analysis_enabled = True
    settings.drawing_analysis_jurisdictions = ["US"]
    settings.drawing_ensemble_tools = ["molscribe"]
    settings.drawing_image_cache_dir = None
    settings.drawing_max_patents = 0
    settings.drawing_concurrency = 1
    settings.drawing_cascade_enabled = True
    settings.drawing_classifier_enabled = True
    settings.drawing_text_validation_enabled = False
    return settings


@pytest.mark.asyncio
async def test_analyze_single_patent_returns_no_pages_summary(tmp_path) -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.fetch_all_drawings = AsyncMock(return_value=[])

    with patch(
        "praviar_pipeline.pipeline.step2d_drawings._fetch_pdf_fallback",
        new=AsyncMock(return_value=[]),
    ):
        result = await _analyze_single_patent(
            patent_id="US123",
            epo_client=epo_client,
            seg_runner=None,
            all_runners={},
            target_smiles="CCO",
            settings=settings,
            work_dir=tmp_path,
            patent_text="",
        )

    assert result.patent_id == "US123"
    assert result.pages_fetched == 0
    assert result.drawing_summary == "No drawing pages available for US123"


@pytest.mark.asyncio
async def test_live_acquisition_failure_without_successful_fallback_raises(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.fetch_all_drawings = AsyncMock(
        side_effect=httpx.ReadTimeout(
            "timed out",
            request=httpx.Request("GET", "https://ops.epo.org/images"),
        )
    )
    monkeypatch.setattr(patent_analysis, "drawing_evidence_can_influence", lambda _s: True)

    with (
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._fetch_pdf_fallback",
            new=AsyncMock(return_value=[]),
        ),
        pytest.raises(DrawingAcquisitionError) as exc_info,
    ):
        await _analyze_single_patent(
            patent_id="US123",
            epo_client=epo_client,
            seg_runner=None,
            all_runners={},
            target_smiles="CCO",
            settings=settings,
            work_dir=tmp_path,
            patent_text="",
        )

    assert exc_info.value.failure_types == ("ReadTimeout",)


@pytest.mark.asyncio
async def test_live_acquisition_failure_can_recover_through_pdf_fallback(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.fetch_all_drawings = AsyncMock(side_effect=RuntimeError("EPO page failure"))
    monkeypatch.setattr(patent_analysis, "drawing_evidence_can_influence", lambda _s: True)

    with (
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._fetch_pdf_fallback",
            new=AsyncMock(return_value=[(1, b"page-bytes")]),
        ),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._analyze_structure_image",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await _analyze_single_patent(
            patent_id="US123",
            epo_client=epo_client,
            seg_runner=None,
            all_runners={},
            target_smiles="CCO",
            settings=settings,
            work_dir=tmp_path,
            patent_text="",
        )

    assert result.pages_fetched == 1


@pytest.mark.asyncio
async def test_live_pdf_failure_after_semantic_epo_empty_raises(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.fetch_all_drawings = AsyncMock(return_value=[])
    monkeypatch.setattr(patent_analysis, "drawing_evidence_can_influence", lambda _s: True)

    with (
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._fetch_pdf_fallback",
            new=AsyncMock(side_effect=RuntimeError("invalid PDF")),
        ),
        pytest.raises(DrawingAcquisitionError) as exc_info,
    ):
        await _analyze_single_patent(
            patent_id="US123",
            epo_client=epo_client,
            seg_runner=None,
            all_runners={},
            target_smiles="CCO",
            settings=settings,
            work_dir=tmp_path,
            patent_text="",
        )

    assert exc_info.value.failure_types == ("RuntimeError",)


@pytest.mark.asyncio
async def test_live_confirmed_no_drawing_document_remains_semantic_empty(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.fetch_all_drawings = AsyncMock(return_value=[])
    monkeypatch.setattr(patent_analysis, "drawing_evidence_can_influence", lambda _s: True)

    with patch(
        "praviar_pipeline.pipeline.step2d_drawings._fetch_pdf_fallback",
        new=AsyncMock(return_value=[]),
    ):
        result = await _analyze_single_patent(
            patent_id="US123",
            epo_client=epo_client,
            seg_runner=None,
            all_runners={},
            target_smiles="CCO",
            settings=settings,
            work_dir=tmp_path,
            patent_text="",
        )

    assert result.pages_fetched == 0
    assert result.drawing_summary == "No drawing pages available for US123"


@pytest.mark.asyncio
async def test_shadow_acquisition_failures_remain_diagnostic_abstentions(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.fetch_all_drawings = AsyncMock(side_effect=RuntimeError("EPO failure"))
    monkeypatch.setattr(patent_analysis, "drawing_evidence_can_influence", lambda _s: False)

    with patch(
        "praviar_pipeline.pipeline.step2d_drawings._fetch_pdf_fallback",
        new=AsyncMock(side_effect=RuntimeError("PDF failure")),
    ):
        result = await _analyze_single_patent(
            patent_id="US123",
            epo_client=epo_client,
            seg_runner=None,
            all_runners={},
            target_smiles="CCO",
            settings=settings,
            work_dir=tmp_path,
            patent_text="",
        )

    assert result.pages_fetched == 0
    assert result.drawing_summary == "No drawing pages available for US123"


@pytest.mark.asyncio
async def test_live_segmentation_runtime_failure_raises_typed_error(tmp_path) -> None:
    page_path = tmp_path / "page.png"
    page_path.write_bytes(b"page")
    seg_runner = MagicMock()
    seg_runner.segment = AsyncMock(side_effect=RuntimeError("model crashed"))

    with pytest.raises(DrawingSegmentationError) as exc_info:
        await patent_analysis.segment_patent_pages(
            "US123",
            tmp_path,
            [(1, page_path)],
            seg_runner,
            fail_closed=True,
        )

    assert exc_info.value.failure_types == ("RuntimeError",)


@pytest.mark.asyncio
async def test_shadow_segmentation_runtime_failure_remains_abstention(tmp_path) -> None:
    page_path = tmp_path / "page.png"
    page_path.write_bytes(b"page")
    seg_runner = MagicMock()
    seg_runner.segment = AsyncMock(side_effect=RuntimeError("model crashed"))

    result = await patent_analysis.segment_patent_pages(
        "US123",
        tmp_path,
        [(1, page_path)],
        seg_runner,
        fail_closed=False,
    )

    assert result.all_segments == []


@pytest.mark.asyncio
async def test_analyze_single_patent_uses_pdf_fallback_and_attaches_page_context(
    tmp_path,
) -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.fetch_all_drawings = AsyncMock(return_value=[])

    async def _structure_side_effect(**kwargs) -> DrawingStructure:
        return DrawingStructure(
            patent_id=kwargs["patent_id"],
            page_number=kwargs["page_number"],
            structure_index=kwargs["structure_index"],
            canonical_smiles="CCO",
            tanimoto_to_target=0.82,
            drawing_risk_signal=DrawingRiskLevel.HIGH,
        )

    with (
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._fetch_pdf_fallback",
            new=AsyncMock(return_value=[(1, b"page-bytes")]),
        ) as fallback_mock,
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._analyze_structure_image",
            new=AsyncMock(side_effect=_structure_side_effect),
        ),
    ):
        result = await _analyze_single_patent(
            patent_id="US123",
            epo_client=epo_client,
            seg_runner=None,
            all_runners={},
            target_smiles="CCO",
            settings=settings,
            work_dir=tmp_path,
            patent_text="",
        )

    fallback_mock.assert_awaited_once_with(
        "US123",
        epo_client,
        tmp_path / "US123",
        max_pages=5,
        max_pdf_bytes=1024 * 1024,
        max_pixels_per_page=4_000_000,
        max_total_pixels=10_000_000,
    )
    assert result.pages_fetched == 1
    assert result.structures_found == 1
    assert result.structures[0].bbox == (0, 0, 0, 0)
    assert result.structures[0].original_page_image.endswith("page_001.png")


@pytest.mark.asyncio
async def test_analyze_single_patent_returns_no_segments_summary(tmp_path) -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.fetch_all_drawings = AsyncMock(return_value=[(1, b"page-bytes")])
    seg_runner = MagicMock()
    seg_runner.segment = AsyncMock(return_value=[])

    result = await _analyze_single_patent(
        patent_id="US123",
        epo_client=epo_client,
        seg_runner=seg_runner,
        all_runners={},
        target_smiles="CCO",
        settings=settings,
        work_dir=tmp_path,
        patent_text="",
    )

    assert result.pages_fetched == 1
    assert result.structures_found == 0
    assert result.drawing_summary == "No structures found in 1 pages of US123"


@pytest.mark.asyncio
async def test_analyze_single_patent_skips_missing_segments_and_keeps_bbox(tmp_path) -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.fetch_all_drawings = AsyncMock(return_value=[(1, b"page-bytes")])
    seg_runner = MagicMock()
    segment_path = tmp_path / "segment.png"
    segment_path.write_bytes(b"segment")
    seg_runner.segment = AsyncMock(
        return_value=[
            SegmentationResult(segment_index=0, bbox=(1, 2, 3, 4), image_path=""),
            SegmentationResult(
                segment_index=1,
                bbox=(5, 6, 7, 8),
                image_path=str(segment_path),
            ),
        ]
    )

    async def _structure_side_effect(**kwargs) -> DrawingStructure:
        return DrawingStructure(
            patent_id=kwargs["patent_id"],
            page_number=kwargs["page_number"],
            structure_index=kwargs["structure_index"],
            canonical_smiles="CCO",
            tanimoto_to_target=0.42,
            drawing_risk_signal=DrawingRiskLevel.MEDIUM,
        )

    with patch(
        "praviar_pipeline.pipeline.step2d_drawings._analyze_structure_image",
        new=AsyncMock(side_effect=_structure_side_effect),
    ):
        result = await _analyze_single_patent(
            patent_id="US123",
            epo_client=epo_client,
            seg_runner=seg_runner,
            all_runners={},
            target_smiles="CCO",
            settings=settings,
            work_dir=tmp_path,
            patent_text="",
        )

    assert result.structures_found == 1
    assert result.structures[0].page_number == 1
    assert result.structures[0].structure_index == 1
    assert result.structures[0].bbox == (5, 6, 7, 8)


@pytest.mark.asyncio
async def test_analyze_patent_drawings_respects_limit_and_appends_claims_text() -> None:
    settings = _settings()
    settings.drawing_max_patents = 1
    epo_client = MagicMock()
    epo_client.close = AsyncMock()
    patent_calls: list[dict[str, str]] = []
    patents = [
        SimpleNamespace(patent_id="US1", abstract="ABSTRACT", claims_text="CLAIMS"),
        SimpleNamespace(patent_id="US2", abstract="SECOND", claims_text="OTHER"),
    ]

    async def _analyze_side_effect(**kwargs) -> PatentDrawingAnalysis:
        patent_calls.append(
            {
                "patent_id": kwargs["patent_id"],
                "patent_text": kwargs["patent_text"],
            }
        )
        return PatentDrawingAnalysis(patent_id=kwargs["patent_id"], drawing_summary="ok")

    with (
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._get_runners",
            return_value={"molscribe": MagicMock()},
        ),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._get_segmentation_runner", return_value=None
        ),
        patch("praviar_pipeline.pipeline.step2d_drawings.EPOOPSClient", return_value=epo_client),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._analyze_single_patent",
            new=AsyncMock(side_effect=_analyze_side_effect),
        ),
    ):
        result = await analyze_patent_drawings(patents, "CCO", settings)

    assert len(result.patent_analyses) == 1
    assert [call["patent_id"] for call in patent_calls] == ["US1"]
    assert patent_calls[0]["patent_text"] == "ABSTRACT\nCLAIMS"
    epo_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_patent_drawings_closes_epo_client_after_success() -> None:
    settings = _settings()
    epo_client = MagicMock()
    epo_client.close = AsyncMock()
    patent = SimpleNamespace(patent_id="US1", abstract="", claims_text="")

    with (
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._get_runners",
            return_value={"molscribe": MagicMock()},
        ),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._get_segmentation_runner", return_value=None
        ),
        patch("praviar_pipeline.pipeline.step2d_drawings.EPOOPSClient", return_value=epo_client),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._analyze_single_patent",
            new=AsyncMock(return_value=PatentDrawingAnalysis(patent_id="US1")),
        ),
    ):
        await analyze_patent_drawings([patent], "CCO", settings)

    epo_client.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Splitter guard: _maybe_split_oversized_segments
# ---------------------------------------------------------------------------


def _splitter_settings(**overrides: object) -> SimpleNamespace:
    """SimpleNamespace settings stub aligned with SubCropConfig.from_settings.

    Uses real values (not MagicMock) because SubCropConfig.from_settings does
    explicit ``int(...)`` / ``float(...)`` / ``bool(...)`` coercion.
    """
    base: dict[str, object] = dict(
        drawing_split_enabled=True,
        drawing_split_min_height_trigger_px=200,
        drawing_split_kernel_fraction=0.02,
        drawing_split_min_component_area=200,
        drawing_split_max_aspect=10.0,
        drawing_split_min_gap_px=20,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _draw_two_benzenes_horizontal(path: Path) -> None:
    """Two benzene-like hexagons side by side; height >= 200 to trip the guard."""
    img = np.full((220, 600, 3), 255, dtype=np.uint8)
    pts1 = np.array([[60, 100], [100, 70], [140, 100], [140, 140], [100, 170], [60, 140]])
    cv2.polylines(img, [pts1], isClosed=True, color=(0, 0, 0), thickness=3)
    pts2 = pts1.copy()
    pts2[:, 0] += 280
    cv2.polylines(img, [pts2], isClosed=True, color=(0, 0, 0), thickness=3)
    cv2.imwrite(str(path), img)


def _draw_single_benzene(path: Path, *, height: int = 220, width: int = 220) -> None:
    """One small benzene; should not split even when tall enough to trigger."""
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    pts = np.array([[60, 60], [100, 30], [140, 60], [140, 100], [100, 130], [60, 100]])
    cv2.polylines(img, [pts], isClosed=True, color=(0, 0, 0), thickness=3)
    cv2.imwrite(str(path), img)


class TestMaybeSplitOversizedSegments:
    """Guard fires only on tall, splittable crops; passthrough otherwise."""

    def test_short_segment_is_passthrough(self, tmp_path: Path) -> None:
        crop = tmp_path / "short.png"
        _draw_two_benzenes_horizontal(crop)  # 220 tall, but trigger=500
        seg = SegmentationResult(
            segment_index=0,
            bbox=(0, 0, 600, 220),  # height=220 < 500
            image_path=str(crop),
            width=600,
            height=220,
        )
        out = _maybe_split_oversized_segments(
            [(3, seg)],
            _splitter_settings(drawing_split_min_height_trigger_px=500),
            tmp_path,
        )
        assert out == [(3, seg)], "short segments must pass through untouched"

    def test_disabled_flag_is_passthrough(self, tmp_path: Path) -> None:
        crop = tmp_path / "two.png"
        _draw_two_benzenes_horizontal(crop)
        seg = SegmentationResult(
            segment_index=0,
            bbox=(0, 0, 600, 220),
            image_path=str(crop),
        )
        out = _maybe_split_oversized_segments(
            [(1, seg)],
            _splitter_settings(drawing_split_enabled=False),
            tmp_path,
        )
        assert out == [(1, seg)]

    def test_tall_two_molecule_segment_splits(self, tmp_path: Path) -> None:
        crop = tmp_path / "two_horiz_tall.png"
        _draw_two_benzenes_horizontal(crop)
        # Trigger at 200 so the 220-tall image qualifies.
        # The original detector bbox was at (100, 50)..(700, 270) on the page;
        # use this so we can verify sub-bbox offsets are preserved.
        seg = SegmentationResult(
            segment_index=7,
            bbox=(100, 50, 700, 270),
            image_path=str(crop),
            confidence=0.91,
        )
        out = _maybe_split_oversized_segments(
            [(2, seg)],
            _splitter_settings(drawing_split_min_height_trigger_px=200),
            tmp_path,
        )
        assert len(out) == 2, [r[1].bbox for r in out]
        for page_num, sub in out:
            assert page_num == 2
            assert sub.parent_segment_index == 7
            # Sub bboxes must be in page coords, offset by parent's top-left.
            assert sub.bbox[0] >= 100
            assert sub.bbox[1] >= 50
            assert sub.confidence == 0.91
            assert Path(sub.image_path).exists()

    def test_single_component_tall_crop_passes_through(self, tmp_path: Path) -> None:
        crop = tmp_path / "single_tall.png"
        # Tall enough to trigger but contains a single molecule => no split.
        _draw_single_benzene(crop, height=260, width=260)
        seg = SegmentationResult(
            segment_index=0,
            bbox=(0, 0, 260, 260),
            image_path=str(crop),
        )
        out = _maybe_split_oversized_segments(
            [(1, seg)],
            _splitter_settings(drawing_split_min_height_trigger_px=200),
            tmp_path,
        )
        # split_crop returns 1 sub-crop => helper must keep the original.
        assert out == [(1, seg)]

    def test_corrupt_image_keeps_original(self, tmp_path: Path) -> None:
        crop = tmp_path / "broken.png"
        crop.write_bytes(b"not-a-png")
        seg = SegmentationResult(
            segment_index=4,
            bbox=(0, 0, 600, 600),  # height=600 >= trigger
            image_path=str(crop),
        )
        out = _maybe_split_oversized_segments(
            [(0, seg)],
            _splitter_settings(drawing_split_min_height_trigger_px=200),
            tmp_path,
        )
        # cv2.imread returns None => split_crop raises => guard logs + keeps original.
        assert out == [(0, seg)]

    def test_segment_with_empty_image_path_passes_through(self, tmp_path: Path) -> None:
        seg = SegmentationResult(
            segment_index=0,
            bbox=(0, 0, 600, 600),
            image_path="",
        )
        out = _maybe_split_oversized_segments(
            [(0, seg)],
            _splitter_settings(drawing_split_min_height_trigger_px=200),
            tmp_path,
        )
        assert out == [(0, seg)]
