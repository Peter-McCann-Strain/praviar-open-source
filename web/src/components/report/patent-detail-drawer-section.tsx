"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import { ChevronDown, ChevronRight, type LucideIcon } from "lucide-react";

export function PatentDetailDrawerSection({
  title,
  icon: Icon,
  children,
  defaultOpen = true,
}: {
  title: string;
  icon: LucideIcon;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-[var(--border-subtle)] last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full py-3 text-left hover:bg-[var(--surface-muted)] px-1 rounded transition-colors"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
        )}
        <Icon className="h-3.5 w-3.5 text-brand-primary" />
        <span className="text-sm font-medium text-[var(--text-primary)]">
          {title}
        </span>
      </button>
      {open ? <div className="pb-4 pl-7 pr-1">{children}</div> : null}
    </div>
  );
}
