import { Badge } from "@/components/ui/badge";

interface GapBadge {
  label: string;
  count: number;
}

interface DecisionEvidenceGapsProps {
  gapBadges: GapBadge[];
}

export function DecisionEvidenceGaps({ gapBadges }: DecisionEvidenceGapsProps) {
  if (gapBadges.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        Coverage Gaps
      </p>
      <div className="flex flex-wrap gap-2">
        {gapBadges.map((gapBadge) => (
          <Badge key={gapBadge.label} variant="warning">
            {gapBadge.label}: {gapBadge.count}
          </Badge>
        ))}
      </div>
    </div>
  );
}
