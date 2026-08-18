"use client";

import { useMemo, useState, type ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { AudienceTaskPanel } from "@/components/help/audience-task-panel";
import { ContactCard } from "@/components/help/contact-card";
import { FaqCard } from "@/components/help/faq-card";
import { GettingStartedCard } from "@/components/help/getting-started-card";
import { GlossaryCard } from "@/components/help/glossary-card";
import { HelpNoResultsState } from "@/components/help/no-results-state";
import { HelpPageHeader } from "@/components/help/page-header";
import { HelpSearchInput } from "@/components/help/search-input";
import { HelpSupportRail } from "@/components/help/support-rail";
import { KeyboardShortcutsCard } from "@/components/help/keyboard-shortcuts-card";
import { PipelineStepsCard } from "@/components/help/pipeline-steps-card";
import { RiskLevelsCard } from "@/components/help/risk-levels-card";
import { HelpSectionNav } from "@/components/help/section-nav";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";
import { getHelpResultCounts } from "@/components/help/helpers";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useClientReady } from "@/hooks/use-client-ready";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";

export default function HelpPage() {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const clientReady = useClientReady();
  const [search, setSearch] = useState("");
  const capabilities = clientReady ? principal.data : undefined;
  const query = search.trim().toLowerCase();
  const hasQuery = query.length > 0;
  const resultCounts = useMemo(
    () => getHelpResultCounts(query, capabilities ?? null),
    [capabilities, query],
  );
  const resultSummary = hasQuery
    ? resultCounts.hasResults
      ? `${resultCounts.total} matching result${
          resultCounts.total === 1 ? "" : "s"
        } across visible help guidance, workflows, support, and glossary terms.`
      : "No matching help guidance, workflows, support routes, or glossary terms."
    : "Search workflow guidance, pipeline steps, FAQ answers, support routes, and patent/FTO glossary terms.";
  const showAudience = !hasQuery || resultCounts.audience > 0;
  const showGettingStarted = !hasQuery || resultCounts.gettingStarted > 0;
  const showPipeline = !hasQuery || resultCounts.pipeline > 0;
  const showFaq = !hasQuery || resultCounts.faq > 0;
  const showGlossary = !hasQuery || resultCounts.glossary > 0;
  const showRisks = !hasQuery || resultCounts.risks > 0;
  const showShortcuts = !hasQuery || resultCounts.shortcuts > 0;
  const showContact = !hasQuery || resultCounts.contact > 0;
  const showSupportRail =
    !hasQuery || resultCounts.workflows > 0 || resultCounts.support > 0;
  const supportRail = showSupportRail ? (
    <div className="lg:col-start-2 lg:row-start-1">
      <HelpMobileDisclosure
        expanded={hasQuery}
        title="Common workflows and support"
        detail="Action routes, access controls, monitoring, and help"
      >
        <HelpSupportRail capabilities={capabilities} query={query} />
      </HelpMobileDisclosure>
    </div>
  ) : null;
  const searchInput = (
    <HelpSearchInput
      value={search}
      onChange={setSearch}
      hasQuery={hasQuery}
      onClear={() => setSearch("")}
      resultSummary={resultSummary}
    />
  );
  const resultSections = (
    <>
      {showAudience ? (
        <HelpMobileDisclosure
          expanded={hasQuery}
          title="Choose guidance by role"
          detail="Counsel, scientist, admin, and founder tasks"
        >
          <AudienceTaskPanel capabilities={capabilities} query={query} />
        </HelpMobileDisclosure>
      ) : null}
      {showGettingStarted ? (
        <HelpMobileDisclosure
          expanded={hasQuery}
          title="Getting started"
          detail="Three steps from compound input to reviewed results"
        >
          <GettingStartedCard capabilities={capabilities} query={query} />
        </HelpMobileDisclosure>
      ) : null}
      {showPipeline ? (
        <HelpMobileDisclosure
          expanded={hasQuery}
          title="Pipeline steps"
          detail="Eight stages from identity resolution to report packet"
        >
          <PipelineStepsCard query={query} />
        </HelpMobileDisclosure>
      ) : null}
      {showFaq ? (
        <HelpMobileDisclosure
          expanded={hasQuery}
          title="Frequently asked questions"
          detail="Scope, sources, exports, billing, privacy, and consistency"
        >
          <FaqCard capabilities={capabilities} query={query} />
        </HelpMobileDisclosure>
      ) : null}
      {showGlossary ? (
        <HelpMobileDisclosure
          expanded={hasQuery}
          title="Patent and FTO glossary"
          detail="Key legal, chemical, and evidence terminology"
        >
          <GlossaryCard query={query} />
        </HelpMobileDisclosure>
      ) : null}
      {showRisks ? (
        <HelpMobileDisclosure
          expanded={hasQuery}
          title="Risk levels explained"
          detail="High, medium, low, and clear review posture"
        >
          <RiskLevelsCard query={query} />
        </HelpMobileDisclosure>
      ) : null}
      {showShortcuts ? (
        <HelpMobileDisclosure
          expanded={hasQuery}
          title="Keyboard shortcuts"
          detail="Command palette and panel controls"
        >
          <KeyboardShortcutsCard query={query} />
        </HelpMobileDisclosure>
      ) : null}
      {showContact ? (
        <HelpMobileDisclosure
          expanded={hasQuery}
          title="Contact and support"
          detail="Route product, access, workflow, or operational questions"
        >
          <ContactCard />
        </HelpMobileDisclosure>
      ) : null}
      {hasQuery && !resultCounts.hasResults ? (
        <HelpNoResultsState search={search} />
      ) : null}
    </>
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
      <HelpPageHeader capabilities={capabilities} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]">
        {hasQuery ? (
          <>
            <div className="min-w-0 space-y-6 lg:col-start-1 lg:row-start-1">
              {searchInput}
            </div>
            {supportRail}
            <div className="min-w-0 space-y-6 lg:col-start-1">
              {resultSections}
            </div>
          </>
        ) : (
          <>
            <div className="min-w-0 space-y-6">
              <HelpSectionNav />
              {searchInput}
              {resultSections}
            </div>
            {supportRail}
          </>
        )}
      </div>
    </div>
  );
}

function HelpMobileDisclosure({
  children,
  detail,
  expanded,
  title,
}: {
  children: ReactNode;
  detail: string;
  expanded: boolean;
  title: string;
}) {
  if (expanded) return children;

  return (
    <ResponsiveDisclosure
      className="group"
      summary={
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3 text-left shadow-[var(--shadow-xs)] sm:hidden [&::-webkit-details-marker]:hidden">
          <span>
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </span>
            <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
              {detail}
            </span>
          </span>
          <ArrowRight
            className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-90"
            aria-hidden="true"
          />
        </summary>
      }
    >
      <div className="mt-3 sm:mt-0">{children}</div>
    </ResponsiveDisclosure>
  );
}
