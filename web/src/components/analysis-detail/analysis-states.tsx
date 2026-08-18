"use client";

import Link from "next/link";
import {
  AlertTriangle,
  FileSearch,
  Loader2,
  LockKeyhole,
  type LucideIcon,
} from "lucide-react";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";
import { Button } from "@/components/ui/button";

type AnalysisStateVariant = "auth" | "loading" | "temporary" | "unavailable";
type AnalysisStateTone = "default" | "warning" | "error";

interface AnalysisStateCopy {
  icon: LucideIcon;
  tone: AnalysisStateTone;
  eyebrow: string;
  title: string;
  description: string;
  contextItems: string[];
  recoveryTitle: string;
  recoveryBody: string;
}

const ANALYSIS_STATE_COPY: Record<AnalysisStateVariant, AnalysisStateCopy> = {
  auth: {
    icon: LockKeyhole,
    tone: "default",
    eyebrow: "Analysis access",
    title: "Checking analysis access",
    description:
      "Confirming your team-scoped session before any compound, pipeline, or report evidence is shown.",
    contextItems: [
      "Session check in progress",
      "No analysis data exposed",
      "Actions open after access",
    ],
    recoveryTitle: "Preparing a private analysis workspace",
    recoveryBody:
      "Praviar requests private analysis data only after an authenticated workspace token is available.",
  },
  loading: {
    icon: Loader2,
    tone: "default",
    eyebrow: "Analysis workspace",
    title: "Loading analysis workspace",
    description:
      "Retrieving compound summary, pipeline progress, source counts, and review handoff state for this analysis.",
    contextItems: [
      "Pipeline status requested",
      "Compound details gated",
      "Report actions wait",
    ],
    recoveryTitle: "Opening a governed view",
    recoveryBody:
      "Risk, patent, export, and report controls remain unavailable until the analysis record is loaded.",
  },
  temporary: {
    icon: AlertTriangle,
    tone: "error",
    eyebrow: "Analysis load",
    title: "Analysis temporarily unavailable",
    description:
      "The analysis service did not return a usable workspace. No pipeline data, report content, or reviewer decisions were changed.",
    contextItems: [
      "No analysis data changed",
      "Retry requests a fresh view",
      "Private details withheld",
    ],
    recoveryTitle: "Retry the analysis request",
    recoveryBody:
      "A retry asks for the latest workspace state without changing the underlying analysis.",
  },
  unavailable: {
    icon: FileSearch,
    tone: "warning",
    eyebrow: "Analysis lookup",
    title: "Analysis unavailable in this workspace",
    description:
      "We could not open an analysis for your current team. It may belong to another organization, no longer be present, or the link may be incomplete.",
    contextItems: [
      "Team-scoped access",
      "No analysis data exposed",
      "Return to analysis library",
    ],
    recoveryTitle: "Open the analysis library",
    recoveryBody:
      "Use the library to confirm which FTO packets are available to your organization.",
  },
};

interface AnalysisStateShellProps {
  variant: AnalysisStateVariant;
  onRetry?: () => void;
}

function AnalysisStateShell({ variant, onRetry }: AnalysisStateShellProps) {
  const copy = ANALYSIS_STATE_COPY[variant];
  const titleId = `analysis-state-${variant}-title`;
  const isPending = variant === "auth" || variant === "loading";

  return (
    <OperationalStatusFrame
      actionLabel="Retry analysis load"
      className="mx-auto w-full max-w-[90rem]"
      contextItems={copy.contextItems}
      dataTestId={`analysis-state-${variant}`}
      description={copy.description}
      eyebrow={copy.eyebrow}
      headingLevel={1}
      icon={copy.icon}
      isLoading={variant === "loading"}
      isPending={isPending}
      onRetry={onRetry}
      recoveryBody={copy.recoveryBody}
      recoveryTitle={copy.recoveryTitle}
      secondaryAction={
        <Button variant="outline" className="min-h-11 w-full sm:w-auto" asChild>
          <Link href="/analyses">Back to Analyses</Link>
        </Button>
      }
      title={copy.title}
      titleId={titleId}
      tone={copy.tone}
    />
  );
}

export function AnalysisAuthState() {
  return <AnalysisStateShell variant="auth" />;
}

export function AnalysisErrorState({ onRetry }: { onRetry: () => void }) {
  return <AnalysisStateShell variant="temporary" onRetry={onRetry} />;
}

export function AnalysisLoadingState() {
  return <AnalysisStateShell variant="loading" />;
}

export function AnalysisNotFoundState() {
  return <AnalysisStateShell variant="unavailable" />;
}
