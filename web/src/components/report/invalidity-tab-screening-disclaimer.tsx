"use client";

interface InvalidityTabScreeningDisclaimerProps {
  screeningDisclaimer: string;
}

export function InvalidityTabScreeningDisclaimer({
  screeningDisclaimer,
}: InvalidityTabScreeningDisclaimerProps) {
  return (
    <div className="praviar-glass-chip rounded-lg p-3">
      <p className="text-xs text-[var(--text-tertiary)]">
        {screeningDisclaimer}
      </p>
    </div>
  );
}
