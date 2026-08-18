from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from praviar_pipeline.models.epo_publication import EPTrustedAcquisitionKey

from api import epo_provenance_runtime


def _key(key_id: str, purpose: str, marker: int) -> EPTrustedAcquisitionKey:
    return EPTrustedAcquisitionKey(
        key_id=key_id,
        public_key=bytes([marker]) * 32,
        purpose=purpose,
        not_before=datetime(2026, 1, 1, tzinfo=UTC),
        not_after=datetime(2030, 1, 1, tzinfo=UTC),
        status="active",
        revocation_epoch=0,
    )


class _Provider:
    def __init__(self, keys: dict[str, EPTrustedAcquisitionKey]) -> None:
        self._keys = keys

    async def load_trusted_keys(self) -> dict[str, EPTrustedAcquisitionKey]:
        return self._keys


class _Store:
    def __init__(self, keys: dict[str, EPTrustedAcquisitionKey]) -> None:
        self._keys = keys

    async def load_trusted_checkpoint_keys(
        self,
    ) -> dict[str, EPTrustedAcquisitionKey]:
        return self._keys


class _Result:
    def __init__(self, value: object) -> None:
        self._value = value

    def mappings(self) -> _Result:
        return self

    def one(self) -> object:
        return self._value

    def scalar_one(self) -> object:
        return self._value


class _Connection:
    def __init__(self, boundary: dict[str, object], isolation: str) -> None:
        self._boundary = boundary
        self._isolation = isolation

    async def execute(self, statement: object) -> _Result:
        return (
            _Result(self._isolation)
            if "SHOW transaction_isolation" in str(statement)
            else _Result(self._boundary)
        )


class _ConnectionContext:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _Connection:
        return self._connection

    async def __aexit__(self, *args: object) -> None:
        return None


class _Engine:
    def __init__(self, boundary: dict[str, object], isolation: str = "serializable") -> None:
        self._connection = _Connection(boundary, isolation)

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(self._connection)


def _boundary() -> dict[str, object]:
    return {
        "current_user": "praviar_epo_checkpoint_writer",
        "is_superuser": False,
        "bypasses_rls": False,
        "inherits_roles": False,
        "has_memberships": False,
        "has_current_table": True,
        "has_history_table": True,
        "has_schema_usage": True,
        "current_select": True,
        "current_insert": True,
        "current_update": True,
        "current_delete": False,
        "history_select": True,
        "history_insert": True,
        "history_update": False,
        "history_delete": False,
        "owns_current_table": False,
        "integrity_triggers_enabled": True,
    }


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    epo_provenance_runtime._checkpoint_store = None
    epo_provenance_runtime._acquisition_key_provider = None
    epo_provenance_runtime._engine = None
    yield
    epo_provenance_runtime._checkpoint_store = None
    epo_provenance_runtime._acquisition_key_provider = None
    epo_provenance_runtime._engine = None


@pytest.mark.asyncio
async def test_startup_verifies_kms_separation_and_exact_database_boundary() -> None:
    checkpoint = {
        "authority-checkpoint": _key("authority-checkpoint", "authority_checkpoint", 1),
        "register-checkpoint": _key("register-checkpoint", "register_checkpoint", 2),
    }
    acquisition = {
        "authority-acquisition": _key("authority-acquisition", "authority_acquisition", 3),
        "register-acquisition": _key("register-acquisition", "register_acquisition", 4),
    }
    epo_provenance_runtime._checkpoint_store = _Store(checkpoint)  # type: ignore[assignment]
    epo_provenance_runtime._acquisition_key_provider = _Provider(acquisition)  # type: ignore[assignment]
    epo_provenance_runtime._engine = _Engine(_boundary())  # type: ignore[assignment]

    await epo_provenance_runtime.verify_epo_provenance_runtime(
        SimpleNamespace(db_epo_checkpoint_user="praviar_epo_checkpoint_writer")  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_startup_rejects_an_overprivileged_checkpoint_principal() -> None:
    checkpoint = {
        "authority-checkpoint": _key("authority-checkpoint", "authority_checkpoint", 1),
        "register-checkpoint": _key("register-checkpoint", "register_checkpoint", 2),
    }
    acquisition = {
        "authority-acquisition": _key("authority-acquisition", "authority_acquisition", 3),
        "register-acquisition": _key("register-acquisition", "register_acquisition", 4),
    }
    boundary = _boundary()
    boundary["current_delete"] = True
    epo_provenance_runtime._checkpoint_store = _Store(checkpoint)  # type: ignore[assignment]
    epo_provenance_runtime._acquisition_key_provider = _Provider(acquisition)  # type: ignore[assignment]
    epo_provenance_runtime._engine = _Engine(boundary)  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="over-privileged"):
        await epo_provenance_runtime.verify_epo_provenance_runtime(
            SimpleNamespace(db_epo_checkpoint_user="praviar_epo_checkpoint_writer")  # type: ignore[arg-type]
        )
