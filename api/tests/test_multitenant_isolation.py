"""Executable multitenant isolation canaries."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import deps
from api.db.models import Base, ExportJob, UserRole
from api.db.session import (
    _set_rls_context_after_begin,
    bind_current_org_to_session,
    bind_org_to_sync_session,
    bind_public_share_grant_hash_to_session,
    get_current_org_id,
    set_current_org_id,
)

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/a1b2c3d4e5f6_enable_row_level_security.py"
)
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "alembic/versions"
RLS_POLICY_REPAIR_MIGRATION = MIGRATIONS_DIR / "1c2d3e4f5a6b_refresh_org_isolation_rls_policies.py"
EXPORT_JOB_USER_NULLABILITY_MIGRATION = (
    MIGRATIONS_DIR / "6f4c2a8d9b0e_make_export_job_user_nullable.py"
)
PUBLIC_SHARE_RLS_MIGRATION = MIGRATIONS_DIR / "y9z0a1b2c3d4_add_recipient_bound_report_grants.py"
ORGANIZATION_COMPOUNDS_MIGRATION = MIGRATIONS_DIR / "c8d9e0f1a2b3_add_organization_compounds.py"
SECURITY_HARDENING_MIGRATION = (
    MIGRATIONS_DIR / "x8y9z0a1b2c3_harden_credit_ledger_and_api_key_lookup.py"
)
DIRECT_ORG_RLS_EXCEPTIONS = {
    "users": "Auth bootstrap: Clerk user lookup happens before org context is known.",
}


class _Request:
    def __init__(self, org_id: uuid.UUID) -> None:
        self.headers = {
            "Authorization": "Bearer dev-token",
            "X-Test-Org-Id": str(org_id),
        }
        self.url = SimpleNamespace(path="/api/v1/analyses")


@pytest.mark.asyncio
async def test_bind_current_org_sets_rls_context_on_active_session():
    session = AsyncMock()
    org_id = uuid.uuid4()

    await bind_current_org_to_session(session, org_id)

    assert get_current_org_id() == str(org_id)
    session.execute.assert_awaited_once()
    (statement,) = session.execute.await_args.args
    rendered = str(statement)
    assert "set_config" in rendered
    assert "app.current_org_id" in statement.compile().params.values()
    assert str(org_id) in statement.compile().params.values()
    set_current_org_id(None)


@pytest.mark.asyncio
async def test_bind_public_share_grant_hash_sets_transaction_context():
    session = AsyncMock()

    grant_hash = "a" * 64
    await bind_public_share_grant_hash_to_session(session, grant_hash)

    session.execute.assert_awaited_once()
    (statement,) = session.execute.await_args.args
    rendered = str(statement)
    assert "set_config" in rendered
    assert "app.public_share_grant_hash" in statement.compile().params.values()
    assert grant_hash in statement.compile().params.values()


def test_bind_org_to_sync_session_reapplies_org_after_new_transaction():
    class _FakeSyncSession:
        def __init__(self) -> None:
            self.info: dict[str, str] = {}
            self.statements: list[object] = []

        def execute(self, statement):
            self.statements.append(statement)

    class _FakeConnection:
        def __init__(self) -> None:
            self.statements: list[object] = []

        def execute(self, statement):
            self.statements.append(statement)

    session = _FakeSyncSession()
    connection = _FakeConnection()
    org_id = uuid.uuid4()

    bind_org_to_sync_session(session, org_id)  # type: ignore[arg-type]
    _set_rls_context_after_begin(session, None, connection)

    assert session.info["rls_org_id"] == str(org_id)
    assert len(session.statements) == 1
    assert len(connection.statements) == 1
    for statement in (*session.statements, *connection.statements):
        rendered = str(statement)
        params = statement.compile().params.values()  # type: ignore[union-attr]
        assert "set_config" in rendered
        assert "app.current_org_id" in params
        assert str(org_id) in params


@pytest.mark.asyncio
async def test_dev_token_test_org_header_binds_requested_org(monkeypatch: pytest.MonkeyPatch):
    org_id = uuid.uuid4()
    db = AsyncMock()
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(allow_dev_auth_bypass=True, app_env="dev"),
    )

    user = await deps.get_current_user(_Request(org_id), db)  # type: ignore[arg-type]

    assert user.org_id == org_id
    assert user.role == UserRole.ADMIN
    assert get_current_org_id() == str(org_id)
    db.execute.assert_awaited_once()
    set_current_org_id(None)


def test_rls_migration_covers_org_scoped_tables_and_forces_rls():
    migration_source = MIGRATION.read_text(encoding="utf-8")
    # Tables with a direct org_id column; each carries its own RLS policy.
    for table in (
        "analyses",
        "audit_logs",
        "notifications",
        "monitors",
        "batch_analyses",
        "analysis_reviewer_decisions",
        "api_keys",
        "export_jobs",
    ):
        assert f'"{table}"' in migration_source

    # comments and attorney_feedback have no direct org_id column; they are
    # scoped indirectly through analysis_id -> analyses.org_id and are
    # deliberately excluded from RLS. The migration documents this exclusion.
    for excluded in ("comments", "attorney_feedback"):
        assert excluded in migration_source

    assert "FORCE ROW LEVEL SECURITY" in migration_source
    assert "current_setting('app.current_org_id', true)::uuid" in migration_source
    assert 'op.add_column(\n        "export_jobs"' in migration_source
    assert 'op.create_index(\n        "ix_export_jobs_org_status"' in migration_source


def test_all_direct_org_models_are_rls_protected_or_reviewed_exceptions():
    migration_source = "\n".join(
        path.read_text(encoding="utf-8") for path in MIGRATIONS_DIR.glob("*.py")
    )
    direct_org_tables = {
        table.name for table in Base.metadata.tables.values() if "org_id" in table.c
    }
    expected_rls_tables = direct_org_tables - set(DIRECT_ORG_RLS_EXCEPTIONS)

    missing_table_names = [
        table for table in sorted(expected_rls_tables) if f'"{table}"' not in migration_source
    ]
    assert missing_table_names == []

    # Some migrations apply RLS via an f-string template loop (ORG_SCOPED_TABLES)
    # rather than per-table literal strings. Tables in this set are covered by
    # the loop body in the initial enable-RLS migration or the repair migration.
    # Any table added to the ORM *after* those migrations must have its own
    # explicit "CREATE POLICY org_isolation ON <table>" in a dedicated migration.
    _rls_template_covered = frozenset(
        {
            # a1b2c3d4e5f6_enable_row_level_security.py
            "analyses",
            "audit_logs",
            "notifications",
            "monitors",
            "batch_analyses",
            "analysis_reviewer_decisions",
            "api_keys",
            "export_jobs",
            # 1c2d3e4f5a6b_refresh_org_isolation_rls_policies.py
            "analysis_review_statuses",
            "comment_assignment_events",
            "comment_thread_escalations",
            "config_presets",
            "stripe_events",
            # f6a7b8c9d0e1_extend_rls_org_table_matrix.py (if it exists)
            "faithfulness_scores",
        }
    )

    for table in sorted(expected_rls_tables):
        if table in _rls_template_covered:
            assert f'"{table}"' in migration_source, (
                f"{table} must appear in an RLS migration's ORG_SCOPED_TABLES tuple"
            )
        else:
            assert f"CREATE POLICY org_isolation ON {table}" in migration_source, (
                f"{table} must have org_isolation policy creation in migrations"
            )
            assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in migration_source, (
                f"{table} must force RLS in migrations"
            )

    assert DIRECT_ORG_RLS_EXCEPTIONS == {
        "users": "Auth bootstrap: Clerk user lookup happens before org context is known."
    }


def test_forward_rls_policy_repair_covers_all_direct_org_tables():
    migration_source = RLS_POLICY_REPAIR_MIGRATION.read_text(encoding="utf-8")
    expected_rls_tables = {
        "analyses",
        "analysis_review_statuses",
        "analysis_reviewer_decisions",
        "api_keys",
        "audit_logs",
        "batch_analyses",
        "comment_assignment_events",
        "comment_thread_escalations",
        "config_presets",
        "export_jobs",
        "faithfulness_scores",
        "monitors",
        "notifications",
        "stripe_events",
    }

    for table in sorted(expected_rls_tables):
        assert f'"{table}"' in migration_source

    for future_table in (
        "analysis_checkpoint_decisions",
        "comments",
        "monitor_alerts",
    ):
        assert f'"{future_table}"' not in migration_source

    assert "DROP POLICY IF EXISTS org_isolation ON {table}" in migration_source
    assert "CREATE POLICY org_isolation ON {table}" in migration_source
    assert "current_setting('app.current_org_id', true) ~*" in migration_source
    assert "ELSE NULL::uuid" in migration_source


def test_public_share_rls_policy_requires_exact_bound_grant_hash():
    migration_source = PUBLIC_SHARE_RLS_MIGRATION.read_text(encoding="utf-8")

    assert "CREATE POLICY public_grant_lookup ON external_report_grants" in migration_source
    assert "FOR SELECT" in migration_source
    assert (
        "grant_token_hash = current_setting('app.public_share_grant_hash', true)"
        in migration_source
    )
    assert "ALTER TABLE external_report_grants FORCE ROW LEVEL SECURITY" in migration_source


def test_organization_compounds_policy_is_forced_and_fail_closed() -> None:
    migration_source = ORGANIZATION_COMPOUNDS_MIGRATION.read_text(encoding="utf-8")

    assert "ALTER TABLE organization_compounds ENABLE ROW LEVEL SECURITY" in migration_source
    assert "ALTER TABLE organization_compounds FORCE ROW LEVEL SECURITY" in migration_source
    assert "CREATE POLICY org_isolation ON organization_compounds" in migration_source
    assert "WHEN current_setting('app.current_org_id', true)" in migration_source
    assert "ELSE NULL::uuid" in migration_source
    assert "WITH CHECK" in migration_source


def test_credit_ledger_migration_is_append_only_and_org_consistent():
    source = SECURITY_HARDENING_MIGRATION.read_text(encoding="utf-8")

    assert "credit_ledger_select_isolation" in source
    assert "credit_ledger_insert_isolation" in source
    assert "BEFORE UPDATE OR DELETE ON analysis_credit_ledger" in source
    assert "analysis_credit_ledger is append-only" in source
    assert "ck_analysis_credit_ledger_kind" in source
    assert "ck_analysis_credit_ledger_delta_sign" in source
    assert "uq_credit_ledger_consume_reservation" in source
    assert "uq_credit_ledger_refund_reservation" in source
    assert "validate_analysis_credit_ledger_org" in source
    assert "WHERE id = NEW.analysis_id AND org_id = NEW.org_id" in source
    assert "WHERE id = NEW.user_id AND org_id = NEW.org_id" in source


def test_api_key_lookup_policy_uses_exact_hmac_not_public_prefix():
    source = SECURITY_HARDENING_MIGRATION.read_text(encoding="utf-8")

    assert "app.api_key_hash" in source
    assert "key_hash = current_setting('app.api_key_hash', true)" in source
    assert "api_key_select_isolation" in source
    assert "ck_api_keys_active_namespaced_prefix" in source
    upgrade_source = source.split("def downgrade", maxsplit=1)[0]
    assert "app.api_key_prefix" not in upgrade_source


def test_export_job_user_id_schema_matches_set_null_contract():
    """Export jobs must survive user deletion without violating NOT NULL."""
    cascade_source = (MIGRATIONS_DIR / "0043_add_indexes_cascades_relationships.py").read_text(
        encoding="utf-8"
    )
    nullability_source = EXPORT_JOB_USER_NULLABILITY_MIGRATION.read_text(encoding="utf-8")

    assert ExportJob.__table__.c.user_id.nullable is True
    assert '("export_jobs", "user_id", "users")' in cascade_source
    assert '("export_jobs", "user_id", "users")' in cascade_source
    assert '_replace_fk(table, column, referent, ondelete="SET NULL")' in cascade_source
    assert 'EXPORT_JOBS_TABLE = "export_jobs"' in nullability_source
    assert 'EXPORT_JOB_USER_ID_COLUMN = "user_id"' in nullability_source
    assert "op.alter_column(" in nullability_source
    assert "EXPORT_JOBS_TABLE" in nullability_source
    assert "EXPORT_JOB_USER_ID_COLUMN" in nullability_source
    assert "existing_type=postgresql.UUID(as_uuid=True)" in nullability_source
    assert "nullable=True" in nullability_source
