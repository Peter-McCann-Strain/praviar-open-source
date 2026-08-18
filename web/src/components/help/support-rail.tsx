import Link from "next/link";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
import {
  HELP_SUPPORT_ITEMS,
  HELP_SECTION_SEARCH_TERMS,
  HELP_WORKFLOWS,
  canAccessHelpWorkflow,
  matchesHelpQuery,
} from "@/components/help/helpers";
import { Badge } from "@/components/ui/badge";
import {
  canAccessWorkspaceHref,
  type PrincipalCapabilities,
} from "@/hooks/use-principal-capabilities";

interface HelpSupportRailProps {
  capabilities?: PrincipalCapabilities;
  query?: string;
}

export function HelpSupportRail({
  capabilities,
  query = "",
}: HelpSupportRailProps) {
  const normalizedQuery = query.trim().toLowerCase();
  const workflows = HELP_WORKFLOWS.filter(
    (item) =>
      canAccessHelpWorkflow(capabilities, item) &&
      matchesHelpQuery(
        normalizedQuery,
        ...HELP_SECTION_SEARCH_TERMS.workflows,
        item.label,
        item.desc,
      ),
  );
  const supportItems = HELP_SUPPORT_ITEMS.filter(
    (item) =>
      canAccessWorkspaceHref(capabilities, item.href) &&
      matchesHelpQuery(
        normalizedQuery,
        ...HELP_SECTION_SEARCH_TERMS.support,
        item.label,
        item.value,
        item.desc,
      ),
  );

  return (
    <div className="space-y-4 lg:sticky lg:top-24 lg:self-start">
      {workflows.length > 0 ? (
        <section
          aria-labelledby="help-workflows-heading"
          className="praviar-control-plane-header rounded-lg border border-[var(--border-subtle)] p-4 shadow-[var(--shadow-sm)]"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Common workflows
              </p>
              <h2
                id="help-workflows-heading"
                className="mt-1 text-base font-semibold text-[var(--text-primary)]"
              >
                Move from guidance to action
              </h2>
            </div>
            <Badge variant="secondary">Support</Badge>
          </div>

          <div className="mt-4 grid gap-2">
            {workflows.map((item) => {
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group flex min-w-0 items-start gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 p-3 text-left shadow-[var(--shadow-xs)] transition-colors hover:border-brand-primary/35 hover:bg-brand-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex min-w-0 items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                      <span className="min-w-0 [overflow-wrap:anywhere]">
                        {item.label}
                      </span>
                      <ArrowUpRight
                        className="h-3.5 w-3.5 shrink-0 text-[var(--text-tertiary)] transition-colors group-hover:text-brand-primary"
                        aria-hidden="true"
                      />
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">
                      {item.desc}
                    </span>
                  </span>
                </Link>
              );
            })}
          </div>
        </section>
      ) : null}

      {supportItems.length > 0 ? (
        <section
          aria-labelledby="help-support-heading"
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-sm)]"
        >
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-success/25 bg-success/10 text-success">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h2
                id="help-support-heading"
                className="text-base font-semibold text-[var(--text-primary)]"
              >
                Support posture
              </h2>
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                Help content is safe to browse; operational changes happen only
                from the linked workspaces.
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-3">
            {supportItems.map((item) => {
              const Icon = item.icon;

              return (
                <Link
                  key={item.label}
                  href={item.href}
                  className="flex min-w-0 items-start gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3 transition-colors hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                >
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                      {item.label}
                    </span>
                    <span className="mt-0.5 block text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                      {item.value}
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">
                      {item.desc}
                    </span>
                  </span>
                </Link>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}
