"""Document-building helpers for chat over FTO reports."""

from __future__ import annotations

from api.schemas.chat import ChatPolicy
from api.services.chat_document_sections import (
    build_patent_sections,
    build_report_sections,
    find_patent_analysis,
)

REPORT_CHAT_SYSTEM = (
    "You are an expert FTO (Freedom-to-Operate) analysis assistant. "
    "You have been given a complete FTO analysis report for a specific compound. "
    "Your role is to:\n\n"
    "1. Answer questions ONLY based on the provided report data. "
    "Never hallucinate or invent information.\n"
    "2. Always cite the specific section of the report you are drawing from.\n"
    "   Attach a valid source citation immediately after every substantive assertion; "
    "never group multiple assertions behind one citation or place an uncited conclusion "
    "beside a cited statement.\n"
    "3. When discussing risk levels, reference the specific patent IDs and claim elements.\n"
    "4. If asked about something not covered in the report, clearly state that the "
    "information is not available.\n"
    '5. Use precise patent terminology: "claim elements", "independent claims", '
    '"dependent claims", "prosecution history estoppel", '
    '"doctrine of equivalents".\n'
    "6. Be concise but thorough. Lead with the answer, then provide supporting evidence.\n"
    "7. When comparing patents, organize your response in a structured way.\n\n"
    "You are helping IP professionals, R&D teams, and patent attorneys review and "
    "understand this FTO analysis."
)

PATENT_CHAT_SYSTEM = (
    "You are an expert patent analysis assistant. You have been given detailed data "
    "about a specific patent from an FTO analysis. Your role is to:\n\n"
    "1. Answer questions ONLY based on the provided patent data. "
    "Never invent claim elements or risk assessments.\n"
    "2. Always cite the specific claims, elements, or sections you reference.\n"
    "   Attach a valid source citation immediately after every substantive assertion; "
    "never group multiple assertions behind one citation or place an uncited conclusion "
    "beside a cited statement.\n"
    "3. Explain claim scope, element-by-element analysis, and risk levels clearly.\n"
    "4. If asked about information not in the provided data, clearly state it is "
    "not available.\n"
    "5. Be precise with patent terminology and reference specific claim numbers.\n\n"
    "You are helping the user understand this patent's implications for their compound."
)


def _format_bool(value: object) -> str:
    return "yes" if bool(value) else "no"


def build_policy_context_block(policy: ChatPolicy) -> str:
    """Return a deterministic system-context block for governed chat."""
    capability_lines = [
        f"- {name}" for name in policy.allowed_capabilities or ["report_grounded_qna"]
    ]
    blocked_lines = [f"- {name}" for name in policy.blocked_capabilities]
    evidence_lines = [
        f"- {item.get('field', 'unknown')}: {item.get('value', '')}"
        for item in policy.evidence_basis
    ]
    directive_lines = [f"- {directive}" for directive in policy.system_directives]

    parts = [
        "## Governed Chat Policy",
        "",
        f"Trust mode: {policy.trust_mode}",
        f"Capability profile: {policy.capability_profile}",
        (
            "External retrieval allowed: "
            f"{_format_bool(policy.tool_policy.external_retrieval_allowed)}"
        ),
        (
            "Monitoring actions allowed: "
            f"{_format_bool(policy.tool_policy.monitoring_actions_allowed)}"
        ),
        "",
        "Allowed capabilities:",
        *capability_lines,
    ]
    if blocked_lines:
        parts.extend(["", "Blocked capabilities:", *blocked_lines])
    if evidence_lines:
        parts.extend(["", "Evidence basis:", *evidence_lines])
    if directive_lines:
        parts.extend(["", "System directives:", *directive_lines])
    parts.append("")
    return "\n".join(parts)


def build_chat_system_prompt(base_prompt: str, policy: ChatPolicy) -> str:
    """Fold governed policy context into the assistant system prompt."""
    return f"{base_prompt}\n\n{build_policy_context_block(policy)}"


def build_report_document(report_data: dict) -> dict:
    """Structure the full FTO report as a citable Anthropic document."""
    compound = report_data.get("compound", {})
    sections = build_report_sections(report_data)

    return {
        "type": "document",
        "source": {"type": "content", "content": sections},
        "title": f"FTO Report: {compound.get('name', 'Unknown Compound')}",
        "context": (
            f"Generated {report_data.get('generated_at', '')} "
            f"by Praviar FTO Analysis {report_data.get('praviar_pipeline_version', '')}"
        ),
        "citations": {"enabled": True},
        "cache_control": {"type": "ephemeral", "ttl": "1h"},
    }


def build_patent_document(patent_id: str, report_data: dict) -> dict:
    """Structure a single-patent view as a citable Anthropic document."""
    patent_analysis = find_patent_analysis(report_data, patent_id)
    if not patent_analysis:
        return build_report_document(report_data)
    sections = build_patent_sections(
        patent_id=patent_id,
        report_data=report_data,
        patent_analysis=patent_analysis,
    )

    return {
        "type": "document",
        "source": {"type": "content", "content": sections},
        "title": f"Patent Analysis: {patent_id}",
        "citations": {"enabled": True},
        "cache_control": {"type": "ephemeral", "ttl": "1h"},
    }
