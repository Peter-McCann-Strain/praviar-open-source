"""Dedicated database sessions for the claimed-use legal-ledger boundary."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.config import get_settings
from api.db.session import _reset_org_id_on_checkin, get_async_session_factory

PrivilegedSessionKind = Literal["writer", "erasure"]

_engines: dict[PrivilegedSessionKind, AsyncEngine] = {}
_factories: dict[PrivilegedSessionKind, async_sessionmaker[AsyncSession]] = {}

_ISSUE_FUNCTION_SIGNATURE = "public.issue_claimed_use_receipt(jsonb)"
_REVOKE_FUNCTION_SIGNATURE = (
    "public.revoke_claimed_use_receipt(uuid,uuid,uuid,text,timestamp with time zone)"
)
_ERASE_FUNCTION_SIGNATURE = "public.erase_claimed_use_receipts(uuid,uuid,uuid,uuid,text)"
_AUTHORIZE_ERASURE_FUNCTION_SIGNATURE = (
    "public.authorize_claimed_use_erasure(uuid,uuid,uuid,text,uuid,text)"
)


@dataclass(frozen=True)
class _RuntimeIdentityContract:
    bypass_rls: bool
    may_write: bool = False
    may_revoke: bool = False
    may_erase: bool = False
    may_authorize_erasure: bool = False
    requires_zero_table_access: bool = False


def _database_url(kind: PrivilegedSessionKind) -> str:
    settings = get_settings()
    url = (
        settings.claimed_use_writer_database_url
        if kind == "writer"
        else settings.global_erasure_database_url
    )
    if not url:
        variable = (
            "CLAIMED_USE_WRITER_DATABASE_URL" if kind == "writer" else "GLOBAL_ERASURE_DATABASE_URL"
        )
        raise RuntimeError(f"{variable} is required for this operation")
    return url


def _get_engine(kind: PrivilegedSessionKind) -> AsyncEngine:
    engine = _engines.get(kind)
    if engine is not None:
        return engine
    settings = get_settings()
    engine = create_async_engine(
        _database_url(kind),
        echo=bool(settings.debug),
        pool_size=2 if kind == "writer" else 1,
        max_overflow=1 if kind == "writer" else 0,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle,
        connect_args={
            "server_settings": {"statement_timeout": str(settings.db_statement_timeout_ms)},
            "command_timeout": settings.db_command_timeout,
        },
    )
    event.listen(engine.sync_engine, "checkin", _reset_org_id_on_checkin)
    _engines[kind] = engine
    return engine


def _get_factory(
    kind: PrivilegedSessionKind,
) -> async_sessionmaker[AsyncSession]:
    factory = _factories.get(kind)
    if factory is None:
        factory = async_sessionmaker(
            _get_engine(kind),
            class_=AsyncSession,
            expire_on_commit=False,
        )
        _factories[kind] = factory
    return factory


@asynccontextmanager
async def claimed_use_privileged_session(
    kind: PrivilegedSessionKind,
    *,
    org_id: uuid.UUID | None = None,
) -> AsyncIterator[AsyncSession]:
    """Yield a transaction-capable session using only the named DB identity."""
    async with _get_factory(kind)() as session:
        try:
            if org_id is not None:
                await session.execute(
                    select(func.set_config("app.current_org_id", str(org_id), True))
                )
            yield session
        except Exception:
            await session.rollback()
            raise


async def verify_claimed_use_privilege_boundary() -> None:
    """Fail API startup if its public identity crosses the ledger boundary."""
    factory = get_async_session_factory()
    principal = await _verify_runtime_identity(
        name="runtime",
        factory=factory,
        contract=_RuntimeIdentityContract(
            bypass_rls=False,
            may_authorize_erasure=True,
        ),
    )
    await _verify_protected_function_security(
        factory=factory,
        runtime_principals={principal},
        expected_function_grantees={
            _ISSUE_FUNCTION_SIGNATURE: {
                get_settings().db_claimed_use_writer_user,
            },
            _REVOKE_FUNCTION_SIGNATURE: {
                get_settings().db_claimed_use_writer_user,
            },
            _AUTHORIZE_ERASURE_FUNCTION_SIGNATURE: {
                get_settings().db_api_user,
                get_settings().db_worker_user,
            },
            _ERASE_FUNCTION_SIGNATURE: {
                get_settings().db_global_erasure_user,
            },
        },
    )


async def verify_claimed_use_worker_privilege_boundary() -> None:
    """Fail ledger-worker startup unless all three identities remain bounded."""
    factory = get_async_session_factory()
    checks = {
        "worker": (
            factory,
            _RuntimeIdentityContract(
                bypass_rls=True,
                may_authorize_erasure=True,
            ),
        ),
        "writer": (
            _get_factory("writer"),
            _RuntimeIdentityContract(
                bypass_rls=False,
                may_write=True,
                may_revoke=True,
            ),
        ),
        "erasure": (
            _get_factory("erasure"),
            _RuntimeIdentityContract(
                bypass_rls=False,
                may_erase=True,
                requires_zero_table_access=True,
            ),
        ),
    }
    principals = {
        await _verify_runtime_identity(
            name=name,
            factory=identity_factory,
            contract=contract,
        )
        for name, (identity_factory, contract) in checks.items()
    }
    if len(principals) != 3:
        raise RuntimeError(
            "claimed-use worker, writer, and erasure database principals must be distinct"
        )
    await _verify_protected_function_security(
        factory=factory,
        runtime_principals=principals,
        expected_function_grantees={
            _ISSUE_FUNCTION_SIGNATURE: {
                get_settings().db_claimed_use_writer_user,
            },
            _REVOKE_FUNCTION_SIGNATURE: {
                get_settings().db_claimed_use_writer_user,
            },
            _AUTHORIZE_ERASURE_FUNCTION_SIGNATURE: {
                get_settings().db_api_user,
                get_settings().db_worker_user,
            },
            _ERASE_FUNCTION_SIGNATURE: {
                get_settings().db_global_erasure_user,
            },
        },
    )


async def _verify_runtime_identity(
    *,
    name: str,
    factory: async_sessionmaker[AsyncSession],
    contract: _RuntimeIdentityContract,
) -> str:
    async with factory() as session:
        row = (
            (
                await session.execute(
                    text(
                        """
                    SELECT
                        runtime_role.rolname AS principal,
                        runtime_role.rolsuper AS is_superuser,
                        runtime_role.rolbypassrls AS bypass_rls,
                        runtime_role.rolinherit AS inherits_privileges,
                        runtime_role.rolcanlogin AS can_login,
                        (
                            SELECT count(*)
                              FROM pg_auth_members AS membership
                             WHERE membership.member = runtime_role.oid
                        ) AS membership_count,
                        (
                            SELECT count(*)
                              FROM pg_class AS relation
                              JOIN pg_namespace AS namespace
                                ON namespace.oid = relation.relnamespace
                             WHERE namespace.nspname = 'public'
                               AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
                               AND has_table_privilege(
                                    current_user,
                                    relation.oid,
                                    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
                               )
                        ) AS accessible_table_count,
                        has_table_privilege(
                            current_user,
                            'public.analysis_claimed_use_receipts',
                            'INSERT,UPDATE,DELETE'
                        ) AS direct_dml,
                        has_table_privilege(
                            current_user,
                            'public.claimed_use_erasure_authorizations',
                            'INSERT,UPDATE,DELETE'
                        ) AS direct_authorization_dml,
                        has_table_privilege(
                            current_user,
                            'public.claimed_use_erasure_capabilities',
                            'INSERT,UPDATE,DELETE'
                        ) AS direct_capability_dml,
                        has_table_privilege(
                            current_user,
                            'public.audit_logs',
                            'UPDATE,DELETE'
                        ) AS audit_mutation,
                        has_function_privilege(
                            current_user,
                            :issue_function_signature,
                            'EXECUTE'
                        ) AS may_write,
                        has_function_privilege(
                            current_user,
                            :revoke_function_signature,
                            'EXECUTE'
                        ) AS may_revoke,
                        has_function_privilege(
                            current_user,
                            :erase_function_signature,
                            'EXECUTE'
                        ) AS may_erase,
                        has_function_privilege(
                            current_user,
                            :authorize_erasure_function_signature,
                            'EXECUTE'
                        ) AS may_authorize_erasure
                      FROM pg_roles AS runtime_role
                     WHERE runtime_role.rolname = current_user
                    """
                    ),
                    {
                        "issue_function_signature": _ISSUE_FUNCTION_SIGNATURE,
                        "revoke_function_signature": _REVOKE_FUNCTION_SIGNATURE,
                        "erase_function_signature": _ERASE_FUNCTION_SIGNATURE,
                        "authorize_erasure_function_signature": (
                            _AUTHORIZE_ERASURE_FUNCTION_SIGNATURE
                        ),
                    },
                )
            )
            .mappings()
            .one()
        )

    actual = {
        "is_superuser": bool(row["is_superuser"]),
        "bypass_rls": bool(row["bypass_rls"]),
        "inherits_privileges": bool(row["inherits_privileges"]),
        "can_login": bool(row["can_login"]),
        "membership_count": int(row["membership_count"]),
        "accessible_table_count": int(row["accessible_table_count"]),
        "direct_dml": bool(row["direct_dml"]),
        "direct_authorization_dml": bool(row["direct_authorization_dml"]),
        "direct_capability_dml": bool(row["direct_capability_dml"]),
        "audit_mutation": bool(row["audit_mutation"]),
        "may_write": bool(row["may_write"]),
        "may_revoke": bool(row["may_revoke"]),
        "may_erase": bool(row["may_erase"]),
        "may_authorize_erasure": bool(row["may_authorize_erasure"]),
    }
    expected = {
        "is_superuser": False,
        "bypass_rls": contract.bypass_rls,
        "inherits_privileges": False,
        "can_login": True,
        "membership_count": 0,
        "accessible_table_count": (
            0 if contract.requires_zero_table_access else int(row["accessible_table_count"])
        ),
        "direct_dml": False,
        "direct_authorization_dml": False,
        "direct_capability_dml": False,
        "audit_mutation": False,
        "may_write": contract.may_write,
        "may_revoke": contract.may_revoke,
        "may_erase": contract.may_erase,
        "may_authorize_erasure": contract.may_authorize_erasure,
    }
    if actual != expected:
        raise RuntimeError(f"claimed-use database privilege contract failed for {name}")
    return str(row["principal"])


async def _verify_protected_function_security(
    *,
    factory: async_sessionmaker[AsyncSession],
    runtime_principals: set[str],
    expected_function_grantees: dict[str, set[str]],
) -> None:
    async with factory() as session:
        function_rows = (
            (
                await session.execute(
                    text(
                        """
                        WITH protected(signature) AS (
                            VALUES
                                (:issue_function_signature),
                                (:revoke_function_signature),
                                (:authorize_erasure_function_signature),
                                (:erase_function_signature)
                        )
                        SELECT
                            protected.signature,
                            protected_function.oid IS NOT NULL AS function_exists,
                            function_owner.rolname AS owner_name,
                            function_owner.rolsuper AS owner_is_superuser,
                            function_owner.rolbypassrls AS owner_bypasses_rls,
                            function_owner.rolinherit AS owner_inherits_privileges,
                            function_owner.rolcanlogin AS owner_can_login,
                            (
                                SELECT count(*)
                                  FROM pg_auth_members AS membership
                                 WHERE membership.member = function_owner.oid
                            ) AS owner_membership_count
                          FROM protected
                          LEFT JOIN pg_proc AS protected_function
                            ON protected_function.oid = to_regprocedure(
                                protected.signature
                            )
                          LEFT JOIN pg_roles AS function_owner
                            ON function_owner.oid = protected_function.proowner
                        """
                    ),
                    {
                        "issue_function_signature": _ISSUE_FUNCTION_SIGNATURE,
                        "revoke_function_signature": _REVOKE_FUNCTION_SIGNATURE,
                        "erase_function_signature": _ERASE_FUNCTION_SIGNATURE,
                        "authorize_erasure_function_signature": (
                            _AUTHORIZE_ERASURE_FUNCTION_SIGNATURE
                        ),
                    },
                )
            )
            .mappings()
            .all()
        )
        acl_rows = (
            (
                await session.execute(
                    text(
                        """
                        WITH protected(signature) AS (
                            VALUES
                                (:issue_function_signature),
                                (:revoke_function_signature),
                                (:authorize_erasure_function_signature),
                                (:erase_function_signature)
                        )
                        SELECT
                            protected.signature,
                            CASE
                                WHEN privilege.grantee = 0 THEN 'PUBLIC'
                                ELSE grantee.rolname
                            END AS grantee_name,
                            privilege.privilege_type
                          FROM protected
                          JOIN pg_proc AS protected_function
                            ON protected_function.oid = to_regprocedure(
                                protected.signature
                            )
                          CROSS JOIN LATERAL aclexplode(
                            COALESCE(
                                protected_function.proacl,
                                acldefault('f', protected_function.proowner)
                            )
                          ) AS privilege
                          LEFT JOIN pg_roles AS grantee
                            ON grantee.oid = privilege.grantee
                        """
                    ),
                    {
                        "issue_function_signature": _ISSUE_FUNCTION_SIGNATURE,
                        "revoke_function_signature": _REVOKE_FUNCTION_SIGNATURE,
                        "erase_function_signature": _ERASE_FUNCTION_SIGNATURE,
                        "authorize_erasure_function_signature": (
                            _AUTHORIZE_ERASURE_FUNCTION_SIGNATURE
                        ),
                    },
                )
            )
            .mappings()
            .all()
        )
        default_acl_rows = (
            (
                await session.execute(
                    text(
                        """
                        SELECT
                            CASE
                                WHEN privilege.grantee = 0 THEN 'PUBLIC'
                                ELSE grantee.rolname
                            END AS grantee_name,
                            privilege.privilege_type
                          FROM pg_roles AS function_owner
                          JOIN pg_namespace AS namespace
                            ON namespace.nspname = 'public'
                          LEFT JOIN pg_default_acl AS defaults
                            ON defaults.defaclrole = function_owner.oid
                           AND defaults.defaclnamespace = namespace.oid
                           AND defaults.defaclobjtype = 'f'
                          CROSS JOIN LATERAL aclexplode(
                            COALESCE(
                                defaults.defaclacl,
                                acldefault('f', function_owner.oid)
                            )
                          ) AS privilege
                          LEFT JOIN pg_roles AS grantee
                            ON grantee.oid = privilege.grantee
                         WHERE function_owner.rolname = :expected_owner
                        """
                    ),
                    {"expected_owner": get_settings().db_migration_role},
                )
            )
            .mappings()
            .all()
        )

    owners = {
        str(row["owner_name"])
        for row in function_rows
        if bool(row["function_exists"]) and row["owner_name"] is not None
    }
    expected_owner = get_settings().db_migration_role
    actual_acls: dict[str, set[tuple[str, str]]] = {
        signature: set() for signature in expected_function_grantees
    }
    for row in acl_rows:
        signature = str(row["signature"])
        actual_acls.setdefault(signature, set()).add(
            (str(row["grantee_name"]), str(row["privilege_type"]))
        )
    expected_acls = {
        signature: {
            (expected_owner, "EXECUTE"),
            *((grantee, "EXECUTE") for grantee in grantees),
        }
        for signature, grantees in expected_function_grantees.items()
    }
    actual_default_acls = {
        (str(row["grantee_name"]), str(row["privilege_type"])) for row in default_acl_rows
    }
    contract_holds = (
        len(function_rows) == 4
        and all(bool(row["function_exists"]) for row in function_rows)
        and all(not bool(row["owner_is_superuser"]) for row in function_rows)
        and all(not bool(row["owner_bypasses_rls"]) for row in function_rows)
        and all(not bool(row["owner_inherits_privileges"]) for row in function_rows)
        and all(not bool(row["owner_can_login"]) for row in function_rows)
        and all(int(row["owner_membership_count"]) == 0 for row in function_rows)
        and owners == {expected_owner}
        and owners.isdisjoint(runtime_principals)
        and actual_acls == expected_acls
        and actual_default_acls == {(expected_owner, "EXECUTE")}
    )
    if not contract_holds:
        raise RuntimeError(
            "claimed-use protected function ownership and PUBLIC ACL contract failed"
        )


async def dispose_claimed_use_privileged_engines() -> None:
    """Dispose both privileged pools and clear their lazy factories."""
    for engine in _engines.values():
        await engine.dispose()
    _engines.clear()
    _factories.clear()
