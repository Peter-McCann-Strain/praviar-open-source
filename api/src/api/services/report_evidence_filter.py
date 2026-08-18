"""Pure helpers and business-rule predicates for governed evidence search."""

from __future__ import annotations

import re
from typing import Any

PUBLIC_OPEN_SOURCE_PREFIXES = (
    "patentsview",
    "uspto",
    "ptab",
    "epo",
    "epo_ops",
    "wipo",
    "patentscope",
    "pubchem",
    "surechembl",
    "orange_book",
    "purple_book",
    "pubmed",
    "crossref",
    "google_patents",
)

LICENSED_SOURCE_PREFIXES = (
    "clarivate",
    "derwent",
    "questel",
    "patsnap",
    "acclaimip",
    "anaqua",
    "lexisnexis",
    "patentsight",
    "deepip",
    "iprally",
)

EXTERNAL_RETRIEVAL_TRUST_MODES = frozenset({"counsel", "monitor"})
PATENT_IDENTIFIER_RE = re.compile(r"\b(?:US\s*)?\d{6,10}(?:\s*[A-Z]\d?)?\b", re.IGNORECASE)
PROVIDER_STATUS_PRIORITY = {"declared_only": 0, "caution_only": 1, "active": 2}
PROVIDER_EXECUTION_PRIORITY = {
    "placeholder_contract": 0,
    "report_materialized": 1,
    "bundled_dataset": 2,
    "live_api": 3,
}

DOMAIN_GENERIC_QUERY_TOKENS = frozenset(
    {
        "evidence",
        "patent",
        "patents",
        "record",
        "records",
        "report",
        "search",
    }
)
BLOCKING_INTENT_TOKENS = frozenset({"block", "blocked", "blocker", "blockers", "blocking"})


def text(value: object) -> str:
    return str(value or "").strip()


def normalized_trust_mode(report: dict[str, Any]) -> str:
    trust_mode = text(report.get("trust_mode") or "explorer").lower()
    if trust_mode in {"explorer", "counsel", "monitor"}:
        return trust_mode
    return "explorer"


def external_retrieval_allowed(report: dict[str, Any]) -> bool:
    return normalized_trust_mode(report) in EXTERNAL_RETRIEVAL_TRUST_MODES


def looks_like_patent_identifier(query: str) -> bool:
    return bool(PATENT_IDENTIFIER_RE.search(query))


def query_patent_identifier(query: str) -> str | None:
    match = PATENT_IDENTIFIER_RE.search(query)
    if not match:
        return None
    return text(match.group(0))


def excerpt(content_text: str, query: str, *, limit: int = 220) -> str:
    content = content_text.strip()
    if not content:
        return ""

    lowered = content.lower()
    query_lower = query.lower()
    index = lowered.find(query_lower)
    if index == -1 or len(content) <= limit:
        return content[:limit]

    start = max(0, index - 70)
    end = min(len(content), index + len(query) + 110)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content) else ""
    return f"{prefix}{content[start:end]}{suffix}"


def query_has_blocking_intent(query: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    return bool(tokens & BLOCKING_INTENT_TOKENS)


def collect_blocking_patent_ids(report: dict[str, Any]) -> set[str]:
    """Return only patent IDs explicitly recorded as blocking by the report."""

    blocking_ids: set[str] = set()
    clearance_decision = report.get("clearance_decision") or {}
    decision_audit = clearance_decision.get("decision_audit") or {}
    claim_program_summary = decision_audit.get("claim_program_summary") or {}
    commercial_exposure = report.get("commercial_exposure") or {}

    candidate_lists = [
        claim_program_summary.get("blocking_patent_ids") or [],
        commercial_exposure.get("blocking_patent_ids") or [],
    ]
    for jurisdiction_decision in report.get("jurisdiction_decisions", []) or []:
        if isinstance(jurisdiction_decision, dict):
            candidate_lists.append(jurisdiction_decision.get("blocking_patent_ids") or [])

    for candidates in candidate_lists:
        for patent_id in candidates:
            normalized = text(patent_id)
            if normalized:
                blocking_ids.add(normalized)
    return blocking_ids


def matches(
    query: str,
    *parts: object,
    require_all_discriminative_tokens: bool = False,
) -> tuple[bool, float, str]:
    haystack_parts = [text(part) for part in parts if text(part)]
    if not haystack_parts:
        return False, 0.0, ""

    query_lower = query.lower().strip()
    raw_tokens = re.findall(r"[a-z0-9]+", query_lower)
    tokens = ["blocking" if token in BLOCKING_INTENT_TOKENS else token for token in raw_tokens]
    joined = " ".join(haystack_parts)
    joined_lower = joined.lower()

    substring = query_lower in joined_lower
    token_hits = sum(token in joined_lower for token in tokens)
    discriminative_tokens = [token for token in tokens if token not in DOMAIN_GENERIC_QUERY_TOKENS]
    if (
        require_all_discriminative_tokens
        and discriminative_tokens
        and any(token not in joined_lower for token in discriminative_tokens)
    ):
        return False, 0.0, joined
    if not substring and token_hits == 0:
        return False, 0.0, ""

    relevance = 0.55
    if substring:
        relevance += 0.2
    if tokens:
        relevance += min(token_hits / len(tokens), 1.0) * 0.25
    return True, min(relevance, 0.99), joined


def classify_provider(source_name: str) -> str | None:
    normalized = text(source_name).lower().replace(" ", "_")
    if not normalized:
        return None
    if any(normalized.startswith(prefix) for prefix in PUBLIC_OPEN_SOURCE_PREFIXES):
        return "public_open"
    if any(normalized.startswith(prefix) for prefix in LICENSED_SOURCE_PREFIXES):
        return "licensed_overlay"
    return None


def provider_id_from_source(source_name: str) -> str:
    normalized = text(source_name).lower().replace(" ", "_")
    return normalized or "provider"


def collect_sources(report: dict[str, Any]) -> list[str]:
    sources: set[str] = set()
    for source in report.get("search_sources_used", []) or []:
        if text(source):
            sources.add(text(source))
    matter_evidence_index = report.get("matter_evidence_index") or {}
    for key in ("source_names", "authoritative_source_names", "supporting_source_names"):
        for source in matter_evidence_index.get(key, []) or []:
            if text(source):
                sources.add(text(source))
    for artifact in report.get("evidence_artifacts", []) or []:
        if isinstance(artifact, dict):
            for part in text(artifact.get("source_name")).split(","):
                if text(part):
                    sources.add(text(part))
    for adapter in report.get("evidence_adapter_results", []) or []:
        if isinstance(adapter, dict) and text(adapter.get("adapter_name")):
            sources.add(text(adapter.get("adapter_name")))
    for log_entry in report.get("search_strategy_log", []) or []:
        if not isinstance(log_entry, dict):
            continue
        for source in log_entry.get("sources", []) or []:
            if text(source):
                sources.add(text(source))
    return sorted(sources)


def collect_jurisdictions(report: dict[str, Any]) -> list[str]:
    jurisdictions: set[str] = set()
    decision_scope = report.get("decision_scope", {}) or {}
    certification_scope = report.get("certification_scope", {}) or {}
    for source_list in (
        decision_scope.get("jurisdictions", []) or [],
        report.get("target_jurisdictions", []) or [],
        certification_scope.get("certified_jurisdictions", []) or [],
    ):
        for jurisdiction in source_list:
            value = text(jurisdiction)
            if value:
                jurisdictions.add(value)
    for log_entry in report.get("search_strategy_log", []) or []:
        if not isinstance(log_entry, dict):
            continue
        for jurisdiction in log_entry.get("jurisdictions", []) or []:
            value = text(jurisdiction)
            if value:
                jurisdictions.add(value)
    return sorted(jurisdictions)


def collect_modalities(report: dict[str, Any]) -> list[str]:
    routing_profile = report.get("routing_profile", {}) or {}
    decision_scope = report.get("decision_scope", {}) or {}
    values = [
        text(routing_profile.get("modality")),
        text(routing_profile.get("matter_type")),
        text(decision_scope.get("matter_type")),
        text(report.get("asset_type_hint")),
    ]
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def report_compound_context(report: dict[str, Any]) -> tuple[str, str, int | None]:
    compound = report.get("compound")
    if not isinstance(compound, dict):
        return "", "", None
    cid_raw = compound.get("pubchem_cid")
    cid: int | None = None
    if isinstance(cid_raw, int):
        cid = cid_raw
    elif isinstance(cid_raw, str) and cid_raw.isdigit():
        cid = int(cid_raw)
    return (
        text(compound.get("name")),
        text(compound.get("canonical_smiles") or compound.get("smiles")),
        cid,
    )


def external_query_jurisdictions(report: dict[str, Any]) -> list[str]:
    jurisdictions = collect_jurisdictions(report)
    mapped: list[str] = []
    for jurisdiction in jurisdictions:
        normalized = text(jurisdiction).upper()
        if normalized == "UK":
            mapped.append("GB")
        elif normalized:
            mapped.append(normalized)
    return mapped
