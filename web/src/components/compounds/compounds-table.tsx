import { Atom, ChevronRight, FileText } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { CompoundItem } from "@/hooks/use-compounds";
import {
  formatAnalysisCount,
  formatCompoundDate,
  normalizeFunctionalGroups,
} from "@/components/compounds/helpers";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";

interface CompoundsTableProps {
  compounds: CompoundItem[];
  selectedId: string | null;
  searchQuery: string;
  isLoading?: boolean;
  isUpdating?: boolean;
  isOutOfRangeEmptyPage?: boolean;
  getDetailId: (compoundId: string) => string;
  onToggleSelect: (compoundId: string) => void;
  onSearchExampleSelect: (value: string) => void;
}

export function CompoundsTable({
  compounds,
  selectedId,
  searchQuery,
  isLoading = false,
  isUpdating = false,
  isOutOfRangeEmptyPage = false,
  getDetailId,
  onToggleSelect,
  onSearchExampleSelect,
}: CompoundsTableProps) {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const canCreateAnalysis = principal.data?.can_create_analysis === true;
  const hasSearch = searchQuery.trim().length > 0;
  const loadingTitle = hasSearch
    ? "Loading matching compounds"
    : "Loading compound records";

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-2 border-b border-[var(--border-subtle)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Compound evidence records
          </h2>
          <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
            Normalized identifiers, molecular properties, evidence counts, and
            indexed chemistry signals.
          </p>
        </div>
        {isUpdating ? (
          <span
            className="w-fit rounded-md border border-brand-primary/20 bg-brand-primary/10 px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-brand-primary"
            role="status"
            aria-live="polite"
          >
            Updating records
          </span>
        ) : null}
      </div>
      <CardContent
        aria-label="Compound records horizontal scroll area"
        className="overflow-hidden p-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] md:overflow-x-auto md:p-0"
        role="region"
        tabIndex={0}
      >
        <table
          className="w-full min-w-0 md:min-w-[940px]"
          aria-busy={isLoading || isUpdating ? "true" : undefined}
        >
          <caption className="sr-only">
            Compound records with normalized identifiers, molecular properties,
            analysis counts, functional groups, and first analyzed dates.
          </caption>
          <thead className="sr-only md:not-sr-only md:sticky md:top-0 md:z-10 md:table-header-group">
            <tr className="praviar-glass-strip border-b border-[var(--border-default)]">
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
              >
                Compound identity
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
              >
                Identifiers
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
              >
                Formula
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
              >
                MW
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
              >
                Evidence
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
              >
                Functional groups
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
              >
                First Analyzed Here
              </th>
            </tr>
          </thead>
          <tbody className="block space-y-3 md:table-row-group md:divide-y md:divide-[var(--border-subtle)] md:space-y-0">
            {isLoading && compounds.length === 0 ? (
              <tr className="block md:table-row">
                <td
                  className="block px-4 py-0 md:table-cell md:px-6"
                  colSpan={7}
                >
                  <EmptyState
                    icon={FileText}
                    title={loadingTitle}
                    description="Keeping the compound controls available while the library query updates."
                  />
                </td>
              </tr>
            ) : isOutOfRangeEmptyPage ? (
              <tr className="block md:table-row">
                <td
                  className="block px-4 py-0 md:table-cell md:px-6"
                  colSpan={7}
                >
                  <EmptyState
                    icon={FileText}
                    title="Refreshing compound page"
                    description="The current result window is empty while the library moves back to a valid page."
                  />
                </td>
              </tr>
            ) : compounds.length > 0 ? (
              compounds.map((compound) => {
                const isSelected = selectedId === compound.id;
                const detailId = getDetailId(compound.id);
                return (
                  <tr
                    key={compound.id}
                    className={cn(
                      "block rounded-lg border border-l-[3px] p-3 shadow-[var(--shadow-xs)] transition-colors md:table-row md:border-x-0 md:border-b-0 md:border-r-0 md:p-0 md:shadow-none",
                      isSelected
                        ? "border-l-brand-primary bg-brand-primary/5 md:bg-brand-primary/5"
                        : "border-l-brand-primary/30 bg-[var(--surface-muted)]/60 hover:bg-[var(--surface-subtle)] md:bg-transparent",
                    )}
                  >
                    <td className="block pb-3 md:table-cell md:px-4 md:py-3">
                      <button
                        type="button"
                        aria-expanded={isSelected}
                        aria-controls={isSelected ? detailId : undefined}
                        aria-label={`${isSelected ? "Hide" : "Show"} details for ${compound.name}`}
                        className="group flex min-h-11 w-full min-w-0 items-start justify-between gap-3 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
                        onClick={() => onToggleSelect(compound.id)}
                      >
                        <span className="min-w-0">
                          <span
                            className="block break-words text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]"
                            title={compound.name}
                          >
                            {compound.name}
                          </span>
                          <span className="mt-1 block text-xs text-[var(--text-tertiary)]">
                            Normalized compound dossier
                          </span>
                        </span>
                        <ChevronRight
                          className={cn(
                            "mt-0.5 h-4 w-4 shrink-0 text-[var(--text-disabled)] transition-transform group-hover:text-brand-primary",
                            isSelected && "rotate-90 text-brand-primary",
                          )}
                          aria-hidden="true"
                        />
                      </button>
                    </td>
                    <td className="grid min-w-0 gap-1 py-2 md:table-cell md:px-4 md:py-3">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        Identifiers
                      </span>
                      <div className="min-w-0 space-y-1">
                        <IdentifierLine
                          label="SMILES"
                          value={compound.canonical_smiles}
                        />
                        <IdentifierLine
                          label="InChI"
                          value={compound.inchi_key}
                        />
                      </div>
                    </td>
                    <td className="grid grid-cols-[6.5rem_1fr] items-center gap-3 py-2 md:table-cell md:px-4 md:py-3">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        Formula
                      </span>
                      <p className="font-mono text-sm font-semibold text-[var(--text-secondary)]">
                        {compound.molecular_formula || "\u2014"}
                      </p>
                    </td>
                    <td className="grid grid-cols-[6.5rem_1fr] items-center gap-3 py-2 md:table-cell md:px-4 md:py-3 md:text-right">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        MW
                      </span>
                      <span className="tabular-nums text-sm text-[var(--text-secondary)]">
                        {compound.molecular_weight !== null
                          ? compound.molecular_weight.toFixed(1)
                          : "\u2014"}
                      </span>
                    </td>
                    <td className="grid grid-cols-[6.5rem_1fr] items-center gap-3 py-2 md:table-cell md:px-4 md:py-3">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        Analyses
                      </span>
                      <Badge
                        variant="secondary"
                        className="w-fit justify-self-start whitespace-nowrap"
                      >
                        {formatAnalysisCount(compound.analysis_count)}
                      </Badge>
                    </td>
                    <td className="grid min-w-0 gap-1 py-2 md:table-cell md:px-4 md:py-3">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        Groups
                      </span>
                      <FunctionalGroupChips
                        groups={compound.functional_groups}
                      />
                    </td>
                    <td className="grid grid-cols-[6.5rem_1fr] items-center gap-3 py-2 md:table-cell md:px-4 md:py-3">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        First Analyzed Here
                      </span>
                      <span className="text-sm text-[var(--text-secondary)]">
                        {formatCompoundDate(compound.first_analyzed_at)}
                      </span>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr className="block md:table-row">
                <td
                  className="block px-4 py-0 md:table-cell md:px-6"
                  colSpan={7}
                >
                  <EmptyState
                    icon={hasSearch ? FileText : Atom}
                    title={
                      hasSearch
                        ? "No compounds match this search"
                        : "No compounds yet"
                    }
                    description={
                      hasSearch
                        ? "Try a compound name, SMILES fragment, InChI key, or a broader identifier."
                        : "Compounds will appear here after you run your first FTO analysis."
                    }
                    action={
                      !hasSearch && canCreateAnalysis
                        ? { label: "New Analysis", href: "/analyses/new" }
                        : undefined
                    }
                    examples={
                      hasSearch
                        ? [
                            { label: "Aspirin", value: "aspirin" },
                            {
                              label: "carboxylic acid",
                              value: "carboxylic acid",
                            },
                            { label: "BSYN", value: "BSYN" },
                          ]
                        : undefined
                    }
                    onExampleClick={onSearchExampleSelect}
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function IdentifierLine({ label, value }: { label: string; value: string }) {
  const displayValue = value || "\u2014";

  return (
    <p
      className="grid min-w-0 grid-cols-[3.25rem_minmax(0,1fr)] items-baseline gap-1 font-mono text-xs leading-5 text-[var(--text-tertiary)] md:block"
      aria-label={`${label}: ${displayValue}`}
    >
      <span className="font-sans text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-disabled)] md:mr-1">
        {label}
      </span>
      <span
        className="block min-w-0 max-w-full overflow-hidden text-ellipsis whitespace-nowrap align-bottom md:inline-block md:max-w-[12rem]"
        title={displayValue}
      >
        {displayValue}
      </span>
    </p>
  );
}

function FunctionalGroupChips({ groups }: { groups: string[] }) {
  const normalizedGroups = normalizeFunctionalGroups(groups);
  const visibleGroups = normalizedGroups.slice(0, 2);
  const extraCount = Math.max(
    0,
    normalizedGroups.length - visibleGroups.length,
  );

  if (visibleGroups.length === 0) {
    return (
      <span className="text-xs text-[var(--text-tertiary)]">
        Groups not indexed
      </span>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {visibleGroups.map((group, index) => (
        <span
          key={`${group}-${index}`}
          aria-label={`Functional group: ${group}`}
          className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-0.5 text-xs text-[var(--text-tertiary)] md:max-w-[9rem]"
          title={group}
        >
          {group}
        </span>
      ))}
      {extraCount > 0 ? (
        <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-0.5 text-xs text-[var(--text-tertiary)]">
          +{extraCount}
        </span>
      ) : null}
    </div>
  );
}
