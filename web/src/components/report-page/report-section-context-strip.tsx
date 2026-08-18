"use client";

import { FileText, Info, Search, ShieldCheck, Sparkles } from "lucide-react";
import type { ReportChatLaunchContext } from "@/components/report/chat-launch-context";
import { Button } from "@/components/ui/button";
import {
  getOverflowTabs,
  PRIMARY_TABS,
  type ReportTabConfig,
  type ReportTabId,
} from "./tabs";

interface ReportSectionContextStripProps {
  tab: ReportTabId;
  tabCounts: Record<string, number>;
  hasReasoningTraces: boolean;
  onAskAi?: (context: ReportChatLaunchContext) => void;
  onSearch: () => void;
}

const SECTION_DESCRIPTIONS: Record<ReportTabId, string> = {
  overview:
    "Decision-support synthesis of clearance posture, key risks, and recommended next steps.",
  patents:
    "Material patents, claim-level risk, blocking records, and evidence references.",
  claims:
    "Element-by-element claim mapping for patents selected into material review.",
  evidence:
    "Governed evidence search, provenance scope, source authority, and review handoff.",
  drawings:
    "Extracted patent structures and molecule evidence for chemistry review.",
  invalidity:
    "Prior-art posture and validity challenges that may affect blocking risk.",
  regulatory:
    "Regulatory and data-context notes relevant to commercialization review.",
  comments: "Internal collaboration, reviewer notes, and handoff discussion.",
  audit:
    "Reviewer decisions, evidence provenance, and traceable approval posture.",
  meta: "Source coverage, evidence quality, verification checks, and report readiness.",
  reasoning:
    "Decision-support notes surfaced for counsel review and quality checks.",
};

const SECTION_REVIEW_FOCUS: Record<ReportTabId, string> = {
  overview:
    "Decision posture, blocker rationale, and unresolved reliance gates.",
  patents:
    "Claim evidence, active blockers, expiry, legal status, and family risk.",
  claims:
    "Element mapping, missing limitations, and source-linked claim support.",
  evidence:
    "Source authority, provenance gaps, provider scope, and reviewer-ready handoff.",
  drawings:
    "Structure extraction quality, molecule match confidence, and chemistry gaps.",
  invalidity:
    "Prior-art pressure, enablement issues, and validity assumptions.",
  regulatory:
    "Commercialization context, data-exclusivity notes, and jurisdiction caveats.",
  comments: "Reviewer handoff, unresolved questions, and decision ownership.",
  audit: "Reviewer decisions, source provenance, and approval posture.",
  meta: "Source coverage, verification checks, and export-readiness blockers.",
  reasoning:
    "Reasoning trace quality, uncertainty, and follow-up review questions.",
};

export function ReportSectionContextStrip({
  tab,
  tabCounts,
  hasReasoningTraces,
  onAskAi,
  onSearch,
}: ReportSectionContextStripProps) {
  const activeTab = getTabConfig(tab, hasReasoningTraces);
  const evidenceCounts = getEvidenceCounts(tabCounts);
  const reviewFocus = SECTION_REVIEW_FOCUS[tab];
  const critiqueSectionLabel =
    tab === "evidence"
      ? "AI-assisted section critique: evidence workspace"
      : `AI-assisted section critique: ${activeTab.label.toLowerCase()} evidence`;
  const launchContext = buildSectionLaunchContext(
    activeTab.label,
    SECTION_DESCRIPTIONS[tab],
    reviewFocus,
    evidenceCounts,
  );

  return (
    <section
      aria-label="Report section context"
      className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 shadow-[var(--shadow-xs)]"
      data-no-print
    >
      <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_minmax(21rem,0.42fr)]">
        <div className="grid min-w-0 gap-4 p-4 lg:grid-cols-[minmax(16rem,0.95fr)_minmax(0,1.05fr)] lg:items-center">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
              <FileText className="h-4 w-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Current section
              </p>
              <h2 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                {activeTab.label}
              </h2>
              <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:break-word]">
                {SECTION_DESCRIPTIONS[tab]}
              </p>
            </div>
          </div>

          <div className="hidden min-w-0 gap-2 sm:grid sm:grid-cols-3">
            {evidenceCounts.map((item) => (
              <div
                key={item.label}
                className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-3 py-2"
              >
                <p className="truncate text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  {item.label}
                </p>
                <p className="mt-1 whitespace-nowrap text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                  {item.value}
                </p>
              </div>
            ))}
          </div>

          <div className="hidden min-w-0 rounded-md border border-brand-primary/15 bg-brand-primary/[0.07] px-3 py-2 sm:block lg:col-span-2">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-brand-primary">
              Review focus
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
              {reviewFocus}
            </p>
          </div>
        </div>

        <div className="grid gap-2 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]/64 p-4 xl:border-l xl:border-t-0">
          <div className="hidden gap-2 sm:grid sm:grid-cols-2">
            <Button
              type="button"
              className="min-h-11 justify-start gap-2"
              onClick={() => onAskAi?.(launchContext)}
              disabled={!onAskAi}
              aria-label={critiqueSectionLabel}
            >
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              Check for gaps
            </Button>
            <Button
              type="button"
              variant="outline"
              className="min-h-11 justify-start gap-2"
              onClick={onSearch}
            >
              <Search className="h-4 w-4" aria-hidden="true" />
              Search evidence
            </Button>
          </div>
          <div className="flex min-w-0 items-start gap-2 rounded-md border border-warning/20 bg-warning/10 px-3 py-2 text-warning">
            <ShieldCheck
              className="mt-0.5 h-4 w-4 shrink-0"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <p className="text-xs font-semibold">Counsel review required</p>
              <p className="mt-0.5 text-xs leading-4 text-[var(--text-secondary)]">
                Decision support only; verify before commercial reliance.
              </p>
            </div>
          </div>
        </div>
      </div>
      <div className="hidden items-start gap-2 border-t border-[var(--border-subtle)] px-4 py-2 text-xs leading-5 text-[var(--text-tertiary)] sm:flex">
        <Info
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-primary"
          aria-hidden="true"
        />
        <p>
          Section counts reflect the generated report packet; use search for
          reviewed evidence inside this report only.
        </p>
      </div>
    </section>
  );
}

function buildSectionLaunchContext(
  sectionLabel: string,
  description: string,
  reviewFocus: string,
  metadata: Array<{ label: string; value: string }>,
): ReportChatLaunchContext {
  const groundingMetadata = [
    { label: "Review focus", value: reviewFocus },
    { label: "Grounding", value: "Report packet only" },
    { label: "Reliance", value: "Counsel review required" },
  ];

  return {
    actionLabel: "Check section gaps",
    description,
    intent: "section",
    metadata: [...metadata, ...groundingMetadata],
    prompt: `Critique the ${sectionLabel} section of this FTO report for gaps. Focus on ${reviewFocus.toLowerCase()} Identify the evidence basis, blocker implications, uncertainty, and counsel follow-up questions. Keep the answer grounded in this generated report packet, call out unsupported or missing evidence, and do not present the critique as independent verification.`,
    title: `${sectionLabel} section`,
  };
}

function getTabConfig(
  tab: ReportTabId,
  hasReasoningTraces: boolean,
): ReportTabConfig {
  return (
    [...PRIMARY_TABS, ...getOverflowTabs(hasReasoningTraces)].find(
      (config) => config.id === tab,
    ) ?? PRIMARY_TABS[0]
  );
}

function getEvidenceCounts(tabCounts: Record<string, number>) {
  return [
    {
      label: "Patents",
      value: `${(tabCounts.patents ?? 0).toLocaleString()} records`,
    },
    {
      label: "Claims",
      value: `${(tabCounts.claims ?? 0).toLocaleString()} analyzed`,
    },
    {
      label: "Structures",
      value: `${(tabCounts.drawings ?? 0).toLocaleString()} extracted`,
    },
  ];
}
