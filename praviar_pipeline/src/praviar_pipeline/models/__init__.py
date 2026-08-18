"""Pydantic data models for the Praviar Pipeline FTO pipeline."""

from praviar_pipeline.models.analysis import (
    AnalysisEvaluation,
    ClaimAnalysis,
    ClaimElement,
    DesignAroundSuggestion,
    ElementStatus,
    EvaluationIssue,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.audit import (
    AnalysisAuditEntry,
    PipelineAuditTrail,
    SearchFunnelEntry,
    StepTiming,
    StepTokenUsage,
    TriageAuditEntry,
)
from praviar_pipeline.models.compound import (
    DerivedStructureCandidate,
    RelatedCompound,
    ResolvedCompound,
    StructureIntegrityCheck,
    TautomerEnumerationRecord,
)
from praviar_pipeline.models.critic import (
    CriticFinding,
    CriticIssueSeverity,
    CriticIssueType,
    CriticReport,
)
from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingEvidenceStore,
    DrawingRiskLevel,
    DrawingStructure,
    OCSRResult,
    PatentDrawingAnalysis,
    SegmentationResult,
)
from praviar_pipeline.models.equivalents import (
    ChemicalEquivalenceContext,
    ClaimAmendment,
    DoEAssessment,
    EstoppelResult,
    FWRAssessment,
    ProsecutionHistory,
    RejectionRecord,
)
from praviar_pipeline.models.invalidity import (
    ClaimChart,
    ClaimChartEntry,
    EnablementScreening,
    GrahamFactors,
    InvalidityArgument,
    InvalidityAssessment,
    InvalidityLLMResponse,
    PriorArtReference,
    PTABProceeding,
    PTABResult,
)
from praviar_pipeline.models.patent import (
    LegalEvent,
    LegalStatus,
    PatentFamily,
    PatentFamilyMember,
    PatentHit,
    PatentSource,
    PatentTermInfo,
)
from praviar_pipeline.models.reasoning import AgentRound, ReasoningTrace, ToolCall
from praviar_pipeline.models.report import (
    REPORT_DISCLAIMER,
    ActionItem,
    ActionPriority,
    ActionType,
    AnalysisFailure,
    AttorneyFeedback,
    ClaimAssertionSupport,
    ClaimCorrection,
    ClaimSourceSpanMap,
    DataLimitation,
    FTOReport,
    RiskSummary,
    SourceHealth,
    SourceHealthEntry,
    SourceSpanReference,
    SourceStatus,
)
from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.models.triage import Relevance, TriageBatch, TriageResult
from praviar_pipeline.models.verification import VerificationCheck, VerificationResult

__all__ = [
    "REPORT_DISCLAIMER",
    "ActionItem",
    "ActionPriority",
    "ActionType",
    "AgentRound",
    "AnalysisAuditEntry",
    "AnalysisEvaluation",
    "AnalysisFailure",
    "AttorneyFeedback",
    "ChemicalEquivalenceContext",
    "ClaimAmendment",
    "ClaimAnalysis",
    "ClaimAssertionSupport",
    "ClaimChart",
    "ClaimChartEntry",
    "ClaimCorrection",
    # analysis
    "ClaimElement",
    "ClaimSourceSpanMap",
    # critic
    "CriticFinding",
    "CriticIssueSeverity",
    "CriticIssueType",
    "CriticReport",
    "DataLimitation",
    "DerivedStructureCandidate",
    "DesignAroundSuggestion",
    # equivalents
    "DoEAssessment",
    # drawing
    "DrawingAnalysisResults",
    "DrawingEvidenceStore",
    "DrawingRiskLevel",
    "DrawingStructure",
    "ElementStatus",
    "EnablementScreening",
    "EstoppelResult",
    "EvaluationIssue",
    "ExpandedSearchQueries",
    # report
    "FTOReport",
    "FWRAssessment",
    "GrahamFactors",
    "InvalidityArgument",
    # invalidity
    "InvalidityAssessment",
    "InvalidityLLMResponse",
    "LegalEvent",
    "LegalStatus",
    "OCSRResult",
    "PTABProceeding",
    "PTABResult",
    "PatentAnalysis",
    "PatentDrawingAnalysis",
    "PatentFamily",
    "PatentFamilyMember",
    # patent
    "PatentHit",
    "PatentSource",
    "PatentTermInfo",
    "PipelineAuditTrail",
    "PriorArtReference",
    "ProsecutionHistory",
    "ReasoningTrace",
    "RejectionRecord",
    # compound
    "RelatedCompound",
    "Relevance",
    "ResolvedCompound",
    "RiskLevel",
    "RiskSummary",
    # audit
    "SearchFunnelEntry",
    "SegmentationResult",
    "SourceHealth",
    "SourceHealthEntry",
    "SourceSpanReference",
    "SourceStatus",
    "StepTiming",
    "StepTokenUsage",
    "StructureIntegrityCheck",
    "TautomerEnumerationRecord",
    "ToolCall",
    "TriageAuditEntry",
    "TriageBatch",
    # triage
    "TriageResult",
    "VerificationCheck",
    # verification
    "VerificationResult",
]
