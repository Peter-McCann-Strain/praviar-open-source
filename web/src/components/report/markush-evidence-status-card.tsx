import { FileCheck2, ShieldAlert, ShieldCheck } from "lucide-react";
import type { PipelineAuditTrail } from "@praviar/shared-types";
import { Card, CardContent } from "@/components/ui/card";

interface MarkushEvidenceStatusCardProps {
  audit: PipelineAuditTrail;
}

const STATUS_COPY = {
  verified_manual: {
    label: "Independently verified",
    detail:
      "A supervised PATENTSCOPE Markush search is bound to this matter and its original export.",
  },
  not_run: {
    label: "Not run",
    detail:
      "Positive small-molecule clearance remains blocked until an analyst imports and a distinct reviewer verifies PATENTSCOPE Markush evidence.",
  },
  incomplete: {
    label: "Review incomplete",
    detail:
      "The imported PATENTSCOPE evidence is not independently verified and cannot support positive clearance.",
  },
  unavailable: {
    label: "Unavailable",
    detail:
      "PATENTSCOPE Markush evidence was unavailable. The retrieval gap remains clearance-blocking.",
  },
  not_applicable: {
    label: "Not applicable",
    detail: "This matter does not require the small-molecule Markush lane.",
  },
} as const;

function shortHash(value: string | null | undefined) {
  if (!value) return "—";
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

export function MarkushEvidenceStatusCard({
  audit,
}: MarkushEvidenceStatusCardProps) {
  const plan = audit.query_plan;
  const status = plan?.true_markush_coverage_status ?? "not_run";
  const copy = STATUS_COPY[status] ?? STATUS_COPY.incomplete;
  const receipt = plan?.markush_evidence;
  const verified = status === "verified_manual" && Boolean(receipt);
  const notApplicable = status === "not_applicable";
  const Icon = verified
    ? ShieldCheck
    : notApplicable
      ? FileCheck2
      : ShieldAlert;
  const executedAt =
    receipt?.executed_at &&
    new Intl.DateTimeFormat("en-GB", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "UTC",
    }).format(new Date(receipt.executed_at));
  const serverImportedAt =
    receipt?.server_imported_at &&
    new Intl.DateTimeFormat("en-GB", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "UTC",
    }).format(new Date(receipt.server_imported_at));

  return (
    <Card role="region" aria-label="Markush coverage evidence">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <span
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                verified
                  ? "bg-success/10 text-success"
                  : notApplicable
                    ? "bg-[var(--surface-muted)] text-[var(--text-tertiary)]"
                    : "bg-warning/10 text-warning"
              }`}
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                Markush coverage evidence
              </p>
              <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                {copy.label}
              </h3>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                {copy.detail}
              </p>
            </div>
          </div>
          <span
            className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${
              verified
                ? "border-success/25 bg-success/10 text-success"
                : notApplicable
                  ? "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-tertiary)]"
                  : "border-warning/25 bg-warning/10 text-warning"
            }`}
          >
            {verified
              ? "Clearance gate satisfied"
              : notApplicable
                ? "Gate not required"
                : "Clearance gate blocked"}
          </span>
        </div>

        {receipt ? (
          <>
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 p-3">
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Executed / imported
                </dt>
                <dd className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                  {executedAt || "Not recorded"}
                </dd>
                <dd className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                  {serverImportedAt
                    ? `Server import ${serverImportedAt}`
                    : "Server import not recorded"}
                </dd>
              </div>
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 p-3">
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Search contract
                </dt>
                <dd className="mt-1 text-sm font-medium capitalize text-[var(--text-primary)]">
                  {receipt.chemical_search_mode} ·{" "}
                  {receipt.markush_method.replaceAll("_", " ")} ·{" "}
                  {receipt.markush_match_mode}
                  {receipt.wipo_query_field
                    ? ` · ${receipt.wipo_query_field}`
                    : ""}
                </dd>
              </div>
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 p-3">
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Results / selected
                </dt>
                <dd className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                  {receipt.result_count ?? "—"} /{" "}
                  {receipt.selected_publication_ids?.length ?? 0}
                </dd>
              </div>
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 p-3">
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Family grouping
                </dt>
                <dd className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                  {receipt.family_grouping_enabled ? "Enabled" : "Disabled"}
                </dd>
              </div>
            </dl>

            <dl className="grid gap-x-8 gap-y-3 border-t border-[var(--border-subtle)] pt-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">Analyst</dt>
                <dd className="mt-1 break-all text-[var(--text-secondary)]">
                  {receipt.analyst_identity || "Not recorded"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Independent reviewer
                </dt>
                <dd className="mt-1 break-all text-[var(--text-secondary)]">
                  {receipt.reviewer_identity || "Pending"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Target structure digest
                </dt>
                <dd
                  className="mt-1 font-mono text-xs text-[var(--text-secondary)]"
                  title={receipt.target_structure_sha256}
                >
                  {shortHash(receipt.target_structure_sha256)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Query structure digest
                </dt>
                <dd
                  className="mt-1 font-mono text-xs text-[var(--text-secondary)]"
                  title={receipt.query_structure_sha256}
                >
                  {shortHash(receipt.query_structure_sha256)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Original export
                </dt>
                <dd className="mt-1 break-all text-[var(--text-secondary)]">
                  {receipt.artifact_filename || "Not recorded"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Search-controls capture
                </dt>
                <dd
                  className="mt-1 break-all text-[var(--text-secondary)]"
                  title={receipt.controls_artifact_sha256 || undefined}
                >
                  {receipt.controls_artifact_filename || "Not recorded"} ·{" "}
                  <span className="font-mono text-xs">
                    {shortHash(receipt.controls_artifact_sha256)}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Organization binding
                </dt>
                <dd className="mt-1 break-all text-[var(--text-secondary)]">
                  {receipt.organization_id}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Original artifact digest
                </dt>
                <dd
                  className="mt-1 font-mono text-xs text-[var(--text-secondary)]"
                  title={receipt.imported_artifact_sha256 || undefined}
                >
                  {shortHash(receipt.imported_artifact_sha256)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Receipt digest
                </dt>
                <dd
                  className="mt-1 font-mono text-xs text-[var(--text-secondary)]"
                  title={receipt.receipt_sha256}
                >
                  {shortHash(receipt.receipt_sha256)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">
                  Server attestation key
                </dt>
                <dd className="mt-1 break-all text-[var(--text-secondary)]">
                  {receipt.attestation_key_id || "Not attested"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--text-tertiary)]">Source</dt>
                <dd className="mt-1 text-[var(--text-secondary)]">
                  <a
                    className="font-medium text-[var(--brand-primary)] underline decoration-[color:rgba(var(--brand-primary-rgb),0.3)] underline-offset-4 hover:decoration-current"
                    href={receipt.source_url}
                    rel="noreferrer"
                    target="_blank"
                  >
                    WIPO PATENTSCOPE
                  </a>
                </dd>
              </div>
            </dl>

            {receipt.limitations?.length ? (
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-muted)]/30 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
                  Recorded limitations
                </p>
                <ul className="mt-2 space-y-1.5 text-sm leading-6 text-[var(--text-secondary)]">
                  {receipt.limitations.map((limitation) => (
                    <li key={limitation} className="flex gap-2">
                      <span aria-hidden="true">•</span>
                      <span>{limitation}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
