import { SearchIcon, X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface HelpSearchInputProps {
  hasQuery?: boolean;
  onClear?: () => void;
  value: string;
  onChange: (value: string) => void;
  resultSummary?: string;
}

export function HelpSearchInput({
  hasQuery = false,
  onChange,
  onClear,
  resultSummary,
  value,
}: HelpSearchInputProps) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 shadow-[var(--shadow-xs)]">
      <div className="relative">
        <SearchIcon
          className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]"
          aria-hidden="true"
        />
        <input
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Search help topics..."
          aria-label="Search help topics"
          className="h-11 w-full rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] pl-10 pr-12 text-sm text-[var(--text-primary)] transition-colors placeholder:text-[var(--text-disabled)] focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/30"
        />
        {hasQuery && onClear ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute right-1 top-1/2 h-9 w-9 -translate-y-1/2"
            onClick={onClear}
            aria-label="Clear help search"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
      {resultSummary ? (
        <p
          className="mt-2 text-xs leading-5 text-[var(--text-secondary)]"
          aria-live="polite"
        >
          {resultSummary}
        </p>
      ) : null}
    </div>
  );
}
