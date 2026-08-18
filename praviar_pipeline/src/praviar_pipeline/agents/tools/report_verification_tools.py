"""ReportVerificationToolkit — 5 tools for fact-checking report assertions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.agents.tools.report_verification_tools_helpers import (
    build_report_verification_tool_definitions,
    exec_check_assignee,
    exec_check_date,
    exec_check_element_status,
    exec_check_patent_exists,
    exec_check_risk_level,
    normalize_assignee,
)

logger = structlog.get_logger()
_normalize_assignee = normalize_assignee

if TYPE_CHECKING:
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore
VERIFICATION_TOOL_DEFINITIONS: list[dict[str, Any]] = build_report_verification_tool_definitions()
_ASSERTION_ID = re.compile(r"^A[0-9]{5}-[a-f0-9]{12}$")
_PATENT_ID = re.compile(r"^[A-Z]{2}[0-9]{4,16}[A-Z][0-9]$")


@dataclass(frozen=True, slots=True)
class VerificationToolReceipt:
    assertion_id: str
    assertion_sha256: str
    receipt_id: str
    result: str
    tool_input_json: str
    tool_input_sha256: str
    tool_name: str


class ReportVerificationToolkit:
    """Toolkit for the verification agent to fact-check report assertions.

    Implements the Toolkit protocol (tool_definitions + execute).
    Never raises — returns structured match/mismatch results.
    """

    def __init__(self, data_store: ReportDataStore) -> None:
        self._store = data_store
        self._receipts: list[VerificationToolReceipt] = []
        self._handlers: dict[str, Any] = {
            "check_patent_exists": self._exec_check_patent_exists,
            "check_risk_level": self._exec_check_risk_level,
            "check_element_status": self._exec_check_element_status,
            "check_date": self._exec_check_date,
            "check_assignee": self._exec_check_assignee,
        }

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        return VERIFICATION_TOOL_DEFINITIONS

    @property
    def receipts(self) -> tuple[VerificationToolReceipt, ...]:
        return tuple(self._receipts)

    def _record_receipt(
        self,
        *,
        assertion_id: str,
        assertion_text: str,
        tool_name: str,
        tool_input: dict[str, Any],
        result: str,
    ) -> None:
        assertion_sha256 = hashlib.sha256(assertion_text.encode("utf-8")).hexdigest()
        tool_input_json = json.dumps(
            tool_input,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        tool_input_sha256 = hashlib.sha256(tool_input_json.encode("utf-8")).hexdigest()
        canonical = json.dumps(
            {
                "assertion_id": assertion_id,
                "assertion_sha256": assertion_sha256,
                "result": result,
                "tool_input_json": tool_input_json,
                "tool_input_sha256": tool_input_sha256,
                "tool_name": tool_name,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        self._receipts.append(
            VerificationToolReceipt(
                assertion_id=assertion_id,
                assertion_sha256=assertion_sha256,
                receipt_id=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                result=result,
                tool_input_json=tool_input_json,
                tool_input_sha256=tool_input_sha256,
                tool_name=tool_name,
            )
        )

    async def execute(self, tool_name: str, tool_input: dict) -> str:
        assertion_id = str(tool_input.get("assertion_id") or "").strip()
        assertion_text = str(tool_input.get("assertion_text") or "").strip()
        handler_input = dict(tool_input)
        handler_input.pop("assertion_id", None)
        handler_input.pop("assertion_text", None)
        handler = self._handlers.get(tool_name)
        if not handler:
            result = f"Unknown tool: {tool_name}. Available: {list(self._handlers.keys())}"
            self._record_receipt(
                assertion_id=assertion_id,
                assertion_text=assertion_text,
                tool_name=tool_name,
                tool_input=handler_input,
                result=result,
            )
            return result
        try:
            expected_digest = hashlib.sha256(assertion_text.encode("utf-8")).hexdigest()
            if (
                not _ASSERTION_ID.fullmatch(assertion_id)
                or not assertion_text
                or not assertion_id.endswith(expected_digest[:12])
            ):
                result = (
                    "Tool call rejected: assertion_id and exact assertion_text "
                    "are missing or do not match"
                )
            elif not _tool_input_is_bound_to_assertion(
                tool_name,
                assertion_text,
                handler_input,
            ):
                result = (
                    "Tool call rejected: verification query is not applicable "
                    "to the bound assertion"
                )
            else:
                result = await handler(handler_input)
        except Exception:
            logger.error(
                "verification_tool_error",
                tool=tool_name,
            )
            result = f"Tool '{tool_name}' failed with a data access or validation error"
        self._record_receipt(
            assertion_id=assertion_id,
            assertion_text=assertion_text,
            tool_name=tool_name,
            tool_input=handler_input,
            result=result,
        )
        return result

    async def _exec_check_patent_exists(self, input_data: dict) -> str:
        return await exec_check_patent_exists(self._store, input_data)

    async def _exec_check_risk_level(self, input_data: dict) -> str:
        return await exec_check_risk_level(self._store, input_data)

    async def _exec_check_element_status(self, input_data: dict) -> str:
        return await exec_check_element_status(self._store, input_data)

    async def _exec_check_date(self, input_data: dict) -> str:
        return await exec_check_date(self._store, input_data)

    async def _exec_check_assignee(self, input_data: dict) -> str:
        return await exec_check_assignee(self._store, input_data)


def _canonical_alnum(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _tool_input_is_bound_to_assertion(
    tool_name: str,
    assertion_text: str,
    tool_input: dict[str, Any],
) -> bool:
    """Require every deterministic query entity/value to occur in the assertion."""
    assertion = _canonical_alnum(assertion_text)
    raw_patent_id = str(tool_input.get("patent_id", "")).strip()
    patent_id = _canonical_alnum(raw_patent_id)
    if not _PATENT_ID.fullmatch(raw_patent_id) or patent_id not in assertion:
        return False

    if tool_name == "check_patent_exists":
        return True
    if tool_name == "check_risk_level":
        claimed = _canonical_alnum(tool_input.get("claimed_risk_level", ""))
        return bool(claimed and claimed in assertion)
    if tool_name == "check_element_status":
        claim_number = _canonical_alnum(tool_input.get("claim_number", ""))
        element_number = _canonical_alnum(tool_input.get("element_number", ""))
        status = _canonical_alnum(tool_input.get("claimed_status", ""))
        return bool(
            claim_number
            and element_number
            and status
            and f"claim{claim_number}" in assertion
            and f"element{element_number}" in assertion
            and status in assertion
        )
    if tool_name == "check_date":
        date_type = _canonical_alnum(tool_input.get("date_type", ""))
        claimed_date = _canonical_alnum(tool_input.get("claimed_date", ""))
        return bool(
            date_type and claimed_date and date_type in assertion and claimed_date in assertion
        )
    if tool_name == "check_assignee":
        claimed = _canonical_alnum(tool_input.get("claimed_assignee", ""))
        return bool(claimed and claimed in assertion)
    return False


def verification_tool_receipt_is_valid(receipt: VerificationToolReceipt) -> bool:
    """Recompute every digest in an immutable receipt before trusting it."""
    if not (
        _ASSERTION_ID.fullmatch(receipt.assertion_id)
        and re.fullmatch(r"[a-f0-9]{64}", receipt.assertion_sha256)
        and re.fullmatch(r"[a-f0-9]{64}", receipt.tool_input_sha256)
        and re.fullmatch(r"[a-f0-9]{64}", receipt.receipt_id)
        and receipt.assertion_id.endswith(receipt.assertion_sha256[:12])
    ):
        return False
    if (
        hashlib.sha256(receipt.tool_input_json.encode("utf-8")).hexdigest()
        != receipt.tool_input_sha256
    ):
        return False
    canonical = json.dumps(
        {
            "assertion_id": receipt.assertion_id,
            "assertion_sha256": receipt.assertion_sha256,
            "result": receipt.result,
            "tool_input_json": receipt.tool_input_json,
            "tool_input_sha256": receipt.tool_input_sha256,
            "tool_name": receipt.tool_name,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest() == receipt.receipt_id


def verification_tool_receipt_is_applicable(
    receipt: VerificationToolReceipt,
    assertion_text: str,
) -> bool:
    """Revalidate the receipt query against the exact report assertion."""
    if (
        not verification_tool_receipt_is_valid(receipt)
        or hashlib.sha256(assertion_text.encode("utf-8")).hexdigest() != receipt.assertion_sha256
    ):
        return False
    try:
        tool_input = json.loads(receipt.tool_input_json)
    except json.JSONDecodeError:
        return False
    return isinstance(tool_input, dict) and _tool_input_is_bound_to_assertion(
        receipt.tool_name,
        assertion_text,
        tool_input,
    )
