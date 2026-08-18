"use client";

import type { PatentTermInfo } from "@praviar/shared-types";

interface TermFact {
  label: string;
  value: string;
  tone?: "default" | "warning";
}

function formatConfidence(value: number): string {
  if (!Number.isFinite(value)) return "Unknown";
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(normalized)}%`;
}

function formatMaintenanceStatus(
  status: PatentTermInfo["maintenance_fee_status"],
) {
  return status.replaceAll("_", " ");
}

function getMaintenanceTone(
  status: PatentTermInfo["maintenance_fee_status"],
): TermFact["tone"] {
  return status === "paid" ? "default" : "warning";
}

function TermFactCard({ label, value, tone = "default" }: TermFact) {
  return (
    <div
      className={[
        "min-w-0 rounded-md border px-3 py-2",
        tone === "warning"
          ? "border-warning/25 bg-warning/10"
          : "border-[var(--border-subtle)] bg-[var(--bg-surface)]/70",
      ].join(" ")}
    >
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 break-words text-xs font-semibold leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {value}
      </dd>
    </div>
  );
}

export function PatentDetailDrawerTermBreakdown({
  info,
}: {
  info: PatentTermInfo;
}) {
  const maintenanceTone = getMaintenanceTone(info.maintenance_fee_status);
  const calculationNotes = Array.isArray(info.calculation_notes)
    ? info.calculation_notes.filter(Boolean)
    : [];
  const termFacts: TermFact[] = [
    info.effective_filing_date
      ? { label: "Filing date", value: info.effective_filing_date }
      : null,
    info.grant_date ? { label: "Grant date", value: info.grant_date } : null,
    info.base_expiry ? { label: "Base expiry", value: info.base_expiry } : null,
    (info.pta_days ?? 0) > 0
      ? { label: "PTA days", value: `+${info.pta_days}` }
      : null,
    (info.pte_days ?? 0) > 0
      ? { label: "PTE days", value: `+${info.pte_days}` }
      : null,
    info.terminal_disclaimer
      ? {
          label: "Terminal disclaimer",
          value: `Yes${
            info.td_linked_patent ? ` (linked to ${info.td_linked_patent})` : ""
          }${
            info.td_linked_expiry
              ? `, linked expiry ${info.td_linked_expiry}`
              : ""
          }`,
          tone: "warning",
        }
      : null,
    info.adjusted_expiry
      ? { label: "Adjusted expiry", value: info.adjusted_expiry }
      : null,
    {
      label: "Maintenance fees",
      value: formatMaintenanceStatus(info.maintenance_fee_status),
      tone: maintenanceTone,
    },
    info.maintenance_fee_next_due
      ? {
          label: "Next fee due",
          value: info.maintenance_fee_next_due,
          tone: maintenanceTone,
        }
      : null,
    {
      label: "Term confidence",
      value: formatConfidence(info.calculation_confidence),
      tone: info.calculation_confidence >= 0.8 ? "default" : "warning",
    },
  ].filter((item): item is TermFact => Boolean(item));

  return (
    <div className="space-y-3">
      <dl className="grid gap-2 sm:grid-cols-2">
        {termFacts.map((fact) => (
          <TermFactCard key={`${fact.label}-${fact.value}`} {...fact} />
        ))}
      </dl>
      {calculationNotes.length > 0 ? (
        <div className="rounded-md border border-warning/25 bg-warning/10 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-warning">
            Calculation caveats
          </p>
          <ul className="mt-1 grid gap-1 text-xs leading-5 text-[var(--text-secondary)]">
            {calculationNotes.map((note, index) => (
              <li
                key={`${note}-${index}`}
                className="break-words [overflow-wrap:anywhere]"
              >
                {note}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
