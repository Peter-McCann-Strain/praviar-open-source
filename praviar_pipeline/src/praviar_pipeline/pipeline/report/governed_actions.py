"""Decision-consistent action items derived only after clearance governance."""

from __future__ import annotations

from collections import defaultdict

from praviar_pipeline.models.report import (
    ActionItem,
    ActionPriority,
    ActionType,
    ClearanceOutcome,
)


def _validated_design_around_suggestions(analysis) -> list[object]:
    return [
        suggestion
        for suggestion in getattr(analysis, "design_around_suggestions", []) or []
        if getattr(suggestion, "smiles", None)
        and getattr(suggestion, "rdkit_valid", None) is True
        and getattr(suggestion, "pharmacophore_preserved", None) is True
        and getattr(suggestion, "tanimoto_to_original", None) is not None
    ]


def _ipr_prerequisites_complete(assessment) -> bool:
    if assessment is None:
        return False
    return bool(
        assessment.ipr_prior_art_scope_verified
        and assessment.ipr_timing_verified
        and assessment.ipr_estoppel_and_rpi_verified
        and assessment.ipr_discretionary_denial_reviewed
        and any(
            argument.type in {"anticipation", "obviousness"} and bool(argument.key_evidence)
            for argument in assessment.arguments
        )
        and any(
            reference.ipr_eligible_printed_publication
            and bool(reference.ipr_eligibility_basis.strip())
            for reference in assessment.prior_art
        )
    )


def build_governed_action_items(report, clearance_outputs: dict) -> list[ActionItem]:
    """Build final actions from governed claim decisions, never upstream risk labels."""
    clearance = clearance_outputs["clearance_decision"]
    outcome = clearance.decision
    decision_scope = clearance_outputs["decision_scope"]
    target_jurisdictions = set(decision_scope.jurisdictions)
    governed_decisions = [
        decision
        for decision in clearance_outputs.get("claim_program_decisions", [])
        if not target_jurisdictions or decision.jurisdiction in target_jurisdictions
    ]
    analyses_by_id = {
        analysis.patent_id: analysis for analysis in getattr(report, "patent_analyses", []) or []
    }
    invalidity_by_id = {
        assessment.patent_id: assessment
        for assessment in getattr(report, "invalidity_assessments", []) or []
    }
    summary = clearance.decision_audit.claim_program_summary
    blocking_claim_ids = set(summary.blocking_claim_ids)
    blocking_by_patent: dict[str, list[str]] = defaultdict(list)
    for claim_id in blocking_claim_ids:
        patent_id, _, claim_suffix = claim_id.partition("#claim")
        blocking_by_patent[patent_id].append(claim_suffix or "?")

    jurisdiction_label = ", ".join(sorted(target_jurisdictions)) or "the governed target"
    items: list[ActionItem] = []
    if outcome == ClearanceOutcome.BLOCKED:
        blocker_ids = sorted(blocking_by_patent)
        items.append(
            ActionItem(
                action_type=ActionType.HALT,
                priority=ActionPriority.CRITICAL,
                description=(
                    f"Pause the scoped commercial action in {jurisdiction_label} until "
                    "counsel resolves the governed blocking claims."
                ),
                patent_ids=blocker_ids,
                reasoning=(
                    "The final clearance decision is BLOCKED on complete, target-scope "
                    "claim, status, accused-act, territory, timing, and evidence gates."
                ),
                estimated_timeline="Before commitment, launch, manufacture, import, sale, or use.",
            )
        )
        for patent_id in blocker_ids:
            analysis = analyses_by_id.get(patent_id)
            invalidity = invalidity_by_id.get(patent_id)
            validated_suggestions = (
                _validated_design_around_suggestions(analysis) if analysis is not None else []
            )
            if invalidity is not None and _ipr_prerequisites_complete(invalidity):
                items.append(
                    ActionItem(
                        action_type=ActionType.CHALLENGE_IPR,
                        priority=ActionPriority.HIGH,
                        description=(
                            f"Counsel to evaluate an IPR for {patent_id}; all retained "
                            "§311(b), timing, estoppel/RPI, and discretionary-denial "
                            "prerequisites are explicitly verified."
                        ),
                        patent_ids=[patent_id],
                        reasoning=str(getattr(invalidity, "reasoning", "") or ""),
                        estimated_timeline="Counsel-controlled petition assessment.",
                    )
                )
            if validated_suggestions:
                items.append(
                    ActionItem(
                        action_type=ActionType.DESIGN_AROUND,
                        priority=ActionPriority.HIGH,
                        description=(
                            f"R&D and counsel to evaluate {len(validated_suggestions)} "
                            f"structure-validated design-around hypothesis(es) for {patent_id} "
                            "against every governed blocking claim."
                        ),
                        patent_ids=[patent_id],
                        reasoning=str(getattr(validated_suggestions[0], "suggestion", "") or ""),
                        estimated_timeline="After feasibility, activity, and claim re-testing.",
                    )
                )
            if not validated_suggestions and not _ipr_prerequisites_complete(invalidity):
                items.append(
                    ActionItem(
                        action_type=ActionType.LICENSE,
                        priority=ActionPriority.HIGH,
                        description=(
                            f"Counsel to verify current ownership and evaluate a license or "
                            f"other negotiated resolution for {patent_id}; no counterparty "
                            "is named until an authoritative ownership record is retained."
                        ),
                        patent_ids=[patent_id],
                        reasoning=(
                            "A governed blocker remains and neither a validated design-around "
                            "nor a fully qualified IPR record is available."
                        ),
                    )
                )
    elif outcome == ClearanceOutcome.UNCLEAR:
        incomplete_by_patent: dict[str, set[str]] = defaultdict(set)
        for decision in governed_decisions:
            if not decision.evidence_sufficient:
                incomplete_by_patent[decision.patent_id].update(decision.missing_components)
        affected_ids = sorted(incomplete_by_patent)
        items.append(
            ActionItem(
                action_type=ActionType.HALT,
                priority=ActionPriority.HIGH,
                description=(
                    f"Do not rely on this report for the scoped action in "
                    f"{jurisdiction_label} until the clearance record is complete."
                ),
                patent_ids=affected_ids,
                reasoning=(
                    "The final governed outcome is UNCLEAR. Automated license, design-around, "
                    "challenge, or risk-acceptance advice is withheld."
                ),
                estimated_timeline="Before a reliance decision.",
            )
        )
        for patent_id in affected_ids:
            gaps = sorted(incomplete_by_patent[patent_id])
            items.append(
                ActionItem(
                    action_type=ActionType.MONITOR,
                    priority=ActionPriority.HIGH,
                    description=(
                        f"Counsel and the evidence team to close the governed record for "
                        f"{patent_id}: {', '.join(gaps[:6])}."
                    ),
                    patent_ids=[patent_id],
                    reasoning=(
                        "This is an evidence-collection instruction, not a conclusion "
                        "that the patent blocks or clears the scoped action."
                    ),
                )
            )

    priority_order = {
        ActionPriority.CRITICAL: 0,
        ActionPriority.HIGH: 1,
        ActionPriority.MEDIUM: 2,
        ActionPriority.LOW: 3,
    }
    return sorted(
        items,
        key=lambda item: (
            priority_order.get(item.priority, 4),
            item.action_type.value,
            item.patent_ids,
        ),
    )


def build_governed_key_risks(clearance_outputs: dict) -> list[str]:
    """Project decision-consistent risks without leaking supporting-scope screens."""
    clearance = clearance_outputs["clearance_decision"]
    outcome = clearance.decision
    target_jurisdictions = set(clearance_outputs["decision_scope"].jurisdictions)
    decisions = [
        decision
        for decision in clearance_outputs.get("claim_program_decisions", [])
        if not target_jurisdictions or decision.jurisdiction in target_jurisdictions
    ]
    summary = clearance.decision_audit.claim_program_summary
    if outcome == ClearanceOutcome.CLEAR:
        return []
    if outcome == ClearanceOutcome.BLOCKED:
        claims_by_patent: dict[str, list[str]] = defaultdict(list)
        for claim_id in summary.blocking_claim_ids:
            patent_id, _, claim_number = claim_id.partition("#claim")
            claims_by_patent[patent_id].append(claim_number or "?")
        return [
            (
                f"Governed blocking exposure: {patent_id} claim"
                f"{'s' if len(claim_numbers) != 1 else ''} "
                f"{', '.join(sorted(claim_numbers))} passed the target-scope claim, "
                "status, accused-act, territory, timing, and evidence gates."
            )
            for patent_id, claim_numbers in sorted(claims_by_patent.items())
        ]

    incomplete_by_patent: dict[str, set[str]] = defaultdict(set)
    for decision in decisions:
        if not decision.evidence_sufficient:
            incomplete_by_patent[decision.patent_id].update(decision.missing_components)
    if not incomplete_by_patent:
        return ["The governed target-scope decision remains UNCLEAR; reliance is withheld."]
    return [
        (f"Unresolved target-scope record for {patent_id}: {', '.join(sorted(gaps)[:6])}.")
        for patent_id, gaps in sorted(incomplete_by_patent.items())
    ]


__all__ = ["build_governed_action_items", "build_governed_key_risks"]
