"""Production wiring for EPO provenance trust and durable checkpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.clients.epo_publication_server import EPOPublicationServerClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from api.config import APISettings, get_settings
from api.db.epo_checkpoint_store import PostgresEPAtomicCheckpointStore
from api.services.epo_kms_keys import (
    EPCheckpointKMSKeyProvider,
    EPKMSKeyProvider,
    EPKMSKeyringConfig,
)

if TYPE_CHECKING:
    import httpx

_engine: AsyncEngine | None = None
_checkpoint_store: PostgresEPAtomicCheckpointStore | None = None
_acquisition_key_provider: EPKMSKeyProvider | None = None


def _build_key_providers(
    settings: APISettings,
) -> tuple[EPKMSKeyProvider, EPCheckpointKMSKeyProvider]:
    acquisition_config = EPKMSKeyringConfig.from_json(
        settings.epo_acquisition_kms_keyring_json.get_secret_value(),
        expected_keyset_purpose="acquisition",
    )
    checkpoint_config = EPKMSKeyringConfig.from_json(
        settings.epo_checkpoint_kms_keyring_json.get_secret_value(),
        expected_keyset_purpose="checkpoint",
    )
    return (
        EPKMSKeyProvider(acquisition_config),
        EPCheckpointKMSKeyProvider(checkpoint_config),
    )


def get_epo_checkpoint_store(
    settings: APISettings | None = None,
) -> PostgresEPAtomicCheckpointStore:
    """Return the process-wide store using a checkpoint-only database login."""
    global _acquisition_key_provider, _checkpoint_store, _engine  # noqa: PLW0603
    if _checkpoint_store is not None:
        return _checkpoint_store
    current = settings or get_settings()
    if not current.epo_checkpoint_database_url:
        raise ValueError("EPO_CHECKPOINT_DATABASE_URL is required")
    if not current.epo_checkpoint_database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("EPO checkpoint persistence requires an asyncpg PostgreSQL URL")
    acquisition_provider, checkpoint_provider = _build_key_providers(current)
    _engine = create_async_engine(
        current.epo_checkpoint_database_url,
        pool_size=2,
        max_overflow=1,
        pool_timeout=current.db_pool_timeout,
        pool_pre_ping=True,
        pool_recycle=current.db_pool_recycle,
        isolation_level="SERIALIZABLE",
        connect_args={
            "server_settings": {
                "statement_timeout": str(current.db_statement_timeout_ms),
            },
            "command_timeout": current.db_command_timeout,
        },
    )
    _acquisition_key_provider = acquisition_provider
    _checkpoint_store = PostgresEPAtomicCheckpointStore(
        _engine,
        key_provider=checkpoint_provider,
        source_stream_id=current.epo_checkpoint_source_stream_id,
        schema_epoch=current.epo_checkpoint_schema_epoch,
    )
    return _checkpoint_store


async def build_epo_publication_server_client(
    *,
    settings: APISettings | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> EPOPublicationServerClient:
    """Build the live client with acquisition trust and durable CAS injected."""
    global _acquisition_key_provider  # noqa: PLW0603
    current = settings or get_settings()
    store = get_epo_checkpoint_store(current)
    if _acquisition_key_provider is None:
        raise RuntimeError("EPO acquisition key provider was not initialized")
    acquisition_keys = await _acquisition_key_provider.load_trusted_keys()
    return EPOPublicationServerClient(
        client=http_client,
        trusted_acquisition_public_keys=acquisition_keys,
        checkpoint_store=store,
    )


async def verify_epo_provenance_runtime(settings: APISettings | None = None) -> None:
    """Fail worker startup unless KMS trust and DB least privilege are live."""
    current = settings or get_settings()
    store = get_epo_checkpoint_store(current)
    # This is deliberately a live KMS read. Missing ADC, IAM, a destroyed key
    # version, checksum mismatch, or governed-fingerprint drift aborts startup.
    checkpoint_keys = await store.load_trusted_checkpoint_keys()
    if _acquisition_key_provider is None:
        raise RuntimeError("EPO acquisition key provider was not initialized")
    acquisition_keys = await _acquisition_key_provider.load_trusted_keys()
    if len(checkpoint_keys) < 2 or len(acquisition_keys) < 2:
        raise RuntimeError("EPO provenance keyrings are incomplete")
    if set(checkpoint_keys).intersection(acquisition_keys):
        raise RuntimeError("EPO acquisition and checkpoint key ids overlap")
    if len(
        {key.public_key for key in (*checkpoint_keys.values(), *acquisition_keys.values())}
    ) != len(checkpoint_keys) + len(acquisition_keys):
        raise RuntimeError("EPO acquisition and checkpoint key material overlap")

    if _engine is None:
        raise RuntimeError("EPO checkpoint engine was not initialized")
    async with _engine.connect() as connection:
        boundary = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT
                        current_user AS current_user,
                        role.rolsuper AS is_superuser,
                        role.rolbypassrls AS bypasses_rls,
                        role.rolinherit AS inherits_roles,
                        EXISTS (
                            SELECT 1
                            FROM pg_auth_members AS membership
                            WHERE membership.member = role.oid
                        ) AS has_memberships,
                        to_regclass('public.epo_atomic_checkpoints') IS NOT NULL
                            AS has_current_table,
                        to_regclass('public.epo_atomic_checkpoint_history') IS NOT NULL
                            AS has_history_table,
                        has_schema_privilege(current_user, 'public', 'USAGE')
                            AS has_schema_usage,
                        has_table_privilege(
                            current_user, 'public.epo_atomic_checkpoints', 'SELECT'
                        ) AS current_select,
                        has_table_privilege(
                            current_user, 'public.epo_atomic_checkpoints', 'INSERT'
                        ) AS current_insert,
                        has_table_privilege(
                            current_user, 'public.epo_atomic_checkpoints', 'UPDATE'
                        ) AS current_update,
                        has_table_privilege(
                            current_user, 'public.epo_atomic_checkpoints', 'DELETE'
                        ) AS current_delete,
                        has_table_privilege(
                            current_user, 'public.epo_atomic_checkpoint_history', 'SELECT'
                        ) AS history_select,
                        has_table_privilege(
                            current_user, 'public.epo_atomic_checkpoint_history', 'INSERT'
                        ) AS history_insert,
                        has_table_privilege(
                            current_user, 'public.epo_atomic_checkpoint_history', 'UPDATE'
                        ) AS history_update,
                        has_table_privilege(
                            current_user, 'public.epo_atomic_checkpoint_history', 'DELETE'
                        ) AS history_delete,
                        (
                            SELECT tableowner = current_user
                            FROM pg_tables
                            WHERE schemaname = 'public'
                              AND tablename = 'epo_atomic_checkpoints'
                        ) AS owns_current_table,
                        (
                            SELECT count(*) = 4
                            FROM pg_trigger
                            WHERE tgrelid IN (
                                'public.epo_atomic_checkpoints'::regclass,
                                'public.epo_atomic_checkpoint_history'::regclass
                            )
                              AND NOT tgisinternal
                              AND tgenabled = 'O'
                        ) AS integrity_triggers_enabled
                    FROM pg_roles AS role
                    WHERE role.rolname = current_user
                    """
                    )
                )
            )
            .mappings()
            .one()
        )
        transaction_isolation = (
            await connection.execute(text("SHOW transaction_isolation"))
        ).scalar_one()

    expected_true = {
        "has_current_table",
        "has_history_table",
        "has_schema_usage",
        "current_select",
        "current_insert",
        "current_update",
        "history_select",
        "history_insert",
        "integrity_triggers_enabled",
    }
    expected_false = {
        "is_superuser",
        "bypasses_rls",
        "inherits_roles",
        "has_memberships",
        "current_delete",
        "history_update",
        "history_delete",
        "owns_current_table",
    }
    if boundary["current_user"] != current.db_epo_checkpoint_user:
        raise RuntimeError("EPO checkpoint database principal does not match configuration")
    if any(boundary[name] is not True for name in expected_true):
        raise RuntimeError("EPO checkpoint database grants or integrity triggers are incomplete")
    if any(boundary[name] is not False for name in expected_false):
        raise RuntimeError("EPO checkpoint database principal is over-privileged")
    if transaction_isolation != "serializable":
        raise RuntimeError("EPO checkpoint database is not using serializable transactions")


async def dispose_epo_provenance_runtime() -> None:
    global _acquisition_key_provider, _checkpoint_store, _engine  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _checkpoint_store = None
    _acquisition_key_provider = None


__all__ = [
    "build_epo_publication_server_client",
    "dispose_epo_provenance_runtime",
    "get_epo_checkpoint_store",
    "verify_epo_provenance_runtime",
]
