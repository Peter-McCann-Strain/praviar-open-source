from __future__ import annotations

import pytest

from praviar_pipeline.clients.pubchem_helpers import (
    extract_first_property,
    extract_info_values,
    extract_sdq_rows,
    normalize_props,
)


def test_normalize_props_maps_connectivity_smiles() -> None:
    props = normalize_props({"CID": 1, "ConnectivitySMILES": "CCO"})

    assert props["CanonicalSMILES"] == "CCO"
    assert "ConnectivitySMILES" not in props


def test_extract_first_property_returns_empty_dict_when_missing() -> None:
    assert extract_first_property({}) == {}


def test_extract_info_values_returns_empty_list_when_missing() -> None:
    assert extract_info_values({}, "Synonym") == []


def test_extract_sdq_rows_supports_dict_and_list_wrappers() -> None:
    rows, total = extract_sdq_rows({"SDQOutputSet": {"rows": [{"a": 1}], "totalCount": 3}})
    assert rows == [{"a": 1}]
    assert total == 3

    rows, total = extract_sdq_rows({"SDQOutputSet": [{"rows": [{"b": 2}], "totalCount": 4}]})
    assert rows == [{"b": 2}]
    assert total == 4


def test_extract_sdq_rows_rejects_unexpected_type() -> None:
    with pytest.raises(TypeError):
        extract_sdq_rows({"SDQOutputSet": "bad"})
