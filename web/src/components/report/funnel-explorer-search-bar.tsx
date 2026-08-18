"use client";

import { useState } from "react";
import { Search, X } from "lucide-react";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";

export function PatentSearchBar({
  onSearch,
  searchResult,
  onClear,
}: {
  onSearch: (query: string) => void;
  searchResult: string | null;
  onClear: () => void;
}) {
  const [query, setQuery] = useState("");
  useAuthBoundaryReset(() => {
    setQuery("");
  });

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-disabled)]" />
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && onSearch(query)}
            placeholder="Find patent in funnel (e.g., US-7851188-B2)"
            aria-label="Find patent in funnel"
            className="praviar-glass-field min-h-11 w-full rounded-lg py-2 pl-9 pr-3 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] focus:border-brand-primary/50 focus:outline-none focus:ring-2 focus:ring-brand-primary/70"
          />
        </div>
        {searchResult ? (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              onClear();
            }}
            aria-label="Clear patent search"
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-[var(--border-default)] hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          >
            <X
              className="h-3.5 w-3.5 text-[var(--text-tertiary)]"
              aria-hidden="true"
            />
          </button>
        ) : null}
      </div>
      {searchResult ? (
        <div className="praviar-glass-chip rounded-lg p-3">
          <p className="text-xs text-brand-primary">{searchResult}</p>
        </div>
      ) : null}
    </div>
  );
}
