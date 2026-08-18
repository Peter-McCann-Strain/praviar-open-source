"use client";

import {
  BellRing,
  CreditCard,
  KeyRound,
  Loader2,
  LockKeyhole,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";

type AccountControlSurface = "settings" | "notifications" | "billing";
type AccountControlVariant = "auth" | "loading" | "restricted" | "temporary";
type AccountControlTone = "default" | "warning" | "error";

interface AccountControlStatusStateProps {
  surface: AccountControlSurface;
  variant: AccountControlVariant;
  onRetry?: () => void;
}

interface AccountControlCopy {
  icon: LucideIcon;
  tone: AccountControlTone;
  aiBriefItems?: string[];
  eyebrow: string;
  title: string;
  description: string;
  contextItems: string[];
  recoveryTitle: string;
  recoveryBody: string;
}

const SURFACE_LABEL: Record<AccountControlSurface, string> = {
  settings: "API key settings",
  notifications: "notification preferences",
  billing: "billing controls",
};

const SURFACE_ICON: Record<AccountControlSurface, LucideIcon> = {
  settings: KeyRound,
  notifications: BellRing,
  billing: CreditCard,
};

const LOADING_DESCRIPTION: Record<AccountControlSurface, string> = {
  settings:
    "Retrieving API key status, integration controls, and security configuration for your organization.",
  notifications:
    "Retrieving email notification preferences, monitor alert delivery, and activity digest settings.",
  billing:
    "Retrieving subscription status, usage, plan limits, and invoice history for your organization.",
};

const TEMPORARY_TITLE: Record<AccountControlSurface, string> = {
  settings: "API key settings temporarily unavailable",
  notifications: "Notification preferences temporarily unavailable",
  billing: "Billing controls temporarily unavailable",
};

const TEMPORARY_AI_BRIEF: Record<AccountControlSurface, string[]> = {
  settings: [
    "Keep API keys and integration toggles read-only until the control view reloads.",
    "Retry only requests the latest organization-scoped settings snapshot.",
    "Ask an administrator to confirm role access if the state repeats.",
  ],
  notifications: [
    "Keep monitor alerts and digest preferences unchanged during recovery.",
    "Retry only refreshes notification settings for the active organization.",
    "Use existing alert delivery records as the source of truth until reload.",
  ],
  billing: [
    "Keep plan, invoice, and Report Credit records unchanged during recovery.",
    "Retry only requests the latest billing control snapshot.",
    "Use existing receipts or exported invoices until billing controls reload.",
  ],
};

function getAccountControlCopy(
  surface: AccountControlSurface,
  variant: AccountControlVariant,
): AccountControlCopy {
  const label = SURFACE_LABEL[surface];

  if (variant === "auth") {
    return {
      icon: LockKeyhole,
      tone: "default",
      eyebrow: "Control access",
      title: `Checking ${label} access`,
      description:
        "Confirming your team-scoped session before Praviar requests private control-plane records.",
      contextItems: [
        "Session check in progress",
        "No control data exposed",
        "Actions unlock after access",
      ],
      recoveryTitle: "Preparing a governed control view",
      recoveryBody:
        "Praviar only requests organization-scoped settings after an authenticated workspace token is available.",
    };
  }

  if (variant === "loading") {
    return {
      icon: Loader2,
      tone: "default",
      eyebrow: "Control workspace",
      title: `Loading ${label}`,
      description: LOADING_DESCRIPTION[surface],
      contextItems: [
        "Private controls requested",
        "Existing settings unchanged",
        "Actions wait for a fresh view",
      ],
      recoveryTitle: "Opening the current control state",
      recoveryBody:
        "Create, revoke, subscription, and preference actions remain unavailable until the latest control state is loaded.",
    };
  }

  if (variant === "restricted") {
    return {
      icon: TriangleAlert,
      tone: "warning",
      eyebrow: "Control access",
      title:
        surface === "billing"
          ? "Billing access restricted"
          : `${capitalizeFirst(label)} restricted`,
      description:
        "This control area is limited to organization administrators. No settings or billing records have been changed.",
      contextItems: [
        "Admin access required",
        "No changes applied",
        "Private records withheld",
      ],
      recoveryTitle: "Use an administrator account",
      recoveryBody:
        "Ask an organization administrator to review this control area or update your role before making changes.",
    };
  }

  return {
    icon: SURFACE_ICON[surface],
    tone: "error",
    aiBriefItems: TEMPORARY_AI_BRIEF[surface],
    eyebrow: "Control load",
    title: TEMPORARY_TITLE[surface],
    description:
      "The service did not return a usable control view. Existing settings, subscriptions, and delivery preferences are unchanged.",
    contextItems: [
      "No settings changed",
      "Retry requests a fresh view",
      "Private records withheld",
    ],
    recoveryTitle: "Retry the control request",
    recoveryBody:
      "A retry asks for the latest organization-scoped control state without creating, revoking, upgrading, or saving anything.",
  };
}

export function AccountControlStatusState({
  surface,
  variant,
  onRetry,
}: AccountControlStatusStateProps) {
  const copy = getAccountControlCopy(surface, variant);
  const Icon = copy.icon;
  const titleId = `${surface}-account-control-${variant}-title`;
  const isPending = variant === "auth" || variant === "loading";

  return (
    <OperationalStatusFrame
      actionLabel="Retry control load"
      contextItems={copy.contextItems}
      dataTestId={`${surface}-account-control-${variant}`}
      description={copy.description}
      eyebrow={copy.eyebrow}
      icon={Icon}
      aiBrief={
        copy.aiBriefItems
          ? {
              items: copy.aiBriefItems,
              note: "No purchase, revoke, or preference update is submitted from this recovery state.",
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
