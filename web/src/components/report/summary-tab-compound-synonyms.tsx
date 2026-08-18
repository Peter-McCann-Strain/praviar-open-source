"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";

export function CompoundSynonyms({ synonyms }: { synonyms: string[] }) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? synonyms : synonyms.slice(0, 3);
  const remaining = synonyms.length - 3;

  return (
    <div className="border-b border-[var(--border-default)] py-1.5">
      <span className="mb-1 block text-sm text-[var(--text-secondary)]">
        Synonyms
      </span>
      <div className="flex flex-wrap gap-1">
        {visible.map((synonym) => (
          <Badge key={synonym} variant="outline" className="text-xs">
            {synonym}
          </Badge>
        ))}
        {remaining > 0 && !showAll ? (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="inline-flex min-h-11 items-center rounded-md px-3 text-xs font-semibold text-[var(--brand-primary)] transition-colors hover:bg-brand-primary/10 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          >
            Show {remaining} more
          </button>
        ) : null}
        {showAll && remaining > 0 ? (
          <button
            type="button"
            onClick={() => setShowAll(false)}
            className="inline-flex min-h-11 items-center rounded-md px-3 text-xs font-semibold text-[var(--brand-primary)] transition-colors hover:bg-brand-primary/10 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          >
            Show less
          </button>
        ) : null}
      </div>
    </div>
  );
}
