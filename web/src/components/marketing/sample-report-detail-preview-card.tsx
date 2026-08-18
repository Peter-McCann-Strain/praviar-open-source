"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { MoleculeViewer2D } from "@/components/chemistry/molecule-viewer-2d";
import { FtoDossierPreview } from "@/components/brand";
import type { DossierEvidenceRow, DossierRiskDriver } from "@/components/brand";
import type { DemoArtifactPayload } from "@/marketing/live-demo";

interface SampleReportDetailPreviewCardProps {
  demoArtifact: DemoArtifactPayload;
  className?: string;
  compactItemLimit?: number;
  mobileDisclosure?: boolean;
  mobileSummaryOnly?: boolean;
  mobileVisualHidden?: boolean;
}

export function SampleReportDetailPreviewCard({
  demoArtifact,
  className,
  compactItemLimit,
  mobileDisclosure = false,
  mobileSummaryOnly = false,
  mobileVisualHidden = false,
}: SampleReportDetailPreviewCardProps) {
  const [mobileExpanded, setMobileExpanded] = useState(false);
  const riskDrivers: DossierRiskDriver[] =
    demoArtifact.keyFindings.length > 0
      ? demoArtifact.keyFindings.map((finding, index) => ({
          label: `Driver ${index + 1}`,
          reference:
            demoArtifact.evidenceRows?.[index]?.patentId ??
            demoArtifact.claimSnapshot.patentId,
          detail: finding,
          severity:
            demoArtifact.evidenceRows?.[index]?.riskLevel ??
            demoArtifact.verdict,
        }))
      : demoArtifact.claimSnapshot.elements.map((element) => ({
          label: element.label,
          reference: `${demoArtifact.claimSnapshot.patentId} claim ${demoArtifact.claimSnapshot.claimNumber}`,
          detail: element.evidence,
          severity: demoArtifact.verdict,
        }));
  const evidenceRows: DossierEvidenceRow[] =
    demoArtifact.evidenceRows?.map((row) => ({
      reference: row.patentId,
      assignee: row.assignee,
      claimReference: row.claimReference,
      expiry: row.expiryDate ?? undefined,
      rationale: row.rationale,
      risk: row.riskLevel,
      sourceLabel: row.sourceLabel,
      sourceUrl: row.sourceUrl,
    })) ?? [];

  const dossierPreview = (
    <FtoDossierPreview
      compact
      compactItemLimit={compactItemLimit}
      mobileSummaryOnly={mobileSummaryOnly}
      mobileVisualHidden={mobileVisualHidden}
      className={mobileDisclosure ? undefined : className}
      compoundName={demoArtifact.compoundName}
      risk={demoArtifact.verdict}
      summary={demoArtifact.executiveSummary.split("\n\n")[0]}
      metrics={[
        {
          label: "Sample families flagged",
          value: String(demoArtifact.familiesFlaggedForReviewCount),
        },
        {
          label: "Sample records reviewed",
          value: String(demoArtifact.patentsAnalyzed),
        },
        { label: "Illustrative timing", value: demoArtifact.runtimeLabel },
      ]}
      riskDrivers={riskDrivers}
      evidenceRows={evidenceRows}
      claimPreview={{
        title: demoArtifact.claimSnapshot.patentTitle,
        reference: `${demoArtifact.claimSnapshot.patentId} · claim ${demoArtifact.claimSnapshot.claimNumber}`,
        text:
          demoArtifact.claimSnapshot.elements[0]?.evidence ??
          demoArtifact.claimSnapshot.claimStatus,
        rationale: demoArtifact.designAround,
      }}
      visual={
        <MoleculeViewer2D
          smiles={demoArtifact.canonicalSmiles}
          width={320}
          height={220}
          label={demoArtifact.compoundName}
          className="mx-auto min-h-[200px] border-0 bg-transparent"
        />
      }
      eyebrow="Synthetic FTO dossier"
      evidenceLabel={`${demoArtifact.patentsAnalyzed} fictional records reviewed`}
      statusLabel="Fictional sample"
      riskLabelOverrides={{
        high: "High sample priority",
        medium: "Medium sample priority",
        low: "Low sample priority",
        clear: "No overlap in sample",
      }}
      provenanceItems={[
        demoArtifact.sourceReference,
        "Fictional product data",
        "Not a legal opinion",
      ]}
    />
  );

  if (!mobileDisclosure) {
    return dossierPreview;
  }

  return (
    <div className={className}>
      <div className="group" data-testid="founder-dossier-disclosure">
        <button
          type="button"
          aria-expanded={mobileExpanded}
          aria-controls="founder-dossier-mobile-content"
          onClick={() => setMobileExpanded((expanded) => !expanded)}
          className="praviar-glass-panel-soft flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 rounded-lg px-4 py-3 text-left marker:content-none lg:hidden"
        >
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              Inspect synthetic dossier evidence
            </span>
            <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">
              {demoArtifact.patentsAnalyzed} fictional records reviewed
            </span>
          </span>
          <ChevronDown
            className={`h-4 w-4 shrink-0 text-[var(--text-tertiary)] transition-transform ${
              mobileExpanded ? "rotate-180" : ""
            }`}
            aria-hidden="true"
          />
        </button>
        <div
          id="founder-dossier-mobile-content"
          data-testid="founder-dossier-content"
          className={`${mobileExpanded ? "mt-3 block" : "hidden"} lg:mt-0 lg:block`}
        >
          {dossierPreview}
        </div>
      </div>
    </div>
  );
}
