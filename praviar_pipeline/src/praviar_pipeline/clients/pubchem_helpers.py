"""Pure response-shaping helpers for the PubChem client."""

from __future__ import annotations

from typing import Any, cast

_PROP_ALIASES: dict[str, str] = {
    "ConnectivitySMILES": "CanonicalSMILES",
}


def normalize_props(props: dict) -> dict:
    """Normalize PubChem property key names for backward compatibility."""
    for api_key, expected_key in _PROP_ALIASES.items():
        if api_key in props and expected_key not in props:
            props[expected_key] = props.pop(api_key)
    return props


def extract_first_property(data: dict) -> dict:
    """Extract the first property record from a PropertyTable payload."""
    properties = data.get("PropertyTable", {}).get("Properties", [])
    if not properties:
        return {}
    return normalize_props(properties[0])


def extract_info_values(data: dict, field_name: str) -> list[Any]:
    """Extract a list-valued field from PubChem InformationList payloads."""
    info_list = data.get("InformationList", {}).get("Information", [])
    if not info_list:
        return []
    return cast("list[Any]", info_list[0].get(field_name, []))


def extract_sdq_rows(data: dict) -> tuple[list[dict], int]:
    """Extract paginated rows and total count from an SDQ payload."""
    output_set = data.get("SDQOutputSet")
    if output_set is None:
        raise KeyError("SDQOutputSet")

    if not output_set:
        return [], 0

    if isinstance(output_set, list):
        if len(output_set) == 0:
            return [], 0
        wrapper = output_set[0]
    elif isinstance(output_set, dict):
        wrapper = output_set
    else:
        raise TypeError(type(output_set).__name__)

    return wrapper.get("rows", []), wrapper.get("totalCount", 0)
