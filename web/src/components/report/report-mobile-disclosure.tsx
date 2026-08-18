"use client";

import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";
import { cn } from "@/lib/utils";

interface ReportMobileDisclosureProps {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  description: string;
  initiallyOpen?: boolean;
  label: string;
  testId?: string;
}

/** Decision-first on phones while preserving the complete, expanded desktop record. */
export function ReportMobileDisclosure({
  children,
  className,
  contentClassName,
  description,
  initiallyOpen,
  label,
  testId,
}: ReportMobileDisclosureProps) {
  return (
    <ResponsiveDisclosure
      className={cn("group sm:contents print:contents", className)}
      data-testid={testId}
      initiallyOpen={initiallyOpen}
      summary={
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3 text-left shadow-[var(--shadow-xs)] marker:content-none sm:hidden print:hidden [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              {label}
            </span>
            <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
              {description}
            </span>
          </span>
          <ChevronDown
            className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
            aria-hidden="true"
          />
        </summary>
      }
    >
      <div
        className={cn("mt-3 sm:mt-0 print:mt-0 print:block", contentClassName)}
      >
        {children}
      </div>
    </ResponsiveDisclosure>
  );
}
