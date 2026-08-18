"use client";

import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import {
  getSummaryCoveredJurisdictions,
  getSummaryHasAdditionalConfiguredSources,
} from "@/components/report/summary-tab-helpers";
import { getReportSourceHealthReadiness } from "@/components/report-page/report-reliance-readiness";
import { Button } from "@/components/ui/button";
import type { BlockerFamilyRecord, FTOReport } from "@praviar/shared-types";

interface KeyRisksSectionProps {
  report: FTOReport;
  onPatentClick: (patentId: string) => void;
  onClaimClick: (patentId: string, claimNumber: number) => void;
}

export function KeyRisksSection({
  report,
  onPatentClick,
  onClaimClick,
}: KeyRisksSectionProps) {
  const blockerFamilies =
    report.clearance_decision?.decision_audit?.blocker_families ?? [];
  const narrativeRisks = report.risk_summary.key_risks;
  if (blockerFamilies.length === 0 && narrativeRisks.length === 0) {
    return null;
  }
  const directJurisdictionCount = getSummaryCoveredJurisdictions(report);
  const hasAdditionalConfiguredSources =
    getSummaryHasAdditionalConfiguredSources(report);
  const sourceHealth = getReportSourceHealthReadiness(report);

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Risk docket
            </p>
            <h3 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
              Key Risks
            </h3>
          </div>
          <span className="rounded-md border border-error/20 bg-error/5 px-2.5 py-1 text-xs font-semibold text-error">
            {blockerFamilies.length > 0
              ? `${blockerFamilies.length} blocking famil${blockerFamilies.length === 1 ? "y" : "ies"}`
              : `${narrativeRisks.length} unresolved driver${narrativeRisks.length === 1 ? "" : "s"}`}
          </span>
        </div>
        <div className="space-y-2">
          {blockerFamilies.length > 0
            ? blockerFamilies.map((blocker, index) => (
                <CanonicalBlockerDocket
                  key={blocker.blocker_id}
                  blocker={blocker}
                  index={index}
                  onClaimClick={onClaimClick}
                  onPatentClick={onPatentClick}
                />
              ))
            : narrativeRisks.map((risk, index) => (
                <UnstructuredRiskDocket
                  key={`${risk}-${index}`}
                  risk={risk}
                  index={index}
                />
              ))}
        </div>
        <p className="text-xs text-[var(--text-tertiary)]">
          Based on {report.risk_summary.total_patents_analyzed} patents analyzed
          ; source health: {sourceHealth.value}
          {sourceHealth.hasCaveats ? ` (${sourceHealth.detail})` : ""};{" "}
          {directJurisdictionCount} direct jurisdiction
          {directJurisdictionCount === 1 ? "" : "s"} covered
          {hasAdditionalConfiguredSources
            ? "; additional configured sources reported healthy"
            : ""}
        </p>
      </CardContent>
    </Card>
  );
}

function CanonicalBlockerDocket({
  blocker,
  index,
  onClaimClick,
  onPatentClick,
}: {
  blocker: BlockerFamilyRecord;
  index: number;
  onClaimClick: (patentId: string, claimNumber: number) => void;
  onPatentClick: (patentId: string) => void;
}) {
  const claims = blocker.blocking_claims;
  const accusedActs = uniqueSorted(
    claims.flatMap((claim) => claim.accused_acts),
  );
  const recordBasis = uniqueSorted(
    claims.flatMap((claim) => claim.record_basis),
  );
  const invalidityPostures = uniqueSorted(
    claims
      .map((claim) => claim.invalidity_strength?.trim() ?? "")
      .filter(Boolean),
  );
  const identifier = String(index + 1).padStart(2, "0");

  return (
    <ReportMobileDisclosure
      label={`Family ${identifier} · ${blocker.primary_blocking_patent_id}`}
      description={`${blocker.jurisdictions.join(", ")} · ${claims.length} verified blocking claim${claims.length === 1 ? "" : "s"} · counsel review required`}
    >
      <div
        className="praviar-risk-docket-row grid gap-3 rounded-lg p-3 sm:grid-cols-[3rem_minmax(0,1fr)]"
        data-testid={`risk-docket-${index + 1}`}
        data-blocker-id={blocker.blocker_id}
      >
        <DocketIndex value={identifier} label="Family" />
        <div className="min-w-0">
          <dl className="grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            <RiskDatum label="Patent / family">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="min-h-11 max-w-full justify-start px-0 font-mono text-xs font-semibold text-brand-primary"
                aria-label={`Open patent ${blocker.primary_blocking_patent_id} in report evidence`}
                onClick={() =>
                  onPatentClick(blocker.primary_blocking_patent_id)
                }
              >
                <span className="truncate">
                  {blocker.primary_blocking_patent_id}
                </span>
              </Button>
              <span className="block text-xs font-normal text-[var(--text-tertiary)]">
                {blocker.family_id}
              </span>
            </RiskDatum>
            <RiskDatum label="Jurisdiction / family scope">
              {blocker.jurisdictions.join(", ")}
              <span className="block text-xs font-normal text-[var(--text-tertiary)]">
                {blocker.material_family_patent_ids.length} material family
                publication
                {blocker.material_family_patent_ids.length === 1 ? "" : "s"}
              </span>
            </RiskDatum>
            <RiskDatum label="Status / accused acts">
              Verified active status
              <span className="block text-xs font-normal text-[var(--text-tertiary)]">
                {accusedActs.join(", ")}
              </span>
            </RiskDatum>
            <RiskDatum label="Blocking claims">
              <span className="space-y-1">
                {claims.map((claim) => (
                  <Button
                    key={claim.claim_id}
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="flex min-h-11 max-w-full justify-start px-0 font-mono text-xs font-semibold text-brand-primary"
                    aria-label={`Open ${claim.claim_id} in report evidence`}
                    onClick={() =>
                      onClaimClick(claim.patent_id, claim.claim_number)
                    }
                  >
                    <span className="truncate">
                      {claim.patent_id} · claim {claim.claim_number}
                    </span>
                  </Button>
                ))}
              </span>
            </RiskDatum>
            <RiskDatum label="Literal / equivalents">
              <span className="space-y-1">
                {claims.map((claim) => (
                  <span
                    key={claim.claim_id}
                    className="block text-xs font-normal leading-5"
                  >
                    Claim {claim.claim_number}: literal{" "}
                    {formatPosture(claim.literal_risk)} · DoE{" "}
                    {formatPosture(claim.doe_risk)}
                  </span>
                ))}
              </span>
            </RiskDatum>
            <RiskDatum label="Invalidity / record basis">
              {invalidityPostures.length > 0
                ? invalidityPostures.map(formatPosture).join(", ")
                : "Invalidity not assessed in blocker record"}
              <span className="block text-xs font-normal text-[var(--text-tertiary)]">
                {recordBasis.length} verified record-basis item
                {recordBasis.length === 1 ? "" : "s"}
              </span>
            </RiskDatum>
          </dl>
          <div className="mt-3 border-t border-[var(--border-subtle)] pt-3 text-sm leading-6 text-[var(--text-primary)]">
            <p>
              Governed blocking exposure is recorded under{" "}
              <span className="font-mono text-xs">{blocker.blocker_id}</span>.
              Every claim shown here passed the claim, verified active-status,
              accused-act, territory, timing, evidence, and invalidity gates.
              Ownership and term are not inferred into this decision record.
            </p>
          </div>
        </div>
      </div>
    </ReportMobileDisclosure>
  );
}

function UnstructuredRiskDocket({
  risk,
  index,
}: {
  risk: string;
  index: number;
}) {
  const identifier = String(index + 1).padStart(2, "0");
  return (
    <ReportMobileDisclosure
      label={`Driver ${identifier} · canonical record unavailable`}
      description="Narrative-only legacy risk · family and claim identity not inferred"
    >
      <div
        className="praviar-risk-docket-row grid gap-3 rounded-lg p-3 sm:grid-cols-[3rem_minmax(0,1fr)]"
        data-testid={`risk-docket-${index + 1}`}
      >
        <DocketIndex value={identifier} label="Driver" />
        <div className="min-w-0">
          <p className="rounded-md border border-warning/25 bg-warning/5 p-3 text-xs font-semibold leading-5 text-warning">
            Canonical blocker-family record unavailable. Patent, family, claim,
            owner, status, and evidence bindings are deliberately not inferred
            from this narrative.
          </p>
          <p className="mt-3 text-sm leading-6 text-[var(--text-primary)]">
            {risk}
          </p>
        </div>
      </div>
    </ReportMobileDisclosure>
  );
}

function DocketIndex({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex items-center gap-2 sm:block">
      <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border border-error/20 bg-error/10 text-xs font-bold tabular-nums text-error">
        {value}
      </span>
      <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)] sm:mt-2 sm:block">
        {label}
      </span>
    </div>
  );
}

function RiskDatum({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/65 px-3 py-2">
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 min-w-0 break-words text-sm font-semibold leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {children}
      </dd>
    </div>
  );
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values.filter((value) => value.trim()))].sort();
}

function formatPosture(value: string | undefined): string {
  return value?.trim() ? value.replaceAll("_", " ") : "not assessed";
}
