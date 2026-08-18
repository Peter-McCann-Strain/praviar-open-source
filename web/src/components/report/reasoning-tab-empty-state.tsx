"use client";

import { Card, CardContent } from "@/components/ui/card";

export function ReasoningTabEmptyState() {
  return (
    <Card>
      <CardContent className="p-8 text-center">
        <p className="text-[var(--text-tertiary)]">
          Decision notes appear when adaptive review escalates to deeper
          evidence checks.
        </p>
        <p className="text-xs text-[var(--text-disabled)] mt-1">
          First-stage matters stay on the fast path and keep this section brief.
        </p>
      </CardContent>
    </Card>
  );
}
