import { AlertTriangle } from "lucide-react";

interface DecisionEvidenceWarningsProps {
  warnings: string[];
}

export function DecisionEvidenceWarnings({
  warnings,
}: DecisionEvidenceWarningsProps) {
  if (warnings.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-warning" />
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          Evidence Warnings
        </p>
      </div>
      <ul className="space-y-2">
        {warnings.slice(0, 5).map((warning, index) => (
          <li
            key={`${warning}-${index}`}
            className="rounded-lg border border-warning/20 bg-warning/5 px-4 py-3 text-sm text-[var(--text-secondary)]"
          >
            {warning}
          </li>
        ))}
      </ul>
    </div>
  );
}
