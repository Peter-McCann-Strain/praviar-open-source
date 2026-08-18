import { Search, X } from "lucide-react";
import { useId, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MAX_COMPOUND_SEARCH_LENGTH } from "@/components/compounds/helpers";

interface CompoundsSearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onClearSearch: () => void;
  total: number;
  visibleCount: number;
}

export function CompoundsSearchBar({
  value,
  onChange,
  onClearSearch,
  total,
  visibleCount,
}: CompoundsSearchBarProps) {
  const searchId = useId();
  const helpId = useId();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchLabel = `Search: ${value.trim()}`;
  const hasSearch = value.trim().length > 0;
  const searchLengthLabel = `${value.length} / ${MAX_COMPOUND_SEARCH_LENGTH}`;

  return (
    <section
      aria-label="Compound library controls"
      className="praviar-surface-premium rounded-lg border border-[var(--card-border)] p-3 sm:p-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
        <div className="min-w-0 flex-1">
          <label
            htmlFor={searchId}
            className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]"
          >
            Search compounds
          </label>
          <div className="relative">
            <Search
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]"
              aria-hidden="true"
            />
            <Input
              id={searchId}
              ref={searchInputRef}
              placeholder="Search by name, SMILES, or InChI Key..."
              className="h-11 pl-10"
              value={value}
              maxLength={MAX_COMPOUND_SEARCH_LENGTH}
              autoComplete="off"
              spellCheck={false}
              aria-describedby={helpId}
              onChange={(event) => onChange(event.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 px-3 py-2 sm:grid-cols-2 lg:w-[24rem]">
          <span className="min-w-0">
            <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Index scope
            </span>
            <span className="mt-0.5 block text-sm font-medium text-[var(--text-primary)]">
              Private workspace
            </span>
          </span>
          <span className="min-w-0">
            <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Visible records
            </span>
            <span className="mt-0.5 block text-sm font-medium tabular-nums text-[var(--text-primary)]">
              {visibleCount.toLocaleString()} / {total.toLocaleString()}
            </span>
          </span>
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 text-xs leading-5 text-[var(--text-tertiary)]">
          <p id={helpId}>
            Search queries normalized names, SMILES fragments, InChI keys, and
            indexed compound identifiers. Queries are capped at{" "}
            {MAX_COMPOUND_SEARCH_LENGTH} characters.
          </p>
          <p
            className="mt-0.5 font-mono text-xs text-[var(--text-disabled)]"
            aria-label="Compound search length"
          >
            {searchLengthLabel}
          </p>
        </div>
        {hasSearch ? (
          <div
            className="flex min-w-0 max-w-full flex-wrap items-center gap-2"
            aria-label="Active compound filters"
            role="group"
          >
            <span
              className="inline-flex max-w-full min-w-0 rounded-full border border-[var(--border-default)] bg-[var(--surface-muted)] px-3 py-1 text-xs text-[var(--text-secondary)]"
              title={searchLabel}
              aria-label={searchLabel}
            >
              <span className="min-w-0 truncate">{searchLabel}</span>
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 text-xs"
              onClick={() => {
                onClearSearch();
                searchInputRef.current?.focus();
              }}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              Clear compound search
            </Button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
