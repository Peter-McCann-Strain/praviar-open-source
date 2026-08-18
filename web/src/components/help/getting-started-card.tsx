import { BookOpen } from "lucide-react";
import {
  HELP_SECTION_SEARCH_TERMS,
  getGettingStartedSteps,
  matchesHelpQuery,
} from "@/components/help/helpers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { PrincipalCapabilities } from "@/hooks/use-principal-capabilities";

interface GettingStartedCardProps {
  capabilities?: PrincipalCapabilities;
  query?: string;
}

export function GettingStartedCard({
  capabilities,
  query = "",
}: GettingStartedCardProps) {
  const normalizedQuery = query.trim().toLowerCase();
  const availableSteps = getGettingStartedSteps(capabilities);
  const steps = availableSteps.filter((item) =>
    matchesHelpQuery(
      normalizedQuery,
      ...HELP_SECTION_SEARCH_TERMS.gettingStarted,
      item.title,
      item.desc,
    ),
  );
  const isFocusedResult =
    normalizedQuery.length > 0 && steps.length < availableSteps.length;
  const readOnlyPath = capabilities?.can_create_analysis === false;

  return (
    <Card id="getting-started" className="scroll-mt-36">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-brand-primary" />
          Getting Started
        </CardTitle>
        <p className="mt-1 type-body-md text-[var(--text-tertiary)]">
          {isFocusedResult
            ? readOnlyPath
              ? "Matching guidance for reviewing shared FTO work"
              : "Matching setup guidance for your first FTO analysis"
            : readOnlyPath
              ? "Three steps to value from a shared FTO packet"
              : "Three steps to your first FTO analysis"}
        </p>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            "grid grid-cols-1 gap-4",
            steps.length > 1 && "sm:grid-cols-2",
            steps.length > 2 && "lg:grid-cols-3",
          )}
        >
          {steps.map((item) => (
            <div
              key={item.step}
              className="flex items-start gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-5"
            >
              <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-brand-primary/15 text-xs font-bold text-brand-primary">
                {item.step}
              </div>
              <div>
                <p className="type-label-sm text-[var(--text-primary)]">
                  {item.title}
                </p>
                <p className="mt-1 type-caption text-[var(--text-tertiary)]">
                  {item.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
