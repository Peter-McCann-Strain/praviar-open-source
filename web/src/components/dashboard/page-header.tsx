"use client";

import Link from "next/link";
import {
  Activity,
  ClipboardCheck,
  Clock3,
  FileCheck2,
  FileSearch,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  AppSurfaceHeader,
  type AppSurfaceHeaderMetric,
} from "@/components/shared/app-surface-header";

import { relativeTime } from "@/components/dashboard/helpers";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";

interface DashboardPageHeaderProps {
  latestUpdatedAt?: string;
  reviewCount?: number;
  showAction?: boolean;
  runningCount?: number;
  sampleWindowSize?: number;
  totalAnalyses?: number;
}

export function DashboardPageHeader({
  latestUpdatedAt,
  reviewCount,
  showAction = true,
  runningCount,
  sampleWindowSize,
  totalAnalyses,
}: DashboardPageHeaderProps) {
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const canCreateAnalysis = principal.data?.can_create_analysis === true;
  const showSignals = typeof totalAnalyses === "number";
  const signalMetrics: AppSurfaceHeaderMetric[] = [];
  const metricWindowDetail =
    typeof sampleWindowSize === "number"
      ? `Latest ${sampleWindowSize.toLocaleString()} ${
          sampleWindowSize === 1 ? "analysis" : "analyses"
        }`
      : undefined;

  if (showSignals) {
    signalMetrics.push(
      {
        icon: <FileCheck2 className="h-3.5 w-3.5" />,
        label: "Workspace",
        value: totalAnalyses.toLocaleString(),
        detail: "All analyses",
      },
      {
        icon: <Activity className="h-3.5 w-3.5" />,
        label: "Live",
        value: (runningCount ?? 0).toLocaleString(),
        detail: metricWindowDetail,
        tone: runningCount ? "active" : "default",
      },
      {
        icon: <ClipboardCheck className="h-3.5 w-3.5" />,
        label: "Review",
        value: (reviewCount ?? 0).toLocaleString(),
        detail: metricWindowDetail,
        tone: reviewCount ? "warning" : "default",
      },
    );

    if (latestUpdatedAt) {
      signalMetrics.push({
        icon: <Clock3 className="h-3.5 w-3.5" />,
        label: "Updated",
        mobileHidden: true,
        value: formatRelativeTime(latestUpdatedAt),
      });
    }

    if (sampleWindowSize != null) {
      signalMetrics.push({
        icon: <ShieldCheck className="h-3.5 w-3.5" />,
        label: "Metric window",
        mobileHidden: true,
        value: `Latest ${sampleWindowSize}`,
      });
    }
  }

  const metrics = showSignals ? signalMetrics : undefined;

  return (
    <AppSurfaceHeader
      chrome="dashboard"
      className="-mx-4 sm:mx-0"
      data-praviar-dashboard-command-deck="app-evidence"
      dataTestId="dashboard-app-surface-header"
      eyebrow="Praviar patent intelligence workspace"
      title="Dashboard"
      description="FTO activity, review load, and high-risk findings in one operational view."
      markSize="lg"
      metrics={metrics}
      mobileDensity="compact"
      mobileMetricColumns="three"
      art={
        <div
          aria-hidden="true"
          className="praviar-command-deck-art pointer-events-none absolute inset-y-0 right-0 -z-10 hidden w-1/2 opacity-45 lg:block"
        />
      }
      actions={
        showAction && canCreateAnalysis ? (
          <Button asChild className="min-h-11 w-full gap-2 lg:w-auto">
            <Link href="/analyses/new">
              <FileSearch className="h-4 w-4" />
              New Analysis
            </Link>
          </Button>
        ) : null
      }
    />
  );
}
