"use client";

import {
  BellRing,
  Layers,
  Loader2,
  LockKeyhole,
  type LucideIcon,
} from "lucide-react";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";

type WorkspaceStatusVariant = "auth" | "loading" | "restricted" | "temporary";
type WorkspaceStatusSurface = "batch" | "monitors";
type WorkspaceStatusTone = "default" | "error";

interface WorkspaceStatusStateProps {
  surface: WorkspaceStatusSurface;
  variant: WorkspaceStatusVariant;
  onRetry?: () => void;
}

interface WorkspaceStatusCopy {
  icon: LucideIcon;
  tone: WorkspaceStatusTone;
  aiBriefItems?: string[];
  eyebrow: string;
  title: string;
  description: string;
  contextItems: string[];
  recoveryTitle: string;
  recoveryBody: string;
}

const SURFACE_LABEL: Record<WorkspaceStatusSurface, string> = {
  batch: "diligence portfolio workspace",
  monitors: "patent monitoring workspace",
};

const SURFACE_ICON: Record<WorkspaceStatusSurface, LucideIcon> = {
  batch: Layers,
  monitors: BellRing,
};

const LOADING_DESCRIPTION: Record<WorkspaceStatusSurface, string> = {
  batch:
    "Retrieving batch jobs, compound run progress, report links, and portfolio completion status.",
  monitors:
    "Retrieving monitor schedules, alert posture, watch targets, and latest patent-change status.",
};

const TEMPORARY_TITLE: Record<WorkspaceStatusSurface, string> = {
  batch: "Diligence portfolio temporarily unavailable",
  monitors: "Patent monitoring temporarily unavailable",
};

const TEMPORARY_AI_BRIEF: Record<WorkspaceStatusSurface, string[]> = {
  batch: [
    "Keep batch jobs and report handoffs unchanged while the workspace reloads.",
    "Retry only requests the latest organization-scoped portfolio state.",
    "Use previously exported packet links for counsel review until live status returns.",
  ],
  monitors: [
    "Keep monitor schedules and watch targets unchanged while the workspace reloads.",
    "Retry only requests the latest alert and patent-change state.",
    "Use the last delivered alert digest as the temporary review reference.",
  ],
};

function getWorkspaceStatusCopy(
  surface: WorkspaceStatusSurface,
  variant: WorkspaceStatusVariant,
): WorkspaceStatusCopy {
  const label = SURFACE_LABEL[surface];

  if (variant === "auth") {
    return {
      icon: LockKeyhole,
      tone: "default",
      eyebrow: "Workspace access",
      title: `Checking ${label} access`,
      description:
        "Confirming your team-scoped session before Praviar requests private operational records.",
      contextItems: [
        "Session check in progress",
        "No workspace records exposed",
        "Controls unlock after access",
      ],
      recoveryTitle: "Preparing a governed workspace view",
      recoveryBody:
        "Praviar only requests organization-scoped operating data after an authenticated workspace token is available.",
    };
  }

  if (variant === "loading") {
    return {
      icon: Loader2,
      tone: "default",
      eyebrow: "Operational workspace",
      title: `Loading ${label}`,
      description: LOADING_DESCRIPTION[surface],
      contextItems: [
        "Private workspace requested",
        "Run state remains unchanged",
        "Actions wait for a fresh view",
      ],
      recoveryTitle: "Opening the current operating view",
      recoveryBody:
        "Create, pause, cancel, and review controls remain unavailable until the latest workspace state is loaded.",
    };
  }

  if (variant === "restricted") {
    return {
      icon: LockKeyhole,
      tone: "error",
      eyebrow: "Workspace access",
      title: `${capitalizeFirst(label)} access restricted`,
      description:
        "Your current session is not authorized to view this organization-scoped workspace. Cached records are hidden until access is confirmed again.",
      contextItems: [
        "Cached records hidden",
        "No workspace data exposed",
        "Retry after access changes",
      ],
      recoveryTitle: "Confirm workspace access",
      recoveryBody:
        "A retry requests a fresh authorization check before any operating records are shown.",
    };
  }

  return {
    icon: SURFACE_ICON[surface],
    tone: "error",
    aiBriefItems: TEMPORARY_AI_BRIEF[surface],
    eyebrow: "Workspace load",
    title: TEMPORARY_TITLE[surface],
    description:
      "The service did not return a usable workspace view. Existing analyses, monitors, reports, and review records are unchanged.",
    contextItems: [
      "No operating data changed",
      "Retry requests a fresh view",
      "Private records withheld",
    ],
    recoveryTitle: "Retry the workspace request",
    recoveryBody:
      "A retry asks for the latest organization-scoped workspace state without changing any batch job, monitor, or report data.",
  };
}

export function WorkspaceStatusState({
  surface,
  variant,
  onRetry,
}: WorkspaceStatusStateProps) {
  const copy = getWorkspaceStatusCopy(surface, variant);
  const Icon = copy.icon;
  const titleId = `${surface}-workspace-status-${variant}-title`;
  const isPending = variant === "auth" || variant === "loading";

  return (
    <OperationalStatusFrame
      actionLabel="Retry workspace load"
      contextItems={copy.contextItems}
      dataTestId={`${surface}-workspace-status-${variant}`}
      description={copy.description}
      eyebrow={copy.eyebrow}
      icon={Icon}
      aiBrief={
        copy.aiBriefItems
          ? {
              items: copy.aiBriefItems,
              note: "No batch, monitor, report, or reviewer record is changed from this recovery state.",
            }
          : undefined
      }
      isLoading={variant === "loading"}
      isPending={isPending}
      onRetry={onRetry}
      recoveryBody={copy.recoveryBody}
      recoveryTitle={copy.recoveryTitle}
      title={copy.title}
      titleId={titleId}
      tone={copy.tone}
    />
  );
}

function capitalizeFirst(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
