from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.pipeline.drawings.preprocessing import (
    get_preprocessing_steps,
    image_hash,
    jurisdiction_from_patent_id,
)


def test_image_hash_is_stable() -> None:
    assert image_hash(b"abc123") == image_hash(b"abc123")


def test_image_hash_changes_with_content() -> None:
    assert image_hash(b"abc123") != image_hash(b"xyz789")


def test_jurisdiction_from_patent_id_maps_known_prefixes() -> None:
    assert jurisdiction_from_patent_id("US123") == "US"
    assert jurisdiction_from_patent_id("EP123") == "EP"
    assert jurisdiction_from_patent_id("JP123") == "JP"


def test_jurisdiction_from_patent_id_returns_unknown_for_unmapped_prefix() -> None:
    assert jurisdiction_from_patent_id("ZZ123") == "UNKNOWN"


def test_get_preprocessing_steps_respects_disabled_jurisdiction_awareness() -> None:
    settings = SimpleNamespace(
        drawing_preprocessing=["clahe", "binarize"],
        drawing_jurisdiction_aware=False,
    )
    assert get_preprocessing_steps("JP", settings) == ["clahe", "binarize"]


def test_get_preprocessing_steps_adds_jp_steps_once() -> None:
    settings = SimpleNamespace(
        drawing_preprocessing=["clahe", "denoise"],
        drawing_jurisdiction_aware=True,
    )
    assert get_preprocessing_steps("JP", settings) == ["clahe", "denoise", "sharpen"]


def test_get_preprocessing_steps_adds_cn_denoise() -> None:
    settings = SimpleNamespace(
        drawing_preprocessing=["clahe", "binarize"],
        drawing_jurisdiction_aware=True,
    )
    assert get_preprocessing_steps("CN", settings) == ["denoise", "clahe", "binarize"]
