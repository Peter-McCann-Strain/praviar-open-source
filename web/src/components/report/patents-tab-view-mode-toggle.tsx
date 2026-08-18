"use client";

import { LayoutGrid, Table2 } from "lucide-react";

export function PatentsViewModeToggle({
  viewMode,
  onChange,
}: {
  viewMode: "cards" | "table";
  onChange: (mode: "cards" | "table") => void;
}) {
  return (
    <div className="flex items-center justify-end gap-2">
      <button
        type="button"
        onClick={() => onChange("cards")}
        className={`inline-flex h-11 w-11 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 ${
          viewMode === "cards"
            ? "bg-[var(--surface-active)] text-[var(--text-primary)]"
            : "text-[var(--text-tertiary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        }`}
        aria-label="Card view"
      >
        <LayoutGrid className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => onChange("table")}
        className={`inline-flex h-11 w-11 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 ${
          viewMode === "table"
            ? "bg-[var(--surface-active)] text-[var(--text-primary)]"
            : "text-[var(--text-tertiary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        }`}
        aria-label="Table view"
      >
        <Table2 className="h-4 w-4" />
      </button>
    </div>
  );
}
