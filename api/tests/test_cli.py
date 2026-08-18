from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from certification_keyring_fixtures import (
    TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
)

from api import cli


def _report_access_settings(app_env: str = "dev") -> SimpleNamespace:
    return SimpleNamespace(
        app_env=app_env,
        report_certification_public_keyring=TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
    )


def test_openapi_export_includes_problem_detail_schema():
    from api.main import create_app

    schema = create_app().openapi()

    assert "ProblemDetail" in schema["components"]["schemas"]


def test_export_openapi_bootstrap_adds_repo_pipeline_path(monkeypatch):
    pipeline_src = str(cli.REPO_ROOT / "praviar_pipeline" / "src")
    monkeypatch.setenv("PYTHONPATH", "src")
    monkeypatch.setattr(sys, "path", [path for path in sys.path if path != pipeline_src])

    cli._ensure_praviar_pipeline_importable()

    assert sys.path[0] == pipeline_src
    assert os.environ["PYTHONPATH"].split(os.pathsep)[:2] == [pipeline_src, "src"]


def test_run_pipeline_job_forwards_persisted_execution_fence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    execution_id = uuid.uuid4()
    execute = MagicMock(return_value={"status": "completed", "analysis_id": str(analysis_id)})
    monkeypatch.setattr("api.workers.tasks.execute_fto_pipeline", execute)

    result = cli.main(
        [
            "run-pipeline-job",
            "--analysis-id",
            str(analysis_id),
            "--org-id",
            str(org_id),
            "--execution-id",
            str(execution_id),
        ]
    )

    assert result == 0
    execute.assert_called_once_with(
        analysis_id=str(analysis_id),
        org_id=str(org_id),
        execution_id=str(execution_id),
        provider_retry_attempt=0,
    )
    assert '"status": "completed"' in capsys.readouterr().out


def test_run_pipeline_job_rejects_invalid_fence_before_worker_import(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli.main(
        [
            "run-pipeline-job",
            "--analysis-id",
            "not-a-uuid",
            "--org-id",
            str(uuid.uuid4()),
            "--execution-id",
            str(uuid.uuid4()),
        ]
    )

    assert result == 2
    assert "must all be UUIDs" in capsys.readouterr().err


def test_run_pipeline_job_treats_prior_terminal_failure_as_idempotent_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = MagicMock(return_value={"status": "already_failed"})
    monkeypatch.setattr("api.workers.tasks.execute_fto_pipeline", execute)

    result = cli.main(
        [
            "run-pipeline-job",
            "--analysis-id",
            str(uuid.uuid4()),
            "--org-id",
            str(uuid.uuid4()),
            "--execution-id",
            str(uuid.uuid4()),
        ]
    )

    assert result == 0


def test_run_pipeline_job_forwards_cloud_run_retry_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = MagicMock(return_value={"status": "completed"})
    monkeypatch.setattr("api.workers.tasks.execute_fto_pipeline", execute)
    monkeypatch.setenv("CLOUD_RUN_TASK_ATTEMPT", "1")

    result = cli.main(
        [
            "run-pipeline-job",
            "--analysis-id",
            str(uuid.uuid4()),
            "--org-id",
            str(uuid.uuid4()),
            "--execution-id",
            str(uuid.uuid4()),
        ]
    )

    assert result == 0
    assert execute.call_args.kwargs["provider_retry_attempt"] == 1


def test_run_pipeline_job_fails_when_active_fence_was_not_adopted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = MagicMock(return_value={"status": "already_running"})
    monkeypatch.setattr("api.workers.tasks.execute_fto_pipeline", execute)

    result = cli.main(
        [
            "run-pipeline-job",
            "--analysis-id",
            str(uuid.uuid4()),
            "--org-id",
            str(uuid.uuid4()),
            "--execution-id",
            str(uuid.uuid4()),
        ]
    )

    assert result == 1


def test_run_pipeline_job_rejects_invalid_cloud_run_retry_attempt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli.main(
        [
            "run-pipeline-job",
            "--analysis-id",
            str(uuid.uuid4()),
            "--org-id",
            str(uuid.uuid4()),
            "--execution-id",
            str(uuid.uuid4()),
            "--task-attempt",
            "-1",
        ]
    )

    assert result == 2
    assert "non-negative integer" in capsys.readouterr().err


def test_generated_typescript_keeps_lint_rules_active():
    generated = "/* tslint:disable */\n/* eslint-disable */\nexport type Risk = 'high';\n"

    normalized = cli._normalize_generated_typescript(generated)

    assert "/* tslint:disable */" in normalized
    assert "eslint-disable" not in normalized
    assert "export type Risk = 'high';" in normalized


def test_generated_claimed_use_signed_literals_are_required():
    generated_paths = (
        cli.REPO_ROOT / "packages" / "shared-types" / "src" / "generated.ts",
        cli.REPO_ROOT / "web" / "src" / "lib" / "shared-types" / "generated.ts",
    )
    required_literals = (
        'schema_version: "claimed-use-match-v3";',
        "claimed_use_match: true;",
        "product_identity_match: true;",
        'reviewer_role: "attorney";',
        'attestation_statement_version: "claimed-use-counsel-affirmation-v1";',
    )

    for generated_path in generated_paths:
        generated = generated_path.read_text(encoding="utf-8")
        interface = generated.split("export interface ClaimedUseMatchReceipt {", maxsplit=1)[
            1
        ].split("\n}", maxsplit=1)[0]
        for required_literal in required_literals:
            assert required_literal in interface
            assert required_literal.replace(":", "?:", 1) not in interface


def test_dev_seed_ignores_the_mandatory_stripe_receipt_sentinel():
    statement = cli._non_sentinel_organization_count_statement()
    compiled = statement.compile()

    assert cli.STRIPE_RECEIPT_SENTINEL_CLERK_ORG_ID in compiled.params.values()
    assert "clerk_org_id" in str(compiled)


def test_demo_seed_builds_organization_usage_for_every_persisted_compound():
    org_id = uuid.uuid4()
    compound_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    completed_at = datetime(2026, 7, 17, tzinfo=UTC)

    rows = cli._build_organization_compound_usage_rows(
        org_id=org_id,
        compounds=[
            SimpleNamespace(id=compound_id, name=f"Compound {index}")
            for index, compound_id in enumerate(compound_ids, start=1)
        ],
        first_analyzed_at=completed_at,
    )

    assert [row.compound_id for row in rows] == compound_ids
    assert [row.display_name for row in rows] == [
        "Compound 1",
        "Compound 2",
        "Compound 3",
    ]
    assert {row.org_id for row in rows} == {org_id}
    assert {row.first_analyzed_at for row in rows} == {completed_at}
    assert {row.analysis_count for row in rows} == {1}


def test_demo_seed_lifecycle_contract_matches_report_publishability():
    from api.fixtures.demo_reports import (
        aspirin_report,
        sofosbuvir_report,
        succinic_acid_report,
    )

    with patch(
        "api.services.report_access.get_settings",
        return_value=_report_access_settings(),
    ):
        cli._validate_demo_report_seed_contract(
            completed_reports=(
                ("sofosbuvir", sofosbuvir_report()),
                ("aspirin", aspirin_report()),
            ),
            intentionally_failed_reports=(("succinic_acid", succinic_acid_report()),),
        )


def test_demo_seed_lifecycle_contract_rejects_unpublishable_completed_report():
    from api.fixtures.demo_reports import succinic_acid_report

    with (
        patch(
            "api.services.report_access.get_settings",
            return_value=_report_access_settings(),
        ),
        pytest.raises(ValueError, match="completed succinic_acid seed"),
    ):
        cli._validate_demo_report_seed_contract(
            completed_reports=(("succinic_acid", succinic_acid_report()),),
            intentionally_failed_reports=(),
        )


def test_development_fixture_marker_is_explicit_and_narrow():
    from api.services.analyses import _is_development_fixture

    assert _is_development_fixture({"development_fixture": True}) is True
    assert _is_development_fixture({"development_fixture": False}) is False
    assert _is_development_fixture({"trust_mode": "explorer"}) is False
    assert _is_development_fixture(None) is False


def test_demo_seed_review_and_monitor_artifacts_match_current_report():
    from api.fixtures.demo_reports import sofosbuvir_report
    from api.services.monitors import _monitor_seed_matches
    from api.services.report_access import report_payload_fingerprint, reviewable_finding_keys

    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    report = sofosbuvir_report()
    analysis = SimpleNamespace(
        id=analysis_id,
        org_id=org_id,
        compound_name="Sofosbuvir",
        compound_smiles="CCC",
    )
    attorney = SimpleNamespace(
        id=user_id,
        clerk_user_id="dev_attorney",
        full_name="Patent Attorney",
        email="attorney@dev.local",
    )

    decision = cli._build_demo_reviewer_decision(
        analysis=analysis,
        attorney=attorney,
        report_data=report,
    )
    monitor = cli._build_demo_monitor(
        analysis=analysis,
        user=attorney,
        report_data=report,
    )

    assert (decision.finding_type, decision.finding_ref) in reviewable_finding_keys(report)
    assert decision.report_fingerprint == report_payload_fingerprint(report)
    assert decision.reviewer_user_id == attorney.clerk_user_id
    assert monitor.source_analysis_id == analysis_id
    assert monitor.source_report_id == report["report_id"]
    assert monitor.source_trust_mode == "explorer"
    assert monitor.compound_name == report["compound"]["name"]
    assert monitor.compound_smiles == report["compound"]["canonical_smiles"]
    assert _monitor_seed_matches(
        monitor,
        compound_name=report["compound"]["name"],
        compound_smiles=report["compound"]["canonical_smiles"],
        schedule="daily",
    )
    assert monitor.strategy_version
    assert monitor.monitoring_strategy
    assert monitor.watch_targets


def test_db_bootstrap_roles_statements_create_role_membership_and_runtime_grants():
    statements = cli._db_role_bootstrap_statements(
        app_user="praviar_api",
        worker_user="praviar_worker",
        migration_user="praviar_migrator",
        migration_role="alembic_runner",
    )
    sql = "\n".join(statements)

    assert 'CREATE ROLE "alembic_runner" NOLOGIN' in sql
    assert 'GRANT "alembic_runner" TO CURRENT_USER' in sql
    assert 'GRANT "alembic_runner" TO "praviar_migrator"' in sql
    assert 'ALTER ROLE "alembic_runner" NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT' in sql
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        'TO "alembic_runner"' in sql
    )
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public" in sql
    assert "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public" in sql
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE" in sql
    assert '"praviar_claimed_use_writer"' in sql
    assert '"praviar_global_erasure"' in sql
    assert '"praviar_epo_checkpoint_writer"' in sql
    assert 'ALTER ROLE "praviar_worker" NOSUPERUSER BYPASSRLS NOINHERIT' in sql
    assert 'ALTER ROLE "praviar_global_erasure" NOSUPERUSER NOBYPASSRLS NOINHERIT' in sql
    assert 'ALTER ROLE "praviar_epo_checkpoint_writer" NOSUPERUSER NOBYPASSRLS NOINHERIT' in sql
    assert (
        "ALTER DEFAULT PRIVILEGES FOR ROLE "
        '"alembic_runner" IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC' in sql
    )
    assert "REVOKE INSERT, UPDATE, DELETE ON public.analysis_claimed_use_receipts" in sql
    assert "REVOKE ALL ON public.claimed_use_erasure_authorizations" in sql
    assert "REVOKE UPDATE, DELETE ON public.audit_logs" in sql
    assert "REVOKE ALL ON public.epo_atomic_checkpoints" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON public.epo_atomic_checkpoints" in sql
    assert "GRANT SELECT, INSERT ON public.epo_atomic_checkpoint_history" in sql
    assert "GRANT EXECUTE ON FUNCTION public.issue_claimed_use_receipt" in sql
    assert "GRANT EXECUTE ON FUNCTION public.authorize_claimed_use_erasure" in sql
    assert "GRANT EXECUTE ON FUNCTION public.erase_claimed_use_receipts" in sql
    assert 'ALTER FUNCTION public.issue_claimed_use_receipt(jsonb) OWNER TO "alembic_runner"' in sql
    assert (
        "ALTER FUNCTION public.erase_claimed_use_receipts("
        'uuid, uuid, uuid, uuid, text) OWNER TO "alembic_runner"' in sql
    )
    assert (
        'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM "praviar_global_erasure"' in sql
    )


def test_db_bootstrap_preamble_enables_pgaudit_only_in_deployed_environments():
    assert cli._db_bootstrap_preamble("prod") == ("CREATE EXTENSION IF NOT EXISTS pgaudit",)
    assert cli._db_bootstrap_preamble("dev") == ()
    assert cli._db_bootstrap_preamble("test") == ()


def test_db_bootstrap_roles_rejects_unsafe_identifiers():
    try:
        cli._db_role_bootstrap_statements(
            app_user="praviar_api;DROP ROLE x",
            worker_user="praviar_worker",
            migration_user="praviar_migrator",
            migration_role="alembic_runner",
        )
    except ValueError as exc:
        assert "unsafe PostgreSQL identifier" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("unsafe identifier was accepted")
