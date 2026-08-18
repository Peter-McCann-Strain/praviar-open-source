"""Pure helpers for USPTO ODP client response handling."""

from __future__ import annotations

from praviar_pipeline.utils.patent_ids import clean_patent_number_for_api


def is_key_valid(key: str) -> bool:
    """Check whether the USPTO ODP API key is configured."""
    return bool(key.strip())


def resolve_app_number_from_search(data: dict, patent_number: str) -> str | None:
    """Resolve an application number from an ODP search response."""
    results = data.get("patentFileWrapperDataBag", [])
    if not results:
        return None

    expected = clean_patent_number_for_api(patent_number)
    for entry in results:
        meta = entry.get("applicationMetaData", {})
        observed = clean_patent_number_for_api(str(meta.get("patentNumber") or ""))
        if observed and observed == expected:
            app_num = entry.get("applicationNumberText", "")
            if isinstance(app_num, str) and app_num:
                return app_num

    return None


def extract_first_wrapper_record(data: dict) -> dict:
    """Extract the first application record from an ODP wrapper payload."""
    bag = data.get("patentFileWrapperDataBag", [])
    if not isinstance(bag, list) or not bag or not isinstance(bag[0], dict):
        return {}
    return bag[0]


def extract_named_results(data: dict | list, *keys: str) -> list[dict]:
    """Extract list payloads that may live under one of several ODP keys."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []

    for key in keys:
        values = data.get(key)
        if isinstance(values, list):
            return values
    return []


def merge_continuity_entries(data: dict) -> list[dict]:
    """Merge parent and child continuity bags from application data."""
    parents = data.get("parentContinuityBag", [])
    children = data.get("childContinuityBag", [])
    return list(parents) + list(children)
