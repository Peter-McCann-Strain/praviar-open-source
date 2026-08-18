from __future__ import annotations

import pytest

from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.pipeline.drawings.chemistry import check_substructure, compute_tanimoto


def test_compute_tanimoto_identical_smiles_returns_one() -> None:
    assert compute_tanimoto("CCO", "CCO") == 1.0


def test_compute_tanimoto_invalid_smiles_fails_closed() -> None:
    with pytest.raises(SourceUnavailableError):
        compute_tanimoto("invalid", "CCO")


def test_check_substructure_positive_case() -> None:
    assert check_substructure("c1ccccc1", "Cc1ccccc1") is True


def test_check_substructure_invalid_smiles_fails_closed() -> None:
    with pytest.raises(SourceUnavailableError):
        check_substructure("invalid", "CCO")
