"use client";

import {
  Atom,
  Eye,
  FileSearch2,
  ScanSearch,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  DrawingGovernanceProvenance,
  FTOReport,
  PatentDrawingAnalysis,
} from "@praviar/shared-types";

import { DrawingStructureCard } from "./drawing-structure-card";

interface DrawingsTabProps {
  report: FTOReport;
}

/**
 * Drawings tab — surfaces extracted chemical structures from patent
 * drawings (Step 2.75 of the Praviar pipeline).
 *
 * Renders explicit missing-evidence messaging when ``drawing_analyses`` is
 * empty. Drawing evidence is never inferred from an absent analysis record.
 */
export function DrawingsTab({ report }: DrawingsTabProps) {
  const analyses = report.drawing_analyses ?? [];
  const allStructures = analyses.flatMap((a) => a.structures ?? []);
  const totalStructures = allStructures.length;
  const totalMarkush = allStructures.filter((s) => s.is_markush).length;
  const totalPatents = analyses.filter(
    (analysis) => (analysis.structures?.length ?? 0) > 0,
  ).length;

  if (totalStructures === 0) {
    return (
      <Card className="overflow-hidden border-warning/25">
        <CardHeader className="border-b border-[var(--border-subtle)] bg-warning/5 p-4 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-warning/25 bg-warning/10 text-warning">
                <Atom className="h-5 w-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-warning">
                  Structure-evidence boundary
                </p>
                <CardTitle className="mt-1 text-lg">
                  No governed drawing extracts are attached
                </CardTitle>
              </div>
            </div>
            <Badge variant="warning">Not assessed</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5 p-4 sm:p-6">
          <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
            The report contains no customer-visible structure extraction from
            patent figures. This is an evidence gap. Absence here does not
            establish that relevant molecules, scaffolds, or variable-group
            structures are absent from the source documents.
          </p>
          <dl className="grid gap-3 sm:grid-cols-3">
            <DrawingGapFact
              icon={ScanSearch}
              label="Extracted structures"
              value="0"
            />
            <DrawingGapFact
              icon={ShieldAlert}
              label="Coverage conclusion"
              value="Not available"
            />
            <DrawingGapFact
              icon={FileSearch2}
              label="Required next step"
              value="Inspect source figures"
            />
          </dl>
          <p className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3 text-xs leading-5 text-[var(--text-secondary)]">
            Review the material patent PDFs or run governed drawing extraction
            before relying on structure-level visual coverage.
          </p>
        </CardContent>
      </Card>
    );
  }

  const markushRatePct =
    totalStructures === 0
      ? 0
      : Math.round((totalMarkush / totalStructures) * 100);
  const governance = drawingGovernanceState(analyses);

  return (
    <div className="space-y-6">
      <DrawingGovernancePanel state={governance} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Atom className="h-5 w-5 text-brand-primary" aria-hidden="true" />
            Patent drawings · {totalStructures} structure
            {totalStructures === 1 ? "" : "s"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <SummaryStat label="Patents with drawings" value={totalPatents} />
            <SummaryStat label="Total structures" value={totalStructures} />
            <SummaryStat label="Markush templates" value={totalMarkush} />
            <SummaryStat label="Markush rate" value={`${markushRatePct}%`} />
          </div>
        </CardContent>
      </Card>

      {analyses.map((analysis) => {
        const structures = analysis.structures ?? [];
        if (structures.length === 0) return null;
        const pages = analysis.pages_fetched ?? 0;
        return (
          <section
            key={`${analysis.patent_id}-${pages}`}
            aria-label={`Drawings from ${analysis.patent_id}`}
            className="space-y-3"
          >
            <header className="flex items-baseline justify-between border-b border-[var(--border-default)] pb-2">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                {analysis.patent_id}
              </h3>
              <p className="text-xs text-[var(--text-disabled)]">
                {structures.length} structure
                {structures.length === 1 ? "" : "s"}
                {pages > 0 ? ` · ${pages} pages` : ""}
              </p>
            </header>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {structures.map((s, idx) => (
                <DrawingStructureCard
                  key={`${s.patent_id}-${s.page_number}-${s.structure_index}-${idx}`}
                  structure={s}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

type DrawingGovernanceState =
  | {
      kind: "blocked";
      title: string;
      detail: string;
    }
  | {
      kind: "shadow";
      title: string;
      detail: string;
      provenance: DrawingGovernanceProvenance;
    }
  | {
      kind: "live";
      title: string;
      detail: string;
      provenance: DrawingGovernanceProvenance;
    };

const SHA256_PATTERN = /^[a-f0-9]{64}$/i;
const OCI_DIGEST_PATTERN = /^sha256:[a-f0-9]{64}$/i;

function drawingGovernanceState(
  analyses: PatentDrawingAnalysis[],
): DrawingGovernanceState {
  const withStructures = analyses.filter(
    (analysis) => (analysis.structures?.length ?? 0) > 0,
  );
  const provenances = withStructures.map(
    (analysis) => analysis.governance_provenance,
  );

  if (provenances.some((provenance) => !provenance)) {
    return {
      kind: "blocked",
      title: "Governance provenance missing",
      detail:
        "One or more drawing extracts are not bound to a rollout, evidence gate, calibration, and runtime identity. Do not rely on them for a clearance decision.",
    };
  }

  const complete = provenances as DrawingGovernanceProvenance[];
  const identities = new Set(complete.map(governanceIdentity));
  if (identities.size !== 1) {
    return {
      kind: "blocked",
      title: "Mixed drawing evidence identities",
      detail:
        "The extracts were produced under different governance or runtime identities. Re-run them as one governed evidence set before review or export.",
    };
  }

  const provenance = complete[0];
  if (
    (provenance.rollout_state === "internal" ||
      provenance.rollout_state === "shadow") &&
    !provenance.influence_permitted &&
    !provenance.evidence_gate_passed
  ) {
    return {
      kind: "shadow",
      title: "Shadow evidence · non-influential",
      detail:
        "These extracts are visible for evaluation, but the pipeline did not allow them to affect claims, risk, or the clearance outcome.",
      provenance,
    };
  }

  const liveBindingsPresent =
    (provenance.rollout_state === "beta" ||
      provenance.rollout_state === "production") &&
    provenance.influence_permitted &&
    provenance.evidence_gate_passed &&
    SHA256_PATTERN.test(provenance.runtime_roster_sha256 ?? "") &&
    SHA256_PATTERN.test(provenance.ml_bom_sha256 ?? "") &&
    Boolean(provenance.calibration_artifact_id?.trim()) &&
    (provenance.calibration_artifact_revision ?? 0) > 0 &&
    SHA256_PATTERN.test(provenance.calibration_artifact_sha256 ?? "") &&
    OCI_DIGEST_PATTERN.test(provenance.worker_image_digest ?? "") &&
    (provenance.jurisdictions?.length ?? 0) > 0 &&
    Boolean(provenance.verified_at);

  if (!liveBindingsPresent) {
    return {
      kind: "blocked",
      title: "Live evidence bindings are incomplete",
      detail:
        "This evidence claims live influence but lacks one or more required release, calibration, jurisdiction, or immutable worker bindings. Counsel export is blocked.",
    };
  }

  return {
    kind: "live",
    title: "Governed live evidence",
    detail:
      "The displayed structures are bound to the verified release roster, ML bill of materials, calibration artifact, jurisdictions, and immutable worker image.",
    provenance,
  };
}

function governanceIdentity(provenance: DrawingGovernanceProvenance): string {
  return JSON.stringify([
    provenance.schema_version,
    provenance.rollout_state,
    provenance.influence_permitted,
    provenance.evidence_gate_passed,
    provenance.runtime_roster_sha256,
    provenance.ml_bom_sha256,
    provenance.calibration_artifact_id,
    provenance.calibration_artifact_revision,
    provenance.calibration_artifact_sha256,
    provenance.worker_image_digest,
    [...(provenance.jurisdictions ?? [])].sort(),
    provenance.verified_at,
  ]);
}

function DrawingGovernancePanel({ state }: { state: DrawingGovernanceState }) {
  const blocked = state.kind === "blocked";
  const shadow = state.kind === "shadow";
  const Icon = blocked ? ShieldX : shadow ? Eye : ShieldCheck;
  const badgeVariant = blocked ? "destructive" : shadow ? "warning" : "success";
  const eyebrow = blocked
    ? "Reliance blocked"
    : shadow
      ? "Evaluation boundary"
      : "Production evidence";

  return (
    <Card
      data-testid={`drawing-governance-${state.kind}`}
      className={
        blocked
          ? "border-error/30"
          : shadow
            ? "border-warning/30"
            : "border-success/30"
      }
    >
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <span
              className={
                blocked
                  ? "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-error/10 text-error"
                  : shadow
                    ? "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-warning/10 text-warning"
                    : "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-success/10 text-success"
              }
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                {eyebrow}
              </p>
              <CardTitle className="mt-1 text-base">{state.title}</CardTitle>
            </div>
          </div>
          <Badge variant={badgeVariant}>
            {blocked ? "Do not rely" : shadow ? "Shadow" : "Verified"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="max-w-4xl text-sm leading-6 text-[var(--text-secondary)]">
          {state.detail}
        </p>
        {state.kind !== "blocked" ? (
          <dl className="grid gap-3 border-t border-[var(--border-subtle)] pt-4 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <GovernanceFact
              label="Rollout"
              value={state.provenance.rollout_state}
            />
            <GovernanceFact
              label="Jurisdictions"
              value={state.provenance.jurisdictions?.join(", ") || "None"}
            />
            <GovernanceFact
              label="Calibration"
              value={
                state.provenance.calibration_artifact_id
                  ? `${state.provenance.calibration_artifact_id} · r${state.provenance.calibration_artifact_revision}`
                  : "Not applicable in shadow"
              }
            />
            <GovernanceFact
              label="Verified"
              value={formatGovernanceTimestamp(
                state.provenance.verified_at ?? undefined,
              )}
            />
            {state.kind === "live" ? (
              <>
                <GovernanceFact
                  label="Runtime roster"
                  value={shortHash(state.provenance.runtime_roster_sha256)}
                  mono
                />
                <GovernanceFact
                  label="ML BOM"
                  value={shortHash(state.provenance.ml_bom_sha256)}
                  mono
                />
                <GovernanceFact
                  label="Calibration hash"
                  value={shortHash(
                    state.provenance.calibration_artifact_sha256,
                  )}
                  mono
                />
                <GovernanceFact
                  label="Worker image"
                  value={shortHash(state.provenance.worker_image_digest)}
                  mono
                />
              </>
            ) : null}
          </dl>
        ) : null}
      </CardContent>
    </Card>
  );
}

function GovernanceFact({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="font-semibold uppercase tracking-[0.1em] text-[var(--text-disabled)]">
        {label}
      </dt>
      <dd
        className={`mt-1 break-words text-[var(--text-secondary)] ${mono ? "font-mono" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}

function shortHash(value: string | undefined): string {
  if (!value) return "Not recorded";
  const digest = value.startsWith("sha256:") ? value.slice(7) : value;
  return `sha256:${digest.slice(0, 12)}…`;
}

function formatGovernanceTimestamp(value: string | undefined): string {
  if (!value) return "Not applicable in shadow";
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.valueOf())) return "Invalid timestamp";
  return timestamp.toISOString().replace(".000Z", "Z");
}

function DrawingGapFact({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Atom;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3">
      <Icon className="h-4 w-4 text-brand-primary" aria-hidden="true" />
      <dt className="mt-3 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 text-sm font-semibold leading-5 text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}

function SummaryStat({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-[var(--text-disabled)]">
        {label}
      </p>
      <p className="mt-0.5 text-lg font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
