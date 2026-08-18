"""Configuration contract regressions for fail-fast settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from api import config as config_module
from api.config import APISettings

DELIVERY_KEYRING = (
    '{"schema_version":"praviar.external-report-delivery-keyring.v1",'
    '"active_key_id":"prod-v1","encryption_keys":'
    '{"prod-v1":"QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE"},'
    '"operation_hmac_key":"QkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkI"}'
)


@pytest.fixture(autouse=True)
def _clear_api_settings_env(monkeypatch: pytest.MonkeyPatch):
    """Keep real shell env vars from overriding per-test env files."""
    for key in (
        "APP_ENV",
        "ALLOW_DEV_AUTH_BYPASS",
        "DATABASE_URL",
        "EPO_CHECKPOINT_DATABASE_URL",
        "CLAIMED_USE_WRITER_DATABASE_URL",
        "GLOBAL_ERASURE_DATABASE_URL",
        "REDIS_URL",
        "CHAT_BUDGET_REDIS_URL",
        "REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS",
        "REDIS_SOCKET_TIMEOUT_SECONDS",
        "REDIS_HEALTH_CHECK_INTERVAL_SECONDS",
        "APP_URL",
        "CORS_ORIGINS",
        "CLERK_SECRET_KEY",
        "CLERK_PUBLISHABLE_KEY",
        "CLERK_DOMAIN",
        "CLERK_WEBHOOK_SECRET",
        "SENTRY_DSN",
        "GCS_BUCKET_NAME",
        "GCP_PROJECT_ID",
        "GCP_REGION",
        "PIPELINE_DISPATCH",
        "CERTIFICATION_RELEASE_RECEIPT_JSON",
        "CERTIFICATION_RELEASE_PUBLIC_KEY",
        "CERTIFICATION_RELEASE_KEY_ID",
        "CERTIFICATION_RELEASE_VERIFIER_ID",
        "CERTIFICATION_API_OCI_IMAGE_DIGEST",
        "CERTIFICATION_WORKER_OCI_IMAGE_DIGEST",
        "CERTIFICATION_RUNTIME_POLICY_SHA256",
        "CERTIFICATION_EVIDENCE_POLICY_SHA256",
        "CERTIFICATION_PROMPT_BUNDLE_SHA256",
        "CERTIFICATION_MODEL_BUNDLE_SHA256",
        "CERTIFICATION_TOOL_DEFINITION_BUNDLE_SHA256",
        "CERTIFICATION_COLLECTOR_BUNDLE_SHA256",
        "CLOUD_TASKS_QUEUE_ID",
        "RECONCILIATION_CLOUD_TASKS_QUEUE_ID",
        "WORKERS_SERVICE_URL",
        "TASKS_INVOKER_SA_EMAIL",
        "LEDGER_INVOKER_SA_EMAIL",
        "PLATFORM_ADMIN_USER_IDS",
        "TRUSTED_PROXY_CIDRS",
        "LICENSED_FAMILY_OVERLAY_SEARCH_URL",
        "LICENSED_FAMILY_OVERLAY_API_KEY",
        "LICENSED_FAMILY_OVERLAY_ALLOWED_ORG_IDS",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "PIPELINE_CHECKPOINT_HMAC_SECRET",
        "CLAIMED_USE_ATTESTATION_HMAC_SECRET",
        "EPO_ACQUISITION_KMS_KEYRING_JSON",
        "EPO_CHECKPOINT_KMS_KEYRING_JSON",
        "REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET",
        "REPORT_CERTIFICATION_PUBLIC_KEYRING",
        "POSTMARK_API_TOKEN",
        "POSTMARK_FROM_EMAIL",
        "POSTMARK_OUTBOUND_RETENTION_DAYS",
    ):
        monkeypatch.delenv(key, raising=False)


def _certification_env_lines() -> list[str]:
    return [
        "CERTIFICATION_RELEASE_RECEIPT_JSON={}",
        "CERTIFICATION_RELEASE_PUBLIC_KEY=dGVzdA==",
        "CERTIFICATION_RELEASE_KEY_ID=test-release-key",
        "CERTIFICATION_RELEASE_VERIFIER_ID=test-release-verifier",
        "CERTIFICATION_API_OCI_IMAGE_DIGEST=sha256:" + "1" * 64,
        "CERTIFICATION_WORKER_OCI_IMAGE_DIGEST=sha256:" + "8" * 64,
        "CERTIFICATION_RUNTIME_POLICY_SHA256=" + "2" * 64,
        "CERTIFICATION_EVIDENCE_POLICY_SHA256=" + "3" * 64,
        "CERTIFICATION_PROMPT_BUNDLE_SHA256=" + "4" * 64,
        "CERTIFICATION_MODEL_BUNDLE_SHA256=" + "5" * 64,
        "CERTIFICATION_TOOL_DEFINITION_BUNDLE_SHA256=" + "6" * 64,
        "CERTIFICATION_COLLECTOR_BUNDLE_SHA256=" + "7" * 64,
    ]


REPORT_SIGNING_KEYRING = (
    '{"schema_version":"praviar.report-certification-signing-keyring.v1",'
    '"active_key_id":"report-v2","private_keys":'
    '{"report-v2":"ISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0+P0A="}}'
)
REPORT_PUBLIC_KEYRING = (
    '{"schema_version":"praviar.report-certification-verification-keyring.v1",'
    '"keys":{"report-v2":"5/FioQvsVZr+oZXk3OhLaVaNXSywlj60RsBoXisX8vA="}}'
)
EPO_ACQUISITION_KEYRING = (
    '{"schema_version":"praviar.epo-kms-public-keyring.v1",'
    '"keyset_purpose":"acquisition","keys":['
    '{"key_id":"epo-authority-acquisition-v1","purpose":"authority_acquisition",'
    '"kms_crypto_key_version":"projects/praviar-prod/locations/europe-west2/keyRings/epo/'
    'cryptoKeys/authority-acquisition/cryptoKeyVersions/1",'
    '"expected_public_key_sha256":"' + "1" * 64 + '","expected_protection_level":"HSM",'
    '"not_before":"2026-01-01T00:00:00Z","not_after":"2030-01-01T00:00:00Z",'
    '"status":"active","revocation_epoch":0,"revoked_at":null},'
    '{"key_id":"epo-register-acquisition-v1","purpose":"register_acquisition",'
    '"kms_crypto_key_version":"projects/praviar-prod/locations/europe-west2/keyRings/epo/'
    'cryptoKeys/register-acquisition/cryptoKeyVersions/1",'
    '"expected_public_key_sha256":"' + "2" * 64 + '","expected_protection_level":"HSM",'
    '"not_before":"2026-01-01T00:00:00Z","not_after":"2030-01-01T00:00:00Z",'
    '"status":"active","revocation_epoch":0,"revoked_at":null}]}'
)
EPO_CHECKPOINT_KEYRING = (
    EPO_ACQUISITION_KEYRING.replace(
        '"keyset_purpose":"acquisition"',
        '"keyset_purpose":"checkpoint"',
    )
    .replace("_acquisition", "_checkpoint")
    .replace("-acquisition", "-checkpoint")
)


def test_api_settings_do_not_bake_localhost_defaults_into_field_contract():
    assert APISettings.model_fields["database_url"].default == ""
    assert APISettings.model_fields["redis_url"].default == ""
    assert APISettings.model_fields["chat_budget_redis_url"].default == ""
    assert APISettings.model_fields["app_url"].default == ""
    assert APISettings.model_fields["cors_origins"].default == []
    assert APISettings.model_fields["trusted_proxy_cidrs"].default == []
    assert APISettings.model_fields["gcs_bucket_name"].default == ""
    assert APISettings.model_fields["postmark_from_email"].default == ""


@pytest.mark.parametrize("retention_days", [6, 366])
def test_postmark_outbound_retention_contract_is_bounded(retention_days: int) -> None:
    with pytest.raises(ValidationError) as exc_info:
        APISettings(
            _env_file=None,
            app_env="test",
            postmark_outbound_retention_days=retention_days,
        )

    assert "POSTMARK_OUTBOUND_RETENTION_DAYS must be between 7 and 365" in str(exc_info.value)


def test_postmark_outbound_retention_has_an_explicit_local_default() -> None:
    settings = APISettings(_env_file=None, app_env="test")

    assert settings.postmark_outbound_retention_days == 45


@pytest.mark.parametrize(
    ("token", "sender"),
    [
        ("pm_test", ""),
        ("", "sender@example.invalid"),
    ],
)
def test_postmark_token_and_explicit_sender_are_an_atomic_contract(
    token: str,
    sender: str,
) -> None:
    with pytest.raises(ValidationError, match="must be configured together"):
        APISettings(
            _env_file=None,
            app_env="test",
            postmark_api_token=token,
            postmark_from_email=sender,
        )


def test_api_settings_apply_local_defaults_only_after_explicit_dev_env(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text("APP_ENV=dev\n", encoding="utf-8")

    settings = APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.database_url == config_module.LOCAL_DEV_DATABASE_URL
    assert settings.redis_url == config_module.LOCAL_DEV_REDIS_URL
    assert settings.chat_budget_redis_url == config_module.LOCAL_DEV_REDIS_URL
    assert settings.app_url == config_module.LOCAL_DEV_APP_URL
    assert settings.cors_origins == config_module.LOCAL_DEV_CORS_ORIGINS


def test_api_settings_parse_platform_admin_user_ids(tmp_path: Path):
    platform_admin_id = "11111111-1111-4111-8111-111111111111"
    env_file = tmp_path / "api.env"
    env_file.write_text(
        f'APP_ENV=test\nPLATFORM_ADMIN_USER_IDS=["{platform_admin_id}"]\n',
        encoding="utf-8",
    )

    settings = APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert [str(value) for value in settings.platform_admin_user_ids] == [platform_admin_id]


def test_api_settings_normalize_trusted_proxy_cidrs(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        'APP_ENV=test\nTRUSTED_PROXY_CIDRS=["203.0.113.10", "2001:db8::/64"]\n',
        encoding="utf-8",
    )

    settings = APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.trusted_proxy_cidrs == ["2001:db8::/64", "203.0.113.10/32"]


@pytest.mark.parametrize(
    ("env_key", "expected"),
    [
        ("REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS=0", "REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS"),
        ("REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS=-1", "REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS"),
        ("REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS=nan", "REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS"),
        ("REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS=inf", "REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS"),
        ("REDIS_SOCKET_TIMEOUT_SECONDS=0", "REDIS_SOCKET_TIMEOUT_SECONDS"),
        ("REDIS_SOCKET_TIMEOUT_SECONDS=-1", "REDIS_SOCKET_TIMEOUT_SECONDS"),
        ("REDIS_SOCKET_TIMEOUT_SECONDS=nan", "REDIS_SOCKET_TIMEOUT_SECONDS"),
        ("REDIS_SOCKET_TIMEOUT_SECONDS=inf", "REDIS_SOCKET_TIMEOUT_SECONDS"),
        ("REDIS_HEALTH_CHECK_INTERVAL_SECONDS=0", "REDIS_HEALTH_CHECK_INTERVAL_SECONDS"),
        ("REDIS_HEALTH_CHECK_INTERVAL_SECONDS=-1", "REDIS_HEALTH_CHECK_INTERVAL_SECONDS"),
        ("REDIS_HEALTH_CHECK_INTERVAL_SECONDS=nan", "redis_health_check_interval_seconds"),
        ("REDIS_HEALTH_CHECK_INTERVAL_SECONDS=inf", "redis_health_check_interval_seconds"),
    ],
)
def test_api_settings_reject_invalid_redis_timeouts(
    tmp_path: Path,
    env_key: str,
    expected: str,
):
    env_file = tmp_path / "api.env"
    env_file.write_text(f"APP_ENV=test\n{env_key}\n", encoding="utf-8")

    with pytest.raises(ValidationError) as excinfo:
        APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert expected in str(excinfo.value)


def test_api_settings_reject_invalid_trusted_proxy_cidr(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        'APP_ENV=test\nTRUSTED_PROXY_CIDRS=["not-a-cidr"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_reject_unknown_env_keys(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text("UNKNOWN_SETTING=true\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_reject_legacy_r2_storage_env_keys(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=test\nR2_BUCKET_NAME=legacy-exports\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as excinfo:
        APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert "r2_bucket_name" in str(excinfo.value).lower()


def test_api_env_example_uses_current_settings_contract():
    env_file = Path(__file__).resolve().parents[1] / ".env.example"
    env_text = env_file.read_text(encoding="utf-8")

    assert "GCS_BUCKET_NAME=" in env_text
    assert "R2_" not in env_text

    settings = APISettings(_env_file=env_file)  # type: ignore[call-arg]
    assert settings.app_env == "dev"


def test_api_settings_require_explicit_app_env_outside_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    env_file = tmp_path / "api.env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(config_module, "_running_under_pytest", lambda: False)

    with pytest.raises(ValidationError, match="APP_ENV must be set explicitly"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_reject_dev_auth_bypass_outside_dev(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "ALLOW_DEV_AUTH_BYPASS=true\n"
        "DATABASE_URL=postgresql+asyncpg://user:pass@db.example.com:5432/praviar\n"
        "REDIS_URL=redis://redis.example.com:6379/0\n"
        "APP_URL=https://app.praviar.io\n"
        "CLERK_SECRET_KEY=sk_live_x\n"
        "CLERK_PUBLISHABLE_KEY=pk_live_x\n"
        "CLERK_DOMAIN=clerk.praviar.io\n"
        "CLERK_WEBHOOK_SECRET=whsec_x\n"
        'CORS_ORIGINS=["https://app.praviar.io"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="ALLOW_DEV_AUTH_BYPASS"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_reject_production_localhost_defaults(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/praviar\n"
        "REDIS_URL=redis://localhost:6379/0\n"
        "APP_URL=http://localhost:3000\n"
        "CLERK_SECRET_KEY=sk_live_x\n"
        "CLERK_PUBLISHABLE_KEY=pk_live_x\n"
        "CLERK_DOMAIN=clerk.praviar.io\n"
        "CLERK_WEBHOOK_SECRET=whsec_x\n"
        "PIPELINE_DISPATCH=cloud_tasks\n"
        'CORS_ORIGINS=["https://app.praviar.io"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="local hosts"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("database_url", "redis_url", "app_url", "cors_origin", "expected"),
    [
        (
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/praviar",
            "rediss://redis.example.com:6380/0",
            "https://app.praviar.io",
            "https://app.praviar.io",
            "DATABASE_URL",
        ),
        (
            "postgresql+asyncpg://postgres:postgres@db.example.com:5432/praviar",
            "redis://[::1]:6379/0",
            "https://app.praviar.io",
            "https://app.praviar.io",
            "REDIS_URL",
        ),
        (
            "postgresql+asyncpg://postgres:postgres@db.example.com:5432/praviar",
            "rediss://redis.example.com:6380/0",
            "http://0.0.0.0:3000",
            "https://app.praviar.io",
            "APP_URL",
        ),
        (
            "postgresql+asyncpg://postgres:postgres@db.example.com:5432/praviar",
            "rediss://redis.example.com:6380/0",
            "https://app.praviar.io",
            "http://127.0.0.1:3000",
            "CORS_ORIGINS",
        ),
    ],
)
def test_api_settings_reject_production_loopback_urls(
    tmp_path: Path,
    database_url: str,
    redis_url: str,
    app_url: str,
    cors_origin: str,
    expected: str,
):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        f"DATABASE_URL={database_url}\n"
        f"REDIS_URL={redis_url}\n"
        f"APP_URL={app_url}\n"
        "CLERK_SECRET_KEY=sk_live_x\n"
        "CLERK_PUBLISHABLE_KEY=pk_live_x\n"
        "CLERK_DOMAIN=clerk.praviar.io\n"
        "CLERK_WEBHOOK_SECRET=whsec_x\n"
        "SENTRY_DSN=https://public@example.ingest.sentry.io/1\n"
        "GCS_BUCKET_NAME=praviar-exports\n"
        "PIPELINE_DISPATCH=cloud_tasks\n"
        f'CORS_ORIGINS=["{cors_origin}"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as excinfo:
        APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert expected in str(excinfo.value)


def test_api_settings_reject_prod_without_observability_and_object_storage(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "DATABASE_URL=postgresql+asyncpg://user:pass@db.example.com:5432/praviar\n"
        "REDIS_URL=rediss://redis.example.com:6380/0\n"
        "APP_URL=https://app.praviar.io\n"
        "CLERK_SECRET_KEY=sk_live_x\n"
        "CLERK_PUBLISHABLE_KEY=pk_live_x\n"
        "CLERK_DOMAIN=clerk.praviar.io\n"
        "CLERK_WEBHOOK_SECRET=whsec_x\n"
        "PIPELINE_DISPATCH=cloud_tasks\n"
        'CORS_ORIGINS=["https://app.praviar.io"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as excinfo:
        APISettings(_env_file=env_file)  # type: ignore[call-arg]

    error_text = str(excinfo.value)
    assert "SENTRY_DSN" in error_text
    assert "GCS_BUCKET_NAME" in error_text


def test_api_settings_require_clerk_domain_in_prod(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "DATABASE_URL=postgresql+asyncpg://user:pass@db.example.com:5432/praviar\n"
        "REDIS_URL=rediss://redis.example.com:6380/0\n"
        "APP_URL=https://app.praviar.io\n"
        "CLERK_SECRET_KEY=sk_live_x\n"
        "CLERK_PUBLISHABLE_KEY=pk_live_x\n"
        "CLERK_WEBHOOK_SECRET=whsec_x\n"
        "SENTRY_DSN=https://public@example.ingest.sentry.io/1\n"
        "GCS_BUCKET_NAME=praviar-exports\n"
        'TRUSTED_PROXY_CIDRS=["203.0.113.0/24"]\n'
        "PIPELINE_DISPATCH=cloud_tasks\n"
        'CORS_ORIGINS=["https://app.praviar.io"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as excinfo:
        APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert "CLERK_DOMAIN" in str(excinfo.value)


def test_api_settings_require_stripe_secrets_in_prod(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "DATABASE_URL=postgresql+asyncpg://user:pass@db.example.com:5432/praviar\n"
        "REDIS_URL=rediss://redis.example.com:6380/0\n"
        "APP_URL=https://app.praviar.io\n"
        "API_KEY_HMAC_SECRET=contract-api-key-hmac-secret-with-at-least-32-bytes\n"
        "CLERK_SECRET_KEY=sk_live_x\n"
        "CLERK_PUBLISHABLE_KEY=pk_live_x\n"
        "CLERK_DOMAIN=clerk.praviar.io\n"
        "CLERK_WEBHOOK_SECRET=whsec_x\n"
        "SENTRY_DSN=https://public@example.ingest.sentry.io/1\n"
        "GCS_BUCKET_NAME=praviar-exports\n"
        'TRUSTED_PROXY_CIDRS=["203.0.113.0/24"]\n'
        "PIPELINE_DISPATCH=cloud_tasks\n"
        "GCP_PROJECT_ID=praviar-prod\n"
        "CLOUD_TASKS_QUEUE_ID=pipeline-runs\n"
        "WORKERS_SERVICE_URL=https://workers.praviar.io\n"
        "TASKS_INVOKER_SA_EMAIL=tasks-invoker@praviar-prod.iam.gserviceaccount.com\n"
        'CORS_ORIGINS=["https://app.praviar.io"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as excinfo:
        APISettings(_env_file=env_file)  # type: ignore[call-arg]

    error_text = str(excinfo.value)
    assert "STRIPE_SECRET_KEY" in error_text
    assert "STRIPE_WEBHOOK_SECRET" in error_text


def _production_worker_env(checkpoint_secret: str | None) -> str:
    lines = [
        "APP_ENV=prod",
        "POSTMARK_API_TOKEN=pm_live_contract",
        "POSTMARK_FROM_EMAIL=noreply@example.invalid",
        "POSTMARK_OUTBOUND_RETENTION_DAYS=45",
        "SERVICE_ROLE=worker",
        "DATABASE_URL=postgresql+asyncpg://worker:pass@db.example.com:5432/praviar",
        "EPO_CHECKPOINT_DATABASE_URL=postgresql+asyncpg://epo_writer:pass@db.example.com:5432/praviar",
        f"EPO_ACQUISITION_KMS_KEYRING_JSON='{EPO_ACQUISITION_KEYRING}'",
        f"EPO_CHECKPOINT_KMS_KEYRING_JSON='{EPO_CHECKPOINT_KEYRING}'",
        "CLAIMED_USE_WRITER_DATABASE_URL=postgresql+asyncpg://claimed_writer:pass@db.example.com:5432/praviar",
        "GLOBAL_ERASURE_DATABASE_URL=postgresql+asyncpg://global_erasure:pass@db.example.com:5432/praviar",
        "REDIS_URL=rediss://redis.example.com:6380/0",
        "APP_URL=https://app.praviar.io",
        "SENTRY_DSN=https://public@example.ingest.sentry.io/1",
        "GCS_BUCKET_NAME=praviar-exports",
        'TRUSTED_PROXY_CIDRS=["203.0.113.0/24"]',
        "PIPELINE_DISPATCH=cloud_tasks",
        "GCP_PROJECT_ID=praviar-prod",
        "CLOUD_TASKS_QUEUE_ID=pipeline-runs",
        "RECONCILIATION_CLOUD_TASKS_QUEUE_ID=report-delivery-reconciliation",
        "WORKERS_SERVICE_URL=https://workers.praviar.io",
        "TASKS_INVOKER_SA_EMAIL=tasks-invoker@praviar-prod.iam.gserviceaccount.com",
        "LEDGER_INVOKER_SA_EMAIL=api@praviar-prod.iam.gserviceaccount.com",
        "PIPELINE_CLOUD_RUN_JOB_NAME=projects/praviar-prod/locations/us-central1/jobs/pipeline-worker",
        "PIPELINE_LLM_HARD_BUDGET_USD=50",
        "STRIPE_SECRET_KEY=sk_live_contract",
        (
            "CLAIMED_USE_ATTESTATION_HMAC_SECRET='"
            '{"active_key_id":"counsel-v1","keys":'
            '{"counsel-v1":"production-claimed-use-attestation-key-0001"}}'
            "'"
        ),
        'CORS_ORIGINS=["https://app.praviar.io"]',
        f"REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET='{REPORT_SIGNING_KEYRING}'",
        f"EXTERNAL_REPORT_DELIVERY_KEYRING_SECRET='{DELIVERY_KEYRING}'",
    ]
    lines.extend(_certification_env_lines())
    if checkpoint_secret is not None:
        lines.append(f"PIPELINE_CHECKPOINT_HMAC_SECRET='{checkpoint_secret}'")
    return "\n".join(lines) + "\n"


def test_api_settings_require_checkpoint_hmac_key_ring_for_production_worker(
    tmp_path: Path,
):
    env_file = tmp_path / "worker.env"
    env_file.write_text(_production_worker_env(None), encoding="utf-8")

    with pytest.raises(ValidationError, match="PIPELINE_CHECKPOINT_HMAC_SECRET"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "checkpoint_secret",
    [
        "not-json",
        '{"active_key_id":"prod-v1","keys":{"prod-v1":"short"}}',
        '{"active_key_id":"missing","keys":{"prod-v1":"production-pipeline-checkpoint-hmac-key-0001"}}',
    ],
)
def test_api_settings_reject_invalid_checkpoint_hmac_key_ring_for_production_worker(
    tmp_path: Path,
    checkpoint_secret: str,
):
    env_file = tmp_path / "worker.env"
    env_file.write_text(
        _production_worker_env(checkpoint_secret),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="PIPELINE_CHECKPOINT_HMAC_SECRET"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_accept_rotatable_checkpoint_hmac_key_ring_for_production_worker(
    tmp_path: Path,
):
    env_file = tmp_path / "worker.env"
    secret = (
        '{"active_key_id":"prod-v2","keys":{'
        '"prod-v1":"production-pipeline-checkpoint-hmac-old-key-0001",'
        '"prod-v2":"production-pipeline-checkpoint-hmac-new-key-0002"}}'
    )
    env_file.write_text(_production_worker_env(secret), encoding="utf-8")

    settings = APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.service_role == "worker"
    assert "prod-v2" not in repr(settings.pipeline_checkpoint_hmac_secret)


def test_api_settings_require_explicit_pipeline_llm_budget_for_production_worker(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "worker.env"
    source = _production_worker_env(
        '{"active_key_id":"prod-v1","keys":'
        '{"prod-v1":"production-pipeline-checkpoint-hmac-key-0001"}}'
    ).replace("PIPELINE_LLM_HARD_BUDGET_USD=50\n", "")
    env_file.write_text(source, encoding="utf-8")

    with pytest.raises(ValidationError, match="PIPELINE_LLM_HARD_BUDGET_USD"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_rejects_claimed_use_signing_ring_for_prod_api(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "SERVICE_ROLE=api\n"
        "PIPELINE_DISPATCH=cloud_tasks\n"
        "CLAIMED_USE_ATTESTATION_HMAC_SECRET='"
        '{"active_key_id":"counsel-v1","keys":'
        '{"counsel-v1":"production-claimed-use-attestation-key-0001"}}'
        "'\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValidationError,
        match="CLAIMED_USE_ATTESTATION_HMAC_SECRET \\(must not be configured for api\\)",
    ):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_claimed_use_signing_ring_is_separate_from_worker_checkpoint_ring() -> None:
    secret = (
        '{"active_key_id":"counsel-v2","keys":{'
        '"counsel-v1":"production-claimed-use-hmac-old-key-0001",'
        '"counsel-v2":"production-claimed-use-hmac-new-key-0002"}}'
    )
    settings = APISettings(
        _env_file=None,
        app_env="test",
        claimed_use_attestation_hmac_secret=secret,
    )

    assert settings.claimed_use_attestation_keys.active_key_id == "counsel-v2"
    assert (
        settings.claimed_use_attestation_keys.active_key()
        != settings.checkpoint_integrity_keys.active_key()
    )


def test_api_settings_require_explicit_postmark_retention_in_production(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "worker.env"
    secret = (
        '{"active_key_id":"prod-v1","keys":{'
        '"prod-v1":"production-pipeline-checkpoint-hmac-key-0001"}}'
    )
    env_file.write_text(
        _production_worker_env(secret).replace(
            "POSTMARK_OUTBOUND_RETENTION_DAYS=45\n",
            "",
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValidationError,
        match="POSTMARK_OUTBOUND_RETENTION_DAYS",
    ):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


@pytest.mark.parametrize("service_role", ["api", "worker"])
def test_api_settings_require_postmark_token_for_every_production_role(
    tmp_path: Path,
    service_role: str,
) -> None:
    checkpoint_secret = (
        '{"active_key_id":"prod-v1","keys":{'
        '"prod-v1":"production-pipeline-checkpoint-hmac-key-0001"}}'
    )
    env_file = tmp_path / f"{service_role}.env"
    source = _production_worker_env(checkpoint_secret).replace(
        "SERVICE_ROLE=worker",
        f"SERVICE_ROLE={service_role}",
    )
    env_file.write_text(
        source.replace("POSTMARK_API_TOKEN=pm_live_contract\n", ""),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="POSTMARK_API_TOKEN"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


@pytest.mark.parametrize("service_role", ["api", "worker"])
def test_api_settings_require_postmark_sender_for_every_production_role(
    tmp_path: Path,
    service_role: str,
) -> None:
    checkpoint_secret = (
        '{"active_key_id":"prod-v1","keys":{'
        '"prod-v1":"production-pipeline-checkpoint-hmac-key-0001"}}'
    )
    env_file = tmp_path / f"{service_role}.env"
    source = _production_worker_env(checkpoint_secret).replace(
        "SERVICE_ROLE=worker",
        f"SERVICE_ROLE={service_role}",
    )
    env_file.write_text(
        source.replace("POSTMARK_FROM_EMAIL=noreply@example.invalid\n", ""),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="POSTMARK_FROM_EMAIL"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_require_report_signing_key_ring_for_production_worker(
    tmp_path: Path,
):
    env_file = tmp_path / "worker.env"
    env_file.write_text(
        _production_worker_env(
            '{"active_key_id":"prod-v1","keys":{'
            '"prod-v1":"production-pipeline-checkpoint-hmac-key-0001"}}'
        ).replace(
            f"REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET='{REPORT_SIGNING_KEYRING}'\n",
            "",
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValidationError,
        match="REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET",
    ):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_reject_private_report_signing_key_for_production_api(
    tmp_path: Path,
):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "SERVICE_ROLE=api\n"
        "PIPELINE_DISPATCH=cloud_tasks\n"
        f"REPORT_CERTIFICATION_PUBLIC_KEYRING='{REPORT_PUBLIC_KEYRING}'\n"
        f"REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET='{REPORT_SIGNING_KEYRING}'\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValidationError,
        match="REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET",
    ):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_reject_invalid_report_public_key_ring_for_production_api(
    tmp_path: Path,
):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "SERVICE_ROLE=api\n"
        "PIPELINE_DISPATCH=cloud_tasks\n"
        "REPORT_CERTIFICATION_PUBLIC_KEYRING=not-json\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValidationError,
        match="REPORT_CERTIFICATION_PUBLIC_KEYRING",
    ):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_normalizes_clerk_domain_url(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=test\nCLERK_DOMAIN=https://clerk.praviar.io\n",
        encoding="utf-8",
    )

    settings = APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.clerk_domain == "clerk.praviar.io"


def test_api_settings_require_cloud_tasks_contract_in_prod(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "DATABASE_URL=postgresql+asyncpg://user:pass@db.example.com:5432/praviar\n"
        "REDIS_URL=rediss://redis.example.com:6380/0\n"
        "APP_URL=https://app.praviar.io\n"
        "CLERK_SECRET_KEY=sk_live_x\n"
        "CLERK_PUBLISHABLE_KEY=pk_live_x\n"
        "CLERK_DOMAIN=clerk.praviar.io\n"
        "CLERK_WEBHOOK_SECRET=whsec_x\n"
        "SENTRY_DSN=https://public@example.ingest.sentry.io/1\n"
        "GCS_BUCKET_NAME=praviar-exports\n"
        "PIPELINE_DISPATCH=cloud_tasks\n"
        'CORS_ORIGINS=["https://app.praviar.io"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as excinfo:
        APISettings(_env_file=env_file)  # type: ignore[call-arg]

    error_text = str(excinfo.value)
    assert "GCP_PROJECT_ID" in error_text
    assert "CLOUD_TASKS_QUEUE_ID" in error_text
    assert "RECONCILIATION_CLOUD_TASKS_QUEUE_ID" in error_text
    assert "WORKERS_SERVICE_URL" in error_text
    assert "TASKS_INVOKER_SA_EMAIL" in error_text


def test_api_settings_allow_prod_runtime_with_staging_deployment_label(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "POSTMARK_API_TOKEN=pm_live_contract\n"
        "POSTMARK_FROM_EMAIL=noreply@example.invalid\n"
        "POSTMARK_OUTBOUND_RETENTION_DAYS=45\n"
        "DEPLOYMENT_ENV=staging\n"
        "DATABASE_URL=postgresql+asyncpg://user:pass@db.example.com:5432/praviar\n"
        "REDIS_URL=rediss://redis.example.com:6380/0\n"
        "CHAT_BUDGET_REDIS_URL=rediss://chat-budget.example.com:6380/0\n"
        "APP_URL=https://staging.praviar.io\n"
        "API_KEY_HMAC_SECRET=contract-api-key-hmac-secret-with-at-least-32-bytes\n"
        f"EXTERNAL_REPORT_DELIVERY_KEYRING_SECRET='{DELIVERY_KEYRING}'\n"
        f"REPORT_CERTIFICATION_PUBLIC_KEYRING='{REPORT_PUBLIC_KEYRING}'\n"
        "CLERK_SECRET_KEY=sk_live_x\n"
        "CLERK_PUBLISHABLE_KEY=pk_live_x\n"
        "CLERK_DOMAIN=clerk.praviar.io\n"
        "CLERK_WEBHOOK_SECRET=whsec_x\n"
        "STRIPE_SECRET_KEY=sk_live_stripe\n"
        "STRIPE_WEBHOOK_SECRET=whsec_stripe\n"
        "SENTRY_DSN=https://public@example.ingest.sentry.io/1\n"
        "GCS_BUCKET_NAME=praviar-exports-staging\n"
        'TRUSTED_PROXY_CIDRS=["203.0.113.0/24"]\n'
        "PIPELINE_DISPATCH=cloud_tasks\n"
        "GCP_PROJECT_ID=praviar-staging\n"
        "CLOUD_TASKS_QUEUE_ID=pipeline-runs\n"
        "RECONCILIATION_CLOUD_TASKS_QUEUE_ID=report-delivery-reconciliation\n"
        "WORKERS_SERVICE_URL=https://workers-staging.praviar.io\n"
        "TASKS_INVOKER_SA_EMAIL=tasks-invoker@praviar-staging.iam.gserviceaccount.com\n"
        "PIPELINE_LLM_HARD_BUDGET_USD=50\n"
        'CORS_ORIGINS=["https://staging.praviar.io"]\n'
        + "\n".join(_certification_env_lines())
        + "\n",
        encoding="utf-8",
    )

    settings = APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.app_env == "prod"
    assert settings.deployment_env == "staging"


def test_api_settings_reject_prod_runtime_with_dev_deployment_label(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\nDEPLOYMENT_ENV=dev\nPIPELINE_DISPATCH=cloud_tasks\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="DEPLOYMENT_ENV"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_reject_celery_dispatch_in_prod(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "DATABASE_URL=postgresql+asyncpg://user:pass@db.example.com:5432/praviar\n"
        "REDIS_URL=rediss://redis.example.com:6380/0\n"
        "APP_URL=https://app.praviar.io\n"
        "API_KEY_HMAC_SECRET=contract-api-key-hmac-secret-with-at-least-32-bytes\n"
        "CLERK_SECRET_KEY=sk_live_x\n"
        "CLERK_PUBLISHABLE_KEY=pk_live_x\n"
        "CLERK_DOMAIN=clerk.praviar.io\n"
        "CLERK_WEBHOOK_SECRET=whsec_x\n"
        "SENTRY_DSN=https://public@example.ingest.sentry.io/1\n"
        "GCS_BUCKET_NAME=praviar-exports\n"
        'TRUSTED_PROXY_CIDRS=["203.0.113.0/24"]\n'
        "PIPELINE_DISPATCH=celery\n"
        'CORS_ORIGINS=["https://app.praviar.io"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="PIPELINE_DISPATCH must be 'cloud_tasks'"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_reject_partial_licensed_family_overlay_config(tmp_path: Path):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        'LICENSED_FAMILY_OVERLAY_SEARCH_URL="https://licensed.example/search"\n'
        'LICENSED_FAMILY_OVERLAY_API_KEY="secret"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "search_url",
    [
        "http://licensed.example/search",
        "https://localhost/search",
        "https://127.0.0.1/search",
        "https://10.0.0.1/search",
        "https://169.254.169.254/computeMetadata/v1/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://licensed.local/search",
    ],
)
def test_api_settings_rejects_private_or_local_licensed_family_overlay_url(
    tmp_path: Path,
    search_url: str,
):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=test\n"
        f'LICENSED_FAMILY_OVERLAY_SEARCH_URL="{search_url}"\n'
        'LICENSED_FAMILY_OVERLAY_API_KEY="secret"\n'
        'LICENSED_FAMILY_OVERLAY_ALLOWED_ORG_IDS=["org-1"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="LICENSED_FAMILY_OVERLAY_SEARCH_URL"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_rejects_licensed_family_overlay_url_with_credentials(
    tmp_path: Path,
):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=test\n"
        'LICENSED_FAMILY_OVERLAY_SEARCH_URL="https://user:pass@licensed.example/search"\n'
        'LICENSED_FAMILY_OVERLAY_API_KEY="secret"\n'
        'LICENSED_FAMILY_OVERLAY_ALLOWED_ORG_IDS=["org-1"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="must not include credentials"):
        APISettings(_env_file=env_file)  # type: ignore[call-arg]


def test_api_settings_accepts_public_https_licensed_family_overlay_config(
    tmp_path: Path,
):
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "APP_ENV=test\n"
        'LICENSED_FAMILY_OVERLAY_SEARCH_URL="https://licensed.example/search"\n'
        'LICENSED_FAMILY_OVERLAY_API_KEY="secret"\n'
        'LICENSED_FAMILY_OVERLAY_ALLOWED_ORG_IDS=["org-1"]\n',
        encoding="utf-8",
    )

    settings = APISettings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.licensed_family_overlay_search_url == "https://licensed.example/search"
    assert settings.licensed_family_overlay_allowed_org_ids == ["org-1"]
