"use client";

import type { InvalidityAssessment } from "@/components/report/invalidity-tab-helpers";

interface InvalidityTabEnablementScreeningCardProps {
  enablementScreening: InvalidityAssessment["enablement_screening"];
}

export function InvalidityTabEnablementScreeningCard({
  enablementScreening,
}: InvalidityTabEnablementScreeningCardProps) {
  if (!enablementScreening?.genus_claim_detected) {
    return null;
  }

  return (
    <div className="rounded-lg border border-warning/20 bg-warning/5 p-4 space-y-2">
      <p className="text-xs font-semibold text-warning">
        Enablement Screening Flags
      </p>
      <p className="text-sm text-[var(--text-primary)]">
        Specification enables full scope:{" "}
        <span className="font-medium">
          {enablementScreening.specification_enables_full_scope}
        </span>
      </p>
      {enablementScreening.genus_indicators.length > 0 && (
        <div>
          <p className="text-xs text-[var(--text-tertiary)] mb-1">
            Genus Indicators
          </p>
          <ul className="text-xs text-[var(--text-secondary)] list-disc list-inside">
            {enablementScreening.genus_indicators.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </div>
      )}
      {enablementScreening.amgen_v_sanofi_flags.length > 0 && (
        <div>
          <p className="text-xs text-[var(--text-tertiary)] mb-1">
            Amgen v. Sanofi Flags
          </p>
          <ul className="text-xs text-[var(--text-secondary)] list-disc list-inside">
            {enablementScreening.amgen_v_sanofi_flags.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-[var(--text-secondary)] mt-1">
        {enablementScreening.reasoning}
      </p>
    </div>
  );
}
