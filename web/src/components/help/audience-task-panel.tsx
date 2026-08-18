import Link from "next/link";
import { ArrowRight, Compass, FileSearch, LifeBuoy, Route } from "lucide-react";
import {
  HELP_AUDIENCE_TASKS,
  HELP_SUPPORT_ITEMS,
  HELP_WORKFLOWS,
  HELP_SECTION_SEARCH_TERMS,
  STEP_DESCRIPTIONS,
  canAccessHelpWorkflow,
  matchesHelpQuery,
} from "@/components/help/helpers";
import { Badge } from "@/components/ui/badge";
import {
  canAccessWorkspaceHref,
  type PrincipalCapabilities,
} from "@/hooks/use-principal-capabilities";

interface AudienceTaskPanelProps {
  capabilities?: PrincipalCapabilities;
  query?: string;
}

export function AudienceTaskPanel({
  capabilities,
  query = "",
}: AudienceTaskPanelProps) {
  const normalizedQuery = query.trim().toLowerCase();
  const tasks = HELP_AUDIENCE_TASKS.filter(
    (task) =>
      canAccessWorkspaceHref(capabilities, task.href) &&
      matchesHelpQuery(
        normalizedQuery,
        ...HELP_SECTION_SEARCH_TERMS.audience,
        task.audience,
        task.title,
        task.desc,
        ...task.tags,
      ),
  );
  const visibleWorkflows = HELP_WORKFLOWS.filter((item) =>
    canAccessHelpWorkflow(capabilities, item),
  );
  const visibleSupportItems = HELP_SUPPORT_ITEMS.filter((item) =>
    canAccessWorkspaceHref(capabilities, item.href),
  );
  const commandStats = [
    {
      icon: Route,
      label: "Role routes",
      value: `${tasks.length}`,
      detail: "Counsel, R&D, admin, and founder paths",
    },
    {
      icon: FileSearch,
      label: "Evidence map",
      value: `${Object.keys(STEP_DESCRIPTIONS).length} steps`,
      detail: "From compound resolution to report packet",
    },
    {
      icon: LifeBuoy,
      label: "Handoff paths",
      value: `${visibleSupportItems.length}`,
      detail: "Support, access controls, and monitoring",
    },
  ];

  return (
    <section
      id="common-tasks"
      aria-labelledby="common-tasks-heading"
      className="praviar-control-plane-header scroll-mt-36 overflow-hidden rounded-lg border border-[var(--border-subtle)] p-4 shadow-[var(--shadow-sm)] sm:p-5"
      data-help-command-layer
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.72fr)] xl:items-start">
        <div className="min-w-0">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Help command layer
              </p>
              <h2
                id="common-tasks-heading"
                className="mt-1 text-lg font-semibold text-[var(--text-primary)]"
              >
                Start from the workflow, not the manual
              </h2>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
                Choose the closest role and jump to guidance that matches the
                decision you are trying to make.
              </p>
            </div>
            <Badge variant={normalizedQuery ? "secondary" : "success"}>
              {normalizedQuery
                ? `${tasks.length} route match${tasks.length === 1 ? "" : "es"}`
                : "Task routed"}
            </Badge>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {tasks.map((task) => (
              <Link
                key={task.audience}
                href={task.href}
                className="group flex min-w-0 flex-col rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/76 p-4 shadow-[var(--shadow-xs)] transition-colors hover:border-brand-primary/35 hover:bg-brand-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
              >
                <span className="flex min-w-0 items-center justify-between gap-3">
                  <span className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
                    <Compass className="h-3.5 w-3.5" aria-hidden="true" />
                    {task.audience}
                  </span>
                  <ArrowRight
                    className="h-4 w-4 shrink-0 text-[var(--text-tertiary)] transition-colors group-hover:text-brand-primary"
                    aria-hidden="true"
                  />
                </span>
                <span className="mt-2 min-w-0 text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {task.title}
                </span>
                <span className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  {task.desc}
                </span>
              </Link>
            ))}
          </div>
        </div>

        {!normalizedQuery ? (
          <div
            aria-labelledby="help-command-brief-heading"
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  Command brief
                </p>
                <h3
                  id="help-command-brief-heading"
                  className="mt-1 text-sm font-semibold text-[var(--text-primary)]"
                >
                  Route, verify, hand off
                </h3>
              </div>
              <Badge variant="secondary">
                {visibleWorkflows.length} actions
              </Badge>
            </div>
            <dl className="mt-4 grid gap-2">
              {commandStats.map((item) => {
                const Icon = item.icon;

                return (
                  <div
                    key={item.label}
                    className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-3 py-2"
                  >
                    <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
                        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                      </span>
                      {item.label}
                    </dt>
                    <dd className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                      {item.value}
                    </dd>
                    <dd className="mt-0.5 text-xs leading-5 text-[var(--text-secondary)]">
                      {item.detail}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>
        ) : null}
      </div>
    </section>
  );
}
