"use client";

import { useState, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { ConfidenceDashboard } from "@/components/report/confidence-dashboard";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import { DesignAroundPanel } from "@/components/report/design-around-panel";
import { ActionItemsPanel } from "@/components/report/action-items-panel";
import { CitationPanel } from "@/components/report/citation-panel";
import {
  getSummaryDataIntegrity,
  getSummaryFunnelData,
  getSummaryHasDesignArounds,
} from "@/components/report/summary-tab-helpers";
import {
  AnalysisSummarySection,
  ClearanceDecisionSection,
  CompoundMethodologySection,
  DataIntegrityWarnings,
  KeyRisksSection,
} from "@/components/report/summary-tab-sections";
import { buildCitationMap } from "@/types/citation";
import type { CitationRef } from "@/types/citation";
import type { FTOReport } from "@praviar/shared-types";

interface SummaryTabProps {
  report: FTOReport;
}

function MobileSummaryDisclosure({
  children,
  description,
  label,
}: {
  children: ReactNode;
  description: string;
  label: string;
}) {
  return (
    <details className="group sm:contents">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3 text-left shadow-[var(--shadow-xs)] marker:content-none sm:hidden [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-[var(--text-primary)]">
            {label}
          </span>
          <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
            {description}
          </span>
        </span>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="mt-3 hidden group-open:block sm:mt-0 sm:block">
        {children}
      </div>
    </details>
  );
}

export function SummaryTab({ report }: SummaryTabProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const citationMap = buildCitationMap(
    report.patent_analyses ?? [],
    report.claim_source_span_map,
  );
  const [activeCitation, setActiveCitation] = useState<CitationRef | null>(
    null,
  );
  const {
    evidenceSufficientForClearance,
    failureCount,
    hasMetadataInconsistency,
    limitationCount,
    reviewIssueCount,
    recoverableFailureCount,
    hasDataIntegrityWarnings,
  } = getSummaryDataIntegrity(report);
  const hasDesignArounds = getSummaryHasDesignArounds(report);
  const funnelData = getSummaryFunnelData(report);

  /** Navigate to patent card in Patents tab */
  const navigateToPatent = (patentId: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "patents");
    params.set("patent", patentId);
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  /** Open the exact blocking claim and its evidence layers. */
  const navigateToClaim = (patentId: string, claimNumber: number) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "claims");
    params.set("patent", patentId);
    params.set("claim", String(claimNumber));
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const navigateToCoverageQuality = () => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "meta");
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  return (
    <div className="praviar-summary-workbench grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(19rem,0.42fr)] xl:items-start">
      {hasDataIntegrityWarnings ? (
        <div className="xl:hidden">
          <ReportMobileDisclosure
            label="Evidence coverage caveats"
            description={[
              failureCount > 0
                ? `${failureCount} affected patent${failureCount === 1 ? "" : "s"}`
                : null,
              limitationCount > 0
                ? `${limitationCount} source caveat${limitationCount === 1 ? "" : "s"}`
                : null,
              reviewIssueCount > 0
                ? `${reviewIssueCount} critic issue${reviewIssueCount === 1 ? "" : "s"}`
                : null,
              hasMetadataInconsistency ? "metadata verification needed" : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          >
            <DataIntegrityWarnings
              evidenceSufficientForClearance={evidenceSufficientForClearance}
              failureCount={failureCount}
              hasMetadataInconsistency={hasMetadataInconsistency}
              limitationCount={limitationCount}
              reviewIssueCount={reviewIssueCount}
              onOpenDetails={navigateToCoverageQuality}
              recoverableFailureCount={recoverableFailureCount}
              hasDataIntegrityWarnings={hasDataIntegrityWarnings}
              variant="banner"
            />
          </ReportMobileDisclosure>
        </div>
      ) : null}

      <div className="min-w-0 space-y-6">
        <ClearanceDecisionSection report={report} />
        <KeyRisksSection
          report={report}
          onClaimClick={navigateToClaim}
          onPatentClick={navigateToPatent}
        />

        {/* ═══ 2. Action Items Panel (restricted via UPL redaction) ═══ */}
        <MobileSummaryDisclosure
          label="Counsel next actions"
          description="Open the prioritized action plan and review handoff."
        >
          <ActionItemsPanel report={report} />
        </MobileSummaryDisclosure>
        <MobileSummaryDisclosure
          label="Analysis summary"
          description="Open the evidence-linked narrative and citations."
        >
          <AnalysisSummarySection
            report={report}
            citationMap={citationMap}
            onCitationClick={(index) => {
              const ref = citationMap.get(index);
              if (ref) setActiveCitation(ref);
            }}
          />
        </MobileSummaryDisclosure>

        {/* ═══ 5. Design-Around Strategies ═══ */}
        {hasDesignArounds ? (
          <MobileSummaryDisclosure
            label="Design-around strategies"
            description="Open candidate strategies, assumptions, and evidence gaps."
          >
            <DesignAroundPanel report={report} />
          </MobileSummaryDisclosure>
        ) : null}
      </div>

      <aside
        aria-label="Report reliability and methodology"
        className="praviar-summary-rail min-w-0 space-y-4 xl:sticky xl:top-32"
      >
        <ReportMobileDisclosure
          label="Reliability dashboard"
          description="Inspect source health, confidence, and report limitations."
        >
          <ConfidenceDashboard report={report} />
        </ReportMobileDisclosure>
        <div className="hidden xl:block">
          <DataIntegrityWarnings
            evidenceSufficientForClearance={evidenceSufficientForClearance}
            failureCount={failureCount}
            hasMetadataInconsistency={hasMetadataInconsistency}
            limitationCount={limitationCount}
            reviewIssueCount={reviewIssueCount}
            onOpenDetails={navigateToCoverageQuality}
            recoverableFailureCount={recoverableFailureCount}
            hasDataIntegrityWarnings={hasDataIntegrityWarnings}
          />
        </div>
      </aside>

      <div className="min-w-0 xl:col-span-2">
        <ReportMobileDisclosure
          label="Compound identity, methodology and search funnel"
          description="Inspect compound resolution, source health, and how candidates were found, screened, and analyzed."
        >
          <CompoundMethodologySection
            report={report}
            funnelData={funnelData}
            defaultOpen
          />
        </ReportMobileDisclosure>
      </div>

      <CitationPanel
        citation={activeCitation}
        report={report}
        onClose={() => setActiveCitation(null)}
        onOpenPatent={navigateToPatent}
      />
    </div>
  );
}
