"use client";

import {
  AlertTriangle,
  ArrowRight,
  FileWarning,
  type LucideIcon,
  RefreshCw,
  Scale,
  ShieldCheck,
} from "lucide-react";
import { AIRecoveryBrief } from "@/components/shared/ai-recovery-brief";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface DataIntegrityWarningsProps {
  evidenceSufficientForClearance?: boolean;
  failureCount: number;
  hasMetadataInconsistency: boolean;
  limitationCount: number;
  reviewIssueCount: number;
  onOpenDetails: () => void;
  recoverableFailureCount: number;
  hasDataIntegrityWarnings: boolean;
  variant?: "rail" | "banner";
}

export function DataIntegrityWarnings({
  evidenceSufficientForClearance,
  failureCount,
  hasMetadataInconsistency,
  limitationCount,
  reviewIssueCount,
  onOpenDetails,
  recoverableFailureCount,
  hasDataIntegrityWarnings,
  variant = "rail",
}: DataIntegrityWarningsProps) {
  if (!hasDataIntegrityWarnings) {
    return null;
  }

  const needsReviewFailureCount = failureCount - recoverableFailureCount;
  const isBanner = variant === "banner";
  const title = hasMetadataInconsistency
    ? "Report metadata needs verification"
    : evidenceSufficientForClearance === false
      ? "Report is screening-only until gaps are reviewed"
      : "Report remains usable with caveats";
  const description = hasMetadataInconsistency
    ? "Failure counts do not match across report metadata. Review coverage details before relying on affected conclusions."
    : evidenceSufficientForClearance === false
      ? "Evidence coverage is not clearance-grade. Use this report for screening while reviewers close the listed gaps."
      : "Some evidence processing needs review before relying on affected patent exclusions or source coverage.";

  return (
    <section
      aria-label={
        isBanner ? "Mobile data integrity warnings" : "Data integrity warnings"
      }
      role="status"
      className={[
        "scroll-mt-32 rounded-lg border border-warning/25 bg-warning/5 p-4 shadow-[var(--shadow-xs)]",
        isBanner ? "xl:hidden" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div
        className={[
          "flex min-w-0 items-start gap-3",
          isBanner ? "md:items-center" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-warning/25 bg-warning/10 text-warning">
          <AlertTriangle className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-warning">
            Data integrity warnings
          </p>
          <h2 className="text-base font-semibold leading-6 text-[var(--text-primary)]">
            {title}
          </h2>
          <p className="text-sm leading-6 text-[var(--text-secondary)]">
            {description}
          </p>
        </div>
      </div>

      <dl
        className={[
          "mt-4 grid gap-2",
          isBanner ? "sm:grid-cols-2 lg:grid-cols-4" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {hasMetadataInconsistency ? (
          <IntegrityMetric
            icon={ShieldCheck}
            label="Metadata"
            value="Needs verification"
            tone="warning"
          />
        ) : null}
        {failureCount > 0 ? (
          <IntegrityMetric
            icon={FileWarning}
            label="Affected patents"
            value={`${failureCount} failed analysis`}
            tone="error"
          />
        ) : null}
        {recoverableFailureCount > 0 ? (
          <IntegrityMetric
            icon={RefreshCw}
            label="Recoverable"
            value={`${recoverableFailureCount} retry candidate${
              recoverableFailureCount === 1 ? "" : "s"
            }`}
            tone="warning"
          />
        ) : null}
        {needsReviewFailureCount > 0 ? (
          <IntegrityMetric
            icon={Scale}
            label="Needs review"
            value={`${needsReviewFailureCount} patent${
              needsReviewFailureCount === 1 ? "" : "s"
            }`}
            tone="error"
          />
        ) : null}
        {limitationCount > 0 ? (
          <IntegrityMetric
            icon={ShieldCheck}
            label="Source caveats"
            value={`${limitationCount} data limitation${
              limitationCount === 1 ? "" : "s"
            }`}
            tone="warning"
          />
        ) : null}
        {reviewIssueCount > 0 ? (
          <IntegrityMetric
            icon={Scale}
            label="Critic findings"
            value={`${reviewIssueCount} review issue${reviewIssueCount === 1 ? "" : "s"}`}
            tone="error"
          />
        ) : null}
      </dl>

      <div className="mt-3">
        <ReportMobileDisclosure
          label="Recovery guidance"
          description={[
            failureCount > 0 ? `${failureCount} failed analysis` : null,
            limitationCount > 0
              ? `${limitationCount} source caveat${limitationCount === 1 ? "" : "s"}`
              : null,
            reviewIssueCount > 0
              ? `${reviewIssueCount} critic issue${reviewIssueCount === 1 ? "" : "s"}`
              : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        >
          <AIRecoveryBrief
            ariaLabel={
              isBanner ? "Mobile AI recovery brief" : "AI recovery brief"
            }
            className="mt-3"
            items={[
              "Review affected patents before using exclusion or clearance language.",
              "Keep these caveats attached to counsel handoff and exported packets.",
            ]}
            note="No legal conclusion changed from this recovery guidance."
          />

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {failureCount > 0 ? (
              <Badge variant="destructive" className="text-xs">
                {failureCount} patent{failureCount > 1 ? "s" : ""} failed
                analysis
              </Badge>
            ) : null}
            {limitationCount > 0 ? (
              <Badge variant="warning" className="text-xs">
                {limitationCount} data limitation
                {limitationCount > 1 ? "s" : ""} detected
              </Badge>
            ) : null}
            {reviewIssueCount > 0 ? (
              <Badge variant="destructive" className="text-xs">
                {reviewIssueCount} critic issue{reviewIssueCount > 1 ? "s" : ""}
              </Badge>
            ) : null}
          </div>
        </ReportMobileDisclosure>
      </div>

      <Button
        type="button"
        variant="outline"
        size="sm"
        className={
          isBanner
            ? "mt-4 min-h-11 w-full justify-between sm:w-auto"
            : "mt-4 min-h-11 w-full justify-between"
        }
        onClick={onOpenDetails}
      >
        Open coverage details
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </Button>
    </section>
  );
}

type IntegrityMetricTone = "error" | "warning";

function IntegrityMetric({
  icon: Icon,
  label,
  tone,
  value,
}: {
  icon: LucideIcon;
  label: string;
  tone: IntegrityMetricTone;
  value: string;
}) {
  const toneClass = tone === "error" ? "text-error" : "text-warning";

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/75 p-3">
      <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        <Icon className={`h-3.5 w-3.5 ${toneClass}`} aria-hidden="true" />
        {label}
      </dt>
      <dd className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}
