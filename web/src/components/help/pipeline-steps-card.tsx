import { ExpandableItem } from "@/components/help/expandable-item";
import {
  DEFAULT_STEP_ICON,
  HELP_SECTION_SEARCH_TERMS,
  STEP_DESCRIPTIONS,
  STEP_ICONS,
  matchesHelpQuery,
} from "@/components/help/helpers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PIPELINE_STEPS } from "@/lib/constants";

import { Route } from "lucide-react";
interface PipelineStepsCardProps {
  query: string;
}

export function PipelineStepsCard({ query }: PipelineStepsCardProps) {
  const filteredSteps = PIPELINE_STEPS.filter((step) =>
    matchesHelpQuery(
      query,
      ...HELP_SECTION_SEARCH_TERMS.pipeline,
      step.label,
      STEP_DESCRIPTIONS[step.number] ?? "",
    ),
  );

  if (filteredSteps.length === 0) {
    return null;
  }

  return (
    <Card id="pipeline-steps" className="scroll-mt-36">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Route className="h-4 w-4 text-brand-primary" />
          Pipeline Steps
        </CardTitle>
        <p className="mt-1 type-body-md text-[var(--text-tertiary)]">
          The 8-step FTO analysis pipeline, from compound resolution to final
          report
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {filteredSteps.map((step) => (
          <ExpandableItem
            key={step.number}
            title={`Step ${step.number}: ${step.label}`}
            icon={STEP_ICONS[step.number] ?? DEFAULT_STEP_ICON}
            defaultOpen={step.number === 1 && !query}
          >
            {STEP_DESCRIPTIONS[step.number]}
          </ExpandableItem>
        ))}
      </CardContent>
    </Card>
  );
}
