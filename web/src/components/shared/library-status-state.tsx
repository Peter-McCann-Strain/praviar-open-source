"use client";

import {
  DatabaseZap,
  LibraryBig,
  Loader2,
  LockKeyhole,
  SearchCheck,
  type LucideIcon,
} from "lucide-react";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";

type LibraryStatusVariant = "auth" | "loading" | "restricted" | "temporary";
type LibraryStatusSurface = "patents" | "compounds";
type LibraryStatusTone = "default" | "error";

interface LibraryStatusStateProps {
  surface: LibraryStatusSurface;
  variant: LibraryStatusVariant;
  onRetry?: () => void;
}

interface LibraryStatusCopy {
  icon: LucideIcon;
  tone: LibraryStatusTone;
  aiBriefItems?: string[];
  eyebrow: string;
  title: string;
  description: string;
  contextItems: string[];
  recoveryTitle: string;
  recoveryBody: string;
}

const SURFACE_LABEL: Record<LibraryStatusSurface, string> = {
  patents: "patent evidence library",
  compounds: "compound library",
};

const SURFACE_ICON: Record<LibraryStatusSurface, LucideIcon> = {
  patents: SearchCheck,
  compounds: LibraryBig,
};

const TEMPORARY_AI_BRIEF: Record<LibraryStatusSurface, string[]> = {
  patents: [
    "Keep patent filters and report links unchanged while the index reloads.",
    "Retry only requests the latest organization-scoped patent evidence snapshot.",
    "Use exported reports or saved packets as temporary counsel references.",
  ],
  compounds: [
    "Keep compound identities and analysis counts unchanged while the index reloads.",
    "Retry only requests the latest organization-scoped compound library snapshot.",
    "Start a new FTO analysis only after the library index confirms current state.",
  ],
};

function getLibraryStatusCopy(
  surface: LibraryStatusSurface,
  variant: LibraryStatusVariant,
): LibraryStatusCopy {
  const label = SURFACE_LABEL[surface];
  const SurfaceIcon = SURFACE_ICON[surface];

  if (variant === "auth") {
    return {
      icon: LockKeyhole,
      tone: "default",
      eyebrow: "Library access",
      title: `Checking ${label} access`,
      description:
        "Confirming your team-scoped session before Praviar requests private evidence indexes.",
      contextItems: [
        "Session check in progress",
        "No library data exposed",
        "Filters open after access",
      ],
      recoveryTitle: "Preparing a private evidence index",
      recoveryBody:
        "Praviar only requests organization-scoped library records after an authenticated workspace token is available.",
    };
  }

  if (variant === "loading") {
    return {
      icon: Loader2,
      tone: "default",
      eyebrow: "Library workspace",
      title: `Loading ${label}`,
      description:
        surface === "patents"
          ? "Retrieving patent identifiers, assignees, risk tags, and report links from your FTO analyses."
          : "Retrieving compound identities, analysis counts, molecular details, and library search state.",
      contextItems: [
        "Evidence index requested",
        "Private records gated",
        "Search and filters wait",
      ],
      recoveryTitle: "Opening a governed library view",
      recoveryBody:
        "Search, filter, report, and detail controls remain unavailable until the library index is loaded.",
    };
  }

  if (variant === "restricted") {
    return {
      icon: LockKeyhole,
      tone: "error",
      eyebrow: "Library access",
      title: `${capitalizeFirst(label)} access restricted`,
      description:
        "Your current session is not authorized to view this organization-scoped library. Cached records are hidden until access is confirmed again.",
      contextItems: [
        "Cached records hidden",
        "No private data exposed",
        "Retry after access changes",
      ],
      recoveryTitle: "Confirm library access",
      recoveryBody:
        "A retry requests a fresh authorization check before any evidence records are shown.",
    };
  }

  return {
    icon: SurfaceIcon ?? DatabaseZap,
    tone: "error",
    aiBriefItems: TEMPORARY_AI_BRIEF[surface],
    eyebrow: "Library load",
    title: `${capitalizeFirst(label)} temporarily unavailable`,
    description:
      "The library service did not return a usable workspace. Existing analyses, reports, and review records are unchanged.",
    contextItems: [
      "No library data changed",
      "Retry requests a fresh view",
      "Private records withheld",
    ],
    recoveryTitle: "Retry the library request",
    recoveryBody:
      "A retry asks for the latest organization-scoped index without changing any analysis or report data.",
  };
}

export function LibraryStatusState({
  surface,
  variant,
  onRetry,
}: LibraryStatusStateProps) {
  const copy = getLibraryStatusCopy(surface, variant);
  const Icon = copy.icon;
  const titleId = `${surface}-library-status-${variant}-title`;
  const isPending = variant === "auth" || variant === "loading";

  return (
    <OperationalStatusFrame
      actionLabel="Retry library load"
      contextItems={copy.contextItems}
      dataTestId={`${surface}-library-status-${variant}`}
      description={copy.description}
      eyebrow={copy.eyebrow}
      icon={Icon}
      aiBrief={
        copy.aiBriefItems
          ? {
              items: copy.aiBriefItems,
              note: "No analysis, report, or library record is changed from this recovery state.",
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
