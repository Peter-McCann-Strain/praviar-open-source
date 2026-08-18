"use client";

import { ExternalLink, Globe, X } from "lucide-react";
import type { PatentAnalysis, PatentHit } from "@praviar/shared-types";
import { RiskBadge } from "@/components/shared/risk-badge";
import { FindingConfidenceBadge } from "@/components/report/finding-confidence-badge";
import { PatentDetailDrawerAbstractSection } from "@/components/report/patent-detail-drawer-abstract-section";
import { PatentDetailDrawerClaimsSection } from "@/components/report/patent-detail-drawer-claims-section";
import { PatentDetailDrawerCpcSection } from "@/components/report/patent-detail-drawer-cpc-section";
import { PatentDetailDrawerEventsSection } from "@/components/report/patent-detail-drawer-events-section";
import { PatentDetailDrawerFamilySection } from "@/components/report/patent-detail-drawer-family-section";
import { PatentDetailDrawerInventorsSection } from "@/components/report/patent-detail-drawer-inventors-section";
import { PatentDetailDrawerLegalStatusBadge } from "@/components/report/patent-detail-drawer-legal-status-badge";
import { PatentDetailDrawerLegalStatusSection } from "@/components/report/patent-detail-drawer-legal-status-section";

const HIGH_CONFIDENCE_THRESHOLD = 0.9;
const MODERATE_CONFIDENCE_THRESHOLD = 0.7;

function getClaimAnalysisConfidence(analysis: PatentAnalysis) {
  const claims = analysis.claims_analyzed ?? [];
  const reportedScores = claims
    .map((claim) => claim.overall_confidence)
    .filter(
      (score): score is number =>
        typeof score === "number" &&
        Number.isFinite(score) &&
        score >= 0 &&
        score <= 1,
    );

  if (reportedScores.length === 0) {
    return {
      detail: "No claim score",
      level: "UNKNOWN" as const,
      rationale:
        "No claim-analysis confidence score was reported. Confidence is not inferred from the patent risk level.",
    };
  }

  const average =
    reportedScores.reduce((total, score) => total + score, 0) /
    reportedScores.length;
  const level =
    average >= HIGH_CONFIDENCE_THRESHOLD
      ? ("HIGH" as const)
      : average >= MODERATE_CONFIDENCE_THRESHOLD
        ? ("MODERATE" as const)
        : ("LOW" as const);
  const claimLabel = claims.length === 1 ? "claim" : "claims";

  return {
    detail: `${Math.round(average * 100)}% · ${reportedScores.length}/${claims.length} ${claimLabel}`,
    level,
    rationale:
      "Average of the reported claim-analysis confidence scores. Confidence measures evidentiary support and is independent of the patent risk level.",
  };
}

export function PatentDetailDrawerHeader({
  patent,
  analysis,
  patentLinks,
  onClose,
}: {
  patent: PatentHit;
  analysis: PatentAnalysis | null;
  patentLinks: { googlePatents: string; espacenet: string };
  onClose: () => void;
}) {
  const claimConfidence = analysis
    ? getClaimAnalysisConfidence(analysis)
    : null;

  return (
    <div className="praviar-glass-strip sticky top-0 z-10 border-b border-[var(--border-default)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <code className="text-xs font-mono text-brand-primary">
              {patent.patent_id}
            </code>
            {analysis && <RiskBadge risk={analysis.risk_level} size="sm" />}
            {claimConfidence && (
              <FindingConfidenceBadge
                level={claimConfidence.level}
                rationale={claimConfidence.rationale}
                detail={claimConfidence.detail}
                size="sm"
              />
            )}
            <PatentDetailDrawerLegalStatusBadge status={patent.legal_status} />
          </div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mt-1.5 leading-snug">
            {patent.title}
          </h2>
          {patent.assignees.length > 0 && (
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              {patent.assignees.join(", ")}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
          aria-label="Close patent details"
        >
          <X
            className="h-4 w-4 text-[var(--text-tertiary)]"
            aria-hidden="true"
          />
        </button>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1">
        <a
          href={patentLinks.googlePatents}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-xs text-brand-primary transition-colors hover:bg-brand-primary/5 hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60"
        >
          <ExternalLink className="h-3 w-3" />
          Google Patents
        </a>
        <a
          href={patentLinks.espacenet}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-xs text-brand-primary transition-colors hover:bg-brand-primary/5 hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60"
        >
          <Globe className="h-3 w-3" />
          Espacenet
        </a>
      </div>
    </div>
  );
}

export function PatentDetailDrawerSections({
  patent,
  claimsExpanded,
  onClaimsExpandedChange,
}: {
  patent: PatentHit;
  claimsExpanded: boolean;
  onClaimsExpandedChange: (expanded: boolean) => void;
}) {
  const claimsText = patent.claims_text || "";

  return (
    <div className="p-4 space-y-0">
      <PatentDetailDrawerAbstractSection abstract={patent.abstract} />
      <PatentDetailDrawerLegalStatusSection patent={patent} />

      {claimsText && (
        <PatentDetailDrawerClaimsSection
          claimsText={claimsText}
          claimsExpanded={claimsExpanded}
          onClaimsExpandedChange={onClaimsExpandedChange}
        />
      )}

      {patent.family && patent.family.members.length > 0 ? (
        <PatentDetailDrawerFamilySection
          family={patent.family}
          currentPatentId={patent.patent_id}
        />
      ) : null}

      {patent.cpc_codes.length > 0 ? (
        <PatentDetailDrawerCpcSection codes={patent.cpc_codes} />
      ) : null}

      {patent.inventors.length > 0 ? (
        <PatentDetailDrawerInventorsSection inventors={patent.inventors} />
      ) : null}

      {patent.legal_events.length > 0 ? (
        <PatentDetailDrawerEventsSection events={patent.legal_events} />
      ) : null}
    </div>
  );
}
