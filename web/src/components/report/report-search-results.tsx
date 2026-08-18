"use client";

import { useMemo, useState } from "react";
import {
  ChevronDown,
  MessageSquare,
  Search,
  SearchX,
  ShieldCheck,
  SquareArrowOutUpRight,
  TriangleAlert,
} from "lucide-react";

import type { ReportSearchResult } from "@/hooks/use-report-search";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

interface ReportSearchResultsProps {
  results: ReportSearchResult[];
  totalResults?: number;
  interpretedQuery?: string;
  className?: string;
  failedQuery?: string;
  isShowingPreviousResults?: boolean;
  onAskAboutPatent?: (patentId: string) => void;
  onOpenPatent?: (patentId: string) => void;
  resultQuery?: string;
}

function formatSection(section: string) {
  return section.replaceAll("_", " ");
}

function formatRelevance(relevance: number) {
  if (!Number.isFinite(relevance)) return "Relevance unavailable";
  const normalized = relevance > 1 ? relevance / 100 : relevance;
  return `${Math.round(Math.max(0, Math.min(1, normalized)) * 100)}% relevant`;
}

export function ReportSearchResults({
  results,
  totalResults,
  interpretedQuery,
  className,
  failedQuery,
  isShowingPreviousResults = false,
  onAskAboutPatent,
  onOpenPatent,
  resultQuery,
}: ReportSearchResultsProps) {
  const resultSignature = useMemo(
    () =>
      results
        .map(
          (result) =>
            `${result.patent_id}:${result.section}:${result.relevance}:${result.snippet}`,
        )
        .join("|"),
    [results],
  );
  const [visibility, setVisibility] = useState({
    limit: 6,
    signature: "",
  });
  const visibleLimit =
    visibility.signature === `${interpretedQuery ?? ""}:${resultSignature}`
      ? visibility.limit
      : 6;

  if (!results.length) {
    if (!interpretedQuery) return null;

    return (
      <section
        aria-label="Report search results"
        className={cn("mb-5", className)}
      >
        <EmptyState
          icon={SearchX}
          title="No reviewed evidence matches"
          description="No report evidence matched this search. Try a broader patent number, claim phrase, source name, or compound synonym."
          contextItems={[
            "Report view unchanged",
            "Reviewed evidence only",
            "Search can recover",
          ]}
          className="mx-auto max-w-3xl"
        />
        <p className="mx-auto mt-3 max-w-2xl break-words text-center text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
          Search interpreted as: {interpretedQuery}
        </p>
      </section>
    );
  }

  const visibleResults = results.slice(0, visibleLimit);
  const totalResultCount = Math.max(
    totalResults ?? results.length,
    results.length,
  );
  const hiddenLoadedCount = Math.max(0, results.length - visibleResults.length);
  const resultCountLabel =
    visibleResults.length < totalResultCount
      ? `Showing ${visibleResults.length} of ${totalResultCount} results`
      : `${totalResultCount} result${totalResultCount === 1 ? "" : "s"}`;

  return (
    <section
      aria-label="Report search results"
      className={cn(
        "praviar-surface-premium mb-5 space-y-3 rounded-lg p-3 sm:p-4",
        className,
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase text-[var(--text-tertiary)]">
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            {isShowingPreviousResults
              ? "Previous reviewed evidence matches"
              : "Reviewed evidence matches"}
          </p>
          {interpretedQuery ? (
            <p className="break-words text-sm text-[var(--text-secondary)] [overflow-wrap:anywhere]">
              {interpretedQuery}
            </p>
          ) : null}
        </div>
        <Badge
          variant="secondary"
          className="shrink-0 whitespace-nowrap text-xs uppercase"
        >
          {resultCountLabel}
        </Badge>
      </div>

      {isShowingPreviousResults ? (
        <div
          className="flex min-w-0 items-start gap-2 rounded-lg border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]"
          role="status"
          aria-live="polite"
        >
          <TriangleAlert
            className="mt-0.5 h-4 w-4 shrink-0 text-warning"
            aria-hidden="true"
          />
          <p className="min-w-0 [overflow-wrap:anywhere]">
            <span className="font-semibold text-[var(--text-primary)]">
              Showing previous results
              {resultQuery ? ` for "${resultQuery}"` : ""}.
            </span>{" "}
            The search
            {failedQuery ? ` for "${failedQuery}"` : ""} did not complete, so
            these matches should not be treated as the latest query result.
          </p>
        </div>
      ) : (
        <div
          className="flex min-w-0 items-start gap-2 rounded-lg border border-brand-primary/15 bg-brand-primary/5 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]"
          role="note"
        >
          <ShieldCheck
            className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
            aria-hidden="true"
          />
          <p className="min-w-0 [overflow-wrap:anywhere]">
            <span className="font-semibold text-[var(--text-primary)]">
              Showing reviewed evidence only.
            </span>{" "}
            Your report view remains unchanged.
          </p>
        </div>
      )}

      <div className="space-y-2" role="list">
        {visibleResults.map((result, index) => {
          const hasPatentId = result.patent_id.trim().length > 0;
          const sectionLabel = formatSection(result.section);
          const patentLabel = hasPatentId ? result.patent_id : "Report section";

          return (
            <div
              key={`${result.patent_id}-${result.section}-${index}`}
              className="praviar-glass-chip border-l-2 border-brand-primary/60 min-w-0 space-y-3 rounded-lg p-3"
              role="listitem"
            >
              <div className="flex min-w-0 flex-wrap items-start gap-3">
                <span
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-primary-dim text-xs font-semibold text-[var(--brand-paper)] shadow-[var(--shadow-xs)]"
                  aria-hidden="true"
                >
                  {index + 1}
                </span>
                <div className="min-w-0 space-y-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <Badge
                      variant="outline"
                      className="max-w-full min-w-0 break-all font-mono text-xs uppercase [overflow-wrap:anywhere]"
                      title={patentLabel}
                    >
                      {patentLabel}
                    </Badge>
                    <Badge
                      variant="outline"
                      className="max-w-full min-w-0 break-words text-xs uppercase [overflow-wrap:anywhere]"
                      title={sectionLabel}
                    >
                      {sectionLabel}
                    </Badge>
                    <Badge variant="secondary" className="text-xs uppercase">
                      {formatRelevance(result.relevance)}
                    </Badge>
                  </div>
                  <p className="break-words text-sm leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {result.snippet}
                  </p>
                </div>
              </div>

              {hasPatentId ? (
                <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap">
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11 min-w-0 justify-center gap-2 text-left"
                    onClick={() => onOpenPatent?.(result.patent_id)}
                    aria-label={`Open patent ${patentLabel}`}
                  >
                    <SquareArrowOutUpRight
                      className="h-4 w-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span className="min-w-0 break-all [overflow-wrap:anywhere]">
                      Open {patentLabel}
                    </span>
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    className="min-h-11 min-w-0 justify-center gap-2 text-left"
                    onClick={() => onAskAboutPatent?.(result.patent_id)}
                    aria-label={`Ask about patent ${patentLabel}`}
                  >
                    <MessageSquare
                      className="h-4 w-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span className="min-w-0 break-all [overflow-wrap:anywhere]">
                      Ask about {patentLabel}
                    </span>
                  </Button>
                </div>
              ) : (
                <p className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                  Section-level match from {sectionLabel}; no patent-specific
                  action is attached to this result.
                </p>
              )}
            </div>
          );
        })}
      </div>
      {hiddenLoadedCount > 0 ? (
        <div className="flex justify-center pt-1">
          <Button
            type="button"
            variant="outline"
            className="min-h-11 gap-2"
            onClick={() =>
              setVisibility({
                limit: Math.min(results.length, visibleLimit + 6),
                signature: `${interpretedQuery ?? ""}:${resultSignature}`,
              })
            }
          >
            Show {Math.min(6, hiddenLoadedCount)} more match
            {Math.min(6, hiddenLoadedCount) === 1 ? "" : "es"}
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      ) : visibleResults.length < totalResultCount ? (
        <p className="text-center text-xs leading-5 text-[var(--text-tertiary)]">
          Showing all {visibleResults.length} loaded matches. Refine the search
          to retrieve more of the {totalResultCount.toLocaleString()} reviewed
          evidence matches.
        </p>
      ) : null}
    </section>
  );
}
