import { AlertTriangle } from "lucide-react";
import {
  HELP_SECTION_SEARCH_TERMS,
  RISK_EXPLANATIONS,
  matchesHelpQuery,
} from "@/components/help/helpers";
import { RiskBadge } from "@/components/shared/risk-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface RiskLevelsCardProps {
  query?: string;
}

export function RiskLevelsCard({ query = "" }: RiskLevelsCardProps) {
  const normalizedQuery = query.trim().toLowerCase();
  const explanations = RISK_EXPLANATIONS.filter((item) =>
    matchesHelpQuery(
      normalizedQuery,
      ...HELP_SECTION_SEARCH_TERMS.risks,
      item.level,
      item.meaning,
    ),
  );

  return (
    <Card id="risk-levels" className="scroll-mt-36">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-brand-primary" />
          Risk Levels Explained
        </CardTitle>
        <p className="mt-1 type-body-md text-[var(--text-tertiary)]">
          How Praviar classifies patent infringement risk
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {explanations.map((item) => (
          <div
            key={item.level}
            className="flex items-start gap-4 rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4"
          >
            <div className="flex-shrink-0 pt-0.5">
              <RiskBadge risk={item.level} size="sm" />
            </div>
            <p className="type-body-md text-[var(--text-secondary)]">
              {item.meaning}
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
