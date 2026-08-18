"""Server-owned export branding helpers."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from api.db.models import Organization


def branding_config_from_org_settings(settings: Mapping | None):
    """Return validated export branding from an organization's settings."""
    if not settings:
        return None

    raw_branding = settings.get("export_branding")
    if raw_branding is None:
        return None
    if not isinstance(raw_branding, Mapping):
        raise RuntimeError("Organization export_branding setting must be an object")
    if raw_branding.get("enabled") is False:
        return None

    from praviar_pipeline.rendering.branding import BrandingConfig

    branding_payload = {k: v for k, v in raw_branding.items() if k != "enabled"}
    if branding_payload.get("logo_path"):
        raise RuntimeError(
            "Organization export_branding.logo_path is not supported until "
            "tenant-scoped logo uploads are enabled"
        )
    return BrandingConfig.model_validate(branding_payload)


async def load_export_branding_for_org(db: AsyncSession, *, org_id: uuid.UUID):
    """Load a validated branding snapshot for async route rendering."""
    result = await db.execute(select(Organization.settings).where(Organization.id == org_id))
    settings = result.scalar_one_or_none()
    if settings is not None and not isinstance(settings, Mapping):
        raise RuntimeError("Organization settings must be an object")
    return branding_config_from_org_settings(settings)


def load_export_branding_for_org_sync(
    db: Session,
    organization_model,
    *,
    org_id,
):
    """Load a validated branding snapshot for sync worker rendering."""
    org = db.get(organization_model, org_id)
    if org is None:
        return None
    settings = getattr(org, "settings", None)
    if settings is not None and not isinstance(settings, Mapping):
        raise RuntimeError("Organization settings must be an object")
    return branding_config_from_org_settings(settings)
