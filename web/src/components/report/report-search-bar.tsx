"use client";

import { useState, useRef, useEffect, useId } from "react";
import { Search, X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";

interface ReportSearchBarProps {
  onSearch: (query: string) => void;
  onClear: () => void;
  isSearching?: boolean;
  interpretedQuery?: string;
  resultCount?: number;
  error?: string | null;
  className?: string;
  initialQuery?: string;
}

export function ReportSearchBar({
  onSearch,
  onClear,
  isSearching = false,
  interpretedQuery,
  resultCount,
  error,
  className,
  initialQuery = "",
}: ReportSearchBarProps) {
  const statusId = useId();
  const errorId = useId();
  const [query, setQuery] = useState(initialQuery);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const describedBy = [statusId, error ? errorId : null]
    .filter(Boolean)
    .join(" ");
  const resultCountLabel =
    resultCount != null
      ? `${resultCount} result${resultCount !== 1 ? "s" : ""}`
      : null;

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  useAuthBoundaryReset(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setQuery("");
    onClear();
  });

  const handleChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const trimmedValue = value.trim();
      if (trimmedValue) {
        onSearch(trimmedValue);
      } else {
        onClear();
      }
    }, 300);
  };

  const handleClear = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setQuery("");
    onClear();
    inputRef.current?.focus();
  };

  const handleSubmit = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const trimmedQuery = query.trim();
    if (trimmedQuery) {
      onSearch(trimmedQuery);
    } else {
      onClear();
    }
  };

  return (
    <section
      role="search"
      aria-label="Search reviewed report evidence"
      className={cn("space-y-2", className)}
      data-no-print
      data-praviar-report-search
    >
      <div className="relative">
        <Search
          className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-tertiary)]"
          aria-hidden="true"
        />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            handleSubmit();
          }}
          placeholder="Search reviewed evidence"
          className="praviar-glass-field min-h-11 w-full rounded-lg pl-9 pr-12 text-sm text-[var(--text-primary)] transition-colors placeholder:text-[var(--text-disabled)] focus:border-brand-primary/60 focus:outline-none focus:ring-2 focus:ring-brand-primary/70 focus:ring-offset-2 focus:ring-offset-[var(--bg-base)]"
          aria-label="Search report"
          aria-describedby={describedBy || undefined}
        />
        {isSearching && (
          <Loader2
            className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin motion-reduce:animate-none text-brand-primary"
            aria-hidden="true"
          />
        )}
        {!isSearching && query && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-0 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-lg text-[var(--text-tertiary)] hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
            aria-label="Clear search"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
      </div>
      <p
        id={statusId}
        role="status"
        className={cn(
          "praviar-glass-chip rounded-lg px-2.5 py-2 text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]",
          !isSearching && !interpretedQuery && "sr-only",
        )}
        aria-live="polite"
      >
        {isSearching ? (
          "Searching reviewed evidence."
        ) : interpretedQuery ? (
          <>
            <span className="font-semibold text-[var(--brand-primary)]">
              Reviewed evidence only:
            </span>{" "}
            {interpretedQuery}
            {resultCountLabel ? (
              <span className="ml-1 font-medium text-[var(--text-secondary)]">
                ({resultCountLabel})
              </span>
            ) : null}
          </>
        ) : (
          "Search reviewed report evidence only."
        )}
      </p>
      {error ? (
        <p
          id={errorId}
          role="alert"
          className="rounded-md border border-error/20 bg-error/5 px-2.5 py-2 text-xs text-error"
        >
          {error}
        </p>
      ) : null}
    </section>
  );
}
