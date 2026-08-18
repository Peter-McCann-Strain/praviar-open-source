"""Operational CLI for the Praviar API package."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from api.config import get_settings
from api.db.models import Organization, User, UserRole
from api.db.session import async_session_factory, bind_current_org_to_session

if TYPE_CHECKING:
    from api.db.models import (
        Analysis,
        AnalysisReviewerDecision,
        Compound,
        Monitor,
        OrganizationCompound,
    )

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPENAPI_OUTPUT = REPO_ROOT / "api" / "openapi.generated.json"
DEFAULT_SHARED_TYPES_OUTPUT = REPO_ROOT / "packages" / "shared-types" / "src" / "generated.ts"
IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _quote_pg_identifier(value: str) -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"unsafe PostgreSQL identifier: {value!r}")
    return f'"{value}"'


def _quote_pg_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _db_role_bootstrap_statements(
    *,
    app_user: str,
    worker_user: str,
    migration_user: str,
    migration_role: str,
    epo_checkpoint_user: str = "praviar_epo_checkpoint_writer",
    claimed_use_writer_user: str = "praviar_claimed_use_writer",
    global_erasure_user: str = "praviar_global_erasure",
) -> list[str]:
    app = _quote_pg_identifier(app_user)
    worker = _quote_pg_identifier(worker_user)
    migrator = _quote_pg_identifier(migration_user)
    role = _quote_pg_identifier(migration_role)
    epo_checkpoint = _quote_pg_identifier(epo_checkpoint_user)
    writer = _quote_pg_identifier(claimed_use_writer_user)
    erasure = _quote_pg_identifier(global_erasure_user)
    role_literal = _quote_pg_literal(migration_role)
    runtime_users = f"{app}, {worker}"
    return [
        (
            "DO $$\n"
            "BEGIN\n"
            f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {role_literal}) THEN\n"
            f"    CREATE ROLE {role} NOLOGIN;\n"
            "  END IF;\n"
            "END\n"
            "$$"
        ),
        f"GRANT {role} TO CURRENT_USER",
        f"GRANT {role} TO {migrator}",
        f"ALTER ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT",
        f"GRANT USAGE, CREATE ON SCHEMA public TO {role}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}",
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {role}",
        f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {erasure}",
        f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {erasure}",
        f"GRANT USAGE ON SCHEMA public TO {runtime_users}",
        f"GRANT USAGE ON SCHEMA public TO {writer}, {erasure}, {epo_checkpoint}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {runtime_users}",
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {runtime_users}",
        (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {role} IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {runtime_users}"
        ),
        (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {role} IN SCHEMA public "
            f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {runtime_users}"
        ),
        (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {role} IN SCHEMA public "
            f"REVOKE EXECUTE ON FUNCTIONS FROM {runtime_users}"
        ),
        (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {role} IN SCHEMA public "
            "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
        ),
        (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {role} IN SCHEMA public "
            f"REVOKE ALL ON TABLES FROM {erasure}"
        ),
        (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {role} IN SCHEMA public "
            f"REVOKE ALL ON SEQUENCES FROM {erasure}"
        ),
        f"ALTER ROLE {app} NOSUPERUSER NOBYPASSRLS NOINHERIT",
        f"ALTER ROLE {worker} NOSUPERUSER BYPASSRLS NOINHERIT",
        f"ALTER ROLE {epo_checkpoint} NOSUPERUSER NOBYPASSRLS NOINHERIT",
        f"ALTER ROLE {writer} NOSUPERUSER NOBYPASSRLS NOINHERIT",
        f"ALTER ROLE {erasure} NOSUPERUSER NOBYPASSRLS NOINHERIT",
        f"REVOKE {role} FROM {app}, {worker}, {writer}, {erasure}, {epo_checkpoint}",
        (
            "DO $$\n"
            "BEGIN\n"
            "  IF to_regclass('public.analysis_claimed_use_receipts') IS NOT NULL THEN\n"
            f"    REVOKE INSERT, UPDATE, DELETE ON "
            f"public.analysis_claimed_use_receipts FROM {app}, {worker}, {writer}, {erasure};\n"
            "  END IF;\n"
            "  IF to_regclass('public.epo_atomic_checkpoints') IS NOT NULL THEN\n"
            f"    REVOKE ALL ON public.epo_atomic_checkpoints "
            f"FROM {app}, {worker}, {writer}, {erasure};\n"
            f"    GRANT SELECT, INSERT, UPDATE ON public.epo_atomic_checkpoints "
            f"TO {epo_checkpoint};\n"
            "  END IF;\n"
            "  IF to_regclass('public.epo_atomic_checkpoint_history') IS NOT NULL THEN\n"
            f"    REVOKE ALL ON public.epo_atomic_checkpoint_history "
            f"FROM {app}, {worker}, {writer}, {erasure};\n"
            f"    GRANT SELECT, INSERT ON public.epo_atomic_checkpoint_history "
            f"TO {epo_checkpoint};\n"
            "  END IF;\n"
            "  IF to_regclass('public.claimed_use_erasure_authorizations') IS NOT NULL THEN\n"
            f"    REVOKE ALL ON public.claimed_use_erasure_authorizations "
            f"FROM {app}, {worker}, {writer}, {erasure};\n"
            "  END IF;\n"
            "  IF to_regclass('public.claimed_use_erasure_capabilities') IS NOT NULL THEN\n"
            f"    REVOKE ALL ON public.claimed_use_erasure_capabilities "
            f"FROM {app}, {worker}, {writer}, {erasure};\n"
            "  END IF;\n"
            "  IF to_regclass('public.audit_logs') IS NOT NULL THEN\n"
            f"    REVOKE UPDATE, DELETE ON public.audit_logs "
            f"FROM {app}, {worker}, {writer}, {erasure};\n"
            f"    REVOKE ALL ON public.audit_logs FROM {erasure};\n"
            f"    GRANT INSERT ON public.audit_logs TO {app}, {worker}, {writer};\n"
            "  END IF;\n"
            "  IF to_regclass('public.analyses') IS NOT NULL THEN\n"
            f"    GRANT SELECT ON public.analyses TO {writer};\n"
            f"    GRANT UPDATE (flagged_for_review, updated_at) "
            f"ON public.analyses TO {writer};\n"
            "  END IF;\n"
            "  IF to_regclass('public.analysis_review_statuses') IS NOT NULL THEN\n"
            f"    GRANT SELECT ON public.analysis_review_statuses TO {writer};\n"
            f"    GRANT UPDATE (status, note, reviewer_user_id, reviewer_name, "
            f"reviewer_email, reviewed_at, updated_at) "
            f"ON public.analysis_review_statuses TO {writer};\n"
            "  END IF;\n"
            "  IF to_regclass('public.analysis_claimed_use_receipts') IS NOT NULL THEN\n"
            f"    GRANT SELECT ON public.analysis_claimed_use_receipts TO {writer};\n"
            "  END IF;\n"
            "  IF to_regprocedure('public.issue_claimed_use_receipt(jsonb)') IS NOT NULL THEN\n"
            f"    ALTER FUNCTION public.issue_claimed_use_receipt(jsonb) OWNER TO {role};\n"
            f"    REVOKE ALL ON FUNCTION public.issue_claimed_use_receipt(jsonb) "
            f"FROM PUBLIC, {app}, {worker}, {erasure};\n"
            f"    GRANT EXECUTE ON FUNCTION public.issue_claimed_use_receipt(jsonb) TO {writer};\n"
            "  END IF;\n"
            "  IF to_regprocedure("
            "'public.revoke_claimed_use_receipt(uuid,uuid,uuid,text,timestamp with time zone)'"
            ") IS NOT NULL THEN\n"
            "    ALTER FUNCTION public.revoke_claimed_use_receipt("
            f"uuid, uuid, uuid, text, timestamptz) OWNER TO {role};\n"
            "    REVOKE ALL ON FUNCTION public.revoke_claimed_use_receipt("
            f"uuid, uuid, uuid, text, timestamptz) FROM PUBLIC, {app}, {worker}, {erasure};\n"
            "    GRANT EXECUTE ON FUNCTION public.revoke_claimed_use_receipt("
            f"uuid, uuid, uuid, text, timestamptz) TO {writer};\n"
            "  END IF;\n"
            "  IF to_regprocedure("
            "'public.authorize_claimed_use_erasure(uuid,uuid,uuid,text,uuid,text)'"
            ") IS NOT NULL THEN\n"
            "    ALTER FUNCTION public.authorize_claimed_use_erasure("
            f"uuid, uuid, uuid, text, uuid, text) OWNER TO {role};\n"
            "    REVOKE ALL ON FUNCTION public.authorize_claimed_use_erasure("
            f"uuid, uuid, uuid, text, uuid, text) FROM PUBLIC, {writer}, {erasure};\n"
            "    GRANT EXECUTE ON FUNCTION public.authorize_claimed_use_erasure("
            f"uuid, uuid, uuid, text, uuid, text) TO {app}, {worker};\n"
            "  END IF;\n"
            "  IF to_regprocedure("
            "'public.erase_claimed_use_receipts(uuid,uuid,uuid,uuid,text)'"
            ") IS NOT NULL THEN\n"
            "    ALTER FUNCTION public.erase_claimed_use_receipts("
            f"uuid, uuid, uuid, uuid, text) OWNER TO {role};\n"
            "    REVOKE ALL ON FUNCTION public.erase_claimed_use_receipts("
            f"uuid, uuid, uuid, uuid, text) FROM PUBLIC, {app}, {worker}, {writer};\n"
            "    GRANT EXECUTE ON FUNCTION public.erase_claimed_use_receipts("
            f"uuid, uuid, uuid, uuid, text) TO {erasure};\n"
            "  END IF;\n"
            "END\n"
            "$$"
        ),
    ]


def _ensure_praviar_pipeline_importable() -> None:
    """Make repo-local pipeline imports available for CLI commands."""
    praviar_pipeline_src = str(REPO_ROOT / "praviar_pipeline" / "src")
    if praviar_pipeline_src not in sys.path:
        sys.path.insert(0, praviar_pipeline_src)

    existing_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath_parts = existing_pythonpath.split(os.pathsep) if existing_pythonpath else []
    if praviar_pipeline_src not in pythonpath_parts:
        os.environ["PYTHONPATH"] = os.pathsep.join([praviar_pipeline_src, *pythonpath_parts])


STRIPE_RECEIPT_SENTINEL_CLERK_ORG_ID = "__stripe_receipt_sentinel__"


def _non_sentinel_organization_count_statement():
    """Count real tenant rows while ignoring the mandatory Stripe sentinel."""
    return (
        select(func.count())
        .select_from(Organization)
        .where(Organization.clerk_org_id != STRIPE_RECEIPT_SENTINEL_CLERK_ORG_ID)
    )


async def _seed_dev_db() -> int:
    settings = get_settings()
    if settings.app_env != "dev":
        print("Refusing to seed dev data unless APP_ENV=dev.", file=sys.stderr)
        return 2

    async with async_session_factory() as db:
        count = (await db.execute(_non_sentinel_organization_count_statement())).scalar_one()
        if count > 0:
            print("Database already contains organizations; skipping seed.")
            return 0

        org = Organization(
            clerk_org_id="dev_org_1",
            name="Development Lab",
            slug="dev-lab",
        )
        db.add(org)
        await db.flush()

        users = [
            User(
                clerk_user_id="dev_admin",
                org_id=org.id,
                email="admin@dev.local",
                full_name="Dev Admin",
                role=UserRole.ADMIN,
            ),
            User(
                clerk_user_id="dev_attorney",
                org_id=org.id,
                email="attorney@dev.local",
                full_name="Patent Attorney",
                role=UserRole.ATTORNEY,
            ),
            User(
                clerk_user_id="dev_scientist",
                org_id=org.id,
                email="scientist@dev.local",
                full_name="Research Scientist",
                role=UserRole.SCIENTIST,
            ),
            User(
                clerk_user_id="dev_client",
                org_id=org.id,
                email="client@dev.local",
                full_name="Client User",
                role=UserRole.CLIENT,
            ),
            # Required by the dev-token bypass in deps.py (DEV_CLERK_USER_ID = "dev_user_local")
            User(
                clerk_user_id="dev_user_local",
                org_id=org.id,
                email="dev@praviar.local",
                full_name="Praviar Dev User",
                role=UserRole.ADMIN,
            ),
        ]
        db.add_all(users)
        await db.commit()

    print(f"Seeded 1 organization and {len(users)} users.")
    return 0


def _cmd_seed_dev_db(_: argparse.Namespace) -> int:
    return asyncio.run(_seed_dev_db())


async def _seed_staging_user(
    clerk_org_id: str,
    org_name: str,
    org_slug: str,
    clerk_user_id: str,
    clerk_membership_id: str,
    user_email: str,
    user_full_name: str,
) -> int:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    if not db_url.startswith("postgresql+asyncpg"):
        db_url = "postgresql+asyncpg://" + db_url.split("://", 1)[1]

    engine = create_async_engine(db_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        existing_org = (
            await db.execute(select(Organization).where(Organization.clerk_org_id == clerk_org_id))
        ).scalar_one_or_none()
        if existing_org:
            org = existing_org
            print(f"ORG_EXISTS: {org.id}")
        else:
            org = Organization(
                clerk_org_id=clerk_org_id,
                name=org_name,
                slug=org_slug,
            )
            db.add(org)
            await db.flush()
            print(f"ORG_CREATED: {org.id}")

        existing_user = (
            await db.execute(
                select(User).where(
                    User.clerk_user_id == clerk_user_id,
                    User.org_id == org.id,
                )
            )
        ).scalar_one_or_none()
        if existing_user:
            if (
                existing_user.clerk_membership_id != clerk_membership_id
                or existing_user.clerk_membership_role != "admin"
                or existing_user.role != UserRole.ADMIN
                or not existing_user.membership_active
            ):
                print(
                    "ERROR: existing staging principal does not match the requested "
                    "active Clerk admin membership",
                    file=sys.stderr,
                )
                return 1
            print(f"USER_EXISTS: {existing_user.id}")
        else:
            user = User(
                clerk_user_id=clerk_user_id,
                clerk_membership_id=clerk_membership_id,
                clerk_membership_role="admin",
                org_id=org.id,
                email=user_email,
                full_name=user_full_name,
                role=UserRole.ADMIN,
                membership_active=True,
            )
            db.add(user)
            await db.flush()
            print(f"USER_CREATED: {user.id}")

        await db.commit()
    print("DONE")
    return 0


def _cmd_seed_staging_user(args: argparse.Namespace) -> int:
    return asyncio.run(
        _seed_staging_user(
            clerk_org_id=args.clerk_org_id,
            org_name=args.org_name,
            org_slug=args.org_slug,
            clerk_user_id=args.clerk_user_id,
            clerk_membership_id=args.clerk_membership_id,
            user_email=args.user_email,
            user_full_name=args.user_full_name,
        )
    )


async def _create_test_analysis(
    clerk_user_id: str,
    clerk_org_id: str,
    compound: str,
) -> int:
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from api.db.models import AnalysisStatus
    from api.db.models_analysis import Analysis

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    if not db_url.startswith("postgresql+asyncpg"):
        db_url = "postgresql+asyncpg://" + db_url.split("://", 1)[1]

    engine = create_async_engine(db_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        row = (
            await db.execute(
                select(User)
                .join(Organization, User.org_id == Organization.id)
                .where(
                    User.clerk_user_id == clerk_user_id,
                    Organization.clerk_org_id == clerk_org_id,
                    User.membership_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            print(f"ERROR: no user found with clerk_user_id={clerk_user_id}", file=sys.stderr)
            return 1
        user_id = row.id
        org_id = row.org_id
        print(f"USER_ID: {user_id}", flush=True)
        print(f"ORG_ID: {org_id}", flush=True)

        # RLS on analyses requires app.current_org_id to be set for the session
        await db.execute(select(func.set_config("app.current_org_id", str(org_id), True)))

        analysis = Analysis(
            id=_uuid.uuid4(),
            org_id=org_id,
            compound_input=compound,
            compound_name=compound,
            input_type="name",
            initiated_by=user_id,
            status=AnalysisStatus.PENDING,
        )
        db.add(analysis)
        await db.flush()
        await db.commit()
        print(f"ANALYSIS_ID: {analysis.id}", flush=True)
    print("DONE", flush=True)
    return 0


def _cmd_create_test_analysis(args: argparse.Namespace) -> int:
    return asyncio.run(
        _create_test_analysis(
            clerk_user_id=args.clerk_user_id,
            clerk_org_id=args.clerk_org_id,
            compound=args.compound,
        )
    )


async def _mark_analysis_failed(analysis_ids: list[str], reason: str) -> int:
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from api.db.models import AnalysisStatus
    from api.db.models_analysis import Analysis

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    if not db_url.startswith("postgresql+asyncpg"):
        db_url = "postgresql+asyncpg://" + db_url.split("://", 1)[1]

    engine = create_async_engine(db_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    updated = 0
    async with session_factory() as db:
        for analysis_id in analysis_ids:
            try:
                aid = _uuid.UUID(analysis_id)
            except ValueError:
                print(f"SKIP: {analysis_id!r} is not a valid UUID", file=sys.stderr)
                continue
            row = (
                await db.execute(select(Analysis).where(Analysis.id == aid))
            ).scalar_one_or_none()
            if row is None:
                print(f"NOT FOUND: {analysis_id}", file=sys.stderr)
                continue
            if row.status == AnalysisStatus.FAILED:
                print(f"ALREADY FAILED: {analysis_id}")
                continue
            prev_status = row.status.value
            row.status = AnalysisStatus.FAILED
            row.error_message = reason or "Manually marked failed via CLI"
            await db.flush()
            print(f"MARKED FAILED: {analysis_id} (was {prev_status})")
            updated += 1
        await db.commit()
    print(f"Done. Updated {updated} of {len(analysis_ids)} analyses.")
    return 0


def _cmd_mark_analysis_failed(args: argparse.Namespace) -> int:
    return asyncio.run(
        _mark_analysis_failed(
            analysis_ids=args.analysis_ids,
            reason=args.reason,
        )
    )


async def _bootstrap_db_roles(args: argparse.Namespace) -> int:
    app_env = os.environ.get("APP_ENV", "")
    if app_env in {"dev", "test"} and not args.allow_dev_test:
        print(
            "Refusing to bootstrap database roles in dev/test without --allow-dev-test.",
            file=sys.stderr,
        )
        return 2

    bootstrap_url = os.environ.get(args.bootstrap_url_env, "")
    if not bootstrap_url:
        print(f"{args.bootstrap_url_env} is required.", file=sys.stderr)
        return 2

    try:
        statements = _db_role_bootstrap_statements(
            app_user=args.app_user,
            worker_user=args.worker_user,
            migration_user=args.migration_user,
            migration_role=args.migration_role,
            epo_checkpoint_user=args.epo_checkpoint_user,
            claimed_use_writer_user=args.claimed_use_writer_user,
            global_erasure_user=args.global_erasure_user,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    engine = create_async_engine(bootstrap_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            for statement in _db_bootstrap_preamble(app_env):
                await connection.execute(text(statement))
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()

    print(
        "Bootstrapped database migration role and runtime grants for "
        f"{args.app_user}, {args.worker_user}, and {args.migration_user}."
    )
    return 0


def _db_bootstrap_preamble(app_env: str) -> tuple[str, ...]:
    """Return privileged, environment-specific database bootstrap statements."""
    if app_env != "prod":
        return ()
    # Terraform enables the Cloud SQL pgAudit flags, but Google explicitly
    # requires CREATE EXTENSION to be run by a database principal afterwards.
    return ("CREATE EXTENSION IF NOT EXISTS pgaudit",)


def _cmd_db_bootstrap_roles(args: argparse.Namespace) -> int:
    try:
        statements = _db_role_bootstrap_statements(
            app_user=args.app_user,
            worker_user=args.worker_user,
            migration_user=args.migration_user,
            migration_role=args.migration_role,
            epo_checkpoint_user=args.epo_checkpoint_user,
            claimed_use_writer_user=args.claimed_use_writer_user,
            global_erasure_user=args.global_erasure_user,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps({"statements": statements}, indent=2))
        return 0
    return asyncio.run(_bootstrap_db_roles(args))


def _cmd_export_openapi(args: argparse.Namespace) -> int:
    _ensure_praviar_pipeline_importable()

    from api.main import create_app

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    app = create_app()
    output_path.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    print(f"Wrote OpenAPI schema to {output_path}")
    return 0


def _normalize_generated_typescript(generated: str) -> str:
    """Remove generator-wide lint suppressions that hide contract regressions."""

    return generated.replace("/* eslint-disable */\n", "")


def _cmd_generate_shared_types(args: argparse.Namespace) -> int:
    # pydantic2ts ships as the `pydantic-to-typescript` package on PyPI;
    # the executable name is `pydantic2ts`. Look in the api venv first,
    # then fall back to PATH, since the CLI is typically invoked via
    # `cd api && PYTHONPATH=src python -m api.cli generate-shared-types`
    # which does not have the venv on PATH.
    api_venv_bin = Path(__file__).resolve().parents[2] / ".venv" / "bin"
    pydantic2ts = (
        str(api_venv_bin / "pydantic2ts")
        if (api_venv_bin / "pydantic2ts").exists()
        else shutil.which("pydantic2ts")
    )
    if not pydantic2ts:
        print(
            "pydantic2ts is required to generate shared types. "
            "Install it via `cd api && .venv/bin/pip install pydantic-to-typescript`.",
            file=sys.stderr,
        )
        return 1

    # json-schema-to-typescript (`json2ts`) lives under packages/shared-types/node_modules
    # — install it there with `pnpm add -D --filter @praviar/shared-types
    # json-schema-to-typescript`. We prefer the local node_modules binary
    # over `npx` because npx fails on offline dev machines and
    # introduces nondeterministic version drift.
    shared_types_bin = REPO_ROOT / "packages" / "shared-types" / "node_modules" / ".bin"
    json2ts_local = shared_types_bin / "json2ts"
    if json2ts_local.exists():
        json2ts_cmd = str(json2ts_local)
    elif shutil.which("npx"):
        json2ts_cmd = "npx -p json-schema-to-typescript json2ts"
    else:
        print(
            "json2ts (json-schema-to-typescript) not found. Install via "
            "`pnpm add -D --filter @praviar/shared-types json-schema-to-typescript`.",
            file=sys.stderr,
        )
        return 1

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    praviar_pipeline_src = REPO_ROOT / "praviar_pipeline" / "src"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{praviar_pipeline_src}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(praviar_pipeline_src)
    )

    subprocess.run(
        [
            pydantic2ts,
            "--module",
            "praviar_pipeline.models.shared_contracts",
            "--output",
            str(output_path),
            "--json2ts-cmd",
            json2ts_cmd,
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )

    generated = _normalize_generated_typescript(output_path.read_text(encoding="utf-8"))
    header = (
        "/**\n"
        " * AUTO-GENERATED FILE.\n"
        " *\n"
        " * Source of truth: praviar_pipeline.models.shared_contracts\n"
        " * Regenerate with: bash scripts/generate-types.sh\n"
        " */\n\n"
    )
    output_path.write_text(header + generated, encoding="utf-8")
    print(f"Wrote shared types to {output_path}")
    return 0


def _build_organization_compound_usage_rows(
    *,
    org_id: uuid.UUID,
    compounds: Sequence[Compound],
    first_analyzed_at: datetime,
) -> list[OrganizationCompound]:
    """Build organization-local usage rows for already-persisted seed compounds."""
    from api.db.models import OrganizationCompound

    rows: list[OrganizationCompound] = []
    for compound in compounds:
        if compound.id is None:
            raise ValueError("seed compound must be flushed before organization usage")
        rows.append(
            OrganizationCompound(
                org_id=org_id,
                compound_id=compound.id,
                display_name=compound.name,
                first_analyzed_at=first_analyzed_at,
                analysis_count=1,
            )
        )
    return rows


def _validate_demo_report_seed_contract(
    *,
    completed_reports: Sequence[tuple[str, dict]],
    intentionally_failed_reports: Sequence[tuple[str, dict]],
) -> None:
    """Apply the worker publishability invariant to dev seed lifecycle states."""
    from api.services.report_access import validate_report_publishability

    for label, report in completed_reports:
        try:
            validate_report_publishability(report)
        except ValueError as exc:
            raise ValueError(
                f"publishability validation failed for completed {label} seed: {exc}"
            ) from exc
    for label, report in intentionally_failed_reports:
        try:
            validate_report_publishability(report)
        except ValueError:
            continue
        raise ValueError(f"{label} negative fixture unexpectedly passed publishability validation")


def _build_demo_reviewer_decision(
    *,
    analysis: Analysis,
    attorney: User,
    report_data: dict,
) -> AnalysisReviewerDecision:
    """Build one current, attributable decision for the seeded blocked report."""
    from api.db.models import AnalysisReviewerDecision
    from api.services.report_access import report_payload_fingerprint, reviewable_finding_keys

    finding_key = ("patent", "WO1978000002A1")
    if finding_key not in reviewable_finding_keys(report_data):
        raise ValueError("seeded reviewer decision does not target a current report finding")
    return AnalysisReviewerDecision(
        analysis_id=analysis.id,
        org_id=analysis.org_id,
        finding_type=finding_key[0],
        finding_ref=finding_key[1],
        report_fingerprint=report_payload_fingerprint(report_data),
        decision="accept",
        note="Confirmed high risk; retaining the solid-form lane for counsel review.",
        reviewer_user_id=attorney.clerk_user_id,
        reviewer_name=attorney.full_name or "",
        reviewer_email=attorney.email,
    )


def _build_demo_monitor(
    *,
    analysis: Analysis,
    user: User,
    report_data: dict,
) -> Monitor:
    """Build the seeded monitor from the same governed report metadata as runtime."""
    from api.db.models import Monitor, MonitorSchedule
    from api.services.monitor_runtime import build_monitor_seed_from_report
    from api.services.report_access import normalize_report_trust_mode

    monitoring_strategy, watch_targets, target_jurisdictions, jurisdiction_bundle = (
        build_monitor_seed_from_report(
            report_data,
            schedule=MonitorSchedule.DAILY.value,
            compound_name=str((report_data.get("compound") or {}).get("name") or ""),
        )
    )
    report_compound = report_data.get("compound") or {}
    return Monitor(
        org_id=analysis.org_id,
        user_id=user.id,
        source_analysis_id=analysis.id,
        source_report_id=str(report_data["report_id"]),
        source_trust_mode=normalize_report_trust_mode(report_data),
        compound_smiles=str(report_compound.get("canonical_smiles") or ""),
        compound_name=str(report_compound.get("name") or ""),
        schedule=MonitorSchedule.DAILY,
        is_active=True,
        jurisdiction_bundle=jurisdiction_bundle,
        target_jurisdictions=target_jurisdictions,
        strategy_version=str(monitoring_strategy["version"]),
        monitoring_strategy=monitoring_strategy,
        watch_targets=watch_targets,
        last_run_status="pending",
        last_run_summary="Monitor created — awaiting first low-cost diff pass.",
    )


async def _seed_demo_analyses() -> int:
    from praviar_pipeline.models.report_document import FTOReport
    from praviar_pipeline.showcase_fixture import (
        load_showcase_fixture,
        showcase_fixture_receipt,
        showcase_publication_id,
    )

    from api.db.models import (
        Analysis,
        AnalysisStatus,
        Comment,
        Compound,
        Notification,
        NotificationType,
    )
    from api.fixtures.demo_reports import showcase_report

    settings = get_settings()
    if settings.app_env != "dev":
        print("Refusing to seed demo data unless APP_ENV=dev.", file=sys.stderr)
        return 2

    # Resolve org + users first; identity tables are not RLS-scoped.
    async with async_session_factory() as db:
        org = (
            await db.execute(select(Organization).where(Organization.slug == "dev-lab"))
        ).scalar_one_or_none()
        if org is None:
            print("Dev org not found. Run seed-dev-db first.", file=sys.stderr)
            return 1

        await bind_current_org_to_session(db, org.id)
        existing = (
            await db.execute(
                select(func.count()).select_from(Analysis).where(Analysis.org_id == org.id)
            )
        ).scalar_one()
        if existing > 0:
            print(f"Demo analyses already exist ({existing} rows); skipping.")
            return 0

        users = (await db.execute(select(User).where(User.org_id == org.id))).scalars().all()

    admin = next((u for u in users if u.clerk_user_id == "dev_user_local"), users[0])
    fixture = load_showcase_fixture()
    receipt = showcase_fixture_receipt()
    payload = fixture["payload"]
    report_dict = showcase_report()
    try:
        FTOReport.model_validate(report_dict)
    except Exception as exc:
        print(f"Showcase schema validation failed: {exc}", file=sys.stderr)
        return 1
    try:
        _validate_demo_report_seed_contract(
            completed_reports=((receipt["fixture_id"], report_dict),),
            intentionally_failed_reports=(),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    def _denorm(report_dict: dict) -> dict:
        rs = report_dict["risk_summary"]
        return {
            "overall_risk": rs["overall_risk"],
            "blocking_patents_count": rs.get("blocking_patents_count", 0),
            "total_patents_found": rs.get("total_patents_analyzed", 0),
            "executive_summary": rs.get("executive_summary", ""),
        }

    # Insert demo data with org RLS context bound.
    async with async_session_factory() as db:
        await bind_current_org_to_session(db, org.id)
        demo_completed_at = datetime.now(UTC)
        report_compound = report_dict["compound"]
        compound = payload["compound"]
        fictional_smiles = "[*:42]~[*:43]"

        completed = Analysis(
            org_id=org.id,
            compound_input=str(compound["submitted_identity"]),
            compound_name=str(compound["display_name"]),
            compound_smiles=fictional_smiles,
            input_type="name",
            config={"development_fixture": True, "showcase_fixture": receipt},
            status=AnalysisStatus.COMPLETED,
            completed_at=demo_completed_at,
            current_step=8,
            progress_pct=100.0,
            report_data=report_dict,
            initiated_by=admin.id,
            total_input_tokens=0,
            total_output_tokens=0,
            estimated_cost_usd=0.0,
            pipeline_duration_seconds=24 * 60,
            flagged_for_review=True,
            flagged_by=admin.id,
            **_denorm(report_dict),
        )
        running = Analysis(
            org_id=org.id,
            compound_input=str(compound["submitted_identity"]),
            compound_name=f"{compound['display_name']} — deterministic replay",
            compound_smiles=fictional_smiles,
            input_type="name",
            config={"development_fixture": True, "showcase_fixture": receipt},
            status=AnalysisStatus.RUNNING,
            current_step=4,
            progress_pct=50.0,
            initiated_by=admin.id,
        )
        failed = Analysis(
            org_id=org.id,
            compound_input=str(compound["submitted_identity"]),
            compound_name=f"{compound['display_name']} — partial-source example",
            compound_smiles=fictional_smiles,
            input_type="name",
            config={"development_fixture": True, "showcase_fixture": receipt},
            status=AnalysisStatus.FAILED,
            current_step=2,
            progress_pct=25.0,
            error_message=str(payload["failure_states"][0]["message"]),
            initiated_by=admin.id,
        )
        db.add_all([completed, running, failed])
        await db.flush()

        compound_row = Compound(
            canonical_smiles=fictional_smiles,
            inchi_key="FICTIONALPVXAB-DEMOFIXTUR-N",
            name=str(report_compound["name"]),
            molecular_formula="FICTIONAL",
            molecular_weight=None,
            pubchem_cid=None,
            analysis_count=1,
        )
        db.add(compound_row)
        await db.flush()
        db.add_all(
            _build_organization_compound_usage_rows(
                org_id=org.id,
                compounds=[compound_row],
                first_analyzed_at=demo_completed_at,
            )
        )

        db.add_all(
            [
                Comment(
                    analysis_id=completed.id,
                    org_id=org.id,
                    user_id=admin.id,
                    target_type="patent",
                    target_id=showcase_publication_id(),
                    body=str(payload["review"]["required_actions"][0]),
                ),
                Comment(
                    analysis_id=completed.id,
                    org_id=org.id,
                    user_id=admin.id,
                    target_type="analysis",
                    target_id=str(completed.id),
                    body=str(payload["review"]["required_actions"][1]),
                ),
            ]
        )
        db.add(
            Notification(
                user_id=admin.id,
                org_id=org.id,
                type=NotificationType.ANALYSIS_COMPLETE,
                title=f"{compound['display_name']} is ready for review",
                body=str(payload["disclaimer"]),
                data={"analysis_id": str(completed.id)},
            )
        )
        db.add(
            _build_demo_monitor(
                analysis=completed,
                user=admin,
                report_data=report_dict,
            )
        )

        await db.commit()

    print(
        "Seeded canonical fictional showcase: 3 analysis states, 1 compound, "
        "2 comments, 1 notification, and 1 monitor."
    )
    return 0


def _cmd_seed_demo_analyses(_: argparse.Namespace) -> int:
    return asyncio.run(_seed_demo_analyses())


def _cmd_run_pipeline_job(args: argparse.Namespace) -> int:
    """Execute one fenced pipeline reservation as a Cloud Run Job data plane."""
    analysis_id = str(args.analysis_id or "").strip()
    org_id = str(args.org_id or "").strip()
    execution_id = str(args.execution_id or "").strip()
    try:
        provider_retry_attempt = int(args.task_attempt)
        if provider_retry_attempt < 0:
            raise ValueError
    except (TypeError, ValueError):
        print("Cloud Run task attempt must be a non-negative integer.", file=sys.stderr)
        return 2
    try:
        uuid.UUID(analysis_id)
        uuid.UUID(org_id)
        uuid.UUID(execution_id)
    except ValueError:
        print(
            "analysis ID, organization ID, and execution ID must all be UUIDs.",
            file=sys.stderr,
        )
        return 2

    from api.workers.tasks import execute_fto_pipeline

    result = execute_fto_pipeline(
        analysis_id=analysis_id,
        org_id=org_id,
        execution_id=execution_id,
        provider_retry_attempt=provider_retry_attempt,
    )
    print(json.dumps(result, sort_keys=True))
    status_value = str(result.get("status") or "")
    if status_value in {
        "completed",
        "already_completed",
        "already_failed",
        "cancelled",
        "deleted",
        "stale_execution",
    }:
        return 0
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="praviar-api")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed-dev-db", help="Seed the local development database.")
    seed_parser.set_defaults(func=_cmd_seed_dev_db)

    staging_seed_parser = subparsers.add_parser(
        "seed-staging-user",
        help="Seed a real Clerk org and user into the staging database.",
    )
    staging_seed_parser.add_argument("--clerk-org-id", required=True)
    staging_seed_parser.add_argument("--org-name", required=True)
    staging_seed_parser.add_argument("--org-slug", required=True)
    staging_seed_parser.add_argument("--clerk-user-id", required=True)
    staging_seed_parser.add_argument("--clerk-membership-id", required=True)
    staging_seed_parser.add_argument("--user-email", required=True)
    staging_seed_parser.add_argument("--user-full-name", required=True)
    staging_seed_parser.set_defaults(func=_cmd_seed_staging_user)

    test_analysis_parser = subparsers.add_parser(
        "create-test-analysis",
        help="Create a test analysis record in the database and print its ID.",
    )
    test_analysis_parser.add_argument("--clerk-user-id", required=True)
    test_analysis_parser.add_argument("--clerk-org-id", required=True)
    test_analysis_parser.add_argument("--compound", required=True)
    test_analysis_parser.set_defaults(func=_cmd_create_test_analysis)

    demo_parser = subparsers.add_parser(
        "seed-demo-analyses",
        help="Populate the dev database from the canonical fictional showcase fixture.",
    )
    demo_parser.set_defaults(func=_cmd_seed_demo_analyses)

    bootstrap_parser = subparsers.add_parser(
        "db-bootstrap-roles",
        help="Create the Alembic migration role and runtime grants before migrations.",
    )
    bootstrap_parser.add_argument(
        "--app-user",
        default=os.environ.get("DB_APP_USER", "praviar_api"),
    )
    bootstrap_parser.add_argument(
        "--worker-user",
        default=os.environ.get("DB_WORKER_USER", "praviar_worker"),
    )
    bootstrap_parser.add_argument(
        "--migration-user",
        default=os.environ.get("DB_MIGRATION_USER", "praviar_migrator"),
    )
    bootstrap_parser.add_argument(
        "--migration-role",
        default=os.environ.get("DB_MIGRATION_ROLE", "alembic_runner"),
    )
    bootstrap_parser.add_argument(
        "--claimed-use-writer-user",
        default=os.environ.get(
            "DB_CLAIMED_USE_WRITER_USER",
            "praviar_claimed_use_writer",
        ),
    )
    bootstrap_parser.add_argument(
        "--epo-checkpoint-user",
        default=os.environ.get(
            "DB_EPO_CHECKPOINT_USER",
            "praviar_epo_checkpoint_writer",
        ),
    )
    bootstrap_parser.add_argument(
        "--global-erasure-user",
        default=os.environ.get(
            "DB_GLOBAL_ERASURE_USER",
            "praviar_global_erasure",
        ),
    )
    bootstrap_parser.add_argument("--bootstrap-url-env", default="BOOTSTRAP_DATABASE_URL")
    bootstrap_parser.add_argument("--allow-dev-test", action="store_true")
    bootstrap_parser.add_argument("--dry-run", action="store_true")
    bootstrap_parser.set_defaults(func=_cmd_db_bootstrap_roles)

    mark_failed_parser = subparsers.add_parser(
        "mark-analysis-failed",
        help="Force-fail one or more stuck analyses (e.g. zombie RUNNING rows).",
    )
    mark_failed_parser.add_argument(
        "analysis_ids",
        nargs="+",
        metavar="ANALYSIS_ID",
        help="UUID(s) of analyses to mark as FAILED",
    )
    mark_failed_parser.add_argument(
        "--reason",
        default="Manually marked failed via CLI",
        help="Error message to store on the analysis",
    )
    mark_failed_parser.set_defaults(func=_cmd_mark_analysis_failed)

    openapi_parser = subparsers.add_parser(
        "export-openapi", help="Export the current OpenAPI schema to JSON."
    )
    openapi_parser.add_argument("--output", default=str(DEFAULT_OPENAPI_OUTPUT))
    openapi_parser.set_defaults(func=_cmd_export_openapi)

    types_parser = subparsers.add_parser(
        "generate-shared-types",
        help="Generate TypeScript report types from the Praviar Pipeline report models.",
    )
    types_parser.add_argument("--output", default=str(DEFAULT_SHARED_TYPES_OUTPUT))
    types_parser.set_defaults(func=_cmd_generate_shared_types)

    pipeline_job_parser = subparsers.add_parser(
        "run-pipeline-job",
        help="Execute one persisted pipeline reservation inside a Cloud Run Job.",
    )
    pipeline_job_parser.add_argument(
        "--analysis-id",
        default=os.environ.get("PRAVIAR_PIPELINE_ANALYSIS_ID", ""),
    )
    pipeline_job_parser.add_argument(
        "--org-id",
        default=os.environ.get("PRAVIAR_PIPELINE_ORG_ID", ""),
    )
    pipeline_job_parser.add_argument(
        "--execution-id",
        default=os.environ.get("PRAVIAR_PIPELINE_EXECUTION_ID", ""),
    )
    pipeline_job_parser.add_argument(
        "--task-attempt",
        default=os.environ.get("CLOUD_RUN_TASK_ATTEMPT", "0"),
        help="Zero-based Cloud Run task attempt used to authorize fenced retry takeover.",
    )
    pipeline_job_parser.set_defaults(func=_cmd_run_pipeline_job)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
