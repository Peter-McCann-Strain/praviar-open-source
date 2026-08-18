"""API configuration loaded from environment variables."""

from __future__ import annotations

import os
import re
import sys
import uuid
from functools import lru_cache
from ipaddress import ip_address, ip_network
from math import isfinite
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlparse

import structlog
from praviar_pipeline.checkpoint import (
    DEV_CHECKPOINT_HMAC_KEYRING_SECRET,
    CheckpointIntegrityKeyRing,
)
from praviar_pipeline.models.epo_publication import (
    EP_CHECKPOINT_SCHEMA_EPOCH,
    EP_CHECKPOINT_SOURCE_STREAM_ID,
)
from praviar_pipeline.report_certification_binding import (
    ReportCertificationSigner,
    ReportCertificationVerificationKeyRing,
)
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.external_report_delivery_keyring import (
    DEV_EXTERNAL_REPORT_DELIVERY_KEYRING_SECRET,
    ExternalReportDeliveryKeyRing,
)
from api.services.epo_kms_keys import EPKMSKeyringConfig

logger = structlog.get_logger()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
API_ROOT = REPO_ROOT / "api"
LOCAL_DEV_DATABASE_URL = "postgresql+asyncpg://praviar:praviar_dev@localhost:5432/praviar"
LOCAL_DEV_REDIS_URL = "redis://localhost:6379/0"
LOCAL_DEV_APP_URL = "http://localhost:3000"
LOCAL_DEV_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:3001"]
# These are deny-list values, not addresses passed to a bind operation.
LOCAL_PRODUCTION_HOSTS = {  # nosec B104
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
}
LICENSED_OVERLAY_METADATA_HOSTS = {
    "169.254.169.254",
    "metadata",
    "metadata.google.internal",
}
LICENSED_OVERLAY_PUBLIC_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z][a-z0-9-]{1,62}$"
)


def _running_under_pytest() -> bool:
    return "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ


def _uses_local_host(value: str) -> bool:
    """Return true when a URL targets loopback/local development hosts."""
    if not value:
        return False

    lowered = value.lower()
    try:
        parsed = urlparse(value)
    except ValueError:
        return any(host in lowered for host in LOCAL_PRODUCTION_HOSTS)

    host = (parsed.hostname or "").lower()
    return (
        host in LOCAL_PRODUCTION_HOSTS
        or host.endswith(".localhost")
        or any(f"@{local_host}" in lowered for local_host in LOCAL_PRODUCTION_HOSTS)
    )


def licensed_family_overlay_search_url_error(value: str) -> str | None:
    """Return a validation error when the licensed overlay URL is not public-safe."""
    value = str(value or "").strip()
    if not value:
        return None

    try:
        parsed = urlparse(value)
        _ = parsed.port
    except ValueError as exc:
        return f"must be a valid URL ({exc})"

    if parsed.scheme != "https":
        return "must be a public HTTPS URL"
    if parsed.username or parsed.password:
        return "must not include credentials"
    if parsed.fragment:
        return "must not include a URL fragment"

    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return "must include a hostname"
    if host in LOCAL_PRODUCTION_HOSTS or host.endswith((".localhost", ".local")):
        return "must not target local development hosts"
    if host in LICENSED_OVERLAY_METADATA_HOSTS:
        return "must not target cloud metadata hosts"

    try:
        address = ip_address(host)
    except ValueError:
        if not LICENSED_OVERLAY_PUBLIC_HOST_RE.fullmatch(host):
            return "must use a DNS hostname or public IP literal"
        return None

    if not address.is_global:
        return (
            "must not target private, loopback, link-local, reserved, "
            "unspecified, or multicast IP ranges"
        )
    return None


def is_licensed_family_overlay_search_url_safe(value: str) -> bool:
    return licensed_family_overlay_search_url_error(value) is None


def validate_licensed_family_overlay_search_url(value: str) -> str:
    error = licensed_family_overlay_search_url_error(value)
    if error is not None:
        raise ValueError(f"LICENSED_FAMILY_OVERLAY_SEARCH_URL {error}.")
    return str(value or "").strip()


def _is_positive_finite_number(value: float | int) -> bool:
    return isfinite(float(value)) and value > 0


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # Database
    database_url: str = ""
    epo_checkpoint_database_url: str = ""
    claimed_use_writer_database_url: str = ""
    global_erasure_database_url: str = ""
    db_migration_role: str = "alembic_runner"
    db_api_user: str = "praviar_api"
    db_worker_user: str = "praviar_worker"
    db_epo_checkpoint_user: str = "praviar_epo_checkpoint_writer"
    db_claimed_use_writer_user: str = "praviar_claimed_use_writer"
    db_global_erasure_user: str = "praviar_global_erasure"

    # Redis
    redis_url: str = ""
    # Monetary reservations use a dedicated no-eviction ledger instance.
    chat_budget_redis_url: str = ""
    redis_socket_connect_timeout_seconds: float = 3.0
    redis_socket_timeout_seconds: float = 5.0
    redis_health_check_interval_seconds: int = 30

    # Clerk auth
    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""
    clerk_jwks_url: str = "https://api.clerk.com/v1/jwks"
    clerk_domain: str = ""  # e.g. "clerk.example.invalid" — JWT issuer validation
    clerk_webhook_secret: str = ""

    # API key HMAC secret — used to key the HMAC-SHA256 hash stored in key_hash.
    # Required in production; defaults to a fixed dev sentinel so that dev/test
    # environments do not need to configure the secret explicitly.
    api_key_hmac_secret: SecretStr = SecretStr("dev-hmac-secret-not-for-production")
    # Versioned transient-delivery keyring. Production retains old decrypt-only
    # keys during rotation and keeps a stable operation-HMAC key so replay
    # identity does not change when the active encryption key rotates.
    external_report_delivery_keyring_secret: SecretStr = SecretStr(
        DEV_EXTERNAL_REPORT_DELIVERY_KEYRING_SECRET
    )

    # Dedicated worker-only checkpoint signing key ring. The single secret is
    # a JSON object containing an active key id and one or more rotation keys.
    pipeline_checkpoint_hmac_secret: SecretStr = SecretStr(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)
    # Worker-only public trust roots. Each entry names an immutable Cloud KMS
    # CryptoKeyVersion; no EPO private signing key is delivered to the worker.
    epo_acquisition_kms_keyring_json: SecretStr = SecretStr("")
    epo_checkpoint_kms_keyring_json: SecretStr = SecretStr("")
    epo_checkpoint_source_stream_id: str = Field(
        default=EP_CHECKPOINT_SOURCE_STREAM_ID,
        pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$",
    )
    epo_checkpoint_schema_epoch: int = Field(default=EP_CHECKPOINT_SCHEMA_EPOCH, ge=1)
    # Worker-only signing ring for immutable counsel claimed-use attestations.
    # The public API delegates ledger operations to the internal worker service
    # and must never receive this key material.
    claimed_use_attestation_hmac_secret: SecretStr = SecretStr(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)
    report_certification_signing_keyring_secret: SecretStr = SecretStr("")
    report_certification_public_keyring: str = ""
    certification_release_receipt_json: str = ""
    certification_release_public_key: SecretStr = SecretStr("")
    certification_release_key_id: str = ""
    certification_release_verifier_id: str = ""
    certification_api_oci_image_digest: str = ""
    certification_worker_oci_image_digest: str = ""
    certification_runtime_policy_sha256: str = ""
    certification_evidence_policy_sha256: str = ""
    certification_prompt_bundle_sha256: str = ""
    certification_model_bundle_sha256: str = ""
    certification_tool_definition_bundle_sha256: str = ""
    certification_collector_bundle_sha256: str = ""
    certification_revoked_receipt_ids: tuple[str, ...] = ()

    @property
    def checkpoint_integrity_keys(self) -> CheckpointIntegrityKeyRing:
        """Return runtime-only keys used to verify persisted pipeline evidence receipts."""
        return CheckpointIntegrityKeyRing.from_secret(
            self.pipeline_checkpoint_hmac_secret.get_secret_value()
        )

    @property
    def claimed_use_attestation_keys(self) -> CheckpointIntegrityKeyRing:
        """Return the worker signing ring for counsel claimed-use receipts."""
        return CheckpointIntegrityKeyRing.from_secret(
            self.claimed_use_attestation_hmac_secret.get_secret_value()
        )

    # CORS
    cors_origins: list[str] = []

    # Object storage — GCS via Application Default Credentials (no key needed).
    # Per 10-gcp-architecture.md §6.4. Auth via Workload Identity Federation
    # (Cloud Run) or `gcloud auth application-default login` (local dev).
    gcs_bucket_name: str = ""

    # GCP infrastructure settings — populated by Cloud Run env vars from Terraform.
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"

    # Cloud Tasks dispatcher (W3-C). pipeline_dispatch toggles backend.
    pipeline_dispatch: str = "celery"  # "celery" | "cloud_tasks"
    cloud_tasks_queue_id: str = ""
    reconciliation_cloud_tasks_queue_id: str = ""
    workers_service_url: str = ""
    tasks_invoker_sa_email: str = ""
    ledger_invoker_sa_email: str = ""
    pipeline_cloud_run_job_name: str = ""
    pipeline_llm_hard_budget_usd: float | None = None

    # Observability
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    sentry_profiles_sample_rate: float = 0.0
    honeycomb_api_key: str = ""
    release_version: str = "dev"
    # Optional bearer token for the /metrics endpoint.  When set, requests
    # presenting "Authorization: Bearer <token>" are accepted regardless of
    # peer IP, enabling Managed Prometheus scraping from non-loopback addresses.
    metrics_bearer_token: str = ""

    # Database pool
    db_pool_size: int = 50
    db_max_overflow: int = 20
    db_pool_timeout: float = 30.0
    db_pool_recycle: int = 3600
    db_statement_timeout_ms: int = 30000  # 30s per SQL statement
    db_command_timeout: int = 60  # 60s asyncpg connection-level timeout

    # Worker database pool (sync engine for Celery tasks)
    worker_db_pool_size: int = 5
    worker_db_max_overflow: int = 5
    worker_db_pool_timeout: float = 30.0

    # Celery timeouts (seconds)
    celery_soft_time_limit: int = 3540  # 59-minute soft limit
    celery_hard_time_limit: int = 3600  # 60-minute hard kill
    sse_max_stream_seconds: int = 3720  # 62-minute SSE max
    sse_subscription_timeout: float = 30.0  # Redis pubsub poll interval

    # Cache
    report_cache_ttl: int = 86400  # 24h default

    # Chat
    anthropic_api_key: str = ""
    chat_model: str = "claude-sonnet-4-6"
    chat_max_tokens: int = 4096
    chat_history_ttl: int = 86400  # 24h
    chat_max_history: int = 50  # max messages per conversation
    chat_org_monthly_budget_usd: float = Field(default=25.0, gt=0)
    chat_user_daily_budget_usd: float = Field(default=5.0, gt=0)
    chat_input_cost_per_million_usd: float = Field(default=3.0, gt=0)
    # Report documents use the provider's one-hour prompt-cache write path.
    # Keep this separate from base input pricing so monetary controls cannot
    # undercharge cached traffic when provider pricing differs.
    chat_cache_creation_input_cost_per_million_usd: float = Field(default=6.0, gt=0)
    chat_cache_read_input_cost_per_million_usd: float = Field(default=0.3, gt=0)
    chat_output_cost_per_million_usd: float = Field(default=15.0, gt=0)

    # Export
    # Export paths are constrained to this root and jobs use unique child
    # directories; production deployments override the local temporary root.
    export_dir: str = "/tmp/praviar-exports"  # nosec B108

    # Stripe billing
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""  # Stripe Price ID for Starter plan
    stripe_price_pro: str = ""  # Stripe Price ID for Pro plan
    stripe_price_credit_pack_single_analysis: str = ""
    stripe_price_credit_pack_portfolio_5: str = ""
    stripe_price_credit_pack_diligence_15: str = ""
    stripe_price_credit_pack_scale_30: str = ""

    # Licensed external evidence overlays
    licensed_family_overlay_provider_name: str = "licensed_family_overlay"
    licensed_family_overlay_search_url: str = ""
    licensed_family_overlay_api_key: str = ""
    licensed_family_overlay_allowed_org_ids: list[str] = []
    licensed_family_overlay_timeout_seconds: float = 10.0

    # Email (Postmark)
    postmark_api_token: str = ""
    postmark_from_email: str = ""
    postmark_outbound_retention_days: int | None = None

    # Plan limits — single source of truth for billing + rate limiting
    plan_free_analyses_per_month: int = 2
    plan_starter_analyses_per_month: int = 25
    plan_pro_analyses_per_month: int = 100
    plan_free_analyses_per_hour: int = 1
    plan_starter_analyses_per_hour: int = 20
    plan_pro_analyses_per_hour: int = 100
    plan_free_api_calls_per_minute: int = 100
    plan_starter_api_calls_per_minute: int = 500
    plan_pro_api_calls_per_minute: int = 2000

    # App
    service_role: Literal["api", "worker"] = "api"
    app_url: str = ""  # Frontend URL for email links
    api_prefix: str = "/api/v1"
    app_env: Literal["dev", "test", "prod"] | None = None
    deployment_env: Literal["dev", "test", "staging", "prod"] | None = None
    debug: bool = False
    allow_dev_auth_bypass: bool = False
    require_attorney_role_for_risk_ratings: bool = True
    platform_admin_user_ids: list[uuid.UUID] = []
    trusted_proxy_cidrs: list[str] = []

    def _validate_environment_contract(self) -> None:
        if self.app_env is None:
            if _running_under_pytest():
                object.__setattr__(self, "app_env", "test")
            else:
                raise ValueError(
                    "APP_ENV must be set explicitly to dev, test, or prod. "
                    "Do not rely on implicit development defaults."
                )
        if self.deployment_env is None:
            object.__setattr__(self, "deployment_env", self.app_env)
        if self.app_env == "prod" and self.deployment_env in {"dev", "test"}:
            raise ValueError("DEPLOYMENT_ENV must be 'staging' or 'prod' when APP_ENV=prod.")

        if self.allow_dev_auth_bypass and self.app_env != "dev":
            raise ValueError("ALLOW_DEV_AUTH_BYPASS is only permitted when APP_ENV=dev.")
        if self.pipeline_dispatch not in {"celery", "cloud_tasks"}:
            raise ValueError("PIPELINE_DISPATCH must be 'celery' or 'cloud_tasks'.")
        if self.pipeline_llm_hard_budget_usd is None and self.app_env in {"dev", "test"}:
            object.__setattr__(self, "pipeline_llm_hard_budget_usd", 50.0)
        if self.pipeline_llm_hard_budget_usd is not None and not _is_positive_finite_number(
            self.pipeline_llm_hard_budget_usd
        ):
            raise ValueError("PIPELINE_LLM_HARD_BUDGET_USD must be a positive finite number.")
        if self.app_env == "prod" and self.pipeline_dispatch != "cloud_tasks":
            raise ValueError(
                "PIPELINE_DISPATCH must be 'cloud_tasks' when APP_ENV=prod. "
                "Celery is limited to local development and test environments."
            )

    def _apply_nonproduction_defaults(self) -> None:
        if self.app_env not in {"dev", "test"}:
            return
        if self.postmark_outbound_retention_days is None:
            object.__setattr__(self, "postmark_outbound_retention_days", 45)
        if not self.database_url:
            object.__setattr__(self, "database_url", LOCAL_DEV_DATABASE_URL)
            if self.app_env == "dev":
                logger.warning(
                    "database_url_defaulted_for_dev",
                    hint="DATABASE_URL is unset; using the local development database URL",
                )
        if not self.redis_url:
            object.__setattr__(self, "redis_url", LOCAL_DEV_REDIS_URL)
            if self.app_env == "dev":
                logger.warning(
                    "redis_url_defaulted_for_dev",
                    hint="REDIS_URL is unset; using the local development Redis URL",
                )
        if not self.chat_budget_redis_url:
            object.__setattr__(self, "chat_budget_redis_url", self.redis_url)
        if not self.app_url:
            object.__setattr__(self, "app_url", LOCAL_DEV_APP_URL)
        if not self.cors_origins:
            object.__setattr__(self, "cors_origins", list(LOCAL_DEV_CORS_ORIGINS))

    def _normalise_runtime_config(self) -> None:
        normalized_allowed_org_ids = sorted(
            {
                value
                for value in (
                    str(raw_value or "").strip()
                    for raw_value in self.licensed_family_overlay_allowed_org_ids
                )
                if value
            }
        )
        object.__setattr__(
            self,
            "licensed_family_overlay_allowed_org_ids",
            normalized_allowed_org_ids,
        )
        normalized_proxy_cidrs = sorted(
            {
                str(ip_network(value, strict=False))
                for value in (
                    str(raw_value or "").strip() for raw_value in self.trusted_proxy_cidrs
                )
                if value
            }
        )
        object.__setattr__(self, "trusted_proxy_cidrs", normalized_proxy_cidrs)
        clerk_domain = self.clerk_domain.strip()
        if clerk_domain.startswith(("http://", "https://")):
            parsed_domain = urlparse(clerk_domain).hostname or ""
            clerk_domain = parsed_domain.strip()
        object.__setattr__(self, "clerk_domain", clerk_domain)

        postmark_api_token = self.postmark_api_token.strip()
        postmark_from_email = self.postmark_from_email.strip()
        object.__setattr__(self, "postmark_api_token", postmark_api_token)
        object.__setattr__(self, "postmark_from_email", postmark_from_email)
        if bool(postmark_api_token) != bool(postmark_from_email):
            raise ValueError(
                "POSTMARK_API_TOKEN and POSTMARK_FROM_EMAIL must be configured together; "
                "the sender must be an explicitly verified Postmark address."
            )

        if self.postmark_outbound_retention_days is not None and not (
            7 <= self.postmark_outbound_retention_days <= 365
        ):
            raise ValueError("POSTMARK_OUTBOUND_RETENTION_DAYS must be between 7 and 365")

    def _collect_production_certification_requirements(self, missing: list[str]) -> None:
        if self.postmark_outbound_retention_days is None:
            missing.append("POSTMARK_OUTBOUND_RETENTION_DAYS")
        if not self.postmark_api_token:
            missing.append("POSTMARK_API_TOKEN")
        if not self.postmark_from_email:
            missing.append("POSTMARK_FROM_EMAIL")
        signing_keyring_secret = self.report_certification_signing_keyring_secret.get_secret_value()
        if self.service_role == "api":
            if signing_keyring_secret:
                missing.append(
                    "REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET (must not be configured for api)"
                )
            try:
                ReportCertificationVerificationKeyRing.from_json(
                    self.report_certification_public_keyring
                )
            except ValueError:
                missing.append("REPORT_CERTIFICATION_PUBLIC_KEYRING (invalid key ring)")
        if self.service_role == "worker":
            try:
                ReportCertificationSigner.from_secret(signing_keyring_secret)
            except ValueError:
                missing.append("REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET (invalid key ring)")
        certification_contract = {
            "CERTIFICATION_RELEASE_RECEIPT_JSON": self.certification_release_receipt_json,
            "CERTIFICATION_RELEASE_PUBLIC_KEY": (
                self.certification_release_public_key.get_secret_value()
            ),
            "CERTIFICATION_RELEASE_KEY_ID": self.certification_release_key_id,
            "CERTIFICATION_RELEASE_VERIFIER_ID": self.certification_release_verifier_id,
            "CERTIFICATION_API_OCI_IMAGE_DIGEST": self.certification_api_oci_image_digest,
            "CERTIFICATION_WORKER_OCI_IMAGE_DIGEST": self.certification_worker_oci_image_digest,
            "CERTIFICATION_RUNTIME_POLICY_SHA256": self.certification_runtime_policy_sha256,
            "CERTIFICATION_EVIDENCE_POLICY_SHA256": self.certification_evidence_policy_sha256,
            "CERTIFICATION_PROMPT_BUNDLE_SHA256": self.certification_prompt_bundle_sha256,
            "CERTIFICATION_MODEL_BUNDLE_SHA256": self.certification_model_bundle_sha256,
            "CERTIFICATION_TOOL_DEFINITION_BUNDLE_SHA256": (
                self.certification_tool_definition_bundle_sha256
            ),
            "CERTIFICATION_COLLECTOR_BUNDLE_SHA256": self.certification_collector_bundle_sha256,
        }
        missing.extend(name for name, value in certification_contract.items() if not value)
        try:
            delivery_keyring = ExternalReportDeliveryKeyRing.from_secret(
                self.external_report_delivery_keyring_secret.get_secret_value()
            )
            if (
                self.external_report_delivery_keyring_secret.get_secret_value()
                == DEV_EXTERNAL_REPORT_DELIVERY_KEYRING_SECRET
            ):
                raise ValueError("development keyring is forbidden")
            _ = delivery_keyring.active_encryption_key
        except ValueError:
            missing.append("EXTERNAL_REPORT_DELIVERY_KEYRING_SECRET (invalid keyring)")

    def _collect_production_api_secret_requirements(self, missing: list[str]) -> None:
        if self.service_role != "api":
            return
        if self.api_key_hmac_secret.get_secret_value() == "dev-hmac-secret-not-for-production":
            missing.append("API_KEY_HMAC_SECRET")
        if not self.clerk_secret_key:
            missing.append("CLERK_SECRET_KEY")
        if not self.clerk_webhook_secret:
            missing.append("CLERK_WEBHOOK_SECRET")
        if not self.stripe_secret_key:
            missing.append("STRIPE_SECRET_KEY")
        if not self.stripe_webhook_secret:
            missing.append("STRIPE_WEBHOOK_SECRET")
        if not self.clerk_publishable_key:
            missing.append("CLERK_PUBLISHABLE_KEY")
        if not self.clerk_domain:
            missing.append("CLERK_DOMAIN")
        claimed_use_secret = self.claimed_use_attestation_hmac_secret.get_secret_value()
        if claimed_use_secret != DEV_CHECKPOINT_HMAC_KEYRING_SECRET:
            missing.append("CLAIMED_USE_ATTESTATION_HMAC_SECRET (must not be configured for api)")

    def _collect_production_worker_secret_requirements(self, missing: list[str]) -> None:
        if self.service_role != "worker":
            return
        checkpoint_secret = self.pipeline_checkpoint_hmac_secret.get_secret_value()
        if checkpoint_secret == DEV_CHECKPOINT_HMAC_KEYRING_SECRET:
            missing.append("PIPELINE_CHECKPOINT_HMAC_SECRET")
        else:
            try:
                CheckpointIntegrityKeyRing.from_secret(checkpoint_secret)
            except ValueError:
                missing.append("PIPELINE_CHECKPOINT_HMAC_SECRET (invalid key ring)")
        claimed_use_secret = self.claimed_use_attestation_hmac_secret.get_secret_value()
        if claimed_use_secret == DEV_CHECKPOINT_HMAC_KEYRING_SECRET:
            missing.append("CLAIMED_USE_ATTESTATION_HMAC_SECRET")
        else:
            try:
                CheckpointIntegrityKeyRing.from_secret(claimed_use_secret)
            except ValueError:
                missing.append("CLAIMED_USE_ATTESTATION_HMAC_SECRET (invalid key ring)")
        if not self.stripe_secret_key:
            missing.append("STRIPE_SECRET_KEY")
        for env_name, raw_keyring, expected_purpose in (
            (
                "EPO_ACQUISITION_KMS_KEYRING_JSON",
                self.epo_acquisition_kms_keyring_json.get_secret_value(),
                "acquisition",
            ),
            (
                "EPO_CHECKPOINT_KMS_KEYRING_JSON",
                self.epo_checkpoint_kms_keyring_json.get_secret_value(),
                "checkpoint",
            ),
        ):
            try:
                EPKMSKeyringConfig.from_json(
                    raw_keyring,
                    expected_keyset_purpose=cast(
                        Literal["acquisition", "checkpoint"],
                        expected_purpose,
                    ),
                )
            except ValueError:
                missing.append(f"{env_name} (missing or invalid)")

    def _collect_production_database_requirements(self, missing: list[str]) -> None:
        if not self.database_url:
            missing.append("DATABASE_URL")
        elif _uses_local_host(self.database_url):
            missing.append("DATABASE_URL (must not use local hosts in production)")
        if self.service_role == "api" and (
            self.claimed_use_writer_database_url
            or self.global_erasure_database_url
            or self.epo_checkpoint_database_url
        ):
            missing.append(
                "CLAIMED_USE_WRITER_DATABASE_URL, GLOBAL_ERASURE_DATABASE_URL, and "
                "EPO_CHECKPOINT_DATABASE_URL "
                "(must not be configured for api)"
            )
        if self.service_role == "api" and (
            self.epo_acquisition_kms_keyring_json.get_secret_value()
            or self.epo_checkpoint_kms_keyring_json.get_secret_value()
        ):
            missing.append(
                "EPO_ACQUISITION_KMS_KEYRING_JSON and "
                "EPO_CHECKPOINT_KMS_KEYRING_JSON (must not be configured for api)"
            )

    def _collect_production_worker_database_requirements(self, missing: list[str]) -> None:
        if self.service_role != "worker":
            return
        if not self.epo_checkpoint_database_url:
            missing.append("EPO_CHECKPOINT_DATABASE_URL")
        elif _uses_local_host(self.epo_checkpoint_database_url):
            missing.append("EPO_CHECKPOINT_DATABASE_URL (must not use local hosts in production)")
        if not self.claimed_use_writer_database_url:
            missing.append("CLAIMED_USE_WRITER_DATABASE_URL")
        elif _uses_local_host(self.claimed_use_writer_database_url):
            missing.append(
                "CLAIMED_USE_WRITER_DATABASE_URL (must not use local hosts in production)"
            )
        if not self.global_erasure_database_url:
            missing.append("GLOBAL_ERASURE_DATABASE_URL")
        elif _uses_local_host(self.global_erasure_database_url):
            missing.append("GLOBAL_ERASURE_DATABASE_URL (must not use local hosts in production)")
        privileged_urls = {
            self.database_url,
            self.epo_checkpoint_database_url,
            self.claimed_use_writer_database_url,
            self.global_erasure_database_url,
        }
        if (
            all(
                (
                    self.database_url,
                    self.epo_checkpoint_database_url,
                    self.claimed_use_writer_database_url,
                    self.global_erasure_database_url,
                )
            )
            and len(privileged_urls) != 4
        ):
            missing.append(
                "CLAIMED_USE_WRITER_DATABASE_URL, GLOBAL_ERASURE_DATABASE_URL, "
                "and EPO_CHECKPOINT_DATABASE_URL "
                "(must use four distinct credentials)"
            )
        privileged_principals = {urlparse(url).username for url in privileged_urls if url}
        if len(privileged_urls) == 4 and (
            None in privileged_principals or len(privileged_principals) != 4
        ):
            missing.append(
                "CLAIMED_USE_WRITER_DATABASE_URL, GLOBAL_ERASURE_DATABASE_URL, "
                "and EPO_CHECKPOINT_DATABASE_URL "
                "(database principals must be distinct)"
            )

    def _collect_production_network_requirements(self, missing: list[str]) -> None:
        if not self.redis_url:
            missing.append("REDIS_URL")
        elif _uses_local_host(self.redis_url):
            missing.append("REDIS_URL (must not use local hosts in production)")
        if self.service_role == "api":
            if not self.chat_budget_redis_url:
                missing.append("CHAT_BUDGET_REDIS_URL")
            elif _uses_local_host(self.chat_budget_redis_url):
                missing.append("CHAT_BUDGET_REDIS_URL (must not use local hosts in production)")
            elif self.chat_budget_redis_url == self.redis_url:
                missing.append("CHAT_BUDGET_REDIS_URL (must use a dedicated no-eviction ledger)")
        if not self.app_url or _uses_local_host(self.app_url):
            missing.append("APP_URL (must be a production URL)")
        if any(_uses_local_host(origin) for origin in self.cors_origins):
            missing.append("CORS_ORIGINS (contains local hosts)")
        if not self.trusted_proxy_cidrs:
            missing.append("TRUSTED_PROXY_CIDRS")
        if not self.sentry_dsn:
            missing.append("SENTRY_DSN")
        if not self.gcs_bucket_name:
            missing.append("GCS_BUCKET_NAME")
        if self.pipeline_llm_hard_budget_usd is None:
            missing.append("PIPELINE_LLM_HARD_BUDGET_USD")

    def _collect_production_dispatch_requirements(self, missing: list[str]) -> None:
        if self.pipeline_dispatch != "cloud_tasks":
            return
        if not self.gcp_project_id:
            missing.append("GCP_PROJECT_ID")
        if not self.cloud_tasks_queue_id:
            missing.append("CLOUD_TASKS_QUEUE_ID")
        if not self.reconciliation_cloud_tasks_queue_id:
            missing.append("RECONCILIATION_CLOUD_TASKS_QUEUE_ID")
        if not self.workers_service_url or _uses_local_host(self.workers_service_url):
            missing.append("WORKERS_SERVICE_URL")
        if not self.tasks_invoker_sa_email:
            missing.append("TASKS_INVOKER_SA_EMAIL")
        if self.service_role == "worker":
            if not self.ledger_invoker_sa_email:
                missing.append("LEDGER_INVOKER_SA_EMAIL")
            if not self.pipeline_cloud_run_job_name:
                missing.append("PIPELINE_CLOUD_RUN_JOB_NAME")

    def _validate_production_contract(self) -> None:
        if self.app_env != "prod":
            return
        missing: list[str] = []
        self._collect_production_certification_requirements(missing)
        self._collect_production_api_secret_requirements(missing)
        self._collect_production_worker_secret_requirements(missing)
        self._collect_production_database_requirements(missing)
        self._collect_production_worker_database_requirements(missing)
        self._collect_production_network_requirements(missing)
        self._collect_production_dispatch_requirements(missing)
        if self.debug:
            missing.append("DEBUG (must be false in production)")
        if missing:
            raise ValueError(
                f"Required secrets not configured for production: {', '.join(missing)}. "
                "Set APP_ENV=dev or APP_ENV=test for non-production environments."
            )

    def _warn_nonproduction_auth_config(self) -> None:
        if self.app_env == "prod":
            return
        if self.allow_dev_auth_bypass:
            logger.warning(
                "dev_auth_bypass_enabled",
                hint=(
                    "Static dev-token auth is enabled; never use this outside local development."
                ),
            )
        elif not self.clerk_secret_key:
            logger.warning(
                "clerk_secret_key_missing",
                hint="CLERK_SECRET_KEY is not set and dev auth bypass is disabled",
            )

    def _validate_licensed_overlay_config(self) -> None:
        licensed_overlay_fields = {
            "LICENSED_FAMILY_OVERLAY_SEARCH_URL": self.licensed_family_overlay_search_url,
            "LICENSED_FAMILY_OVERLAY_API_KEY": self.licensed_family_overlay_api_key,
            "LICENSED_FAMILY_OVERLAY_ALLOWED_ORG_IDS": self.licensed_family_overlay_allowed_org_ids,
        }
        licensed_overlay_set = {key for key, value in licensed_overlay_fields.items() if value}
        licensed_overlay_missing = {
            key for key, value in licensed_overlay_fields.items() if not value
        }
        if licensed_overlay_set and licensed_overlay_missing:
            raise ValueError(
                "Partial licensed family overlay configuration detected — "
                f"set fields: {', '.join(sorted(licensed_overlay_set))}; "
                f"missing fields: {', '.join(sorted(licensed_overlay_missing))}. "
                "Either configure the licensed family overlay fully or leave it disabled."
            )
        if self.licensed_family_overlay_search_url:
            object.__setattr__(
                self,
                "licensed_family_overlay_search_url",
                validate_licensed_family_overlay_search_url(
                    self.licensed_family_overlay_search_url
                ),
            )
        if self.licensed_family_overlay_timeout_seconds <= 0:
            raise ValueError("LICENSED_FAMILY_OVERLAY_TIMEOUT_SECONDS must be greater than zero.")

    def _validate_connection_timeouts(self) -> None:
        if not _is_positive_finite_number(self.redis_socket_connect_timeout_seconds):
            raise ValueError(
                "REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS must be a finite value greater than zero."
            )
        if not _is_positive_finite_number(self.redis_socket_timeout_seconds):
            raise ValueError(
                "REDIS_SOCKET_TIMEOUT_SECONDS must be a finite value greater than zero."
            )
        if not _is_positive_finite_number(self.redis_health_check_interval_seconds):
            raise ValueError(
                "REDIS_HEALTH_CHECK_INTERVAL_SECONDS must be a finite value greater than zero."
            )

    def _warn_optional_config(self) -> None:
        if not self.sentry_dsn:
            logger.warning("sentry_dsn_empty", hint="Sentry error tracking is disabled")
        if not self.gcs_bucket_name:
            logger.warning(
                "gcs_not_configured",
                hint="GCS object storage is disabled — exports will fail",
            )
        if not self.clerk_publishable_key and self.allow_dev_auth_bypass:
            logger.warning(
                "clerk_publishable_key_empty_dev_auth",
                hint="JWT auth is unavailable; only the explicit dev-token bypass will work",
            )

    @model_validator(mode="after")
    def _validate_required_secrets(self) -> APISettings:
        """Fail fast when the runtime configuration violates its environment contract."""
        self._validate_environment_contract()
        self._apply_nonproduction_defaults()
        self._normalise_runtime_config()
        self._validate_production_contract()
        self._warn_nonproduction_auth_config()
        self._validate_licensed_overlay_config()
        self._validate_connection_timeouts()
        self._warn_optional_config()
        return self


@lru_cache
def get_settings() -> APISettings:
    """Cached settings singleton."""
    if _running_under_pytest():
        settings_kwargs: dict[str, Any] = {"_env_file": None}
        return APISettings(**settings_kwargs)
    return APISettings()
