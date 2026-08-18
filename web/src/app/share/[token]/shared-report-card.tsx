import type { ReactNode } from "react";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Database,
  FileLock2,
  FileWarning,
  MapPinned,
  RefreshCw,
  Scale,
  ShieldCheck,
  TimerReset,
} from "lucide-react";
import { FtoDossierPreview } from "@/components/brand";
import type { DossierEvidenceRow, DossierRiskDriver } from "@/components/brand";
import { sanitizeReportDiagnosticText } from "@/components/report/report-diagnostic-copy";
import { RiskBadge } from "@/components/shared/risk-badge";
import type { RiskLevel } from "@praviar/shared-types";
import type {
  KeyPatent,
  SharedReport,
  SharedReportIntegritySummary,
} from "./shared-report-types";
import { sanitizePublicEvidenceUrl } from "./public-evidence-url";

const PUBLIC_RISK_LABEL_OVERRIDES = {
  clear: "NO BLOCKERS SURFACED",
} satisfies Partial<Record<string, string>>;

const PUBLIC_SOURCE_LABELS: Record<string, string> = {
  bigquery: "Google patent datasets",
  epo_ops: "EPO OPS",
  google_patents: "Google Patents",
  google_patents_public_datasets: "Google patent datasets",
  patentsview: "PatentsView",
  pubchem_sdq: "PubChem SDQ",
  uspto: "USPTO",
};

type NormalizedKeyPatent = Omit<KeyPatent, "risk_level"> & {
  risk_level: RiskLevel;
};

/**
 * Renders the public, read-only shared FTO report summary. Shared between the
 * server-rendered share page and the client-side mailbox-verified render so both
 * paths produce identical output.
 *
 * The "Generated" date is intentionally formatted with the fixed `en-US`
 * locale (not the viewer's locale) so the value is deterministic regardless of
 * whether this component renders on the server or the client - avoiding a
 * hydration mismatch and inconsistent output across environments.
 */
export function SharedReportCard({
  report,
  headingLevel = 1,
}: {
  report: SharedReport;
  headingLevel?: 1 | 2;
}) {
  const ScreenReaderHeading = headingLevel === 1 ? "h1" : "h2";
  const compoundName = textOrFallback(report.compound_name, "Shared compound");
  const overallRisk = normalizeSharedRisk(report.overall_risk);
  const blockingPatentsCount = nonNegativeCount(report.blocking_patents_count);
  const totalPatentsFound = nonNegativeCount(report.total_patents_found);
  const executiveSummary = textOrFallback(
    report.executive_summary,
    "This shared report did not include an executive summary.",
  );
  const keyFindings = textList(report.key_findings);
  const generatedLabel =
    formatSharedReportDate(report.generated_at) ?? "Generated date unavailable";
  const expiresLabel = formatSharedReportDate(report.share_expires_at);
  const verifiedSessionExpiresLabel = formatSharedReportDateTime(
    report.verified_session_expires_at,
  );
  const sourceSnapshotLabel =
    formatSharedReportDate(report.source_snapshot_at) ?? generatedLabel;
  const patents = normalizeSharedKeyPatents(report.key_patents, overallRisk);
  const totalMaterialPatents = nonNegativeCount(report.total_material_patents);
  const omittedKeyPatentsCount = nonNegativeCount(
    report.omitted_key_patents_count,
  );
  const omittedLimitationsCount = nonNegativeCount(
    report.omitted_limitations_count,
  );
  const patentLabel = `${patents.length} key ${
    patents.length === 1 ? "patent" : "patents"
  }`;
  const evidenceIncludedLabel =
    omittedKeyPatentsCount > 0 && totalMaterialPatents > patents.length
      ? `${patents.length} of ${totalMaterialPatents} reviewed patents shown`
      : patentLabel;
  const hasBlockers = blockingPatentsCount > 0;
  const postureLabel =
    overallRisk === "clear"
      ? "NO BLOCKERS SURFACED"
      : overallRisk.toUpperCase();
  const sourceCoverage = textList(report.source_coverage);
  const jurisdictionScope = textList(report.jurisdiction_scope);
  const evidenceLimitations = textList(report.evidence_limitations).map(
    (limitation) =>
      sanitizeReportDiagnosticText(
        limitation,
        "Evidence caveat requires counsel review.",
      ),
  );
  const standardLimitations = textList(report.standard_limitations).map(
    (limitation) =>
      sanitizeReportDiagnosticText(
        limitation,
        "Standard limitation requires counsel review.",
      ),
  );
  const integritySummary = normalizeSharedIntegritySummary(
    report.integrity_summary,
  );
  const hasEvidenceCaveats =
    evidenceLimitations.length > 0 ||
    omittedKeyPatentsCount > 0 ||
    omittedLimitationsCount > 0 ||
    integritySummary.affectedPatentsCount > 0 ||
    integritySummary.sourceCaveatsCount > 0 ||
    integritySummary.metadataInconsistent ||
    !integritySummary.evidenceSufficientForClearance;
  const needsRecipientCounselReview =
    hasEvidenceCaveats ||
    hasBlockers ||
    overallRisk === "high" ||
    overallRisk === "medium";
  const relianceLabel = needsRecipientCounselReview
    ? "Counsel verification required"
    : "Screening only";
  const previewNoticeTitle = hasEvidenceCaveats
    ? "Partial evidence: counsel verification required"
    : overallRisk === "high"
      ? "IP/legal review recommended"
      : "AI-assisted screening only";
  const jurisdictionLabel =
    jurisdictionScope.length > 0
      ? jurisdictionScope.join(", ")
      : "Report scope";
  const sourceCoverageLabel =
    sourceCoverage.length > 0
      ? sourceCoverage.map(formatPublicSourceLabel).join(", ")
      : "Report evidence";
  const expiresValue = expiresLabel ?? "Sender-managed";
  const emptyEvidenceMessage =
    jurisdictionScope.length > 0 || sourceCoverage.length > 0
      ? `No key patents were included in this shared view for ${jurisdictionLabel} using ${sourceCoverageLabel}. Review the summary and source scope with qualified counsel before relying on the screening posture.`
      : "No key patents were included in this shared view. Review the summary and source scope with qualified counsel before relying on the screening posture.";
  const packageSummary = `This read-only report package summarizes the preliminary patent risk posture, ${
    hasBlockers ? "material blockers" : "review scope"
  }, evidence scope, and counsel verification boundaries.`;
  const intendedUse = textOrFallback(
    report.intended_use,
    "Read-only external FTO screening packet for qualified patent counsel review.",
  );
  const aiSystemNotice = textOrFallback(
    report.ai_system_notice,
    "AI-assisted patent landscape analysis; outputs require human review before reliance.",
  );
  const relianceBoundary = textOrFallback(
    report.reliance_boundary,
    "Not a legal clearance opinion or freedom-to-operate opinion.",
  );
  const riskDrivers: DossierRiskDriver[] = keyFindings.map((finding, index) => {
    const matchedPatent = findPatentMention(finding, patents);
    return {
      label: `Finding ${index + 1}`,
      reference: matchedPatent?.patent_number ?? "Shared finding",
      detail: finding,
      severity: matchedPatent?.risk_level ?? overallRisk,
    };
  });
  const evidenceRows: DossierEvidenceRow[] = patents.map((patent) => ({
    reference: patent.patent_number,
    assignee: patent.assignee,
    claimReference: "Claim relevance",
    expiry: patent.expiry,
    sourceLabel: patent.source_reference,
    sourceUrl: getSafePublicSourceUrl(patent.patent_url),
    rationale:
      findPatentFinding(patent.patent_number, keyFindings) ??
      "Included in the shared report for counsel review.",
    risk: patent.risk_level,
  }));
  const packetProvenanceItems = [
    {
      label: "Packet reference",
      value:
        textOrFallback(report.report_id, "") ||
        textOrFallback(report.share_id, "") ||
        "Not supplied in compact view",
    },
    {
      label: "Packet version",
      value: textOrFallback(report.packet_version, "Public share v1"),
    },
    {
      label: "Source snapshot",
      value: sourceSnapshotLabel,
    },
    {
      label: "Pipeline/model",
      value:
        report.pipeline_version || report.model_version
          ? [report.pipeline_version, report.model_version]
              .filter(Boolean)
              .join(" / ")
          : "Not supplied in compact view",
    },
    {
      label: "Integrity digest",
      value: textOrFallback(
        report.integrity_digest,
        "Not supplied in compact view",
      ),
    },
  ];

  return (
    <div className="space-y-5" data-praviar-share-report>
      <ScreenReaderHeading className="sr-only">
        {compoundName} shared FTO report
      </ScreenReaderHeading>

      <section
        aria-label="Verified recipient session"
        className="relative flex flex-col gap-2 rounded-lg border border-brand-primary/30 bg-[color-mix(in_srgb,var(--bg-surface)_94%,var(--brand-primary)_6%)] px-4 py-3 shadow-[var(--shadow-md)] sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-brand-primary">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            Attributable verified view
          </p>
          <p
            className="mt-1 break-words text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]"
            title={report.verified_recipient_email}
          >
            {report.verified_recipient_email}
          </p>
        </div>
        <p className="text-xs leading-5 text-[var(--text-secondary)] sm:text-right">
          View {report.attributable_view_number}
          <br />
          Session expires {verifiedSessionExpiresLabel ?? "soon"}
        </p>
      </section>

      <FtoDossierPreview
        compoundName={compoundName}
        risk={overallRisk}
        summary={executiveSummary}
        metrics={[
          {
            label: "Blocking",
            value: String(blockingPatentsCount),
          },
          {
            label: "Found",
            value: totalPatentsFound.toLocaleString(),
          },
          { label: "Posture", value: postureLabel },
        ]}
        riskDrivers={riskDrivers}
        evidenceRows={evidenceRows}
        eyebrow="Shared preliminary report"
        scopeLabel="Read-only FTO view"
        evidenceLabel={evidenceIncludedLabel}
        statusLabel="Shared view"
        notice={{
          tone:
            hasEvidenceCaveats || overallRisk === "high" ? "warning" : "info",
          title: previewNoticeTitle,
          body: "This shared report is a structured first pass for review by qualified patent counsel. It is not a legal clearance opinion.",
        }}
        provenanceItems={[
          generatedLabel,
          `${jurisdictionLabel} scope`,
          "Read-only",
          "Not a legal opinion",
        ]}
        emptyEvidenceMessage={emptyEvidenceMessage}
        riskLabelOverrides={PUBLIC_RISK_LABEL_OVERRIDES}
      />

      <section
        aria-label="Shared report trust summary"
        className="light z-20 overflow-hidden rounded-lg border border-[var(--border-emphasis)] bg-[color-mix(in_srgb,var(--bg-elevated)_97%,transparent)] shadow-[var(--shadow-md)] backdrop-blur-xl md:sticky md:top-3"
        data-praviar-share-trust-bar
      >
        <div className="grid grid-cols-2 gap-0 lg:grid-cols-4">
          <ShareTrustSignal
            label="Risk posture"
            value={
              <RiskBadge risk={overallRisk} showIcon label={postureLabel} />
            }
          />
          <ShareTrustSignal
            label="Evidence included"
            value={evidenceIncludedLabel}
            icon={<Database className="h-4 w-4" aria-hidden="true" />}
          />
          <ShareTrustSignal
            label="Jurisdiction scope"
            value={jurisdictionLabel}
            icon={<MapPinned className="h-4 w-4" aria-hidden="true" />}
          />
          <ShareTrustSignal
            label="Reliance status"
            value={relianceLabel}
            icon={
              hasEvidenceCaveats ? (
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              ) : (
                <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              )
            }
          />
        </div>
      </section>

      <SharedDecisionSnapshotPanel
        blockingPatentsCount={blockingPatentsCount}
        evidenceIncludedLabel={evidenceIncludedLabel}
        expiresLabel={expiresValue}
        hasEvidenceCaveats={hasEvidenceCaveats}
        omittedKeyPatentsCount={omittedKeyPatentsCount}
        overallRisk={overallRisk}
        postureLabel={postureLabel}
        topPatentLabel={patents[0]?.patent_number ?? "No key patents shown"}
      />

      <SharedPacketReceiptPanel
        evidenceIncludedLabel={evidenceIncludedLabel}
        expiresLabel={expiresValue}
        generatedLabel={generatedLabel}
        jurisdictionLabel={jurisdictionLabel}
        packetProvenanceItems={packetProvenanceItems}
        relianceBoundary={relianceBoundary}
        reviewStatus={formatWorkspaceReviewStatus(report.review_status)}
        sourceCoverageLabel={sourceCoverageLabel}
      />

      <SharedRelianceStatusPanel
        evidenceLimitations={evidenceLimitations}
        expiresLabel={expiresValue}
        hasEvidenceCaveats={hasEvidenceCaveats}
        integritySummary={integritySummary}
        aiSystemNotice={aiSystemNotice}
        intendedUse={intendedUse}
        omittedKeyPatentsCount={omittedKeyPatentsCount}
        omittedLimitationsCount={omittedLimitationsCount}
        overallRisk={overallRisk}
        relianceBoundary={relianceBoundary}
        standardLimitations={standardLimitations}
      />

      <SharedRecipientReviewPanel
        evidenceIncludedLabel={evidenceIncludedLabel}
        hasEvidenceCaveats={hasEvidenceCaveats}
        jurisdictionLabel={jurisdictionLabel}
        omittedKeyPatentsCount={omittedKeyPatentsCount}
        overallRisk={overallRisk}
        patentLabel={patentLabel}
        sourceCoverageLabel={sourceCoverageLabel}
      />

      <section
        aria-label="Shared report access and evidence scope"
        className="light border-y border-[var(--border-default)] bg-[var(--surface-muted)] px-5 py-5 sm:px-6 lg:px-7"
      >
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 max-w-2xl">
            <div className="flex flex-wrap items-center gap-2">
              <RiskBadge risk={overallRisk} showIcon label={postureLabel} />
              <span className="praviar-glass-pill rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                {patentLabel}
              </span>
              <span className="praviar-glass-pill rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                {generatedLabel}
              </span>
            </div>
            <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">
              {packageSummary}
            </p>
          </div>

          <dl className="grid gap-3 sm:grid-cols-3 lg:w-[24rem] lg:grid-cols-1">
            <ShareDossierFact
              icon={<CalendarClock className="h-4 w-4" aria-hidden="true" />}
              label="Generated"
              value={generatedLabel}
            />
            <ShareDossierFact
              icon={<FileLock2 className="h-4 w-4" aria-hidden="true" />}
              label="Access"
              value="Read-only view"
            />
            <ShareDossierFact
              icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
              label="Workspace review"
              value={formatWorkspaceReviewStatus(report.review_status)}
            />
          </dl>
        </div>

        <div className="mt-5 grid gap-4 border-t border-[var(--border-default)] pt-4 sm:grid-cols-3">
          <ShareEvidenceScope label="Jurisdictions" value={jurisdictionLabel} />
          <ShareEvidenceScope label="Sources" value={sourceCoverageLabel} />
          <ShareEvidenceScope label="Link expires" value={expiresValue} />
        </div>

        <div className="mt-5 border-t border-[var(--border-default)] pt-4">
          <div className="flex gap-3 text-sm leading-6 text-[var(--text-secondary)]">
            <FileWarning
              className="mt-0.5 h-4 w-4 shrink-0 text-[var(--brand-primary)]"
              aria-hidden="true"
            />
            <p>
              AI-assisted preliminary screening only. This share does not
              provide a legal clearance opinion and should be verified by
              qualified patent counsel before commercial decisions.
            </p>
          </div>
          {evidenceLimitations.length > 0 ? (
            <ul className="mt-3 grid gap-2 text-xs leading-5 text-[var(--text-tertiary)] sm:grid-cols-2">
              {evidenceLimitations.map((limitation, index) => (
                <li
                  key={`${limitation}-${index}`}
                  className="praviar-code-surface rounded-lg px-3 py-2 break-words [overflow-wrap:anywhere]"
                >
                  {sanitizeReportDiagnosticText(
                    limitation,
                    "Evidence caveat requires counsel review.",
                  )}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function SharedDecisionSnapshotPanel({
  blockingPatentsCount,
  evidenceIncludedLabel,
  expiresLabel,
  hasEvidenceCaveats,
  omittedKeyPatentsCount,
  overallRisk,
  postureLabel,
  topPatentLabel,
}: {
  blockingPatentsCount: number;
  evidenceIncludedLabel: string;
  expiresLabel: string;
  hasEvidenceCaveats: boolean;
  omittedKeyPatentsCount: number;
  overallRisk: RiskLevel;
  postureLabel: string;
  topPatentLabel: string;
}) {
  const needsReview =
    hasEvidenceCaveats || overallRisk === "high" || overallRisk === "medium";
  const topEvidenceLabel =
    omittedKeyPatentsCount > 0
      ? `${topPatentLabel} + ${omittedKeyPatentsCount} omitted`
      : topPatentLabel;

  const decisionItems = [
    {
      icon:
        overallRisk === "high" || overallRisk === "medium" ? (
          <AlertTriangle className="h-4 w-4" aria-hidden="true" />
        ) : (
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
        ),
      label: "Risk answer",
      value: postureLabel,
      detail: needsReview
        ? "Route to qualified patent counsel before reliance."
        : "Screening basis visible; no clearance opinion is created.",
      tone: needsReview ? "warning" : "default",
    },
    {
      icon: <Scale className="h-4 w-4" aria-hidden="true" />,
      label: "Blocking patents",
      value: blockingPatentsCount.toLocaleString(),
      detail:
        blockingPatentsCount > 0
          ? "Material blockers should lead recipient triage."
          : "No blockers shown in this compact public packet.",
      tone: blockingPatentsCount > 0 ? "warning" : "default",
    },
    {
      icon: <Database className="h-4 w-4" aria-hidden="true" />,
      label: "Top evidence",
      value: topEvidenceLabel,
      detail: evidenceIncludedLabel,
      tone: omittedKeyPatentsCount > 0 ? "warning" : "default",
    },
    {
      icon: <TimerReset className="h-4 w-4" aria-hidden="true" />,
      label: "Validity window",
      value: expiresLabel,
      detail: "Use this before the sender-managed share expires.",
      tone: "default",
    },
  ];

  return (
    <section
      aria-label="Shared decision snapshot"
      className="light overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] shadow-[var(--shadow-sm)]"
      data-praviar-share-decision-snapshot
    >
      <div className="grid gap-0 xl:grid-cols-[minmax(15rem,0.3fr)_minmax(0,1fr)]">
        <div className="border-b border-[var(--border-default)] bg-[var(--surface-muted)] px-5 py-4 sm:px-6 xl:border-b-0 xl:border-r">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--brand-primary)]">
            Decision snapshot
          </p>
          <h2 className="mt-2 text-lg font-semibold leading-7 text-[var(--text-primary)]">
            Start with the business answer
          </h2>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            Recipient triage begins with risk posture, blockers, evidence, and
            validity before packet details.
          </p>
        </div>
        <div className="grid gap-0 sm:grid-cols-2 xl:grid-cols-4">
          {decisionItems.map((item) => (
            <div
              key={item.label}
              className="min-w-0 border-b border-[var(--border-subtle)] px-4 py-4 sm:border-r sm:even:border-r-0 xl:border-b-0 xl:border-r xl:even:border-r xl:last:border-r-0"
            >
              <div className="flex min-w-0 items-start gap-3">
                <span
                  className={[
                    "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
                    item.tone === "warning"
                      ? "border-warning/25 bg-warning/10 text-warning"
                      : "border-brand-primary/15 bg-brand-primary/10 text-brand-primary",
                  ].join(" ")}
                >
                  {item.icon}
                </span>
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    {item.label}
                  </p>
                  <p className="mt-1 break-words text-sm font-semibold leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {item.value}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                    {item.detail}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SharedPacketReceiptPanel({
  evidenceIncludedLabel,
  expiresLabel,
  generatedLabel,
  jurisdictionLabel,
  packetProvenanceItems,
  relianceBoundary,
  reviewStatus,
  sourceCoverageLabel,
}: {
  evidenceIncludedLabel: string;
  expiresLabel: string;
  generatedLabel: string;
  jurisdictionLabel: string;
  packetProvenanceItems: Array<{ label: string; value: string }>;
  relianceBoundary: string;
  reviewStatus: string;
  sourceCoverageLabel: string;
}) {
  const receiptItems = [
    { label: "Generated", value: generatedLabel },
    { label: "Share expiry", value: expiresLabel },
    { label: "Review status", value: reviewStatus },
    { label: "Jurisdictions", value: jurisdictionLabel },
    { label: "Sources", value: sourceCoverageLabel },
    { label: "Evidence shown", value: evidenceIncludedLabel },
  ];

  return (
    <section
      aria-label="Shared packet receipt"
      className="light overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] shadow-[var(--shadow-sm)]"
      data-praviar-share-packet-receipt
    >
      <div className="grid gap-0 lg:grid-cols-[minmax(0,0.34fr)_minmax(0,1fr)]">
        <div className="border-b border-[var(--border-default)] bg-[var(--surface-muted)] px-5 py-4 sm:px-6 lg:border-b-0 lg:border-r">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--brand-primary)]">
            Packet receipt
          </p>
          <h2 className="mt-2 text-lg font-semibold leading-7 text-[var(--text-primary)]">
            Sender-controlled evidence record
          </h2>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            A compact receipt for recipients to preserve alongside counsel
            review, procurement records, or board diligence notes.
          </p>
        </div>
        <div className="min-w-0 p-4 sm:p-5">
          <dl className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {receiptItems.map((item) => (
              <div
                key={item.label}
                className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/75 px-3 py-2.5"
              >
                <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  {item.label}
                </dt>
                <dd className="mt-1 text-sm font-semibold leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {item.value}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-3 rounded-lg border border-brand-primary/15 bg-brand-primary/5 px-3 py-2.5">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-brand-primary">
              Reliance boundary
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
              {relianceBoundary}
            </p>
          </div>
          <section
            aria-label="Shared packet provenance"
            className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/58 p-3"
          >
            <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand-primary)]">
                  Packet provenance
                </p>
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                  Preserve with diligence notes
                </h3>
              </div>
              <p className="text-xs leading-5 text-[var(--text-secondary)]">
                Compact identifiers for reconciling this public view with the
                sender workspace.
              </p>
            </div>
            <dl className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
              {packetProvenanceItems.map((item) => (
                <div
                  key={item.label}
                  className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 px-3 py-2"
                >
                  <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    {item.label}
                  </dt>
                  <dd className="mt-1 text-xs font-semibold leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {item.value}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        </div>
      </div>
    </section>
  );
}

function SharedRecipientReviewPanel({
  evidenceIncludedLabel,
  hasEvidenceCaveats,
  jurisdictionLabel,
  omittedKeyPatentsCount,
  overallRisk,
  patentLabel,
  sourceCoverageLabel,
}: {
  evidenceIncludedLabel: string;
  hasEvidenceCaveats: boolean;
  jurisdictionLabel: string;
  omittedKeyPatentsCount: number;
  overallRisk: RiskLevel;
  patentLabel: string;
  sourceCoverageLabel: string;
}) {
  const riskNeedsCounsel = overallRisk === "high" || overallRisk === "medium";
  const actions = [
    {
      icon: <Database className="h-4 w-4" aria-hidden="true" />,
      label: "Confirm evidence scope",
      detail: `${jurisdictionLabel} jurisdiction scope with ${sourceCoverageLabel}.`,
      status: "Scope visible",
    },
    {
      icon: <Scale className="h-4 w-4" aria-hidden="true" />,
      label: riskNeedsCounsel
        ? "Prioritize counsel review"
        : "Document screening basis",
      detail: riskNeedsCounsel
        ? `${evidenceIncludedLabel}; start with the listed material patents and request the full packet for claim-chart review.`
        : `${patentLabel}; preserve this screening record with the sender before relying on absence of blockers.`,
      status: riskNeedsCounsel ? "Counsel first" : "Screening record",
    },
    {
      icon: <FileWarning className="h-4 w-4" aria-hidden="true" />,
      label: "Carry forward caveats",
      detail: hasEvidenceCaveats
        ? "Evidence limitations are part of the shared artifact and should stay attached to any downstream review."
        : "No additional public caveats were included, but this remains a non-opinion screening artifact.",
      status: hasEvidenceCaveats ? "Caveats active" : "Boundary active",
    },
    {
      icon: <ShieldCheck className="h-4 w-4" aria-hidden="true" />,
      label: "Request governed follow-up",
      detail:
        omittedKeyPatentsCount > 0
          ? `${omittedKeyPatentsCount} reviewed patents are omitted from this compact view; ask the sender for the full workspace packet or counsel export.`
          : "Use the sender workspace for full evidence, exports, and report-grounded AI follow-up; this public view stays read-only.",
      status: "No edits here",
    },
  ];

  return (
    <section
      aria-label="Recipient review workflow"
      className="light overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] shadow-[var(--shadow-sm)]"
      data-praviar-share-review-workflow
    >
      <div className="grid gap-0 lg:grid-cols-[minmax(0,0.42fr)_minmax(0,1fr)]">
        <div className="border-b border-[var(--border-default)] bg-[var(--surface-muted)] px-5 py-5 sm:px-6 lg:border-b-0 lg:border-r">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--brand-primary)]">
            Counsel triage
          </p>
          <h2 className="mt-2 text-lg font-semibold leading-7 text-[var(--text-primary)]">
            Decision path before reliance
          </h2>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            Use this public packet to sequence review first, caveats second, and
            full workspace follow-up before any commercial reliance.
          </p>
        </div>
        <div className="grid gap-0 sm:grid-cols-2">
          {actions.map((action) => (
            <div
              key={action.label}
              className="min-w-0 border-b border-[var(--border-subtle)] px-4 py-4 sm:border-r sm:even:border-r-0 [&:nth-last-child(-n+2)]:sm:border-b-0"
            >
              <div className="flex min-w-0 items-start gap-3">
                <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-brand-primary/15 bg-brand-primary/10 text-brand-primary">
                  {action.icon}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {action.label}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                    {action.detail}
                  </p>
                  <span className="mt-2 inline-flex max-w-full items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    <span className="min-w-0 truncate">{action.status}</span>
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SharedRelianceStatusPanel({
  aiSystemNotice,
  evidenceLimitations,
  expiresLabel,
  hasEvidenceCaveats,
  integritySummary,
  intendedUse,
  omittedKeyPatentsCount,
  omittedLimitationsCount,
  overallRisk,
  relianceBoundary,
  standardLimitations,
}: {
  aiSystemNotice: string;
  evidenceLimitations: string[];
  expiresLabel: string;
  hasEvidenceCaveats: boolean;
  integritySummary: NormalizedSharedIntegritySummary;
  intendedUse: string;
  omittedKeyPatentsCount: number;
  omittedLimitationsCount: number;
  overallRisk: RiskLevel;
  relianceBoundary: string;
  standardLimitations: string[];
}) {
  const relianceReviewRequired =
    hasEvidenceCaveats || overallRisk === "high" || overallRisk === "medium";
  const partialEvidenceValue =
    integritySummary.affectedPatentsCount > 0
      ? `${integritySummary.affectedPatentsCount} affected`
      : omittedKeyPatentsCount > 0
        ? `${omittedKeyPatentsCount} omitted`
        : omittedLimitationsCount > 0
          ? `${omittedLimitationsCount} caveat${omittedLimitationsCount === 1 ? "" : "s"} omitted`
          : "None reported";

  return (
    <section
      aria-label="External reliance status"
      role={hasEvidenceCaveats ? "status" : undefined}
      className={[
        "light overflow-hidden rounded-lg border shadow-[var(--shadow-sm)]",
        hasEvidenceCaveats
          ? "border-warning/25 bg-warning/5"
          : "border-[var(--border-default)] bg-[var(--bg-elevated)]",
      ].join(" ")}
      data-praviar-share-reliance-status
    >
      <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(17rem,0.34fr)]">
        <div className="min-w-0 p-5 sm:p-6">
          <div className="flex min-w-0 items-start gap-3">
            <span
              className={[
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border",
                hasEvidenceCaveats
                  ? "border-warning/25 bg-warning/10 text-warning"
                  : "border-brand-primary/20 bg-brand-primary/10 text-brand-primary",
              ].join(" ")}
            >
              {hasEvidenceCaveats ? (
                <AlertTriangle className="h-5 w-5" aria-hidden="true" />
              ) : (
                <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand-primary)]">
                External reliance status
              </p>
              <h2 className="mt-1 text-lg font-semibold leading-7 text-[var(--text-primary)]">
                {hasEvidenceCaveats
                  ? "Partial evidence: counsel verification required"
                  : "Screening only: no legal clearance opinion"}
              </h2>
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                {hasEvidenceCaveats
                  ? "This shared view remains useful for review, but caveats must travel with the report before anyone treats it as clearance support."
                  : "This shared view is a read-only screening artifact. Qualified patent counsel should verify conclusions before commercial reliance."}
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <ShareRelianceMetric
              icon={<FileWarning className="h-3.5 w-3.5" aria-hidden="true" />}
              label="Partial evidence"
              value={partialEvidenceValue}
              tone={
                partialEvidenceValue === "None reported" ? "default" : "warning"
              }
            />
            <ShareRelianceMetric
              icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
              label="Recoverable"
              value={`${integritySummary.recoverableFailuresCount}`}
              tone={
                integritySummary.recoverableFailuresCount > 0
                  ? "warning"
                  : "default"
              }
            />
            <ShareRelianceMetric
              icon={<Scale className="h-3.5 w-3.5" aria-hidden="true" />}
              label="Reliance review"
              value={relianceReviewRequired ? "Required" : "Recommended"}
              tone={relianceReviewRequired ? "warning" : "default"}
            />
            <ShareRelianceMetric
              icon={<TimerReset className="h-3.5 w-3.5" aria-hidden="true" />}
              label="Link expires"
              value={expiresLabel}
              tone="default"
            />
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <ShareRelianceCopy label="Intended use" value={intendedUse} />
            <ShareRelianceCopy
              label="AI system notice"
              value={aiSystemNotice}
            />
            <ShareRelianceCopy
              label="Reliance boundary"
              value={relianceBoundary}
            />
          </div>
        </div>

        <div className="border-t border-[var(--border-default)] p-5 sm:p-6 lg:border-l lg:border-t-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Evidence caveats
          </p>
          {evidenceLimitations.length > 0 ? (
            <ul className="mt-3 grid gap-2 text-xs leading-5 text-[var(--text-secondary)]">
              {evidenceLimitations.map((limitation, index) => (
                <li
                  key={`${limitation}-${index}`}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/75 px-3 py-2 [overflow-wrap:anywhere]"
                >
                  {sanitizeReportDiagnosticText(
                    limitation,
                    "Evidence caveat requires counsel review.",
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
              No additional evidence caveats were included in this public share.
            </p>
          )}
          {omittedLimitationsCount > 0 ? (
            <p className="mt-3 rounded-lg border border-warning/20 bg-warning/10 px-3 py-2 text-xs font-semibold leading-5 text-[var(--text-primary)]">
              {omittedLimitationsCount} additional caveat
              {omittedLimitationsCount === 1 ? "" : "s"} omitted from this
              compact public view.
            </p>
          ) : null}
          {standardLimitations.length > 0 ? (
            <div className="mt-4 border-t border-[var(--border-default)] pt-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Standard limitations
              </p>
              <ul className="mt-3 grid gap-2 text-xs leading-5 text-[var(--text-secondary)]">
                {standardLimitations.map((limitation, index) => (
                  <li
                    key={`${limitation}-${index}`}
                    className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/75 px-3 py-2 [overflow-wrap:anywhere]"
                  >
                    {limitation}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-4 rounded-lg border border-brand-primary/15 bg-brand-primary/5 p-3">
            <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
              <ShieldCheck
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              No legal clearance opinion
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              The shared artifact preserves screening context; it does not
              modify findings, replace reviewer judgment, or create legal
              advice.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function ShareRelianceCopy({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-3">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
        {value}
      </p>
    </div>
  );
}

function ShareRelianceMetric({
  icon,
  label,
  tone,
  value,
}: {
  icon: ReactNode;
  label: string;
  tone: "default" | "warning";
  value: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/75 p-3">
      <p
        className={[
          "flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em]",
          tone === "warning" ? "text-warning" : "text-[var(--text-tertiary)]",
        ].join(" ")}
      >
        <span>{icon}</span>
        {label}
      </p>
      <p className="mt-1 max-w-full break-words text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {value}
      </p>
    </div>
  );
}

interface NormalizedSharedIntegritySummary {
  affectedPatentsCount: number;
  recoverableFailuresCount: number;
  needsReviewCount: number;
  dataLimitationsCount: number;
  sourceCaveatsCount: number;
  evidenceSufficientForClearance: boolean;
  metadataInconsistent: boolean;
}

function normalizeSharedIntegritySummary(
  value: SharedReportIntegritySummary | undefined,
): NormalizedSharedIntegritySummary {
  const affectedPatentsCount = nonNegativeCount(value?.affected_patents_count);
  const recoverableFailuresCount = Math.min(
    nonNegativeCount(value?.recoverable_failures_count),
    affectedPatentsCount,
  );
  return {
    affectedPatentsCount,
    recoverableFailuresCount,
    needsReviewCount: Math.max(
      nonNegativeCount(value?.needs_review_count),
      affectedPatentsCount - recoverableFailuresCount,
    ),
    dataLimitationsCount: nonNegativeCount(value?.data_limitations_count),
    sourceCaveatsCount: nonNegativeCount(value?.source_caveats_count),
    evidenceSufficientForClearance:
      value?.evidence_sufficient_for_clearance === true,
    metadataInconsistent: value?.metadata_inconsistent === true,
  };
}

function nonNegativeCount(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.floor(value)
    : 0;
}

function normalizeSharedRisk(value: unknown): RiskLevel {
  const normalized = String(value ?? "")
    .trim()
    .toLowerCase();
  if (
    normalized === "high" ||
    normalized === "medium" ||
    normalized === "low" ||
    normalized === "clear"
  ) {
    return normalized;
  }
  return "medium";
}

function textOrFallback(value: unknown, fallback: string): string {
  const text = typeof value === "string" ? value.trim() : "";
  return text || fallback;
}

function textList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}

function normalizeSharedKeyPatents(
  value: unknown,
  fallbackRisk: RiskLevel,
): NormalizedKeyPatent[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const patent = item as Partial<KeyPatent>;
    const patentNumber = textOrFallback(patent.patent_number, "");
    if (!patentNumber) {
      return [];
    }
    return [
      {
        patent_number: patentNumber,
        risk_level: normalizeSharedRisk(patent.risk_level ?? fallbackRisk),
        assignee: textOrFallback(patent.assignee, "") || undefined,
        expiry: textOrFallback(patent.expiry, "") || undefined,
        patent_url: textOrFallback(patent.patent_url, "") || undefined,
        source_reference:
          textOrFallback(patent.source_reference, "") || undefined,
      },
    ];
  });
}

function findPatentMention(
  text: string,
  patents: NormalizedKeyPatent[],
): NormalizedKeyPatent | undefined {
  const normalizedText = text.toUpperCase();
  return patents.find((patent) =>
    normalizedText.includes(patent.patent_number.toUpperCase()),
  );
}

function findPatentFinding(
  patentNumber: string,
  findings: string[],
): string | undefined {
  const normalizedPatent = patentNumber.toUpperCase();
  return findings.find((finding) =>
    finding.toUpperCase().includes(normalizedPatent),
  );
}

function getSafePublicSourceUrl(value?: string) {
  return sanitizePublicEvidenceUrl(value) ?? undefined;
}

function ShareTrustSignal({
  label,
  value,
  icon,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="min-w-0 border-b border-[var(--border-subtle)] px-3 py-2.5 sm:px-4 sm:py-3 lg:border-b-0 lg:border-r lg:last:border-r-0">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {icon ? (
          <span className="text-[var(--brand-primary)]">{icon}</span>
        ) : null}
        {label}
      </p>
      <div className="mt-1 min-h-6 max-w-full break-words text-sm font-semibold leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {value}
      </div>
    </div>
  );
}

function formatPublicSourceLabel(source: string) {
  const normalizedSource = source.trim().toLowerCase();
  return PUBLIC_SOURCE_LABELS[normalizedSource] ?? source;
}

function formatSharedReportDate(value: string | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(date);
}

function formatSharedReportDateTime(value: string | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(date);
}

function formatWorkspaceReviewStatus(value: string | undefined): string {
  const normalized = (value ?? "").trim().toLowerCase();
  if (!normalized) return "Workspace review gated";

  const labels: Record<string, string> = {
    approved: "Workspace review complete",
    pending_review: "Pending workspace review",
    rejected: "Workspace review returned",
    needs_revision: "Needs workspace revision",
    draft: "Workspace draft",
  };

  if (labels[normalized]) return labels[normalized];

  const humanized = normalized
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
  return `Workspace review: ${humanized}`;
}

function ShareDossierFact({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="praviar-glass-chip rounded-lg p-3">
      <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
        <span className="text-[var(--brand-primary)]">{icon}</span>
        {label}
      </dt>
      <dd className="mt-2 max-w-full break-words text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {value}
      </dd>
    </div>
  );
}

function ShareEvidenceScope({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 max-w-full break-words text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {value}
      </p>
    </div>
  );
}
