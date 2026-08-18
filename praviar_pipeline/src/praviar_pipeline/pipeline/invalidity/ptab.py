"""PTAB lookup helpers for invalidity assessment."""

from __future__ import annotations

import re
from typing import Literal, cast

from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError
from praviar_pipeline.models.invalidity import PTABProceeding, PTABResult

_TRIAL_NUMBER_RE = re.compile(r"^(IPR|PGR|CBM)\d{4}-\d{5}$")


def _required_mapping(value: object, *, description: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"PTAB {description} is missing")
    return value


async def check_ptab_impl(
    patent_id: str,
    *,
    client_factory,
    parse_date_fn,
    logger,
) -> PTABResult:
    """Query PTAB API for proceedings against a patent."""
    failure_type: str | None = None
    authentication_failure = False
    try:
        async with client_factory() as client:
            raw_proceedings = await client.get_proceedings(patent_id)
            if not raw_proceedings:
                return PTABResult(has_been_challenged=False)

            proceedings = []
            all_cancelled: list[int] = []

            for proc in raw_proceedings:
                if not isinstance(proc, dict):
                    raise ValueError("PTAB proceeding record is malformed")
                trial_metadata = _required_mapping(
                    proc.get("trialMetaData"),
                    description="trial metadata",
                )
                proceeding_number = str(proc.get("trialNumber") or "").strip()
                trial_number_match = _TRIAL_NUMBER_RE.fullmatch(proceeding_number)
                if trial_number_match is None:
                    raise ValueError("PTAB proceeding has an unsupported or missing trial number")
                proc_type = cast(
                    'Literal["IPR", "PGR", "CBM"]',
                    trial_number_match.group(1),
                )
                raw_trial_type_code = str(trial_metadata.get("trialTypeCode") or "").strip()
                if not raw_trial_type_code:
                    raise ValueError("PTAB proceeding has no trial type code")
                top_level_trial_type = str(proc.get("trialTypeCode") or "").strip()
                if top_level_trial_type and top_level_trial_type != proc_type:
                    raise ValueError("PTAB proceeding trial type conflicts with its number")
                proceeding_status = str(trial_metadata.get("trialStatusCategory") or "").strip()
                if not proceeding_status:
                    raise ValueError("PTAB proceeding has no trial status")
                proceeding = PTABProceeding(
                    proceeding_number=proceeding_number,
                    type=proc_type,
                    status=proceeding_status,
                    filing_date=parse_date_fn(trial_metadata.get("accordedFilingDate")),
                    outcome_summary=proceeding_status,
                )
                proceedings.append(proceeding)

                decisions = await client.get_decisions(proceeding.proceeding_number)
                for decision in decisions:
                    if not isinstance(decision, dict):
                        raise ValueError("PTAB decision record is malformed")
                    if "claimsCancelled" in decision or "claimsAmended" in decision:
                        raise ValueError(
                            "PTAB provider claim-effect fields are not a "
                            "controlling cancellation record"
                        )
                    decision_trial = str(
                        decision.get("trialNumber") or proceeding.proceeding_number
                    ).strip()
                    if decision_trial != proceeding.proceeding_number:
                        raise ValueError("PTAB decision is bound to a different trial")
                    decision_data = decision.get("decisionData")
                    if isinstance(decision_data, dict):
                        decision_type = str(
                            decision_data.get("decisionTypeCategory") or ""
                        ).casefold()
                        if decision_type == "final written decision":
                            proceeding.final_written_decision_verified = True
                        if proceeding.decision_date is None:
                            proceeding.decision_date = parse_date_fn(
                                decision_data.get("decisionIssueDate")
                            )
                    document_data = decision.get("documentData")
                    if document_data is not None and not isinstance(document_data, dict):
                        raise ValueError("PTAB decision document metadata is malformed")
                    if isinstance(document_data, dict) and "documentDate" in document_data:
                        raise ValueError("PTAB decision uses an obsolete document date field")

            return PTABResult(
                has_been_challenged=bool(proceedings),
                proceedings=proceedings,
                all_claims_cancelled=sorted(set(all_cancelled)),
            )

    except Exception as exc:
        failure_type = type(exc).__name__
        authentication_failure = isinstance(exc, AuthenticationError)
        logger.error(
            "ptab_auth_failed" if authentication_failure else "ptab_lookup_failed",
            error_type=failure_type,
        )

    # Raise outside the except block: the provider exception may retain a
    # credential-bearing URL in its text, request object, traceback, or cause.
    if failure_type is not None:
        if authentication_failure:
            raise AuthenticationError(
                "PTAB authentication failed",
                source="ptab",
            ) from None
        raise SourceUnavailableError("ptab", "PTAB lookup failed") from None

    raise AssertionError("PTAB lookup reached an unreachable state")
