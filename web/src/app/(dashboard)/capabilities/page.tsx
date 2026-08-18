"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  MARKET_BAR,
  WORKFLOW_STEPS,
  getCapabilityCatalog,
} from "@/components/capabilities/capability-catalog";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useClientReady } from "@/hooks/use-client-ready";
import {
  canAccessWorkspaceHref,
  usePrincipalCapabilities,
} from "@/hooks/use-principal-capabilities";
import { cn } from "@/lib/utils";

const WORKFLOW_STAGE_GROUPS = [
  {
    label: "Scope",
    detail: "Compound, jurisdiction, and launch intent",
    steps: ["Analyze", "Stream"],
  },
  {
    label: "Decide",
    detail: "Report, claims, AI answers, and review",
    steps: ["Report", "Ask AI", "Review"],
  },
  {
    label: "Operate",
    detail: "Monitor, package, share, and govern",
    steps: ["Monitor", "Export", "Share", "Notify", "Govern"],
  },
];

const STORY_TONE_CLASS: Record<string, string> = {
  Counsel:
    "border-[color:color-mix(in_srgb,var(--risk-high)_28%,transparent)] bg-[color:color-mix(in_srgb,var(--risk-high)_5%,transparent)]",
  Diligence: "border-brand-primary/25 bg-brand-primary/7",
  Founder: "border-success/25 bg-success/8",
  Operations: "border-warning/25 bg-warning/8",
};

const STORY_ICON_TONE_CLASS: Record<string, string> = {
  Counsel:
    "bg-[color:color-mix(in_srgb,var(--risk-high)_11%,transparent)] text-[var(--risk-high)]",
  Diligence: "bg-brand-primary/10 text-brand-primary",
  Founder: "bg-success/10 text-success",
  Operations: "bg-warning/10 text-warning",
};

const ROLE_PATH_COPY: Record<
  string,
  {
    actionLabel: string;
    assistantCue: string;
    question: string;
    task: string;
  }
> = {
  Counsel: {
    actionLabel: "Review blocker brief",
    assistantCue: "AI blocker brief preloaded",
    question: "Can this route proceed?",
    task: "Inspect blocking families, claim fit, assumptions, and reviewer handoff.",
  },
  Founder: {
    actionLabel: "Open founder packet",
    assistantCue: "AI external readout preloaded",
    question: "What can I share safely?",
    task: "Read the plain-English risk posture, caveats, and share-ready summary.",
  },
  Diligence: {
    actionLabel: "Compare portfolio work",
    assistantCue: "AI reviewer questions preloaded",
    question: "Which compounds need attention?",
    task: "Compare runs, workload, review ownership, and diligence-ready exports.",
  },
  Operations: {
    actionLabel: "Watch live progress",
    assistantCue: "Live state view",
    question: "Where is the work stuck?",
    task: "Track streaming progress, source gates, queue state, and recovery paths.",
  },
};

export default function CapabilitiesPage() {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const clientReady = useClientReady();
  const capabilities = clientReady ? principal.data : undefined;
  const localDemoWorkspaceEnabled = DEMO_MODE_ENABLED;
  const {
    capabilityGroups: catalogCapabilityGroups,
    demoScriptSteps: catalogDemoScriptSteps,
    demoStories: catalogDemoStories,
    showcaseHref,
  } = getCapabilityCatalog({ localDemoWorkspaceEnabled });
  const capabilityGroups = catalogCapabilityGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        canAccessWorkspaceHref(capabilities, item.href),
      ),
    }))
    .filter((group) => group.items.length > 0);
  const commandCapabilityItems = capabilityGroups.flatMap((group) =>
    group.items.map((item) => ({ ...item, groupTitle: group.title })),
  );
  const demoScriptSteps = catalogDemoScriptSteps.filter((step) =>
    canAccessWorkspaceHref(capabilities, step.href),
  );
  const demoStories = catalogDemoStories.filter((story) =>
    canAccessWorkspaceHref(capabilities, story.href),
  );
  const canCreateAnalysis = capabilities?.can_create_analysis === true;
  const canViewReviewQueue = capabilities?.can_view_review_queue === true;
  const endpointCount = new Set(
    commandCapabilityItems.flatMap((item) => item.endpoints),
  ).size;
  const showcaseLabel = localDemoWorkspaceEnabled
    ? "Open counsel case"
    : "Open analysis library";
  const showcaseActionLabel = localDemoWorkspaceEnabled
    ? "Walk counsel case"
    : "Review live analyses";
  const roleDecisionPaths = demoStories.map((story) => ({
    ...story,
    ...(ROLE_PATH_COPY[story.audience] ?? {
      actionLabel: "Open workflow",
      assistantCue: "Context carried forward",
      question: "What should I do next?",
      task: story.description,
    }),
  }));
  const workflowMetrics = [
    {
      label: "Decision roles",
      value: roleDecisionPaths.length,
      detail: "Counsel, founder, diligence, ops",
    },
    {
      label: "Workflow actions",
      value: commandCapabilityItems.length,
      detail: "Routable FTO workspaces",
    },
    {
      label: "Reviewable proof",
      value: endpointCount,
      detail: "Evidence routes behind each action",
    },
    {
      label: "Handoff steps",
      value: demoScriptSteps.length,
      detail: "AI, review, monitor, export",
    },
  ];

  return (
    <div className="mx-auto max-w-7xl space-y-6 animate-fade-up">
      <AppSurfaceHeader
        className="praviar-workflow-atlas-field"
        eyebrow="Workflow atlas"
        title="FTO Workflow Atlas"
        description="A buyer-safe map of the Praviar case lifecycle: launch a compound, inspect risk evidence, ask governed AI, route findings to review, monitor changes, and package the result."
        dataTestId="capabilities-app-surface-header"
        markSize="lg"
        mobileDensity="compact"
        metrics={[
          {
            label: "Decision roles",
            value: roleDecisionPaths.length.toLocaleString(),
            detail: "Buyer tasks mapped to FTO actions",
            tone: "active",
          },
          {
            label: "Workflow actions",
            value: commandCapabilityItems.length.toLocaleString(),
            detail: "Routable workspaces",
          },
          {
            label: "Reviewable proof",
            value: endpointCount.toLocaleString(),
            detail: "Evidence routes behind actions",
          },
        ]}
        actions={
          <div className="w-full space-y-3 lg:w-[22rem]">
            <Button asChild className="min-h-11 w-full">
              <Link href={showcaseHref}>{showcaseLabel}</Link>
            </Button>
            <nav
              aria-label="Decision role shortcuts"
              className="grid grid-cols-2 gap-2"
            >
              {roleDecisionPaths.map((path) => (
                <Link
                  key={`header-${path.audience}`}
                  href={path.href}
                  className={cn(
                    "group min-h-[4.75rem] rounded-lg border p-3 text-left shadow-[var(--shadow-xs)] transition-colors hover:border-brand-primary/40 hover:bg-brand-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70",
                    STORY_TONE_CLASS[path.audience],
                  )}
                >
                  <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    {path.audience}
                  </span>
                  <span className="mt-1 line-clamp-2 block text-xs font-semibold leading-5 text-[var(--text-primary)]">
                    {path.question}
                  </span>
                </Link>
              ))}
            </nav>
          </div>
        }
      />

      <nav
        aria-label="Workflow atlas sections"
        className="sticky top-[4.5rem] z-20 grid snap-x snap-mandatory grid-flow-col grid-rows-2 auto-cols-[minmax(8rem,1fr)] gap-1 overflow-x-auto overscroll-x-contain rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)]/95 p-1 shadow-[var(--shadow-sm)] backdrop-blur sm:hidden"
      >
        <AtlasJumpLink href="#capabilities-decision" label="Decide" />
        <AtlasJumpLink href="#capabilities-walkthrough" label="Walkthrough" />
        {capabilityGroups.map((group) => (
          <AtlasJumpLink
            key={`jump-${group.title}`}
            href={`#capability-${toSectionId(group.title)}`}
            label={group.title}
          />
        ))}
      </nav>

      <section
        id="capabilities-decision"
        className="scroll-mt-36 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)]/88 p-4 shadow-[var(--shadow-sm)] backdrop-blur sm:p-5"
      >
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={DEMO_MODE_ENABLED ? "success" : "secondary"}>
                {DEMO_MODE_ENABLED
                  ? "Demo fixtures ready"
                  : "Live backend mode"}
              </Badge>
              <Badge variant="outline">Role-aware walkthrough</Badge>
            </div>
            <h2 className="mt-3 text-lg font-semibold text-[var(--text-primary)]">
              Decision router
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
              Start with the user question, then open the exact workspace state
              with the right AI context, evidence record, reviewer ownership,
              and export boundary already visible.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {canCreateAnalysis ? (
              <Button asChild size="sm" variant="outline" className="min-h-11">
                <Link href="/analyses/new">Start adaptive analysis</Link>
              </Button>
            ) : null}
            {canViewReviewQueue ? (
              <Button asChild size="sm" variant="outline" className="min-h-11">
                <Link href="/reviews">Open review queue</Link>
              </Button>
            ) : null}
            <Button asChild size="sm" className="min-h-11">
              <Link href={showcaseHref}>{showcaseActionLabel}</Link>
            </Button>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {roleDecisionPaths.map((path) => {
            const Icon = path.icon;
            return (
              <Link
                key={path.audience}
                href={path.href}
                className={cn(
                  "group flex min-h-[10.5rem] flex-col justify-between rounded-lg border p-4 shadow-[var(--shadow-xs)] transition-colors hover:border-brand-primary/40 hover:bg-brand-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70",
                  STORY_TONE_CLASS[path.audience],
                )}
              >
                <span className="flex items-start justify-between gap-3">
                  <span>
                    <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      {path.audience} path
                    </span>
                    <span className="mt-1 block text-xs font-medium leading-5 text-brand-primary">
                      {path.title}
                    </span>
                    <span className="mt-2 block text-sm font-semibold leading-5 text-[var(--text-primary)]">
                      {path.question}
                    </span>
                  </span>
                  <span
                    className={cn(
                      "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                      STORY_ICON_TONE_CLASS[path.audience],
                    )}
                  >
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                </span>
                <span className="mt-3 block text-xs leading-relaxed text-[var(--text-secondary)]">
                  {path.description} {path.task}
                </span>
                <span className="mt-3 inline-flex w-fit items-center rounded-full border border-brand-primary/18 bg-brand-primary/8 px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-brand-primary">
                  {path.assistantCue}
                </span>
                <span className="mt-4 inline-flex min-h-11 items-center justify-between gap-2 rounded-md border border-brand-primary/20 bg-[var(--bg-surface)]/78 px-3 text-xs font-semibold text-brand-primary shadow-[var(--shadow-xs)]">
                  {path.actionLabel}
                  <ArrowRight
                    className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
                    aria-hidden="true"
                  />
                </span>
              </Link>
            );
          })}
        </div>

        <AtlasMobileDisclosure
          className="mt-4"
          title="Workflow depth and handoff stages"
          detail={`${workflowMetrics[1]?.value ?? 0} actions across scope, decision, and operations`}
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {workflowMetrics.map((metric) => (
              <div
                key={metric.label}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/35 p-4"
              >
                <p className="text-xs font-medium text-[var(--text-tertiary)]">
                  {metric.label}
                </p>
                <p className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
                  {metric.value}
                </p>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  {metric.detail}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            {WORKFLOW_STAGE_GROUPS.map((stage, index) => (
              <div
                key={stage.label}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 p-4 shadow-[var(--shadow-xs)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      Stage {index + 1}
                    </p>
                    <h3 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                      {stage.label}
                    </h3>
                  </div>
                  <span className="rounded-full border border-brand-primary/20 bg-brand-primary/8 px-2 py-0.5 text-xs font-semibold text-brand-primary">
                    {stage.steps.length} steps
                  </span>
                </div>
                <p className="mt-2 min-h-10 text-xs leading-relaxed text-[var(--text-secondary)]">
                  {stage.detail}
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {stage.steps.map((label) => {
                    const step = WORKFLOW_STEPS.find(
                      (candidate) => candidate.label === label,
                    );
                    const Icon = step?.icon;
                    return (
                      <span
                        key={label}
                        className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/35 px-2 text-xs font-semibold text-[var(--text-primary)]"
                      >
                        {Icon ? (
                          <Icon
                            className="h-3.5 w-3.5 text-brand-primary"
                            aria-hidden="true"
                          />
                        ) : null}
                        {label}
                      </span>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </AtlasMobileDisclosure>
      </section>

      <section
        id="capabilities-walkthrough"
        className="grid scroll-mt-36 gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]"
      >
        <AtlasMobileDisclosure
          title="Case walkthrough"
          detail={`${demoScriptSteps.length} evidence-to-handoff steps`}
        >
          <Card>
            <CardHeader className="hidden p-5 pb-2 sm:block">
              <CardTitle className="text-base">Case Walkthrough</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 p-5 sm:pt-2">
              {demoScriptSteps.map((step, index) => {
                const Icon = step.icon;
                return (
                  <Link
                    key={step.label}
                    href={step.href}
                    className="group grid gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)]/30 p-4 transition-colors hover:border-brand-primary/40 hover:bg-brand-primary/5 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-start"
                  >
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-primary/10 text-sm font-semibold text-brand-primary">
                      {index + 1}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Icon
                          className="h-4 w-4 text-brand-primary"
                          aria-hidden="true"
                        />
                        <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                          {step.label}
                        </h2>
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                        {step.description}
                      </p>
                    </div>
                    <ArrowRight
                      className="hidden h-4 w-4 text-[var(--text-tertiary)] transition-transform group-hover:translate-x-0.5 group-hover:text-brand-primary sm:block"
                      aria-hidden="true"
                    />
                  </Link>
                );
              })}
            </CardContent>
          </Card>
        </AtlasMobileDisclosure>

        <AtlasMobileDisclosure
          title="Trust bar"
          detail={`${MARKET_BAR.length} buyer and counsel proof points`}
        >
          <Card>
            <CardHeader className="hidden p-5 pb-2 sm:block">
              <CardTitle className="text-base">Trust Bar</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 p-5 sm:pt-2">
              {MARKET_BAR.map((item) => (
                <div
                  key={item.title}
                  className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)]/30 p-4"
                >
                  <div className="flex items-center gap-2">
                    <CheckCircle2
                      className="h-4 w-4 text-success"
                      aria-hidden="true"
                    />
                    <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                      {item.title}
                    </h2>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">
                    {item.description}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </AtlasMobileDisclosure>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        {capabilityGroups.map((group) => {
          const Icon = group.icon;
          return (
            <AtlasMobileDisclosure
              key={group.title}
              id={`capability-${toSectionId(group.title)}`}
              className="scroll-mt-36"
              title={group.title}
              detail={`${group.items.length} workflow${group.items.length === 1 ? "" : "s"} with evidence routes`}
              icon={<Icon className="h-5 w-5 text-brand-primary" />}
            >
              <Card>
                <CardHeader className="hidden p-5 pb-2 sm:block">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Icon
                      className="h-5 w-5 text-brand-primary"
                      aria-hidden="true"
                    />
                    {group.title}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 p-5 sm:pt-2">
                  {group.items.map((item) => (
                    <article
                      key={item.label}
                      className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)]/30 p-4 transition-colors hover:border-brand-primary/40 hover:bg-brand-primary/5"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                          {item.label}
                        </h3>
                        <Link
                          href={item.href}
                          className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-brand-primary/20 bg-[var(--bg-surface)]/80 px-3 py-1 text-xs font-semibold text-brand-primary shadow-[var(--shadow-xs)] transition-colors hover:bg-brand-primary/8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                        >
                          Open workflow
                          <ArrowRight
                            className="h-3.5 w-3.5"
                            aria-hidden="true"
                          />
                        </Link>
                      </div>
                      <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">
                        {item.description}
                      </p>
                      <details className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 px-3 py-2 text-xs text-[var(--text-secondary)]">
                        <summary className="flex min-h-11 cursor-pointer items-center font-semibold text-[var(--text-primary)] marker:text-brand-primary">
                          {item.label} proof · {item.endpoints.length} route
                          {item.endpoints.length === 1 ? "" : "s"}
                        </summary>
                        <div className="mt-2 flex flex-wrap gap-1">
                          {item.endpoints.map((endpoint) => (
                            <Badge
                              key={endpoint}
                              variant="secondary"
                              className="font-mono text-xs"
                            >
                              {endpoint}
                            </Badge>
                          ))}
                        </div>
                      </details>
                    </article>
                  ))}
                </CardContent>
              </Card>
            </AtlasMobileDisclosure>
          );
        })}
      </section>
    </div>
  );
}

function AtlasJumpLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      className="inline-flex min-h-11 min-w-0 snap-start items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 px-2 py-2 text-center text-xs font-semibold leading-4 text-[var(--text-primary)] [overflow-wrap:anywhere] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
    >
      {label}
    </a>
  );
}

function AtlasMobileDisclosure({
  children,
  className,
  detail,
  icon,
  id,
  title,
}: {
  children: ReactNode;
  className?: string;
  detail: string;
  icon?: ReactNode;
  id?: string;
  title: string;
}) {
  return (
    <ResponsiveDisclosure
      id={id}
      className={cn("group", className)}
      summary={
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3 text-left shadow-[var(--shadow-xs)] sm:hidden [&::-webkit-details-marker]:hidden">
          <span className="flex min-w-0 items-center gap-3">
            {icon ? (
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-primary/8">
                {icon}
              </span>
            ) : null}
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-[var(--text-primary)]">
                {title}
              </span>
              <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                {detail}
              </span>
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

function toSectionId(label: string) {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "-")
    .replace(/^-|-$/gu, "");
}
