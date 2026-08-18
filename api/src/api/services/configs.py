"""Business logic for configuration presets and org defaults."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.db.models import ConfigPreset, Organization, UserRole
from api.errors import APIError
from api.schemas.configs import CreatePresetRequest, SetOrgDefaultsRequest

logger = structlog.get_logger()

_RETIRED_PUBLIC_CONFIG_KEYS = {
    "claude_deep_model",
    "claude_triage_model",
    "pipeline_mode",
    "claim_analysis_depth",
    "report_pipeline_v2",
}


def org_default_config_from_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract the persisted analysis default config from org settings."""
    if not settings:
        return {}

    default_config = settings.get("default_config")
    if default_config is None:
        return {}
    if not isinstance(default_config, Mapping):
        raise APIError(
            500,
            "Internal Server Error",
            "Organization default config is not a valid object",
        )
    config = dict(default_config)
    retired_keys = sorted(set(config) & _RETIRED_PUBLIC_CONFIG_KEYS)
    if retired_keys:
        for k in retired_keys:
            del config[k]
    return config


async def load_org_default_config(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> dict[str, Any]:
    result = await db.execute(select(Organization.settings).where(Organization.id == org_id))
    settings = result.scalar_one_or_none()
    return org_default_config_from_settings(settings)


def _ensure_config_management_access(*, user_role: UserRole, action: str) -> None:
    if user_role not in (UserRole.ADMIN, UserRole.ATTORNEY):
        event = "create_preset_forbidden" if action == "create_preset" else "set_defaults_forbidden"
        logger.warning(
            event,
            role=user_role.value,
        )
        if action == "create_preset":
            raise APIError(
                403,
                "Forbidden",
                "Only an attorney or organization administrator can manage presets",
            )
        raise APIError(
            403,
            "Forbidden",
            "Only an attorney or organization administrator can set defaults",
        )


async def list_presets_for_org(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> list[ConfigPreset]:
    result = await db.execute(select(ConfigPreset).where(ConfigPreset.org_id == org_id))
    return list(result.scalars().all())


async def create_preset(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: UserRole,
    body: CreatePresetRequest,
    request: Request | None = None,
) -> ConfigPreset:
    _ensure_config_management_access(user_role=user_role, action="create_preset")

    if body.is_default:
        result = await db.execute(
            select(ConfigPreset).where(
                ConfigPreset.org_id == org_id,
                ConfigPreset.is_default.is_(True),
            )
        )
        for preset in result.scalars().all():
            preset.is_default = False

    preset = ConfigPreset(
        org_id=org_id,
        created_by=user_id,
        name=body.name,
        description=body.description,
        config=body.config.model_dump(),
        is_default=body.is_default,
    )
    db.add(preset)
    try:
        await db.flush()
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="config_preset.created",
            details={
                "preset_id": str(preset.id),
                "name": body.name,
                "is_default": body.is_default,
                "config_keys": sorted(body.config.model_dump(exclude_none=True).keys()),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except IntegrityError:
        # The "clear existing defaults, then insert is_default=True" sequence is
        # not atomic against a concurrent create under READ COMMITTED: two
        # simultaneous is_default=True creates each clear the (currently visible)
        # defaults and then both insert, so the second commit violates the
        # uq_config_presets_org_one_default partial unique index. Surface that as
        # a ret-able 409 instead of an opaque 500, matching the conflict handling
        # used for other partial-unique creates (e.g. analysis_review_status).
        await db.rollback()
        logger.warning(
            "create_preset_default_conflict",
            user_id=str(user_id),
            org_id=str(org_id),
        )
        raise APIError(
            409,
            "Conflict",
            "Another default preset was created concurrently. Please retry.",
        ) from None
    except Exception:
        await db.rollback()
        raise
    logger.info("create_preset", name=body.name, user_id=str(user_id), org_id=str(org_id))
    return preset


async def set_org_default_config(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: UserRole,
    body: SetOrgDefaultsRequest,
    request: Request | None = None,
) -> None:
    _ensure_config_management_access(user_role=user_role, action="set_defaults")

    result = await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    org = result.scalar_one_or_none()
    if not org:
        raise APIError(404, "Not Found", "Organization not found")

    config = body.normalized_config()
    org.settings = {**(org.settings or {}), "default_config": config}
    try:
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="org.default_config.updated",
            details={
                "config_keys": sorted(config.keys()),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info("set_org_defaults", user_id=str(user_id), org_id=str(org_id))
