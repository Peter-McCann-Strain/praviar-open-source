import { Badge } from "@/components/ui/badge";
import type { DecisionEvidenceReference } from "./report-decision-helpers";

const CATEGORY_LABELS: Record<string, string> = {
  blocking_patent: "Blocking Patent",
  clearance_support: "Clearance Support",
  source_failure: "Source Failure",
  coverage_gap: "Coverage Gap",
  verification_gap: "Verification Gap",
  future_risk: "Future Risk",
  prosecution_signal: "Prosecution Signal",
};

function getCategoryVariant(category: string) {
  switch (category) {
    case "blocking_patent":
    case "source_failure":
    case "verification_gap":
      return "destructive" as const;
    case "coverage_gap":
    case "future_risk":
      return "warning" as const;
    case "clearance_support":
      return "success" as const;
    case "prosecution_signal":
    default:
      return "secondary" as const;
  }
}

interface DecisionEvidenceReferencesProps {
  references: DecisionEvidenceReference[];
}

export function DecisionEvidenceReferences({
  references,
}: DecisionEvidenceReferencesProps) {
  if (references.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        Decisive References
      </p>
      <div className="space-y-3">
        {references.map((reference, index) => (
          <div
            key={`${reference.category}-${reference.patent_id ?? ""}-${index}`}
            className="rounded-lg border border-[var(--border-subtle)] p-4"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={getCategoryVariant(reference.category)}>
                {CATEGORY_LABELS[reference.category] ?? reference.category}
              </Badge>
              {reference.jurisdiction ? (
                <Badge variant="outline">{reference.jurisdiction}</Badge>
              ) : null}
              {reference.patent_id ? (
                <Badge variant="secondary">{reference.patent_id}</Badge>
              ) : null}
              {reference.source_name ? (
                <Badge variant="outline">{reference.source_name}</Badge>
              ) : null}
            </div>
            <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">
              {reference.summary}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
