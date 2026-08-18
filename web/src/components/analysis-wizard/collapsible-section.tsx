"use client";

import { useId, useState, type ComponentType, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface CollapsibleSectionProps {
  title: string;
  icon: ComponentType<{ className?: string }>;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function CollapsibleSection({
  title,
  icon: Icon,
  defaultOpen = false,
  children,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const panelId = useId();

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-default)]">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-controls={panelId}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-[var(--surface-subtle)]"
      >
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-brand-primary" />
          <span className="text-sm font-medium text-[var(--text-primary)]">
            {title}
          </span>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-[var(--text-tertiary)] transition-transform",
            isOpen && "rotate-180",
          )}
        />
      </button>
      <div
        id={panelId}
        hidden={!isOpen}
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-out",
          isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden">
          <div className="space-y-4 border-t border-[var(--border-subtle)] px-4 pb-4 pt-3">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
