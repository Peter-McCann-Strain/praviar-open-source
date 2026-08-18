"""Fail-closed contracts for claimed-use database startup attestation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from api.db import claimed_use_privileged


class _MappedResult:
    def __init__(
        self,
        *,
        one: Mapping[str, Any] | None = None,
        all_rows: list[Mapping[str, Any]] | None = None,
    ) -> None:
        self._one = one
        self._all = all_rows

    def mappings(self) -> _MappedResult:
        return self

    def one(self) -> Mapping[str, Any]:
        assert self._one is not None
        return self._one

    def all(self) -> list[Mapping[str, Any]]:
        assert self._all is not None
        return self._all


class _Session:
    def __init__(
        self,
        *,
        identity: Mapping[str, Any],
        functions: list[Mapping[str, Any]],
        acls: list[Mapping[str, Any]],
        default_acls: list[Mapping[str, Any]],
    ) -> None:
        self._identity = identity
        self._functions = functions
        self._acls = acls
        self._default_acls = default_acls

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(
        self,
        statement: object,
        _params: Mapping[str, Any],
    ) -> _MappedResult:
        sql = str(statement)
        if "runtime_role.rolname AS principal" in sql:
            return _MappedResult(one=self._identity)
        if "FROM pg_roles AS function_owner" in sql:
            return _MappedResult(all_rows=self._default_acls)
        if "grantee_name" in sql:
            return _MappedResult(all_rows=self._acls)
        return _MappedResult(all_rows=self._functions)


class _Factory:
    def __init__(
        self,
        *,
        identity: Mapping[str, Any],
        functions: list[Mapping[str, Any]],
        acls: list[Mapping[str, Any]] | None = None,
        default_acls: list[Mapping[str, Any]] | None = None,
    ) -> None:
        self._identity = identity
        self._functions = functions
        owner = "alembic_runner"
        self._acls = acls or [
            {
                "signature": signature,
                "grantee_name": grantee,
                "privilege_type": "EXECUTE",
            }
            for signature, grantee in (
                (
                    claimed_use_privileged._ISSUE_FUNCTION_SIGNATURE,
                    "alembic_runner",
                ),
                (
                    claimed_use_privileged._ISSUE_FUNCTION_SIGNATURE,
                    "praviar_claimed_use_writer",
                ),
                (
                    claimed_use_privileged._REVOKE_FUNCTION_SIGNATURE,
                    "alembic_runner",
                ),
                (
                    claimed_use_privileged._REVOKE_FUNCTION_SIGNATURE,
                    "praviar_claimed_use_writer",
                ),
                (
                    claimed_use_privileged._AUTHORIZE_ERASURE_FUNCTION_SIGNATURE,
                    "alembic_runner",
                ),
                (
                    claimed_use_privileged._AUTHORIZE_ERASURE_FUNCTION_SIGNATURE,
                    "praviar_api",
                ),
                (
                    claimed_use_privileged._AUTHORIZE_ERASURE_FUNCTION_SIGNATURE,
                    "praviar_worker",
                ),
                (
                    claimed_use_privileged._ERASE_FUNCTION_SIGNATURE,
                    "alembic_runner",
                ),
                (
                    claimed_use_privileged._ERASE_FUNCTION_SIGNATURE,
                    "praviar_global_erasure",
                ),
            )
        ]
        self._default_acls = default_acls or [
            {
                "grantee_name": owner,
                "privilege_type": "EXECUTE",
            }
        ]

    def __call__(self) -> _Session:
        return _Session(
            identity=self._identity,
            functions=self._functions,
            acls=self._acls,
            default_acls=self._default_acls,
        )


def _identity(**overrides: Any) -> dict[str, Any]:
    identity = {
        "principal": "praviar_worker",
        "is_superuser": False,
        "bypass_rls": True,
        "inherits_privileges": False,
        "can_login": True,
        "membership_count": 0,
        "accessible_table_count": 12,
        "direct_dml": False,
        "direct_authorization_dml": False,
        "direct_capability_dml": False,
        "audit_mutation": False,
        "may_write": False,
        "may_revoke": False,
        "may_erase": False,
        "may_authorize_erasure": False,
    }
    identity.update(overrides)
    return identity


def _functions(**overrides: Any) -> list[dict[str, Any]]:
    rows = [
        {
            "signature": signature,
            "function_exists": True,
            "owner_name": "alembic_runner",
            "owner_is_superuser": False,
            "owner_bypasses_rls": False,
            "owner_inherits_privileges": False,
            "owner_can_login": False,
            "owner_membership_count": 0,
        }
        for signature in (
            claimed_use_privileged._ISSUE_FUNCTION_SIGNATURE,
            claimed_use_privileged._REVOKE_FUNCTION_SIGNATURE,
            claimed_use_privileged._AUTHORIZE_ERASURE_FUNCTION_SIGNATURE,
            claimed_use_privileged._ERASE_FUNCTION_SIGNATURE,
        )
    ]
    for row in rows:
        row.update(overrides)
    return rows


def _patch_worker_factories(
    monkeypatch: pytest.MonkeyPatch,
    worker_factory: _Factory,
) -> None:
    writer_factory = _Factory(
        identity=_identity(
            principal="praviar_claimed_use_writer",
            bypass_rls=False,
            may_write=True,
            may_revoke=True,
        ),
        functions=_functions(),
    )
    erasure_factory = _Factory(
        identity=_identity(
            principal="praviar_global_erasure",
            bypass_rls=False,
            accessible_table_count=0,
            may_erase=True,
        ),
        functions=_functions(),
    )
    privileged_factories = {
        "writer": writer_factory,
        "erasure": erasure_factory,
    }
    monkeypatch.setattr(
        claimed_use_privileged,
        "get_async_session_factory",
        lambda: worker_factory,
    )
    monkeypatch.setattr(
        claimed_use_privileged,
        "_get_factory",
        privileged_factories.__getitem__,
    )


@pytest.mark.asyncio
async def test_api_startup_accepts_only_the_public_runtime_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_factory = _Factory(
        identity=_identity(
            principal="praviar_api",
            bypass_rls=False,
            may_authorize_erasure=True,
        ),
        functions=_functions(),
    )
    monkeypatch.setattr(
        claimed_use_privileged,
        "get_async_session_factory",
        lambda: api_factory,
    )
    await claimed_use_privileged.verify_claimed_use_privilege_boundary()


@pytest.mark.asyncio
async def test_worker_startup_rejects_reused_database_principals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_principal = "reused_runtime"
    worker_factory = _Factory(
        identity=_identity(
            principal=shared_principal,
            may_authorize_erasure=True,
        ),
        functions=_functions(),
    )
    writer_factory = _Factory(
        identity=_identity(
            principal=shared_principal,
            bypass_rls=False,
            may_write=True,
            may_revoke=True,
        ),
        functions=_functions(),
    )
    erasure_factory = _Factory(
        identity=_identity(
            principal=shared_principal,
            bypass_rls=False,
            may_erase=True,
            accessible_table_count=0,
        ),
        functions=_functions(),
    )
    privileged_factories = {
        "writer": writer_factory,
        "erasure": erasure_factory,
    }
    monkeypatch.setattr(
        claimed_use_privileged,
        "get_async_session_factory",
        lambda: worker_factory,
    )
    monkeypatch.setattr(
        claimed_use_privileged,
        "_get_factory",
        privileged_factories.__getitem__,
    )

    with pytest.raises(RuntimeError, match="principals must be distinct"):
        await claimed_use_privileged.verify_claimed_use_worker_privilege_boundary()


@pytest.mark.asyncio
async def test_worker_startup_accepts_only_the_bounded_bypassrls_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _Factory(
        identity=_identity(may_authorize_erasure=True),
        functions=_functions(),
    )
    _patch_worker_factories(monkeypatch, factory)

    await claimed_use_privileged.verify_claimed_use_worker_privilege_boundary()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("drift", "value"),
    [
        ("is_superuser", True),
        ("bypass_rls", False),
        ("inherits_privileges", True),
        ("can_login", False),
        ("membership_count", 1),
        ("direct_dml", True),
        ("direct_authorization_dml", True),
        ("direct_capability_dml", True),
        ("audit_mutation", True),
        ("may_write", True),
        ("may_revoke", True),
        ("may_erase", True),
        ("may_authorize_erasure", False),
    ],
)
async def test_worker_startup_rejects_role_or_capability_drift(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
    value: Any,
) -> None:
    identity = _identity(may_authorize_erasure=True)
    identity[drift] = value
    factory = _Factory(
        identity=identity,
        functions=_functions(),
    )
    _patch_worker_factories(monkeypatch, factory)

    with pytest.raises(RuntimeError, match="contract failed for worker"):
        await claimed_use_privileged.verify_claimed_use_worker_privilege_boundary()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "functions",
    [
        _functions(owner_is_superuser=True),
        _functions(owner_bypasses_rls=True),
        _functions(owner_inherits_privileges=True),
        _functions(owner_membership_count=1),
        _functions(owner_can_login=True),
        _functions(owner_name="praviar_worker"),
        _functions(function_exists=False),
        [
            *_functions()[:2],
            {
                **_functions()[2],
                "owner_name": "different_owner",
            },
        ],
    ],
)
async def test_worker_startup_rejects_protected_function_drift(
    monkeypatch: pytest.MonkeyPatch,
    functions: list[Mapping[str, Any]],
) -> None:
    factory = _Factory(
        identity=_identity(may_authorize_erasure=True),
        functions=functions,
    )
    _patch_worker_factories(monkeypatch, factory)

    with pytest.raises(
        RuntimeError,
        match="protected function ownership and PUBLIC ACL contract failed",
    ):
        await claimed_use_privileged.verify_claimed_use_worker_privilege_boundary()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("acls", "default_acls"),
    [
        (
            [
                {
                    "signature": claimed_use_privileged._ISSUE_FUNCTION_SIGNATURE,
                    "grantee_name": "PUBLIC",
                    "privilege_type": "EXECUTE",
                }
            ],
            None,
        ),
        (
            None,
            [
                {
                    "grantee_name": "PUBLIC",
                    "privilege_type": "EXECUTE",
                }
            ],
        ),
    ],
)
async def test_worker_startup_rejects_function_or_default_acl_drift(
    monkeypatch: pytest.MonkeyPatch,
    acls: list[Mapping[str, Any]] | None,
    default_acls: list[Mapping[str, Any]] | None,
) -> None:
    factory = _Factory(
        identity=_identity(may_authorize_erasure=True),
        functions=_functions(),
        acls=acls,
        default_acls=default_acls,
    )
    _patch_worker_factories(monkeypatch, factory)

    with pytest.raises(
        RuntimeError,
        match="protected function ownership and PUBLIC ACL contract failed",
    ):
        await claimed_use_privileged.verify_claimed_use_worker_privilege_boundary()
