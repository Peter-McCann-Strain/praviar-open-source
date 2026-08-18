"""Patent-level helpers for Step 2.75 drawing analysis."""

from __future__ import annotations

import hashlib
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import structlog
from tenacity import RetryError

from praviar_pipeline.errors import (
    DrawingAcquisitionError,
    DrawingSegmentationError,
    EPOCredentialsMissingError,
    PraviarPipelineError,
)
from praviar_pipeline.models.drawing import (
    DrawingStructure,
    PatentDrawingAnalysis,
    SegmentationResult,
)
from praviar_pipeline.ocsr.cropping import SubCropConfig, split_crop
from praviar_pipeline.pipeline.drawing_rollout import drawing_evidence_can_influence
from praviar_pipeline.pipeline.drawings import structure_analysis as drawing_structure_analysis
from praviar_pipeline.utils.private_artifacts import atomic_write_bytes, ensure_private_directory
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from praviar_pipeline.clients.epo_ops import EPOOPSClient
    from praviar_pipeline.config import Settings
    from praviar_pipeline.ocsr.runner import OCSRRunner, SegmentationRunner

logger = structlog.get_logger()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(slots=True)
class PatentDrawingPages:
    drawing_pages: list[tuple[int, bytes]]
    page_paths: list[tuple[int, Path]]
    fetch_time: float


@dataclass(slots=True)
class PatentDrawingSegments:
    all_segments: list[tuple[int, SegmentationResult]]
    seg_time: float


def _maybe_split_oversized_segments(
    all_segments: list[tuple[int, SegmentationResult]],
    settings: Settings,
    patent_dir: Path,
) -> list[tuple[int, SegmentationResult]]:
    """Split unusually large detector crops before OCSR.

    MolDet emits per-molecule bboxes so the splitter rarely fires on the new
    detector path; but DECIMER's region-level bboxes occasionally produce
    super-crops, and even MolDet may output an unusually tall bbox in edge
    cases (stacked stereoisomers drawn as a single visual unit). For each
    segment whose height exceeds ``settings.drawing_split_min_height_trigger_px``
    we run :func:`split_crop` and replace the original with the resulting
    sub-crops. Sub-crops inherit ``parent_segment_index`` from the original.

    No-op when ``settings.drawing_split_enabled`` is false. On per-segment
    failure (corrupt PNG, OpenCV import error, etc.) the original segment is
    kept and a warning is logged — the splitter must never break the pipeline.
    """
    # Defensive guards — older test fixtures use Mock/SimpleNamespace
    # settings that lack split fields. Treat any non-bool
    # `drawing_split_enabled` or non-int trigger as "splitter disabled"
    # rather than raising and breaking unrelated tests.
    enabled = getattr(settings, "drawing_split_enabled", False)
    if not isinstance(enabled, bool) or not enabled:
        return all_segments
    trigger_px = getattr(settings, "drawing_split_min_height_trigger_px", 0)
    if not isinstance(trigger_px, int) or trigger_px <= 0:
        return all_segments

    config = SubCropConfig.from_settings(settings)
    out: list[tuple[int, SegmentationResult]] = []

    for page_num, seg in all_segments:
        h = seg.bbox[3] - seg.bbox[1]
        if h < trigger_px:
            out.append((page_num, seg))
            continue
        if not seg.image_path:
            out.append((page_num, seg))
            continue

        crop_path = Path(seg.image_path)
        split_dir = patent_dir / f"split_p{page_num:03d}_s{seg.segment_index:03d}"

        try:
            sub_crops = split_crop(crop_path, split_dir, config)
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning(
                "split_crop_failed",
                segment_index=seg.segment_index,
                page=page_num,
                error_type=safe_exception_type(exc),
            )
            out.append((page_num, seg))
            continue

        if len(sub_crops) <= 1:
            out.append((page_num, seg))
            continue

        x0, y0 = seg.bbox[0], seg.bbox[1]
        for sub in sub_crops:
            sx1, sy1, sx2, sy2 = sub.bbox_in_crop
            out.append(
                (
                    page_num,
                    SegmentationResult(
                        segment_index=len(out),
                        bbox=(x0 + sx1, y0 + sy1, x0 + sx2, y0 + sy2),
                        image_path=str(sub.image_path),
                        width=sub.width,
                        height=sub.height,
                        confidence=seg.confidence,
                        parent_segment_index=seg.segment_index,
                    ),
                )
            )
        logger.info(
            "split_crop_applied",
            page=page_num,
            parent_segment_index=seg.segment_index,
            n_sub_crops=len(sub_crops),
        )

    return out


async def fetch_and_materialize_patent_pages(
    patent_id: str,
    epo_client: EPOOPSClient | None,
    patent_dir: Path,
    settings: Settings,
    *,
    fetch_pdf_fallback_fn: Callable[..., Awaitable[list[tuple[int, bytes]]]],
) -> PatentDrawingPages:
    """Fetch drawing pages and persist them to disk for downstream processing."""
    t_fetch = time.monotonic()
    drawing_pages: list[tuple[int, bytes]] = []
    failure_types: list[str] = []
    fail_closed = drawing_evidence_can_influence(settings)

    if epo_client:
        try:
            drawing_pages = await epo_client.fetch_all_drawings(
                patent_id,
                max_pages=settings.drawing_max_pages_per_patent,
                fail_closed=fail_closed,
            )
        except EPOCredentialsMissingError as exc:
            failure_types.append(safe_exception_type(exc))
            logger.info(
                "drawing_fetch_skipped_no_credentials",
                error_type=safe_exception_type(exc),
            )
        except (
            PraviarPipelineError,
            RetryError,
            httpx.HTTPError,
            ConnectionError,
            TimeoutError,
            OSError,
            RuntimeError,
            ValueError,
        ) as exc:
            failure_types.append(safe_exception_type(exc))
            logger.warning(
                "drawing_fetch_failed",
                error_type=safe_exception_type(exc),
            )

    if not drawing_pages and epo_client:
        try:
            drawing_pages = await fetch_pdf_fallback_fn(
                patent_id,
                epo_client,
                patent_dir,
                max_pages=settings.drawing_max_pages_per_patent,
                max_pdf_bytes=settings.drawing_pdf_max_bytes,
                max_pixels_per_page=settings.drawing_max_pixels_per_page,
                max_total_pixels=settings.drawing_max_total_pixels_per_patent,
            )
            if drawing_pages:
                logger.info(
                    "drawing_pdf_fallback_success",
                    pages=len(drawing_pages),
                )
        except (
            PraviarPipelineError,
            RetryError,
            httpx.HTTPError,
            ConnectionError,
            TimeoutError,
            OSError,
            ImportError,
            RuntimeError,
            ValueError,
        ) as exc:
            failure_types.append(safe_exception_type(exc))
            logger.warning(
                "drawing_pdf_fallback_failed",
                error_type=safe_exception_type(exc),
            )

    if not drawing_pages and failure_types and fail_closed:
        raise DrawingAcquisitionError(failure_types=tuple(failure_types)) from None

    page_paths: list[tuple[int, Path]] = []
    for page_num, img_bytes in drawing_pages:
        page_path = patent_dir / f"page_{page_num:03d}.png"
        atomic_write_bytes(page_path, img_bytes)
        page_paths.append((page_num, page_path))

    return PatentDrawingPages(
        drawing_pages=drawing_pages,
        page_paths=page_paths,
        fetch_time=time.monotonic() - t_fetch,
    )


async def segment_patent_pages(
    patent_id: str,
    patent_dir: Path,
    page_paths: list[tuple[int, Path]],
    seg_runner: SegmentationRunner | None,
    *,
    fail_closed: bool,
) -> PatentDrawingSegments:
    """Segment page images into structure crops, or fall back to full-page analysis."""
    t_seg = time.monotonic()
    all_segments: list[tuple[int, SegmentationResult]] = []

    if seg_runner:
        for page_num, page_path in page_paths:
            try:
                segments = await seg_runner.segment(
                    page_path, patent_dir / f"segments_p{page_num:03d}"
                )
                for seg in segments:
                    all_segments.append((page_num, seg))
            except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
                logger.warning(
                    "segmentation_failed",
                    page=page_num,
                    error_type=safe_exception_type(exc),
                )
                if fail_closed:
                    raise DrawingSegmentationError(
                        failure_types=(safe_exception_type(exc),)
                    ) from None
    else:
        for page_num, page_path in page_paths:
            all_segments.append(
                (
                    page_num,
                    SegmentationResult(
                        segment_index=0,
                        bbox=(0, 0, 0, 0),
                        image_path=str(page_path),
                    ),
                )
            )

    return PatentDrawingSegments(
        all_segments=all_segments,
        seg_time=time.monotonic() - t_seg,
    )


async def analyze_patent_segments(
    patent_id: str,
    patent_dir: Path,
    all_segments: list[tuple[int, SegmentationResult]],
    all_runners: dict[str, OCSRRunner],
    target_smiles: str,
    settings: Settings,
    *,
    patent_text: str,
    analyze_structure_image_fn: Callable[..., Awaitable[DrawingStructure | None]],
) -> tuple[list[DrawingStructure], float]:
    """Run structure-level analysis over each segment in a patent's drawings."""
    t_ocsr = time.monotonic()
    structures: list[DrawingStructure] = []

    for idx, (page_num, seg) in enumerate(all_segments):
        seg_path = Path(seg.image_path) if seg.image_path else None
        if not seg_path or not seg_path.exists():
            logger.debug(
                "drawing_segment_missing_image",
                page_number=page_num,
                segment_index=idx,
            )
            continue

        structure = await analyze_structure_image_fn(
            image_path=seg_path,
            patent_id=patent_id,
            page_number=page_num,
            structure_index=idx,
            all_runners=all_runners,
            target_smiles=target_smiles,
            settings=settings,
            patent_text=patent_text,
        )
        if structure:
            structure.bbox = seg.bbox
            source_page = patent_dir / f"page_{page_num:03d}.png"
            structure.original_page_image = str(source_page)
            structure.source_page_image_sha256 = _sha256_file(source_page)
            structures.append(structure)

    return structures, time.monotonic() - t_ocsr


async def analyze_single_patent(
    patent_id: str,
    epo_client: EPOOPSClient | None,
    seg_runner: SegmentationRunner | None,
    all_runners: dict[str, OCSRRunner],
    target_smiles: str,
    settings: Settings,
    work_dir: Path,
    *,
    patent_text: str,
    fetch_pdf_fallback_fn: Callable[..., Awaitable[list[tuple[int, bytes]]]],
    analyze_structure_image_fn: Callable[..., Awaitable[DrawingStructure | None]],
    figure_gap_fn: Callable[[str, int], list[str]],
) -> PatentDrawingAnalysis:
    """Run the full patent-level drawing analysis workflow."""
    t0 = time.monotonic()
    patent_dir = work_dir / patent_id.replace("/", "_")
    ensure_private_directory(patent_dir)

    pages = await fetch_and_materialize_patent_pages(
        patent_id=patent_id,
        epo_client=epo_client,
        patent_dir=patent_dir,
        settings=settings,
        fetch_pdf_fallback_fn=fetch_pdf_fallback_fn,
    )
    if not pages.drawing_pages:
        return PatentDrawingAnalysis(
            patent_id=patent_id,
            fetch_time_s=round(pages.fetch_time, 2),
            total_time_s=round(time.monotonic() - t0, 2),
            drawing_summary=f"No drawing pages available for {patent_id}",
        )

    segments = await segment_patent_pages(
        patent_id=patent_id,
        patent_dir=patent_dir,
        page_paths=pages.page_paths,
        seg_runner=seg_runner,
        fail_closed=drawing_evidence_can_influence(settings),
    )
    if not segments.all_segments:
        return PatentDrawingAnalysis(
            patent_id=patent_id,
            pages_fetched=len(pages.drawing_pages),
            fetch_time_s=round(pages.fetch_time, 2),
            segmentation_time_s=round(segments.seg_time, 2),
            total_time_s=round(time.monotonic() - t0, 2),
            drawing_summary=(
                f"No structures found in {len(pages.drawing_pages)} pages of {patent_id}"
            ),
        )

    # Split oversized region-detector crops before OCSR.
    segments.all_segments = _maybe_split_oversized_segments(
        segments.all_segments,
        settings,
        patent_dir,
    )

    structures, ocsr_time = await analyze_patent_segments(
        patent_id=patent_id,
        patent_dir=patent_dir,
        all_segments=segments.all_segments,
        all_runners=all_runners,
        target_smiles=target_smiles,
        settings=settings,
        patent_text=patent_text,
        analyze_structure_image_fn=analyze_structure_image_fn,
    )
    total_time = time.monotonic() - t0

    return drawing_structure_analysis.build_patent_drawing_analysis(
        patent_id=patent_id,
        drawing_pages=pages.drawing_pages,
        structures=structures,
        patent_text=patent_text,
        fetch_time=pages.fetch_time,
        seg_time=segments.seg_time,
        ocsr_time=ocsr_time,
        total_time=total_time,
        figure_gap_fn=figure_gap_fn,
    )
