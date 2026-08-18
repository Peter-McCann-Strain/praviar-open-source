from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.pipeline.drawings.cascade import run_cascade_ocsr


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        drawing_cascade_enabled=True,
        drawing_confidence_threshold=0.8,
        drawing_cascade_high_threshold=0.95,
        drawing_cascade_medium_threshold=0.7,
        drawing_cascade_plausibility_threshold=0.5,
        drawing_cascade_min_resolved_conf=0.65,
        drawing_max_resolved_atoms=100,
    )


def _result(
    smiles: str,
    confidence: float,
    *,
    valid: bool = True,
    tool: str = "tool",
) -> OCSRResult:
    return OCSRResult(
        smiles=smiles,
        confidence=confidence,
        valid=valid,
        tool=tool,
        latency_ms=12.0,
    )


@pytest.mark.asyncio
async def test_run_cascade_no_cascade_runs_all_models(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    settings = _settings()
    settings.drawing_cascade_enabled = False
    runners = {
        "molscribe": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.91))),
        "molsight": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.83))),
    }

    def fake_fuse(results, **kwargs):
        captured["results"] = results
        return _result("CCO", 0.91, tool="fused")

    monkeypatch.setattr("praviar_pipeline.pipeline.drawings.cascade.fuse", fake_fuse)

    result = await run_cascade_ocsr(Path("image.png"), runners, settings)

    assert result.tool == "fused"
    assert set(captured["results"].keys()) == {"molscribe", "molsight"}


@pytest.mark.asyncio
async def test_run_cascade_missing_primary_falls_back_to_all_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    runners = {
        "molsight": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.83))),
        "decimer": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.77))),
    }

    def fake_fuse(results, **kwargs):
        captured["results"] = results
        return _result("CCO", 0.83, tool="fused")

    monkeypatch.setattr("praviar_pipeline.pipeline.drawings.cascade.fuse", fake_fuse)

    await run_cascade_ocsr(Path("image.png"), runners, _settings())

    assert set(captured["results"].keys()) == {"molsight", "decimer"}


@pytest.mark.asyncio
async def test_run_cascade_accepts_high_confidence_plausible_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runners = {
        "molscribe": SimpleNamespace(
            predict=AsyncMock(return_value=_result("CCO", 0.98, tool="molscribe"))
        ),
        "molsight": SimpleNamespace(predict=AsyncMock(return_value=_result("CCC", 0.81))),
    }
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.cascade.score_plausibility",
        lambda smiles: 0.9,
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.cascade.fuse",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fuse should not run")),
    )

    result = await run_cascade_ocsr(Path("image.png"), runners, _settings())

    assert result.tool == "cascade:molscribe_high_conf"
    runners["molsight"].predict.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_cascade_high_confidence_shortcut_still_enforces_atom_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_alkane = "C" * 101
    runners = {
        "molscribe": SimpleNamespace(
            predict=AsyncMock(return_value=_result(long_alkane, 0.99, tool="molscribe"))
        ),
        "molsight": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.81))),
    }
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.cascade.score_plausibility",
        lambda _smiles: 0.9,
    )

    result = await run_cascade_ocsr(Path("image.png"), runners, _settings())

    assert result.valid is False
    assert result.smiles == ""
    assert result.error == "exceeds_max_atoms"
    runners["molsight"].predict.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_cascade_medium_confidence_escalates_subset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    runners = {
        "molscribe": SimpleNamespace(
            predict=AsyncMock(return_value=_result("CCO", 0.8, tool="molscribe"))
        ),
        "molsight": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.82))),
        "decimer": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.78))),
        "molgrapher": SimpleNamespace(predict=AsyncMock(return_value=_result("CCC", 0.75))),
    }

    def fake_fuse(results, **kwargs):
        captured["results"] = results
        return _result("CCO", 0.82, tool="fused")

    monkeypatch.setattr("praviar_pipeline.pipeline.drawings.cascade.fuse", fake_fuse)

    result = await run_cascade_ocsr(Path("image.png"), runners, _settings())

    assert result.tool == "fused"
    assert set(captured["results"].keys()) == {"molscribe", "molsight", "decimer"}
    runners["molgrapher"].predict.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_cascade_low_confidence_runs_full_ensemble(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    runners = {
        "molscribe": SimpleNamespace(
            predict=AsyncMock(return_value=_result("CCO", 0.5, tool="molscribe"))
        ),
        "molsight": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.82))),
        "decimer": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.78))),
        "molgrapher": SimpleNamespace(predict=AsyncMock(return_value=_result("CCC", 0.75))),
    }

    def fake_fuse(results, **kwargs):
        captured["results"] = results
        return _result("CCO", 0.82, tool="fused")

    monkeypatch.setattr("praviar_pipeline.pipeline.drawings.cascade.fuse", fake_fuse)

    await run_cascade_ocsr(Path("image.png"), runners, _settings())

    assert set(captured["results"].keys()) == {"molscribe", "molsight", "decimer", "molgrapher"}


@pytest.mark.asyncio
async def test_run_cascade_implausible_high_confidence_primary_escalates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    runners = {
        "molscribe": SimpleNamespace(
            predict=AsyncMock(return_value=_result("CCO", 0.97, tool="molscribe"))
        ),
        "molsight": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.82))),
        "decimer": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.78))),
    }

    def fake_fuse(results, **kwargs):
        captured["results"] = results
        return _result("CCO", 0.82, tool="fused")

    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.cascade.score_plausibility",
        lambda smiles: 0.2,
    )
    monkeypatch.setattr("praviar_pipeline.pipeline.drawings.cascade.fuse", fake_fuse)

    await run_cascade_ocsr(Path("image.png"), runners, _settings())

    assert set(captured["results"].keys()) == {"molscribe", "molsight", "decimer"}


@pytest.mark.asyncio
async def test_run_cascade_forwards_ocr_labels_to_fuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ocr_labels`` reaches every fuse(...) call site."""
    captured: list[dict] = []
    settings = _settings()
    settings.drawing_cascade_enabled = False
    runners = {
        "molscribe": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.91))),
        "molsight": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.83))),
    }

    def fake_fuse(results, **kwargs):
        captured.append(kwargs)
        return _result("CCO", 0.91, tool="fused")

    monkeypatch.setattr("praviar_pipeline.pipeline.drawings.cascade.fuse", fake_fuse)

    labels = ["Boc", "Ts", "Ms"]
    await run_cascade_ocsr(
        Path("image.png"),
        runners,
        settings,
        ocr_labels=labels,
    )

    assert captured, "fuse was never called"
    assert captured[0]["ocr_labels"] == labels


@pytest.mark.asyncio
async def test_run_cascade_forwards_ocr_labels_in_full_ensemble(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Low-confidence primary path also forwards ``ocr_labels`` to fuse."""
    captured: list[dict] = []
    runners = {
        "molscribe": SimpleNamespace(
            predict=AsyncMock(return_value=_result("CCO", 0.5, tool="molscribe"))
        ),
        "molsight": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.82))),
        "decimer": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.78))),
    }

    def fake_fuse(results, **kwargs):
        captured.append(kwargs)
        return _result("CCO", 0.82, tool="fused")

    monkeypatch.setattr("praviar_pipeline.pipeline.drawings.cascade.fuse", fake_fuse)

    labels = ["Boc", "Fmoc"]
    await run_cascade_ocsr(
        Path("image.png"),
        runners,
        _settings(),
        ocr_labels=labels,
    )

    assert captured, "fuse was never called"
    assert captured[0]["ocr_labels"] == labels


@pytest.mark.asyncio
async def test_run_cascade_no_ocr_labels_passes_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When caller supplies no ``ocr_labels``, fuse() receives None (falsy)."""
    captured: list[dict] = []
    settings = _settings()
    settings.drawing_cascade_enabled = False
    runners = {
        "molscribe": SimpleNamespace(predict=AsyncMock(return_value=_result("CCO", 0.91))),
    }

    def fake_fuse(results, **kwargs):
        captured.append(kwargs)
        return _result("CCO", 0.91, tool="fused")

    monkeypatch.setattr("praviar_pipeline.pipeline.drawings.cascade.fuse", fake_fuse)

    await run_cascade_ocsr(Path("image.png"), runners, settings)

    assert captured, "fuse was never called"
    assert captured[0]["ocr_labels"] is None
