from __future__ import annotations

from api.db import models as db_models


def test_db_models_barrel_exports_and_metadata_tables() -> None:
    expected_names = {
        "APIKey",
        "Analysis",
        "AnalysisCheckpointDecision",
        "AnalysisClaimedUseReceipt",
        "AnalysisCreditLedger",
        "AnalysisReviewerDecision",
        "AnalysisSearchRelevanceFeedback",
        "AnalysisStatus",
        "AttorneyFeedbackRecord",
        "AuditLog",
        "BatchAnalysis",
        "Base",
        "ClaimedUseErasureAuthorizationRecord",
        "Comment",
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
        "MonitorSchedule",
        "Notification",
        "NotificationType",
        "OrgPlan",
        "Organization",
        "OrganizationCompound",
        "PipelineEvent",
        "StripeEvent",
        "User",
        "UserRole",
        "WeeklyDigestDelivery",
    }

    for name in expected_names:
        assert hasattr(db_models, name), name

    assert set(db_models.Base.metadata.tables) == {
        "api_keys",
        "analyses",
        "analysis_review_statuses",
        "analysis_checkpoint_decisions",
        "analysis_claimed_use_receipts",
        "analysis_credit_ledger",
        "analysis_reviewer_decisions",
        "analysis_search_relevance_feedback",
        "attorney_feedback",
        "audit_logs",
        "batch_analyses",
        "claimed_use_erasure_authorizations",
        "clerk_membership_tombstones",
        "clerk_admin_operations",
        "clerk_webhook_receipts",
        "comment_assignment_events",
        "comment_thread_escalations",
        "comments",
        "compounds",
        "config_presets",
        "credit_capacity_requests",
        "epo_atomic_checkpoint_history",
        "epo_atomic_checkpoints",
        "export_jobs",
        "external_report_grants",
        "faithfulness_scores",
        "monitor_alerts",
        "monitor_conclusion_reassessments",
        "monitors",
        "notifications",
        "organizations",
        "organization_compounds",
        "pipeline_events",
        "stripe_events",
        "users",
        "weekly_digest_deliveries",
    }


def test_organization_external_sharing_policy_is_dedicated_and_versioned() -> None:
    columns = db_models.Organization.__table__.columns

    assert columns.external_sharing_policy_mode.default.arg == "approved_domains_only"
    assert columns.external_sharing_approved_domains.default.arg(None) == []
    assert columns.external_sharing_policy_version.default.arg == 1
