"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { ChevronDown, LockKeyhole, Sparkles } from "lucide-react";
import { isAuthBoundaryError } from "@/lib/api-client";
import { AiCommandPanel } from "@/components/dashboard/ai-command-panel";
import { DashboardPageHeader } from "@/components/dashboard/page-header";
import { EmptyDashboard } from "@/components/dashboard/empty-dashboard";
import { ExecutiveDecisionBrief } from "@/components/dashboard/executive-decision-brief";
import {
  buildDashboardMetrics,
  TOUR_STEPS,
} from "@/components/dashboard/helpers";
import { LegalReviewWorkloadPanel } from "@/components/dashboard/legal-review-workload-panel";
import { RiskActivitySection } from "@/components/dashboard/risk-activity-section";
import { RunningPipelinesAlert } from "@/components/dashboard/running-pipelines-alert";
import { SetupReadinessPanel } from "@/components/dashboard/setup-readiness-panel";
import { AppErrorState } from "@/components/shared/app-error-state";
import { OnboardingTooltip } from "@/components/shared/onboarding-tooltip";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useAnalyses } from "@/hooks/use-analysis";
import { useBillingStatus } from "@/hooks/use-billing";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import DashboardLoading from "./loading";

const DASHBOARD_ANALYSES_LIMIT = 100;

function DashboardSecondaryDisclosure({
  children,
  description,
  testId,
  title,
}: {
  children: ReactNode;
  description: string;
  testId: string;
  title: string;
}) {
  return (
    <ResponsiveDisclosure
      className="group min-w-0 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] sm:overflow-visible sm:rounded-none sm:border-0 sm:bg-transparent"
      data-testid={testId}
      summary={
        <summary className="flex min-h-16 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-left marker:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-primary/70 sm:hidden [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </span>
            <span className="mt-0.5 line-clamp-2 block text-xs leading-5 text-[var(--text-secondary)]">
              {description}
            </span>
          </span>
          <ChevronDown
            className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180 motion-reduce:transition-none"
            aria-hidden="true"
          />
        </summary>
      }
    >
      <div className="border-t border-[var(--border-subtle)] p-3 sm:border-0 sm:p-0">
        {children}
      </div>
    </ResponsiveDisclosure>
  );
}

export default function DashboardPage() {
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
  const token = useAuthToken();
  const {
    data: apiData,
    isLoading,
    isError,
    error,
    refetch,
  } = useAnalyses(token, 1, DASHBOARD_ANALYSES_LIMIT);
  const billingStatusQuery = useBillingStatus(token);
  const allAnalyses = apiData?.items ?? [];
  const workspaceAnalysisCount = apiData?.total ?? allAnalyses.length;
  const isAuthMissing = !DEMO_MODE_ENABLED && !token;
  const accessRestricted = isError && isAuthBoundaryError(error);
  const billingAccessRestricted = isAuthBoundaryError(billingStatusQuery.error);

  if (!mounted || isAuthMissing) {
    return (
      <div className="space-y-6 animate-fade-up">
        <DashboardPageHeader showAction={false} />
        <OperationalStatusFrame
          contextItems={[
            "Session check in progress",
            "No dashboard metrics exposed yet",
            "Workspace opens after access is confirmed",
          ]}
          dataTestId="dashboard-access-auth"
          description="Confirming your team-scoped session before Praviar requests private dashboard activity, review, and risk records."
          eyebrow="Workspace access"
          icon={LockKeyhole}
          isPending
          recoveryBody="Praviar waits for an authenticated workspace token before loading organization-scoped metrics, so pending sessions do not flash empty or cross-tenant data."
          recoveryTitle="Preparing a governed dashboard view"
          title="Checking dashboard access"
          titleId="dashboard-access-auth-title"
          tone="default"
        />
      </div>
    );
  }

  if (accessRestricted) {
    return (
      <div className="space-y-6 animate-fade-up">
        <DashboardPageHeader showAction={false} />
        <OperationalStatusFrame
          contextItems={[
            "Cached metrics hidden",
            "No dashboard records exposed",
            "Retry after access changes",
          ]}
          dataTestId="dashboard-access-restricted"
          description="Your current session is not authorized to view this organization-scoped dashboard. Cached metrics stay hidden until access is confirmed again."
          eyebrow="Workspace access"
          icon={LockKeyhole}
          isPending={false}
          onRetry={() => {
            void refetch();
          }}
          recoveryBody="A retry requests a fresh authorization check before any dashboard metrics, review workload, or risk activity are shown."
          recoveryTitle="Confirm dashboard access"
          title="Dashboard access restricted"
          titleId="dashboard-access-restricted-title"
          tone="error"
        />
      </div>
    );
  }

  if (isLoading) {
    return <DashboardLoading />;
  }

  if (isError) {
    return (
      <div className="space-y-6 animate-fade-up">
        <DashboardPageHeader showAction={false} />
        <AppErrorState
          title="Dashboard temporarily unavailable"
          description="We could not load your analysis activity right now. Existing reports are not changed, and new work should wait until the workspace reconnects."
          detail="Analysis activity request failed."
          aiBrief={{
            items: [
              "Keep dashboard metrics read-only until the analysis activity request returns.",
              "Retry only asks for the latest organization-scoped activity snapshot.",
              "Use report packets and review queue links already opened as temporary references.",
            ],
            note: "No analysis, report, or reviewer record is changed from this recovery state.",
          }}
          onAction={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (allAnalyses.length === 0) {
    return (
      <div className="space-y-6 animate-fade-up">
        <DashboardPageHeader showAction={false} />
        <EmptyDashboard
          setupReadiness={<SetupReadinessPanel token={token} />}
        />
      </div>
    );
  }

  const {
    kpi,
    priorityDocket,
    recentAnalyses,
    riskDistribution,
    riskRatingsRestricted,
    runningAnalyses,
  } = buildDashboardMetrics(allAnalyses);

  return (
    <div className="space-y-6 animate-fade-up">
      <DashboardPageHeader
        latestUpdatedAt={recentAnalyses[0]?.updated_at}
        reviewCount={kpi.need_review}
        runningCount={kpi.running_pipelines}
        sampleWindowSize={allAnalyses.length}
        totalAnalyses={workspaceAnalysisCount}
      />
      <DashboardSecondaryDisclosure
        description="Open server-verified setup evidence and recovery actions."
        testId="dashboard-setup-disclosure"
        title="Workspace setup"
      >
        <SetupReadinessPanel token={token} compact />
      </DashboardSecondaryDisclosure>
      <section
        className="space-y-4"
        aria-labelledby="dashboard-today-workbench-title"
        data-testid="dashboard-today-workbench"
      >
        <h2 id="dashboard-today-workbench-title" className="sr-only">
          Today workbench
        </h2>
        <ExecutiveDecisionBrief
          analyses={allAnalyses}
          billingStatus={
            billingAccessRestricted ? undefined : billingStatusQuery.data
          }
          isBillingAccessRestricted={billingAccessRestricted}
          isBillingLoading={billingStatusQuery.isLoading}
          sampleWindowSize={allAnalyses.length}
          totalAnalyses={workspaceAnalysisCount}
        />
        <details
          className="group overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)]"
          data-testid="dashboard-ai-command-disclosure"
        >
          <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-4 py-3 transition-colors marker:hidden hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-primary/60 sm:px-5 [&::-webkit-details-marker]:hidden">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
              <Sparkles className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-[var(--text-primary)]">
                Additional AI-assisted portfolio actions
              </span>
              <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                Expand for source-linked follow-ups beyond the executive next
                move.
              </span>
            </span>
            <ChevronDown
              className="h-4 w-4 shrink-0 text-[var(--text-tertiary)] transition-transform group-open:rotate-180"
              aria-hidden="true"
            />
          </summary>
          <div className="border-t border-[var(--border-subtle)] p-3 sm:p-4">
            <AiCommandPanel
              analyses={allAnalyses}
              sampleWindowSize={allAnalyses.length}
            />
          </div>
        </details>
        <RunningPipelinesAlert runningAnalyses={runningAnalyses} />
        <DashboardSecondaryDisclosure
          description="Inspect assignments, overdue work, escalations, and owner gaps."
          testId="dashboard-legal-review-disclosure"
          title="Legal review workload"
        >
          <LegalReviewWorkloadPanel token={token} />
        </DashboardSecondaryDisclosure>
      </section>
      <DashboardSecondaryDisclosure
        description="Open the risk distribution and ranked evidence action docket."
        testId="dashboard-risk-docket-disclosure"
        title="Risk & action docket"
      >
        <RiskActivitySection
          priorityDocket={priorityDocket}
          recentAnalyses={recentAnalyses}
          riskRatingsRestricted={riskRatingsRestricted}
          riskDistribution={riskDistribution}
          sampleWindowSize={allAnalyses.length}
        />
      </DashboardSecondaryDisclosure>
      <OnboardingTooltip steps={TOUR_STEPS} />
    </div>
  );
}
