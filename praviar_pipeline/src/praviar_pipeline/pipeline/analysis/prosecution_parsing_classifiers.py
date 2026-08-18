"""Classification helpers for prosecution parsing."""

from __future__ import annotations

import re
from typing import Any

_STATUTE_RE = re.compile(r"\b(101|102|103|112)\b")

_AMENDMENT_CODES = {
    "AMND",
    "AMAL",
    "AMEN",
    "A...",
    "RES",
    "RESP",
    "RESP.ARG",
    "REFU",
    "REEX",
    "REM",
    "REQA",
}
_RCE_CODES = {"RCE"}
_INTERVIEW_CODES = {"EXIN", "EXINP", "INTV"}
_APPEAL_CODES = {"AP.BR", "APPEAL", "APDEC", "AFD", "FWD"}
_TD_CODES = {"DIST"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _clean(value).upper()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _unique_strings(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def extract_rejection_bases(*texts: str) -> list[str]:
    combined = " ".join(texts).lower()
    bases: list[str] = []
    for match in _STATUTE_RE.findall(combined):
        if match == "112":
            if "written description" in combined or "enablement" in combined:
                bases.append("112_a")
            elif "indefinit" in combined or "second paragraph" in combined:
                bases.append("112_b")
            else:
                bases.append("112")
        else:
            bases.append(match)
    if "double patent" in combined or "obviousness-type" in combined:
        bases.append("double_patenting")
    if "restriction" in combined:
        bases.append("restriction")
    if any(base in {"102", "103"} for base in bases):
        bases.append("prior_art")
    return _unique_strings(bases)


def classify_office_action_type(office_action: dict[str, Any]) -> str:
    code = _upper(office_action.get("documentCode"))
    desc = _lower(office_action.get("documentDescription") or office_action.get("documentCategory"))
    if code in {"CTNF", "NFOA"} or "non-final" in desc or "non final" in desc:
        return "non_final_office_action"
    if code in {"CTFR", "FOA"} or ("final" in desc and "office action" in desc):
        return "final_office_action"
    if "restriction" in desc:
        return "restriction_requirement"
    if "advisory action" in desc:
        return "advisory_action"
    if "allowance" in desc:
        return "notice_of_allowance"
    if "appeal" in desc:
        return "appeal_event"
    if "interview" in desc:
        return "interview_summary"
    return "other"


def normalize_continuity_type(entry: dict[str, Any]) -> str:
    raw = _lower(entry.get("claimTypeCd") or entry.get("continuityType"))
    if raw in {"cip", "continuation-in-part"} or "continuation in part" in raw:
        return "cip"
    if raw in {"con", "continuation"} or "continuation" in raw:
        return "continuation"
    if raw in {"div", "divisional"} or "divisional" in raw:
        return "divisional"
    if "provisional" in raw:
        return "provisional"
    if "reissue" in raw:
        return "reissue"
    return raw.replace(" ", "_").replace("-", "_") if raw else "other"


def classify_transaction_type(transaction: dict[str, Any]) -> str:
    code = _upper(transaction.get("transactionCode"))
    desc = _lower(transaction.get("transactionDescription"))
    if code in _TD_CODES or "terminal disclaimer" in desc:
        return "terminal_disclaimer"
    if code in _RCE_CODES or "continued examination" in desc:
        return "rce"
    if "after final" in desc:
        return "after_final_response"
    if code in _INTERVIEW_CODES or "interview" in desc:
        return "interview"
    if code in _APPEAL_CODES or "appeal" in desc:
        return "appeal"
    if code in _AMENDMENT_CODES or "amend" in desc:
        return "amendment"
    if "response" in desc:
        return "response"
    if "allowance" in desc:
        return "allowance"
    return "other"
