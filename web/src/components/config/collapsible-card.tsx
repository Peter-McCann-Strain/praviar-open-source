"use client";

import { useId, useState, type ComponentType, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface CollapsibleCardProps {
  title: string;
  icon: ComponentType<{ className?: string }>;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function CollapsibleCard({
  title,
  icon: Icon,
  defaultOpen = false,
  children,
}: CollapsibleCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  const headingId = useId();

  return (
    <Card>
      <h2>
        <button
          id={headingId}
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-controls={panelId}
          className="flex w-full items-center justify-between px-6 py-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
        >
          <span className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-brand-primary" />
            <span className="type-heading-md text-[var(--text-primary)]">
              {title}
            </span>
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-[var(--text-tertiary)] transition-transform duration-300",
              open && "rotate-180",
            )}
          />
        </button>
      </h2>
      <div
        id={panelId}
        role="region"
        aria-labelledby={headingId}
        hidden={!open}
        className={cn(
          "grid transition-[grid-template-rows] duration-300 ease-in-out",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden">
          <CardContent className="space-y-5 pt-0">{children}</CardContent>
        </div>
      </div>
    </Card>
  );
}
