"""Section builders for chat document construction."""

from __future__ import annotations


def build_report_sections(report_data: dict) -> list[dict[str, str]]:
    """Build ordered text sections for the full-report chat document."""
    sections: list[dict[str, str]] = []

    risk_summary = report_data.get("risk_summary", {})
    sections.append(
        {
            "type": "text",
            "text": f"## Executive Summary\n\n"
            f"Overall Risk: {risk_summary.get('overall_risk', 'unknown')}\n"
            f"Blocking Patents: {risk_summary.get('blocking_patents_count', 0)}\n\n"
            f"{risk_summary.get('executive_summary', 'No summary available.')}",
        }
    )

    key_risks = risk_summary.get("key_risks", [])
    if key_risks:
        sections.append(
            {
                "type": "text",
                "text": "## Key Risks\n\n" + "\n".join(f"- {risk}" for risk in key_risks),
            }
        )

    compound = report_data.get("compound", {})
    sections.append(
        {
            "type": "text",
            "text": f"## Compound\n\n"
            f"Name: {compound.get('name', 'unknown')}\n"
            f"SMILES: {compound.get('canonical_smiles', '')}\n"
            f"CID: {compound.get('pubchem_cid', '')}\n"
            f"MW: {compound.get('molecular_weight', '')}",
        }
    )

    sections.extend(_build_patent_analysis_sections(report_data))

    narratives = report_data.get("patent_narratives", {})
    if narratives:
        narrative_text = "## Patent Narratives\n\n"
        for patent_id, narrative in narratives.items():
            narrative_text += f"### {patent_id}\n{narrative}\n\n"
        sections.append({"type": "text", "text": narrative_text})

    doe_assessments = report_data.get("doe_assessments", [])
    if doe_assessments:
        doe_text = "## Doctrine of Equivalents Assessments\n\n"
        for assessment in doe_assessments:
            doe_text += (
                f"### {assessment.get('patent_id', '?')}\n"
                f"Overall Equivalent: {assessment.get('overall_equivalent', False)}\n"
                f"Prosecution History Estoppel: "
                f"{assessment.get('prosecution_estoppel_applies', False)}\n\n"
            )
        sections.append({"type": "text", "text": doe_text})

    invalidity_assessments = report_data.get("invalidity_assessments", [])
    if invalidity_assessments:
        invalidity_text = "## Invalidity Assessments\n\n"
        for assessment in invalidity_assessments:
            invalidity_text += (
                f"### {assessment.get('patent_id', '?')}\n"
                f"Overall Strength: {assessment.get('overall_strength', 'unknown')}\n"
            )
            for prior_art in assessment.get("prior_art", []):
                invalidity_text += (
                    f"  - Prior Art: {prior_art.get('title', '?')} "
                    f"({prior_art.get('anticipation_score', 0):.0%} anticipation)\n"
                )
            invalidity_text += "\n"
        sections.append({"type": "text", "text": invalidity_text})

    failures = report_data.get("analysis_failures", [])
    if failures:
        failure_text = "## Analysis Failures\n\n"
        for failure in failures:
            failure_text += (
                f"- {failure.get('patent_id', '?')}: "
                f"{failure.get('error_type', '?')} "
                f"- {failure.get('error_message', '')[:200]}\n"
            )
        sections.append({"type": "text", "text": failure_text})

    audit = report_data.get("audit_trail", {})
    if audit:
        sections.append(
            {
                "type": "text",
                "text": f"## Pipeline Audit\n\n"
                f"Total Patents Discovered: {audit.get('total_patents_discovered', 0)}\n"
                f"After Hard Filter: {audit.get('patents_after_hard_filter', 0)}\n"
                f"After Ranking: {audit.get('patents_after_ranking', 0)}\n"
                f"After Triage: {audit.get('patents_after_triage', 0)}\n"
                f"Analyzed: {audit.get('patents_analyzed', 0)}",
            }
        )

    return sections


def find_patent_analysis(report_data: dict, patent_id: str) -> dict | None:
    """Return a single patent analysis block from report data."""
    return next(
        (
            analysis
            for analysis in report_data.get("patent_analyses", [])
            if analysis.get("patent_id") == patent_id
        ),
        None,
    )


def build_patent_sections(
    *,
    patent_id: str,
    report_data: dict,
    patent_analysis: dict,
) -> list[dict]:
    """Build ordered text sections for a single-patent chat document."""
    sections = []

    patent_text = f"## Patent Analysis: {patent_id}\n\n"
    patent_text += f"Title: {patent_analysis.get('title', '')}\n"
    patent_text += f"Assignee: {patent_analysis.get('assignee', '')}\n"
    patent_text += f"Risk Level: {patent_analysis.get('risk_level', 'unknown')}\n"
    patent_text += f"Expiry: {patent_analysis.get('expiry_date', 'unknown')}\n\n"
    patent_text += f"Risk Summary: {patent_analysis.get('risk_summary', '')}\n"
    sections.append({"type": "text", "text": patent_text})

    for claim_analysis in patent_analysis.get("claims_analyzed", []):
        claim_text = (
            f"## Claim {claim_analysis.get('claim_number', '?')} "
            f"({claim_analysis.get('claim_type', '')})\n\n"
        )
        claim_text += f"Preamble: {claim_analysis.get('preamble', '')}\n"
        claim_text += (
            f"Status: {claim_analysis.get('overall_status', '')} | "
            f"Confidence: {claim_analysis.get('confidence', 0):.0%}\n"
        )
        if claim_analysis.get("reasoning"):
            claim_text += f"Reasoning: {claim_analysis.get('reasoning', '')}\n\n"
        claim_text += "Elements:\n"
        for element in claim_analysis.get("elements", []):
            claim_text += (
                f"  {element.get('element_number', '?')}. "
                f"[{element.get('status', '?')}] {element.get('element_text', '')}\n"
                f"     Evidence: {element.get('evidence', '')[:300]}\n"
                f"     Reasoning: {element.get('reasoning', '')[:300]}\n\n"
            )
        sections.append({"type": "text", "text": claim_text})

    details = report_data.get("patent_details", {}).get(patent_id, {})
    if details:
        detail_text = "## Patent Details\n\n"
        if details.get("abstract"):
            detail_text += f"Abstract: {details.get('abstract', '')}\n\n"
        if details.get("claims_text"):
            detail_text += f"Full Claims Text:\n{details.get('claims_text', '')}\n\n"
        if details.get("legal_status"):
            detail_text += f"Legal Status: {details.get('legal_status', '')}\n"
        sections.append({"type": "text", "text": detail_text})

    narrative = report_data.get("patent_narratives", {}).get(patent_id, "")
    if narrative:
        sections.append({"type": "text", "text": f"## AI Narrative\n\n{narrative}"})

    doe_assessment = next(
        (
            assessment
            for assessment in report_data.get("doe_assessments", [])
            if assessment.get("patent_id") == patent_id
        ),
        None,
    )
    if doe_assessment:
        doe_text = (
            f"## Doctrine of Equivalents\n\n"
            f"Overall Equivalent: {doe_assessment.get('overall_equivalent', False)}\n"
            f"Prosecution History Estoppel: "
            f"{doe_assessment.get('prosecution_estoppel_applies', False)}\n"
        )
        sections.append({"type": "text", "text": doe_text})

    return sections


def _build_patent_analysis_sections(report_data: dict) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for patent_analysis in report_data.get("patent_analyses", []):
        patent_text = f"## Patent: {patent_analysis.get('patent_id', '')}\n\n"
        patent_text += f"Title: {patent_analysis.get('title', '')}\n"
        patent_text += f"Assignee: {patent_analysis.get('assignee', '')}\n"
        patent_text += f"Risk Level: {patent_analysis.get('risk_level', 'unknown')}\n"
        patent_text += f"Expiry: {patent_analysis.get('expiry_date', 'unknown')}\n\n"
        patent_text += f"Risk Summary: {patent_analysis.get('risk_summary', '')}\n\n"

        for claim_analysis in patent_analysis.get("claims_analyzed", []):
            patent_text += (
                f"### Claim {claim_analysis.get('claim_number', '?')} "
                f"({claim_analysis.get('claim_type', '')})\n"
            )
            patent_text += (
                f"Overall: {claim_analysis.get('overall_status', '')} "
                f"(confidence: {claim_analysis.get('confidence', 0):.0%})\n"
            )
            if claim_analysis.get("reasoning"):
                patent_text += f"Reasoning: {claim_analysis.get('reasoning', '')}\n"
            for element in claim_analysis.get("elements", []):
                patent_text += (
                    f"  - Element {element.get('element_number', '?')}: "
                    f"{element.get('status', '?')} "
                    f"- {element.get('element_text', '')[:200]}\n"
                )
            patent_text += "\n"

        design_arounds = patent_analysis.get("design_around_suggestions", [])
        if design_arounds:
            patent_text += "### Design-Around Strategies\n"
            for strategy in design_arounds:
                patent_text += (
                    f"- {strategy.get('strategy', '')}: {strategy.get('description', '')}\n"
                )

        sections.append({"type": "text", "text": patent_text})
    return sections
