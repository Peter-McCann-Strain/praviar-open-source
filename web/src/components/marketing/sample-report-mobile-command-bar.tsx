"use client";

import { useState } from "react";
import {
  BadgeCheck,
  ChevronDown,
  Database,
  Scale,
  ShieldCheck,
} from "lucide-react";
import type { DemoArtifactPayload } from "@/marketing/live-demo";

interface SampleReportMobileCommandBarProps {
  demoArtifact: DemoArtifactPayload;
}

const MOBILE_REPORT_NAV_ITEMS = [
  {
    href: "#sample-verdict-packet",
    icon: ShieldCheck,
    label: "Summary",
  },
  {
    href: "#sample-claim-chart",
    icon: Scale,
    label: "Claims",
  },
  {
    href: "#sample-evidence-ledger",
    icon: Database,
    label: "Sources",
  },
  {
    href: "#sample-verification-limits",
    icon: BadgeCheck,
    label: "Limits",
  },
] as const;

export function SampleReportMobileCommandBar({
  demoArtifact,
}: SampleReportMobileCommandBarProps) {
  const [sectionsOpen, setSectionsOpen] = useState(false);
  const reportReference = `${demoArtifact.compoundName} sample`;
  const primaryItem = MOBILE_REPORT_NAV_ITEMS[0];
  const secondaryItems = MOBILE_REPORT_NAV_ITEMS.slice(1);
  const sectionsId = "sample-report-mobile-sections";

  return (
    <nav
      aria-label="Sample report command bar"
      className="praviar-mobile-command-surface no-print sticky top-14 z-40 rounded-b-lg border-x-0 border-t-0 px-2 py-1 lg:hidden"
      data-sample-report-mobile-command-bar
      data-state={sectionsOpen ? "expanded" : "collapsed"}
      data-testid="sample-report-mobile-command-bar"
    >
      <div className="mx-auto max-w-lg">
        <div className="grid min-h-11 min-w-0 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_88%,transparent)] p-1 shadow-[var(--shadow-xs)]">
          <div
            role="group"
            aria-label={`${reportReference}, synthetic scenario, ${demoArtifact.familiesFlaggedForReviewCount} sample ${demoArtifact.familiesFlaggedForReviewCount === 1 ? "family" : "families"} flagged for review`}
            className="min-w-0 px-2"
          >
            <p className="truncate text-xs font-semibold leading-4 text-[var(--text-primary)]">
              {reportReference}
            </p>
            <p className="truncate text-xs leading-3 text-[var(--text-secondary)]">
              Fictional · {demoArtifact.familiesFlaggedForReviewCount} flagged
            </p>
          </div>

          <a
            href={primaryItem.href}
            className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-semibold text-brand-primary transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
            onClick={() => setSectionsOpen(false)}
          >
            <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{primaryItem.label}</span>
          </a>

          <button
            type="button"
            aria-controls={sectionsId}
            aria-expanded={sectionsOpen}
            aria-label={
              sectionsOpen ? "Hide report sections" : "Show report sections"
            }
            className="inline-flex h-11 w-11 items-center justify-center rounded-md text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
            onClick={() => setSectionsOpen((open) => !open)}
          >
            <ChevronDown
              className={`h-4 w-4 transition-transform ${
                sectionsOpen ? "rotate-180" : ""
              }`}
              aria-hidden="true"
            />
          </button>
        </div>

        <div
          id={sectionsId}
          hidden={!sectionsOpen}
          className="mt-1 grid grid-cols-3 gap-1 rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_88%,transparent)] p-1 shadow-[var(--shadow-xs)]"
        >
          {secondaryItems.map((item) => {
            const Icon = item.icon;

            return (
              <a
                key={item.href}
                href={item.href}
                className="flex min-h-11 items-center justify-center gap-1.5 rounded-md px-1.5 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
                onClick={() => setSectionsOpen(false)}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{item.label}</span>
              </a>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
