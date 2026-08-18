"""Shared SQLAlchemy declarative base and persisted enum contracts."""

from __future__ import annotations

import enum

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class OrgPlan(enum.StrEnum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    ATTORNEY = "attorney"
    SCIENTIST = "scientist"
    CLIENT = "client"


class AnalysisStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELETED = "deleted"


class ExportFormat(enum.StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    CSV = "csv"
    JSON = "json"
    PPTX = "pptx"


class MonitorSchedule(enum.StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ExportStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class NotificationType(enum.StrEnum):
    ANALYSIS_COMPLETE = "analysis_complete"
    MONITOR_ALERT = "monitor_alert"
    EXPORT_READY = "export_ready"
    TEAM_INVITE = "team_invite"
    BILLING_EVENT = "billing_event"
    SYSTEM = "system"


class ReviewStatus(enum.StrEnum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
