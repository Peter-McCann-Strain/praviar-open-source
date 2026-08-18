from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from praviar_pipeline.ocsr.classifier_v2 import (
    ImageCategory,
    _worker_env,
    configure_from_settings,
    resolve_worker_category,
)


def _settings(*, box: float, nc_min: float) -> SimpleNamespace:
    return SimpleNamespace(
        drawing_classifier_box_score_thresh=box,
        drawing_classifier_non_chemical_min_conf=nc_min,
    )


def test_classifier_configuration_is_required_and_never_reads_threshold_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOLCLASSIFIER_BOX_THRESH", "0.010000")
    monkeypatch.setenv("MOLCLASSIFIER_NC_MIN_CONF", "0.010000")

    config = configure_from_settings(_settings(box=0.8, nc_min=0.95))

    assert _worker_env(config)["MOLCLASSIFIER_BOX_THRESH"] == "0.800000"
    assert _worker_env(config)["MOLCLASSIFIER_NC_MIN_CONF"] == "0.950000"
    assert resolve_worker_category("non_chemical", 0.8, config) is ImageCategory.MOLECULE


@pytest.mark.asyncio
async def test_concurrent_classifier_tasks_cannot_cross_contaminate() -> None:
    ready = asyncio.Event()
    configured = 0

    async def evaluate(
        *,
        box: float,
        nc_min: float,
    ) -> tuple[str, str, ImageCategory]:
        nonlocal configured
        configure_from_settings(_settings(box=box, nc_min=nc_min))
        configured += 1
        if configured == 2:
            ready.set()
        await ready.wait()
        await asyncio.sleep(0)
        worker_env = _worker_env()
        return (
            worker_env["MOLCLASSIFIER_BOX_THRESH"],
            worker_env["MOLCLASSIFIER_NC_MIN_CONF"],
            resolve_worker_category("non_chemical", 0.8),
        )

    high_gate, low_gate = await asyncio.gather(
        evaluate(box=0.9, nc_min=0.95),
        evaluate(box=0.4, nc_min=0.5),
    )

    assert high_gate == ("0.900000", "0.950000", ImageCategory.MOLECULE)
    assert low_gate == ("0.400000", "0.500000", ImageCategory.NON_CHEMICAL)


@pytest.mark.parametrize(
    ("box", "nc_min"),
    [
        (-0.1, 0.95),
        (1.1, 0.95),
        (0.8, float("nan")),
        (0.8, float("inf")),
    ],
)
def test_classifier_configuration_rejects_invalid_thresholds(
    box: float,
    nc_min: float,
) -> None:
    with pytest.raises(RuntimeError, match=r"finite value in \[0, 1\]"):
        configure_from_settings(_settings(box=box, nc_min=nc_min))
