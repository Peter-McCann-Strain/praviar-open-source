"""Shared report schema type aliases."""

from __future__ import annotations

from typing import Literal

RiskLevel = Literal["high", "medium", "low", "clear"]
ClearanceOutcome = Literal["clear", "unclear", "blocked"]
CohortStatus = Literal["certified", "attorney_supervised", "supporting_only"]
DecisionEvidenceCategory = Literal[
    "blocking_patent",
    "clearance_support",
    "source_failure",
    "coverage_gap",
    "verification_gap",
    "future_risk",
    "prosecution_signal",
]
CriticIssueSeverity = Literal["critical", "major", "minor", "info"]
CriticIssueType = Literal[
    "risk_claim_mismatch",
    "internal_inconsistency",
    "cross_patent_inconsistency",
    "missing_limitation",
    "infeasible_design_around",
    "confidence_calibration",
    "assignee_logic_inconsistency",
    "missing_dependent_claim",
    "transitional_phrase_issue",
]
BibliographyReferenceType = Literal["patent", "prior_art", "ptab", "case_law", "regulatory"]
ValidationSeverity = Literal["error", "warning"]
SourceStatus = Literal["ok", "failed", "skipped", "not_configured"]
VerificationSeverity = Literal["pass", "warning", "fail"]
DoEConfidenceBand = Literal["HIGH", "MODERATE", "LOW"]
DisclosureStatus = Literal["yes", "no", "partial"]
PriorArtReferenceType = Literal["patent", "journal_article", "conference_paper", "preprint"]
SourceDatabase = Literal["semantic_scholar", "openalex", "lens", "bigquery", "pubmed", ""]
PTABProceedingType = Literal["IPR", "PGR", "CBM"]
EnablementScope = Literal["yes", "no", "unclear"]
InvalidityStrength = Literal["weak", "moderate", "strong", ""]
EvidenceAuthorityTier = Literal["authoritative", "supporting", "discovery"]
EvidenceAdapterKind = Literal[
    "search",
    "legal_record",
    "regulatory",
    "pipeline",
    "policy",
    "derived",
]
EvidenceCollectionState = Literal["collected", "partial", "missing", "failed", "not_applicable"]
EvidenceDirectivePriority = Literal["critical", "high", "medium", "low"]
RecordComponentStatusValue = Literal["collected", "missing", "failed", "not_applicable"]
EvidenceArtifactType = Literal[
    "search_hit",
    "claims_text",
    "family_context",
    "prosecution_dossier",
    "ep_register_record",
    "ptab_record",
    "orange_book_record",
    "claim_analysis",
    "doe_assessment",
    "invalidity_assessment",
    "critic_review",
    "verification",
    "coverage_gap",
]
