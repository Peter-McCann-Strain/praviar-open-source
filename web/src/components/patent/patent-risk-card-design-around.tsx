"use client";

import type { DesignAroundSuggestion } from "@praviar/shared-types";

interface PatentRiskCardDesignAroundProps {
  suggestions: DesignAroundSuggestion[];
}

export function PatentRiskCardDesignAround({
  suggestions,
}: PatentRiskCardDesignAroundProps) {
  if (suggestions.length === 0) {
    return null;
  }

  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
        Design-Around Suggestions
      </p>
      <ul className="space-y-2">
        {suggestions.map((suggestion, index) => (
          <li
            key={`${suggestion.element_avoided}-${index}`}
            className="rounded-lg bg-[var(--surface-muted)] p-3 text-sm text-[var(--text-primary)]"
          >
            <span className="font-medium text-brand-primary">
              Element {suggestion.element_avoided}:
            </span>{" "}
            {suggestion.suggestion}
            <span className="mt-1 block text-xs text-[var(--text-tertiary)]">
              Feasibility: {suggestion.feasibility}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
