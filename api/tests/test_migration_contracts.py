from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from sqlalchemy import CheckConstraint

from api.db.models import (
    Analysis,
    AnalysisClaimedUseReceipt,
    AnalysisSearchRelevanceFeedback,
    BatchAnalysis,
    EPOAtomicCheckpoint,
    EPOAtomicCheckpointHistory,
    Monitor,
    MonitorConclusionReassessment,
    Organization,
    OrganizationCompound,
    WeeklyDigestDelivery,
)

API_ROOT = Path(__file__).resolve().parents[1]


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(API_ROOT / "src")
    env["APP_ENV"] = "test"
    env["PYTEST_CURRENT_TEST"] = "migration-contract"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_alembic_has_exactly_one_head() -> None:
    result = _run_alembic("heads")

    assert result.returncode == 0, result.stderr
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert heads == ["t6u7v8w9x0y1 (head)"]


def test_epo_checkpoint_migration_is_atomic_monotonic_and_append_only() -> None:
    upgrade = _run_alembic("upgrade", "s5t6u7v8w9x0:t6u7v8w9x0y1", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "CREATE TABLE epo_atomic_checkpoints" in upgrade.stdout
    assert "CREATE TABLE epo_atomic_checkpoint_history" in upgrade.stdout
    assert "trg_epo_atomic_checkpoint_monotonicity" in upgrade.stdout
    assert "trg_epo_atomic_checkpoint_pair" in upgrade.stdout
    assert "DEFERRABLE INITIALLY DEFERRED" in upgrade.stdout
    assert "EPO checkpoint pair is torn or causally mixed" in upgrade.stdout
    assert "EPO checkpoint history is append-only" in upgrade.stdout
    assert "REVOKE ALL ON public.epo_atomic_checkpoints FROM PUBLIC" in upgrade.stdout
    assert "GRANT SELECT, INSERT, UPDATE ON public.epo_atomic_checkpoints" in upgrade.stdout
    assert "TO praviar_epo_checkpoint_writer" in upgrade.stdout

    downgrade = _run_alembic(
        "downgrade",
        "t6u7v8w9x0y1:s5t6u7v8w9x0",
        "--sql",
    )
    assert downgrade.returncode == 0, downgrade.stderr
    assert "Refusing to downgrade: EPO checkpoint provenance records exist" in downgrade.stdout
    assert "DROP TABLE epo_atomic_checkpoint_history" in downgrade.stdout
    assert "DROP TABLE epo_atomic_checkpoints" in downgrade.stdout

    for model in (EPOAtomicCheckpoint, EPOAtomicCheckpointHistory):
        constraints = {
            constraint.name
            for constraint in model.__table__.constraints
            if isinstance(constraint, CheckConstraint)
        }
        prefix = model.__tablename__
        assert {
            f"ck_{prefix}_source_stream",
            f"ck_{prefix}_schema_epoch",
            f"ck_{prefix}_manifest_type",
            f"ck_{prefix}_subject",
            f"ck_{prefix}_positive_counters",
            f"ck_{prefix}_lineage",
        } <= constraints


def test_claimed_use_erasure_capability_migration_is_single_use() -> None:
    upgrade = _run_alembic("upgrade", "r4s5t6u7v8w9:s5t6u7v8w9x0", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "CREATE TABLE claimed_use_erasure_capabilities" in upgrade.stdout
    assert "FORCE ROW LEVEL SECURITY" in upgrade.stdout
    assert "public.authorize_claimed_use_erasure" in upgrade.stdout
    assert "session_user <> 'praviar_api'" in upgrade.stdout
    assert "session_user <> 'praviar_worker'" in upgrade.stdout
    assert "sha256(convert_to(p_capability_secret" in upgrade.stdout
    assert "actor_user_id IS NOT DISTINCT FROM p_actor_user_id" in upgrade.stdout
    assert "invalid, expired, or already consumed" in upgrade.stdout
    assert "DROP FUNCTION public.erase_claimed_use_receipts" in upgrade.stdout

    downgrade = _run_alembic(
        "downgrade",
        "s5t6u7v8w9x0:r4s5t6u7v8w9",
        "--sql",
    )
    assert downgrade.returncode == 0, downgrade.stderr
    assert "Refusing to downgrade while claimed-use erasure capabilities remain" in (
        downgrade.stdout
    )
    assert "DROP TABLE claimed_use_erasure_capabilities" in downgrade.stdout
    assert "CREATE FUNCTION public.erase_claimed_use_receipts" in downgrade.stdout


def test_claimed_use_receipt_migration_is_immutable_and_rls_scoped() -> None:
    upgrade = _run_alembic("upgrade", "q3r4s5t6u7v8:r4s5t6u7v8w9", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "CREATE TABLE analysis_claimed_use_receipts" in upgrade.stdout
    assert "ck_analysis_claimed_use_receipts_digests" in upgrade.stdout
    assert "ck_analysis_claimed_use_receipts_revocation" in upgrade.stdout
    assert "uq_analysis_claimed_use_receipts_active_subject" in upgrade.stdout
    assert "validate_claimed_use_receipt_scope" in upgrade.stdout
    assert "trg_claimed_use_receipt_scope_guard" in upgrade.stdout
    assert "claimed-use receipt subject and issuer are immutable" in upgrade.stdout
    assert "ON DELETE CASCADE" not in upgrade.stdout
    assert "BEFORE INSERT OR UPDATE OR DELETE" in upgrade.stdout
    assert "CREATE TABLE claimed_use_erasure_authorizations" in upgrade.stdout
    assert "claimed-use erasure authorizations are append-only" in upgrade.stdout
    assert "authorization.created_at = transaction_timestamp()" in upgrade.stdout
    assert "jsonb_object_length(NEW.receipt_payload) <> 27" in upgrade.stdout
    assert "SECURITY DEFINER" in upgrade.stdout
    assert "public.issue_claimed_use_receipt" in upgrade.stdout
    assert "public.revoke_claimed_use_receipt" in upgrade.stdout
    assert "public.erase_claimed_use_receipts" in upgrade.stdout
    assert "REVOKE INSERT, UPDATE, DELETE" in upgrade.stdout
    assert "FROM PUBLIC" in upgrade.stdout
    assert (
        "claimed-use receipt deletion requires explicit tenant erasure authorization"
        in upgrade.stdout
    )
    assert "claimed-use receipt updates are limited to revocation" in upgrade.stdout
    assert "claimed-use receipts cannot be inserted as revoked" in upgrade.stdout
    assert "jsonb_typeof(NEW.receipt_payload) IS DISTINCT FROM 'object'" in upgrade.stdout
    assert "NEW.receipt_payload ?& ARRAY[" in upgrade.stdout
    assert "claimed-use signed receipt must be an object with every signed field" in (
        upgrade.stdout
    )
    assert "IS DISTINCT FROM 'claimed-use-match-v3'" in upgrade.stdout
    assert "IS DISTINCT FROM 'true'::jsonb" in upgrade.stdout
    assert "IS DISTINCT FROM NEW.issued_at" in upgrade.stdout
    assert "revoker.id = NEW.issuer_user_id" in upgrade.stdout
    assert "ALTER TABLE analysis_claimed_use_receipts FORCE ROW LEVEL SECURITY" in (upgrade.stdout)
    assert "CREATE POLICY org_isolation ON analysis_claimed_use_receipts" in (upgrade.stdout)
    assert (
        "ALTER TABLE claimed_use_erasure_authorizations FORCE ROW LEVEL SECURITY" in upgrade.stdout
    )
    assert "CREATE POLICY org_isolation ON claimed_use_erasure_authorizations" in upgrade.stdout

    downgrade = _run_alembic(
        "downgrade",
        "r4s5t6u7v8w9:q3r4s5t6u7v8",
        "--sql",
    )
    assert downgrade.returncode == 0, downgrade.stderr
    assert "Refusing to downgrade while claimed-use legal-ledger records remain" in downgrade.stdout
    assert "DROP TABLE analysis_claimed_use_receipts" in downgrade.stdout

    constraints = {
        constraint.name
        for constraint in AnalysisClaimedUseReceipt.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_analysis_claimed_use_receipts_positive_coordinates",
        "ck_analysis_claimed_use_receipts_digests",
        "ck_analysis_claimed_use_receipts_revocation",
    } <= constraints
    columns = set(AnalysisClaimedUseReceipt.__table__.columns.keys())
    assert {
        "issuer_clerk_user_id",
        "issuer_name",
        "issuer_email",
    }.isdisjoint(columns)
    assert (
        next(iter(AnalysisClaimedUseReceipt.__table__.c.analysis_id.foreign_keys)).ondelete is None
    )
    assert next(iter(AnalysisClaimedUseReceipt.__table__.c.org_id.foreign_keys)).ondelete is None


def test_search_relevance_feedback_migration_is_plan_bound_and_rls_scoped() -> None:
    upgrade = _run_alembic("upgrade", "o1q2r3s4t5u6:p2q3r4s5t6u7", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "CREATE TABLE analysis_search_relevance_feedback" in upgrade.stdout
    assert "ck_analysis_search_relevance_feedback_label" in upgrade.stdout
    assert "ck_analysis_search_relevance_feedback_fingerprints" in upgrade.stdout
    assert "validate_search_relevance_feedback_scope" in upgrade.stdout
    assert "trg_search_relevance_feedback_scope_guard" in upgrade.stdout
    assert "audit_trail,query_plan,plan_sha256" in upgrade.stdout
    assert "audit_trail,search_funnel" in upgrade.stdout
    assert "ALTER TABLE analysis_search_relevance_feedback FORCE ROW LEVEL SECURITY" in (
        upgrade.stdout
    )
    assert "CREATE POLICY org_isolation ON analysis_search_relevance_feedback" in (upgrade.stdout)

    downgrade = _run_alembic("downgrade", "p2q3r4s5t6u7:o1q2r3s4t5u6", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    assert "Refusing to downgrade while search relevance feedback remains" in downgrade.stdout
    assert "DROP TABLE analysis_search_relevance_feedback" in downgrade.stdout

    constraints = {
        constraint.name
        for constraint in AnalysisSearchRelevanceFeedback.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_analysis_search_relevance_feedback_label",
        "ck_analysis_search_relevance_feedback_fingerprints",
        "ck_analysis_search_relevance_feedback_json_arrays",
    } <= constraints


def test_monitor_reassessment_lifecycle_migration_is_durable_and_rls_scoped() -> None:
    upgrade = _run_alembic("upgrade", "n0p1q2r3s4t5:o1q2r3s4t5u6", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "CREATE TABLE monitor_conclusion_reassessments" in upgrade.stdout
    assert "ON DELETE SET NULL" in upgrade.stdout
    assert "INSERT INTO monitor_conclusion_reassessments" in upgrade.stdout
    assert "Cannot migrate malformed monitor stale_conclusions" in upgrade.stdout
    assert "Cannot migrate stale conclusions without a source analysis" in upgrade.stdout
    assert "Cannot migrate malformed monitor conclusion identity provenance" in upgrade.stdout
    assert "ALTER TABLE monitor_conclusion_reassessments FORCE ROW LEVEL SECURITY" in upgrade.stdout
    assert "CREATE POLICY org_isolation ON monitor_conclusion_reassessments" in upgrade.stdout
    assert "uq_monitor_conclusion_reassessments_open_episode" in upgrade.stdout
    assert "ck_monitor_conclusion_reassessments_identity" in upgrade.stdout
    assert "ck_monitor_conclusion_reassessments_chronology" in upgrade.stdout
    assert "validate_monitor_conclusion_reassessment_org" in upgrade.stdout
    assert "trg_monitor_conclusion_reassessment_org_guard" in upgrade.stdout
    assert "ADD COLUMN superseded_at" in upgrade.stdout
    assert "ADD COLUMN superseded_conclusion_ids JSONB" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "o1q2r3s4t5u6:n0p1q2r3s4t5", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    no_force = downgrade.stdout.index(
        "ALTER TABLE monitor_conclusion_reassessments NO FORCE ROW LEVEL SECURITY"
    )
    guard = downgrade.stdout.index(
        "Refusing to downgrade while monitor conclusion reassessments remain"
    )
    drop_table = downgrade.stdout.index("DROP TABLE monitor_conclusion_reassessments")
    assert no_force < guard < drop_table
    assert "DROP TABLE monitor_conclusion_reassessments" in downgrade.stdout
    assert "SET conclusion_status = 'fresh'" in downgrade.stdout

    constraints = {
        constraint.name
        for constraint in MonitorConclusionReassessment.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    indexes = {index.name: index for index in MonitorConclusionReassessment.__table__.indexes}
    assert {
        "ck_monitor_conclusion_reassessments_status",
        "ck_monitor_conclusion_reassessments_resolution",
        "ck_monitor_conclusion_reassessments_identity",
        "ck_monitor_conclusion_reassessments_chronology",
    } <= constraints
    assert indexes["uq_monitor_conclusion_reassessments_open_episode"].unique is True
    assert (
        str(
            indexes["uq_monitor_conclusion_reassessments_open_episode"].dialect_options[
                "postgresql"
            ]["where"]
        )
        == "status = 'open' AND monitor_id IS NOT NULL"
    )


def test_alembic_upgrade_head_sql_renders() -> None:
    result = _run_alembic("upgrade", "head", "--sql")

    assert result.returncode == 0, result.stderr
    assert "analysis_checkpoint_decisions" in result.stdout
    assert "ALTER TABLE comments ADD COLUMN org_id" in result.stdout
    assert "sso_enabled" in result.stdout
    assert "deletion_scheduled_at" in result.stdout
    assert "external_sharing_policy_mode" in result.stdout
    assert "external_sharing_approved_domains" in result.stdout
    assert "external_sharing_policy_version" in result.stdout
    assert "CREATE TABLE clerk_admin_operations" in result.stdout
    assert "ck_clerk_admin_operations_state" in result.stdout
    assert "ck_clerk_admin_operations_target_shape" in result.stdout
    assert "ck_clerk_admin_operations_requested_role" in result.stdout
    assert "membership_permission_denied_at" in result.stdout
    assert "membership_permission_denied_by_operation_id" in result.stdout
    assert "membership_permission_convergence_operation_id" in result.stdout
    assert "fk_users_membership_permission_denied_operation" in result.stdout
    assert "fk_users_membership_permission_convergence_operation" in result.stdout
    assert "ck_users_membership_permission_denial_owner" in result.stdout
    assert "ck_users_membership_permission_denial_convergence" in result.stdout
    assert "ck_users_membership_permission_denial_reference_exclusive" in result.stdout
    assert "uq_clerk_admin_operations_open_role_target" in result.stdout
    assert "uq_clerk_admin_operations_open_invite_email" in result.stdout
    assert "sso_status_available" in result.stdout
    assert "sso_required" in result.stdout
    assert "sso_last_synced_at" in result.stdout
    assert "sso_last_refresh_started_at" in result.stdout
    assert "sso_refresh_attempt_id" in result.stdout
    assert "CREATE TABLE credit_capacity_requests" in result.stdout
    assert "ck_credit_capacity_requests_resolution" in result.stdout
    assert "trg_credit_capacity_request_org_guard" in result.stdout
    assert "email_digest_frequency" in result.stdout
    assert "CREATE TABLE organization_compounds" in result.stdout
    assert "CREATE POLICY org_isolation ON organization_compounds" in result.stdout
    assert "CREATE TABLE weekly_digest_deliveries" in result.stdout
    assert "CREATE POLICY weekly_digest_unsubscribe_lookup" in result.stdout
    assert "submitted_identity_confirmed" in result.stdout
    assert "launch_idempotency_key_digest" in result.stdout
    assert "uq_analyses_org_launch_idempotency" in result.stdout
    assert "ck_users_deleted_membership_inactive" in result.stdout
    assert "membership_deleted_at IS NOT NULL" in result.stdout
    assert "ALTER TABLE batch_analyses ADD COLUMN launch_idempotency_key_digest" in result.stdout
    assert "uq_batch_analyses_org_launch_idempotency" in result.stdout
    assert "uq_monitors_org_source_analysis_id" in result.stdout
    assert "offboarding_billing_cancellation_status" in result.stdout
    assert "offboarding_stripe_subscription_id" in result.stdout
    assert "ck_org_offboarding_billing_retry_locator" in result.stdout
    assert "stale_conclusions" in result.stdout
    assert "affected_conclusions" in result.stdout
    assert "ck_monitors_conclusion_status" in result.stdout
    assert "CREATE TABLE analysis_search_relevance_feedback" in result.stdout


def test_monitor_conclusion_invalidation_migration_and_orm_contract() -> None:
    upgrade = _run_alembic("upgrade", "c3d4e5f6a7b8:n0p1q2r3s4t5", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "ADD COLUMN conclusion_status VARCHAR(32)" in upgrade.stdout
    assert "ADD COLUMN stale_conclusions JSONB" in upgrade.stdout
    assert "SET conclusion_status = 'fresh'" in upgrade.stdout
    assert "ck_monitors_conclusion_status" in upgrade.stdout
    assert "ADD COLUMN affected_conclusions JSONB" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "n0p1q2r3s4t5:c3d4e5f6a7b8", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    assert "DROP COLUMN affected_conclusions" in downgrade.stdout
    assert "DROP CONSTRAINT ck_monitors_conclusion_status" in downgrade.stdout
    assert "DROP COLUMN stale_conclusions" in downgrade.stdout
    assert "DROP COLUMN conclusion_status" in downgrade.stdout

    constraints = {
        constraint.name
        for constraint in Monitor.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_monitors_conclusion_status" in constraints


def test_offboarding_billing_cancellation_migration_and_orm_contract() -> None:
    upgrade = _run_alembic("upgrade", "b2c3d4e5f6a7:c3d4e5f6a7b8", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "ADD COLUMN offboarding_billing_cancellation_status VARCHAR(32)" in upgrade.stdout
    assert "ADD COLUMN offboarding_stripe_subscription_id VARCHAR(255)" in upgrade.stdout
    assert "ADD COLUMN offboarding_billing_cancellation_attempts INTEGER" in upgrade.stdout
    assert "ck_org_offboarding_billing_status" in upgrade.stdout
    assert "ck_org_offboarding_billing_confirmation_shape" in upgrade.stdout
    assert "ck_org_offboarding_billing_retry_locator" in upgrade.stdout
    assert "ck_org_offboarding_billing_not_required_locator" in upgrade.stdout
    assert "ck_org_offboarding_billing_attempt_shape" in upgrade.stdout
    assert "ck_org_offboarding_billing_error_shape" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "c3d4e5f6a7b8:b2c3d4e5f6a7", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    assert "DROP CONSTRAINT ck_org_offboarding_billing_error_shape" in downgrade.stdout
    assert "DROP COLUMN offboarding_stripe_subscription_id" in downgrade.stdout
    assert "DROP COLUMN offboarding_billing_cancellation_status" in downgrade.stdout

    constraints = {
        constraint.name
        for constraint in Organization.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_org_offboarding_billing_status",
        "ck_org_offboarding_billing_attempts_nonnegative",
        "ck_org_offboarding_billing_confirmation_shape",
        "ck_org_offboarding_billing_retry_locator",
        "ck_org_offboarding_billing_not_required_locator",
        "ck_org_offboarding_billing_attempt_shape",
        "ck_org_offboarding_billing_error_shape",
    } <= constraints


def test_monitor_source_analysis_uniqueness_migration_and_orm_contract() -> None:
    upgrade = _run_alembic("upgrade", "a2b3c4d5e6f7:b2c3d4e5f6a7", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "UPDATE monitor_alerts AS alerts" in upgrade.stdout
    assert "SET monitor_id = ranked.canonical_id" in upgrade.stdout
    assert "DELETE FROM monitors AS duplicate" in upgrade.stdout
    assert "CREATE UNIQUE INDEX uq_monitors_org_source_analysis_id" in upgrade.stdout
    assert "WHERE source_analysis_id IS NOT NULL" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "b2c3d4e5f6a7:a2b3c4d5e6f7", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    assert "DROP INDEX uq_monitors_org_source_analysis_id" in downgrade.stdout

    indexes = {index.name: index for index in Monitor.__table__.indexes}
    assert indexes["uq_monitors_org_source_analysis_id"].unique is True
    assert (
        str(indexes["uq_monitors_org_source_analysis_id"].dialect_options["postgresql"]["where"])
        == "source_analysis_id IS NOT NULL"
    )


def test_batch_launch_idempotency_migration_and_orm_contract() -> None:
    upgrade = _run_alembic("upgrade", "f1a2b3c4d5e6:a2b3c4d5e6f7", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "ADD COLUMN launch_idempotency_key_digest VARCHAR(64)" in upgrade.stdout
    assert "ADD COLUMN launch_payload_digest VARCHAR(64)" in upgrade.stdout
    assert "ck_batch_analyses_launch_idempotency_pair" in upgrade.stdout
    assert "CREATE UNIQUE INDEX uq_batch_analyses_org_launch_idempotency" in upgrade.stdout
    assert "WHERE launch_idempotency_key_digest IS NOT NULL" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "a2b3c4d5e6f7:f1a2b3c4d5e6", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    assert "DROP INDEX uq_batch_analyses_org_launch_idempotency" in downgrade.stdout
    assert "DROP CONSTRAINT ck_batch_analyses_launch_idempotency_pair" in downgrade.stdout

    constraints = {
        constraint.name
        for constraint in BatchAnalysis.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    indexes = {index.name: index for index in BatchAnalysis.__table__.indexes}
    assert "ck_batch_analyses_launch_idempotency_pair" in constraints
    assert indexes["uq_batch_analyses_org_launch_idempotency"].unique is True


def test_sso_freshness_migration_upgrade_and_downgrade_render() -> None:
    upgrade = _run_alembic("upgrade", "d3e4f5a6b7c8:e4f5a6b7c8d9", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "ADD COLUMN sso_status_available BOOLEAN DEFAULT false NOT NULL" in upgrade.stdout
    assert "ADD COLUMN sso_required BOOLEAN DEFAULT false NOT NULL" in upgrade.stdout
    assert "WHERE settings ->> 'sso_required' = 'true'" in upgrade.stdout
    assert "SET settings = settings - 'sso_required'" in upgrade.stdout
    assert "ADD COLUMN sso_last_synced_at TIMESTAMP WITH TIME ZONE" in upgrade.stdout
    assert "ADD COLUMN sso_last_refresh_started_at TIMESTAMP WITH TIME ZONE" in upgrade.stdout
    assert "ADD COLUMN sso_refresh_attempt_id UUID" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "e4f5a6b7c8d9:d3e4f5a6b7c8", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    assert "jsonb_set" in downgrade.stdout
    assert "DROP COLUMN sso_required" in downgrade.stdout
    assert "DROP COLUMN sso_refresh_attempt_id" in downgrade.stdout
    assert "DROP COLUMN sso_last_refresh_started_at" in downgrade.stdout
    assert "DROP COLUMN sso_last_synced_at" in downgrade.stdout
    assert "DROP COLUMN sso_status_available" in downgrade.stdout


def test_credit_capacity_request_migration_upgrade_and_downgrade_render() -> None:
    upgrade = _run_alembic("upgrade", "e4f5a6b7c8d9:f5a6b7c8d9e0", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "CREATE TABLE credit_capacity_requests" in upgrade.stdout
    assert "ck_credit_capacity_requests_reports" in upgrade.stdout
    assert "ck_credit_capacity_requests_resolution" in upgrade.stdout
    assert "ck_credit_capacity_requests_decline_reason" in upgrade.stdout
    assert "ENABLE ROW LEVEL SECURITY" in upgrade.stdout
    assert "FORCE ROW LEVEL SECURITY" in upgrade.stdout
    assert "CREATE POLICY org_isolation ON credit_capacity_requests" in upgrade.stdout
    assert "validate_credit_capacity_request_org" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "f5a6b7c8d9e0:e4f5a6b7c8d9", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    no_force = downgrade.stdout.index(
        "ALTER TABLE credit_capacity_requests NO FORCE ROW LEVEL SECURITY"
    )
    guard = downgrade.stdout.index("Refusing to downgrade while credit capacity requests remain")
    drop_table = downgrade.stdout.index("DROP TABLE credit_capacity_requests")
    assert no_force < guard < drop_table


def test_digest_frequency_normalization_migration_renders() -> None:
    upgrade = _run_alembic("upgrade", "f5a6b7c8d9e0:a6b7c8d9e0f1", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "email_digest_frequency" in upgrade.stdout
    assert "IN ('daily', 'immediate')" in upgrade.stdout
    assert "'\"weekly\"'::jsonb" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "a6b7c8d9e0f1:f5a6b7c8d9e0", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr


def test_analysis_completed_at_migration_renders() -> None:
    upgrade = _run_alembic("upgrade", "a6b7c8d9e0f1:b7c8d9e0f1a2", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE" in upgrade.stdout
    assert "pipeline_duration_seconds" in upgrade.stdout
    assert "ck_analyses_completed_at_present" in upgrade.stdout
    assert "ix_analyses_org_status_completed_at" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "b7c8d9e0f1a2:a6b7c8d9e0f1", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    assert "DROP INDEX ix_analyses_org_status_completed_at" in downgrade.stdout
    assert "DROP CONSTRAINT ck_analyses_completed_at_present" in downgrade.stdout
    assert "DROP COLUMN completed_at" in downgrade.stdout


def test_analysis_completed_at_constraint_is_present_in_orm_metadata() -> None:
    constraint_names = {
        constraint.name
        for constraint in Analysis.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_analyses_completed_at_present" in constraint_names


def test_organization_compounds_migration_renders_tenant_local_backfill_and_rls() -> None:
    upgrade = _run_alembic("upgrade", "b7c8d9e0f1a2:c8d9e0f1a2b3", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "CREATE TABLE organization_compounds" in upgrade.stdout
    assert "display_name VARCHAR(500)" in upgrade.stdout
    assert "PRIMARY KEY (org_id, compound_id)" in upgrade.stdout
    assert "ck_organization_compounds_analysis_count_positive" in upgrade.stdout
    assert "ix_organization_compounds_org_first" in upgrade.stdout
    assert "ALTER TABLE analyses NO FORCE ROW LEVEL SECURITY" in upgrade.stdout
    assert "Cannot backfill organization_compounds" in upgrade.stdout
    assert "report_data #>> '{compound,inchi_key}'" in upgrade.stdout
    assert "report_data #>> '{compound,compound_type}'" in upgrade.stdout
    assert "compound_type IN ('small_molecule', 'biologic', 'peptide')" in upgrade.stdout
    assert "compound_type = 'small_molecule'" in upgrade.stdout
    assert "INSERT INTO compounds" in upgrade.stdout
    assert "md5('praviar-compound:' || inchi_key)::uuid" in upgrade.stdout
    assert "ON CONFLICT (inchi_key) DO NOTHING" in upgrade.stdout
    assert "unsupported, malformed, or ambiguous compound identity" in upgrade.stdout
    assert "WHERE compound_id IS NOT NULL" in upgrade.stdout
    assert "UPDATE compounds AS c" in upgrade.stdout
    assert "SET name = ''" in upgrade.stdout
    assert "ALTER TABLE analyses FORCE ROW LEVEL SECURITY" in upgrade.stdout
    assert "ENABLE ROW LEVEL SECURITY" in upgrade.stdout
    assert "FORCE ROW LEVEL SECURITY" in upgrade.stdout
    assert "CREATE POLICY org_isolation ON organization_compounds" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "c8d9e0f1a2b3:b7c8d9e0f1a2", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    assert "NO FORCE ROW LEVEL SECURITY" in downgrade.stdout
    assert "DROP TABLE organization_compounds" in downgrade.stdout


def test_organization_compounds_constraint_is_present_in_orm_metadata() -> None:
    constraint_names = {
        constraint.name
        for constraint in OrganizationCompound.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_organization_compounds_analysis_count_positive" in constraint_names


def test_weekly_digest_delivery_migration_renders_durable_state_and_rls() -> None:
    upgrade = _run_alembic("upgrade", "c8d9e0f1a2b3:d9e0f1a2b3c4", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert "CREATE TABLE weekly_digest_deliveries" in upgrade.stdout
    assert "uq_weekly_digest_delivery_user_period" in upgrade.stdout
    assert "uq_weekly_digest_delivery_submission" in upgrade.stdout
    assert "ck_weekly_digest_delivery_state" in upgrade.stdout
    assert "ck_weekly_digest_delivery_active_payload" in upgrade.stdout
    assert "ck_weekly_digest_delivery_provider_acceptance" in upgrade.stdout
    assert "state = 'provider_accepted' AND recipient_email IS NULL" in upgrade.stdout
    assert "validate_weekly_digest_delivery_org" in upgrade.stdout
    assert "ALTER TABLE weekly_digest_deliveries FORCE ROW LEVEL SECURITY" in upgrade.stdout
    assert "CREATE POLICY org_isolation ON weekly_digest_deliveries" in upgrade.stdout
    assert "CREATE POLICY weekly_digest_unsubscribe_lookup" in upgrade.stdout
    assert "app.digest_unsubscribe_token_digest" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "d9e0f1a2b3c4:c8d9e0f1a2b3", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    no_force = downgrade.stdout.index(
        "ALTER TABLE weekly_digest_deliveries NO FORCE ROW LEVEL SECURITY"
    )
    guard = downgrade.stdout.index("cannot downgrade with unresolved weekly digest deliveries")
    drop_table = downgrade.stdout.index("DROP TABLE weekly_digest_deliveries")
    assert no_force < guard < drop_table


def test_weekly_digest_delivery_constraints_are_present_in_orm_metadata() -> None:
    constraint_names = {
        constraint.name
        for constraint in WeeklyDigestDelivery.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert {
        "ck_weekly_digest_delivery_period",
        "ck_weekly_digest_delivery_state",
        "ck_weekly_digest_delivery_token_pair",
        "ck_weekly_digest_delivery_provider_acceptance",
        "ck_weekly_digest_delivery_terminal",
    } <= constraint_names


def test_analysis_launch_idempotency_migration_renders_durable_contract() -> None:
    upgrade = _run_alembic("upgrade", "d9e0f1a2b3c4:e0f1a2b3c4d5", "--sql")
    assert upgrade.returncode == 0, upgrade.stderr
    assert (
        "ADD COLUMN submitted_identity_confirmed BOOLEAN DEFAULT false NOT NULL" in upgrade.stdout
    )
    assert "ADD COLUMN submitted_identity_value TEXT" in upgrade.stdout
    assert "ADD COLUMN launch_idempotency_key_digest VARCHAR(64)" in upgrade.stdout
    assert "ADD COLUMN launch_payload_digest VARCHAR(64)" in upgrade.stdout
    assert "ADD COLUMN pipeline_reconciliation_generation INTEGER DEFAULT 0 NOT NULL" in (
        upgrade.stdout
    )
    assert "ADD COLUMN pipeline_reconciliation_dispatched_at TIMESTAMP WITH TIME ZONE" in (
        upgrade.stdout
    )
    assert "ck_analyses_submitted_input_type" in upgrade.stdout
    assert "ck_analyses_compound_input_normalized" in upgrade.stdout
    assert "btrim(compound_input" in upgrade.stdout
    assert "ck_analyses_submitted_input_type_matches_value" in upgrade.stdout
    assert "UPDATE analyses" in upgrade.stdout
    assert "ck_analyses_submitted_identity_confirmation" in upgrade.stdout
    assert "submitted_identity_value IS NOT NULL" in upgrade.stdout
    assert "ck_analyses_launch_idempotency_pair" in upgrade.stdout
    assert "ck_analyses_pipeline_reconciliation_generation" in upgrade.stdout
    assert "launch_idempotency_key_digest IS NOT NULL" in upgrade.stdout
    assert "launch_payload_digest IS NOT NULL" in upgrade.stdout
    assert "CREATE UNIQUE INDEX uq_analyses_org_launch_idempotency" in upgrade.stdout

    downgrade = _run_alembic("downgrade", "e0f1a2b3c4d5:d9e0f1a2b3c4", "--sql")
    assert downgrade.returncode == 0, downgrade.stderr
    assert "DROP INDEX uq_analyses_org_launch_idempotency" in downgrade.stdout
    assert "DROP COLUMN launch_payload_digest" in downgrade.stdout
    assert "DROP COLUMN submitted_identity_confirmed" in downgrade.stdout


def test_analysis_launch_idempotency_constraints_are_present_in_orm_metadata() -> None:
    constraints_by_name = {
        constraint.name: constraint
        for constraint in Analysis.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    index_names = {index.name for index in Analysis.__table__.indexes}

    assert {
        "ck_analyses_submitted_input_type",
        "ck_analyses_compound_input_normalized",
        "ck_analyses_submitted_input_type_matches_value",
        "ck_analyses_submitted_identity_confirmation",
        "ck_analyses_launch_idempotency_pair",
        "ck_analyses_pipeline_reconciliation_generation",
    } <= constraints_by_name.keys()
    idempotency_pair_sql = str(constraints_by_name["ck_analyses_launch_idempotency_pair"].sqltext)
    identity_confirmation_sql = str(
        constraints_by_name["ck_analyses_submitted_identity_confirmation"].sqltext
    )
    assert "submitted_identity_value IS NOT NULL" in identity_confirmation_sql
    assert "launch_idempotency_key_digest IS NOT NULL" in idempotency_pair_sql
    assert "launch_payload_digest IS NOT NULL" in idempotency_pair_sql
    assert "uq_analyses_org_launch_idempotency" in index_names


def test_clerk_admin_operation_downgrade_renders_fail_closed_guard() -> None:
    result = _run_alembic("downgrade", "d3e4f5a6b7c8:c2d3e4f5a6b7", "--sql")

    assert result.returncode == 0, result.stderr
    sql = result.stdout
    no_force = sql.index("NO FORCE ROW LEVEL SECURITY")
    guard = sql.index("Refusing to downgrade while Clerk admin operations")
    drop_policy = sql.index("DROP POLICY IF EXISTS org_isolation")
    assert no_force < guard < drop_policy
    assert "state NOT IN ('completed', 'failed')" in sql
    assert "membership_permission_denied_at IS NOT NULL" in sql
    assert "membership_permission_denied_by_operation_id IS NOT NULL" in sql
    assert "membership_permission_convergence_operation_id IS NOT NULL" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql[no_force:drop_policy]


def test_external_delivery_migration_identifiers_fit_postgres_limit() -> None:
    migration = (
        API_ROOT / "alembic" / "versions" / "c2d3e4f5a6b7_add_durable_external_report_delivery.py"
    ).read_text(encoding="utf-8")
    identifiers = set(re.findall(r'"((?:ck|fk|ix|uq)_[A-Za-z0-9_]+)"', migration))

    assert identifiers
    assert {identifier for identifier in identifiers if len(identifier) > 63} == set()
