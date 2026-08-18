"""SQLAlchemy ORM models for the Praviar platform.

This module keeps the public ``api.db.models`` import surface stable while the
actual ORM classes live in smaller domain modules under ``api.db.db``.

All JSONB columns use ``default=dict`` or ``default=list`` (callables, NOT literals).
SQLAlchemy invokes the callable on each INSERT, so every row gets its own mutable
container — no shared-state bugs.
"""

from __future__ import annotations

from .models_analysis import (  # noqa: E402
    Analysis,
    Compound,
    ConfigPreset,
    FaithfulnessScore,
    OrganizationCompound,
    PipelineEvent,
)
from .models_base import (
    AnalysisStatus,
    Base,
    ExportFormat,
    ExportStatus,
    MonitorSchedule,
    NotificationType,
    OrgPlan,
    ReviewStatus,
    UserRole,
)
from .models_collaboration import (  # noqa: E402
    AnalysisCheckpointDecision,
    AnalysisClaimedUseReceipt,
    AnalysisReviewerDecision,
    AnalysisReviewStatus,
    AnalysisSearchRelevanceFeedback,
    AttorneyFeedbackRecord,
    Comment,
    CommentAssignmentEvent,
    CommentThreadEscalation,
    Notification,
)
from .models_identity import (  # noqa: E402
    APIKey,
    ClerkAdminOperation,
    ClerkMembershipTombstone,
    ClerkWebhookReceipt,
    Organization,
    User,
)
from .models_operations import (  # noqa: E402
    AnalysisCreditLedger,
    AuditLog,
    BatchAnalysis,
    ClaimedUseErasureAuthorizationRecord,
    CreditCapacityRequest,
    ExportJob,
    Monitor,
    MonitorAlert,
    MonitorConclusionReassessment,
    StripeEvent,
    WeeklyDigestDelivery,
)
from .models_provenance import EPOAtomicCheckpoint, EPOAtomicCheckpointHistory  # noqa: E402
from .models_sharing import ExternalReportGrant  # noqa: E402

__all__ = [
    "APIKey",
    "Analysis",
    "AnalysisCheckpointDecision",
    "AnalysisClaimedUseReceipt",
    "AnalysisCreditLedger",
    "AnalysisReviewerDecision",
    "AnalysisReviewStatus",
    "AnalysisSearchRelevanceFeedback",
    "AnalysisStatus",
    "AttorneyFeedbackRecord",
    "AuditLog",
    "BatchAnalysis",
    "ClerkAdminOperation",
    "ClerkMembershipTombstone",
    "ClerkWebhookReceipt",
    "Base",
    "ClaimedUseErasureAuthorizationRecord",
    "Comment",
    "CommentAssignmentEvent",
    "CommentThreadEscalation",
    "Compound",
    "ConfigPreset",
    "CreditCapacityRequest",
    "EPOAtomicCheckpoint",
    "EPOAtomicCheckpointHistory",
    "ExportFormat",
    "ExportJob",
    "ExportStatus",
    "ExternalReportGrant",
    "FaithfulnessScore",
    "Monitor",
    "MonitorAlert",
    "MonitorConclusionReassessment",
    "MonitorSchedule",
    "Notification",
    "NotificationType",
    "OrgPlan",
    "Organization",
    "OrganizationCompound",
    "PipelineEvent",
    "ReviewStatus",
    "StripeEvent",
    "User",
    "UserRole",
    "WeeklyDigestDelivery",
]
