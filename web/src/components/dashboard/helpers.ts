import type { AnalysisListItem } from "@/types/api";
import type { OnboardingStep } from "@/components/shared/onboarding-tooltip";

export interface DashboardPriorityDocketItem {
  analysis: AnalysisListItem;
  reason: string;
  reasonTone: "critical" | "warning" | "info" | "neutral";
}

const DASHBOARD_ACTIVITY_PREVIEW_LIMIT = 5;

export const TOUR_STEPS: OnboardingStep[] = [
  {
    target: "[href='/analyses/new']",
    title: "Start an Analysis",
    description:
      "Submit a compound name, SMILES, or CAS number to begin a Freedom-to-Operate analysis.",
  },
  {
    target: "[href='/analyses']",
    title: "View Your Analyses",
    description:
      "Track all your FTO analyses, filter by status, and view detailed reports.",
  },
  {
    target: "[href='/monitors']",
    title: "Monitor Patents",
    description:
      "Set up automated patent monitoring to track new filings for your compounds.",
  },
];

export const RISK_LEGEND_COLORS: Record<string, string> = {
  high: "text-error",
  medium: "text-warning",
  low: "text-success",
  clear: "text-info",
};

export function relativeTime(date: string): string {
  const diff = Date.now() - new Date(date).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function getPriorityReason(
  analysis: AnalysisListItem,
): DashboardPriorityDocketItem {
  const reviewStatus = analysis.review_status?.status;

  if (
    analysis.status === "completed" &&
    analysis.review_status?.is_persisted &&
    reviewStatus === "changes_requested"
  ) {
    return {
      analysis,
      reason: "Changes requested",
      reasonTone: "critical",
    };
  }

  if (analysis.status === "failed") {
    return {
      analysis,
      reason: "Run failed",
      reasonTone: "critical",
    };
  }

  if (
    !analysis.risk_ratings_restricted &&
    (analysis.blocking_patents_count ?? 0) > 0
  ) {
    return {
      analysis,
      reason: `${(analysis.blocking_patents_count ?? 0).toLocaleString()} blocking patent${
        analysis.blocking_patents_count === 1 ? "" : "s"
      }`,
      reasonTone: "critical",
    };
  }

  if (analysis.flagged_for_review) {
    return {
      analysis,
      reason: "Flagged for review",
      reasonTone: "warning",
    };
  }

  if (!analysis.risk_ratings_restricted && analysis.overall_risk === "high") {
    return {
      analysis,
      reason: "High-risk finding",
      reasonTone: "warning",
    };
  }

  if (analysis.share_active) {
    const viewCount = analysis.share_view_count ?? 0;
    return {
      analysis,
      reason:
        viewCount > 0
          ? `Shared with ${viewCount.toLocaleString()} view${viewCount === 1 ? "" : "s"}`
          : "Shared report active",
      reasonTone: "info",
    };
  }

  if (analysis.status === "running") {
    return {
      analysis,
      reason: `Running step ${analysis.current_step}/8`,
      reasonTone: "info",
    };
  }

  if (analysis.status === "pending") {
    return {
      analysis,
      reason: "Pending launch",
      reasonTone: "neutral",
    };
  }

  return {
    analysis,
    reason: "Recent movement",
    reasonTone: "neutral",
  };
}

function getPriorityScore(analysis: AnalysisListItem) {
  const reviewStatus = analysis.review_status?.status;

  if (
    analysis.status === "completed" &&
    analysis.review_status?.is_persisted &&
    reviewStatus === "changes_requested"
  ) {
    return 0;
  }
  if (analysis.status === "failed") return 1;
  if (
    !analysis.risk_ratings_restricted &&
    (analysis.blocking_patents_count ?? 0) > 0
  )
    return 2;
  if (analysis.flagged_for_review) return 3;
  if (!analysis.risk_ratings_restricted && analysis.overall_risk === "high")
    return 4;
  if (analysis.share_active && (analysis.share_view_count ?? 0) > 0) return 5;
  if (analysis.share_active) return 6;
  if (analysis.status === "running") return 7;
  if (analysis.status === "pending") return 8;
  return 9;
}

function compareByRecentActivity(
  left: AnalysisListItem,
  right: AnalysisListItem,
) {
  const updatedDelta =
    new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
  if (updatedDelta !== 0) {
    return updatedDelta;
  }
  return left.compound_name.localeCompare(right.compound_name);
}

export function buildDashboardMetrics(allAnalyses: AnalysisListItem[]) {
  const riskRatingsRestricted = allAnalyses.some(
    (analysis) => analysis.risk_ratings_restricted === true,
  );
  const needReview = allAnalyses.filter(
    (analysis) =>
      analysis.status === "completed" &&
      (analysis.flagged_for_review ||
        (!riskRatingsRestricted && analysis.overall_risk === "high") ||
        (analysis.review_status?.is_persisted &&
          analysis.review_status.status === "changes_requested")),
  ).length;
  const highRiskFindings = allAnalyses.filter(
    (analysis) => analysis.overall_risk === "high",
  ).length;
  const clearCompounds = allAnalyses.filter(
    (analysis) => analysis.overall_risk === "clear",
  ).length;
  const runningPipelines = allAnalyses.filter(
    (analysis) => analysis.status === "running",
  ).length;
  const completedAnalyses = allAnalyses.filter(
    (analysis) => analysis.status === "completed",
  ).length;

  return {
    kpi: {
      total_analyses: allAnalyses.length,
      need_review: needReview,
      high_risk_findings: highRiskFindings,
      clear_compounds: clearCompounds,
      running_pipelines: runningPipelines,
      completed_analyses: completedAnalyses,
    },
    riskDistribution: [
      {
        level: "high",
        count: highRiskFindings,
      },
      {
        level: "medium",
        count: allAnalyses.filter(
          (analysis) => analysis.overall_risk === "medium",
        ).length,
      },
      {
        level: "low",
        count: allAnalyses.filter((analysis) => analysis.overall_risk === "low")
          .length,
      },
      {
        level: "clear",
        count: clearCompounds,
      },
    ],
    recentAnalyses: [...allAnalyses]
      .sort(compareByRecentActivity)
      .slice(0, DASHBOARD_ACTIVITY_PREVIEW_LIMIT),
    priorityDocket: [...allAnalyses]
      .filter((analysis) => getPriorityScore(analysis) < 9)
      .sort((left, right) => {
        const priorityDelta = getPriorityScore(left) - getPriorityScore(right);
        if (priorityDelta !== 0) {
          return priorityDelta;
        }
        return compareByRecentActivity(left, right);
      })
      .slice(0, DASHBOARD_ACTIVITY_PREVIEW_LIMIT)
      .map(getPriorityReason),
    runningAnalyses: allAnalyses.filter(
      (analysis) => analysis.status === "running",
    ),
    riskRatingsRestricted,
  };
}
