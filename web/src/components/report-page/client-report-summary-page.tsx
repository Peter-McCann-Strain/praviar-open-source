"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  FileCheck2,
  Scale,
  Search,
  ShieldCheck,
} from "lucide-react";

import { RiskBadge } from "@/components/shared/risk-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useReportSummary } from "@/hooks/use-report";

export function ClientReportSummaryPage({
  analysisId,
}: {
  analysisId: string;
}) {
  const router = useRouter();
  const token = useAuthToken();
  const { data, error, isLoading, refetch } = useReportSummary(
    analysisId,
    token,
  );
  const canOpenFullReport = data?.risk_ratings_restricted === false;

  useEffect(() => {
    if (canOpenFullReport) {
      router.replace(`/analyses/${encodeURIComponent(analysisId)}/report`);
    }
  }, [analysisId, canOpenFullReport, router]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl space-y-4" aria-busy="true">
        <div className="skeleton-shimmer h-40 rounded-lg" />
        <div className="skeleton-shimmer h-72 rounded-lg" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <Card className="mx-auto max-w-2xl border-error/25">
        <CardContent className="p-6">
          <AlertTriangle className="h-6 w-6 text-error" aria-hidden="true" />
          <h1 className="mt-4 text-xl font-semibold text-[var(--text-primary)]">
            Report summary unavailable
          </h1>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            Praviar could not load the authorized executive summary. No full
            report content has been exposed.
          </p>
          <Button
            type="button"
            variant="outline"
            className="mt-4 min-h-11"
            onClick={() => {
              void refetch();
            }}
          >
            Retry summary
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (canOpenFullReport) {
    return (
      <div
        className="mx-auto max-w-4xl rounded-lg border border-[var(--border-subtle)] p-6 text-sm text-[var(--text-secondary)]"
        role="status"
        aria-live="polite"
      >
        Opening the full report workspace…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Button asChild variant="ghost" className="min-h-11 gap-2">
        <Link href="/analyses">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to analyses
        </Link>
      </Button>

      <header className="praviar-control-plane-header rounded-lg border border-[var(--border-subtle)] p-5 shadow-[var(--shadow-sm)] sm:p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--brand-primary)]">
          Authorized executive view
        </p>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold text-[var(--text-primary)] sm:text-3xl">
              FTO report summary
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
              Decision-level context for this analysis. Claim charts, patent
              evidence, reviewer records, and export controls remain available
              through your patent-counsel workspace.
            </p>
          </div>
          {data.overall_risk ? (
            <RiskBadge risk={data.overall_risk} size="lg" />
          ) : null}
        </div>
      </header>

      {data.risk_ratings_restricted ? (
        <div
          role="status"
          className="flex gap-3 rounded-lg border border-info/25 bg-info/8 p-4"
        >
          <ShieldCheck
            className="mt-0.5 h-5 w-5 shrink-0 text-info"
            aria-hidden="true"
          />
          <div>
            <p className="font-semibold text-[var(--text-primary)]">
              Governed conclusions are protected
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              Risk ratings and blocking-patent counts are intentionally withheld
              from this role. The evidence inventory remains visible without
              implying a legal clearance decision.
            </p>
          </div>
        </div>
      ) : null}

      <section
        className="grid gap-3 sm:grid-cols-3"
        aria-label="Report summary metrics"
      >
        <SummaryMetric
          icon={Scale}
          label="Overall risk"
          value={
            data.risk_ratings_restricted
              ? "Counsel-only"
              : (data.overall_risk?.toUpperCase() ?? "Not reported")
          }
        />
        <SummaryMetric
          icon={AlertTriangle}
          label="Blocking patents"
          value={
            data.risk_ratings_restricted
              ? "Counsel-only"
              : (data.blocking_patents_count?.toLocaleString() ??
                "Not reported")
          }
        />
        <SummaryMetric
          icon={Search}
          label="Patents found"
          value={data.total_patents_found.toLocaleString()}
        />
      </section>

      <Card>
        <CardContent className="p-5 sm:p-6">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-primary/10 text-brand-primary">
              <FileCheck2 className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Executive summary
              </p>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                Decision context
              </h2>
            </div>
          </div>
          <div className="mt-5 space-y-4 text-sm leading-7 text-[var(--text-secondary)]">
            {data.executive_summary
              .split(/\n{2,}/u)
              .filter(Boolean)
              .map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
          </div>
        </CardContent>
      </Card>

      <div className="rounded-lg border border-warning/25 bg-warning/8 p-4 text-sm leading-6 text-[var(--text-secondary)]">
        <p className="font-semibold text-[var(--text-primary)]">
          Counsel review boundary
        </p>
        <p className="mt-1">
          This summary is not a legal opinion. Ask your organization&apos;s
          patent counsel for claim-level evidence, jurisdiction scope, and
          reliance decisions.
        </p>
      </div>
    </div>
  );
}

function SummaryMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Scale;
  label: string;
  value: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3 p-4">
        <Icon
          className="mt-0.5 h-4 w-4 text-brand-primary"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-xs text-[var(--text-tertiary)]">{label}</p>
          <p className="mt-1 break-words text-lg font-semibold text-[var(--text-primary)]">
            {value}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
