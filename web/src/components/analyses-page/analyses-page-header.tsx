"use client";

import Link from "next/link";
import { FileSearch } from "lucide-react";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { Button } from "@/components/ui/button";
import type { AnalysisListItem } from "@/types/api";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";

interface AnalysesPageHeaderProps {
  totalCount?: number;
  visibleCount?: number;
  visibleAnalyses?: AnalysisListItem[];
}

type HeaderMetric = {
  detail: string;
  label: string;
  tone?: "default" | "warning";
  value: string;
};

export function AnalysesPageHeader({
  totalCount = 0,
  visibleCount = 0,
  visibleAnalyses = [],
}: AnalysesPageHeaderProps) {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const visibleNeedsReview = visibleAnalyses.filter((analysis) => {
    const reviewStatus = analysis.review_status?.status;
    return (
      analysis.flagged_for_review ||
      reviewStatus === "under_review" ||
      reviewStatus === "changes_requested" ||
      reviewStatus === "pending"
    );
  }).length;
  const visibleActiveShares = visibleAnalyses.filter(
    (analysis) => analysis.share_active,
  ).length;
  const proofItems: HeaderMetric[] = [
    {
      label: "Matching packets",
      value: totalCount.toLocaleString(),
      detail: "Current library scope",
    },
    {
      label: "Current page",
      value: visibleCount.toLocaleString(),
      detail: "Visible packets",
    },
    {
      label: "Page needs review",
      value: visibleNeedsReview.toLocaleString(),
      detail: "Visible review workload",
      tone: visibleNeedsReview > 0 ? "warning" : "default",
    },
    {
      label: "Page shares",
      value: visibleActiveShares.toLocaleString(),
      detail: "Active external links",
    },
  ];

  return (
    <AppSurfaceHeader
      eyebrow="Evidence archive"
      title="Analysis Library"
      description="Search, triage, review state, and shared report handoffs across every FTO packet for your organization."
      dataTestId="analyses-app-surface-header"
      metrics={proofItems}
      actions={
        principal.data?.can_create_analysis === true ? (
          <Button asChild className="min-h-11 w-full gap-2 lg:w-auto">
            <Link href="/analyses/new" className="lg:flex-shrink-0">
              <FileSearch className="h-4 w-4" />
              New Analysis
            </Link>
          </Button>
        ) : null
      }
    />
  );
}
