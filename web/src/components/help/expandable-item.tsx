"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, type LucideIcon } from "lucide-react";

interface ExpandableItemProps {
  title: string;
  children: ReactNode;
  icon?: LucideIcon;
  defaultOpen?: boolean;
}

export function ExpandableItem({
  title,
  children,
  icon: Icon,
  defaultOpen = false,
}: ExpandableItemProps) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  const triggerId = `${panelId}-trigger`;

  return (
    <div className="border-b border-[var(--border-subtle)] last:border-b-0">
      <button
        id={triggerId}
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-[var(--surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
        ) : (
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
        )}
        {Icon ? (
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-brand-primary/10">
            <Icon className="h-3.5 w-3.5 text-brand-primary" />
          </div>
        ) : null}
        <span className="type-body-md font-medium text-[var(--text-primary)]">
          {title}
        </span>
      </button>
      <div
        id={panelId}
        role="region"
        aria-labelledby={triggerId}
        aria-hidden={!open}
        className={`grid transition-[grid-template-rows] duration-200 ease-in-out ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
      >
        <div className="overflow-hidden">
          <div className="type-body-md px-4 pb-4 pl-14 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
