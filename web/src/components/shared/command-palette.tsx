"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { Clock, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  buildNavigationSearchValue,
  getVisibleNavSections,
  hasClerk,
} from "@/components/layout/sidebar-constants";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { useAnalyses } from "@/hooks/use-analysis";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";

function riskColor(
  risk: import("@praviar/shared-types").RiskLevel | string | null,
): string {
  switch (risk?.toLowerCase()) {
    case "high":
      return "text-error";
    case "medium":
      return "text-warning";
    case "low":
      return "text-success";
    case "clear":
      return "text-info";
    default:
      return "text-[var(--text-disabled)]";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "completed":
      return "Completed";
    case "running":
      return "Running";
    case "failed":
      return "Failed";
    case "pending":
      return "Pending";
    default:
      return status;
  }
}

export function CommandPaletteContent({
  orgRole,
}: {
  orgRole: string | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const token = useAuthToken();
  const { data } = useAnalyses(token);
  const principal = usePrincipalCapabilities(token);
  const applicationRole = principal.data?.role ?? null;
  const recentAnalyses = token ? (data?.items?.slice(0, 5) ?? []) : [];

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((previous) => !previous);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const runCommand = useCallback((command: () => void) => {
    setOpen(false);
    command();
  }, []);

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search workspace..." />
      <CommandList>
        <CommandEmpty>
          No matching destination, analysis, or action.
        </CommandEmpty>

        <NavigationCommandGroups
          orgRole={orgRole}
          applicationRole={applicationRole}
          onNavigate={(href) => runCommand(() => router.push(href))}
        />

        {recentAnalyses.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="Recent Analyses">
              {recentAnalyses.map((analysis) =>
                (() => {
                  const riskRestricted =
                    analysis.risk_ratings_restricted ||
                    principal.data?.risk_ratings_restricted;

                  return (
                    <CommandItem
                      key={analysis.id}
                      value={`${analysis.compound_name} ${analysis.id}`}
                      onSelect={() =>
                        runCommand(() =>
                          router.push(`/analyses/${analysis.id}`),
                        )
                      }
                    >
                      <Clock
                        className="mr-2 h-4 w-4 text-[var(--text-tertiary)]"
                        aria-hidden="true"
                      />
                      <span className="flex-1">{analysis.compound_name}</span>
                      <span
                        className={`text-xs font-semibold uppercase ${
                          riskRestricted
                            ? "text-warning"
                            : riskColor(analysis.overall_risk)
                        }`}
                      >
                        {riskRestricted
                          ? "Counsel only"
                          : (analysis.overall_risk ?? "N/A")}
                      </span>
                      <span className="ml-2 text-xs text-[var(--text-tertiary)]">
                        {statusLabel(analysis.status)}
                      </span>
                    </CommandItem>
                  );
                })(),
              )}
            </CommandGroup>
          </>
        ) : null}

        {principal.data?.can_create_analysis === true ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="Actions">
              <CommandItem
                value="New FTO Analysis launch create start compound"
                onSelect={() => runCommand(() => router.push("/analyses/new"))}
              >
                <Plus
                  className="mr-2 h-4 w-4 text-brand-primary"
                  aria-hidden="true"
                />
                <span>New FTO Analysis</span>
              </CommandItem>
            </CommandGroup>
          </>
        ) : null}
      </CommandList>
    </CommandDialog>
  );
}

export function NavigationCommandGroups({
  orgRole,
  applicationRole,
  onNavigate,
}: {
  orgRole: string | null | undefined;
  applicationRole?: string | null;
  onNavigate: (href: string) => void;
}) {
  return getVisibleNavSections(orgRole, applicationRole).map((section) => (
    <CommandGroup key={section.id} heading={section.label}>
      {section.items.map((item) => (
        <CommandItem
          key={item.href}
          value={buildNavigationSearchValue(item)}
          keywords={[...item.keywords]}
          onSelect={() => onNavigate(item.href)}
        >
          <item.icon
            className="mr-1 h-4 w-4 shrink-0 text-[var(--text-tertiary)]"
            aria-hidden="true"
          />
          <span className="min-w-0">
            <span className="block font-medium">{item.label}</span>
            <span className="block truncate text-xs text-[var(--text-tertiary)]">
              {item.description}
            </span>
          </span>
        </CommandItem>
      ))}
    </CommandGroup>
  ));
}

function ClerkScopedCommandPalette() {
  const { isLoaded, orgRole } = useAuth();

  return <CommandPaletteContent orgRole={isLoaded ? orgRole : null} />;
}

export function CommandPalette() {
  if (hasClerk) return <ClerkScopedCommandPalette />;

  return <CommandPaletteContent orgRole="org:admin" />;
}
