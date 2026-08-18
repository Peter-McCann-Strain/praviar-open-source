"use client";

import { useMemo, useState, type RefObject } from "react";
import type { FTOReport } from "@praviar/shared-types";
import { PatentRiskCard } from "@/components/patent/patent-risk-card";
import { Button } from "@/components/ui/button";

/**
 * Number of patent cards rendered in the first synchronous paint. The table
 * view paginates at 10/page; the card view is heavier per row (each card mounts
 * an expandable body plus a FeedbackModal hook tree), so a large landscape with
 * 500+ patents would otherwise render every card at once and lock the main
 * thread on first paint. We render an initial batch and reveal the rest on
 * demand to keep the report interactive.
 */
const INITIAL_VISIBLE_CARDS = 50;
const CARD_BATCH_SIZE = 50;

export function PatentsCardList({
  sortedAnalyses,
  report,
  analysisId,
  canSubmitFeedback = true,
  deepLinkPatent,
  scrollRef,
}: {
  sortedAnalyses: FTOReport["patent_analyses"];
  report: FTOReport;
  analysisId?: string;
  canSubmitFeedback?: boolean;
  deepLinkPatent: string | null;
  scrollRef: RefObject<HTMLDivElement | null>;
}) {
  // Reset the window only when the underlying patent set actually changes, not
  // on every parent re-render. The parent recomputes `sortedAnalyses` into a
  // fresh array each render (drawer open, view-mode toggle, search-param
  // changes), so depending on the array identity would discard "Show more"
  // progress. Key the window on a stable content signature instead.
  const listSignature = useMemo(
    () =>
      `${sortedAnalyses.length}:${sortedAnalyses[0]?.patent_id ?? ""}:${
        sortedAnalyses[sortedAnalyses.length - 1]?.patent_id ?? ""
      }`,
    [sortedAnalyses],
  );
  const [visibleWindow, setVisibleWindow] = useState({
    count: INITIAL_VISIBLE_CARDS,
    signature: listSignature,
  });
  const visibleCount =
    visibleWindow.signature === listSignature
      ? visibleWindow.count
      : INITIAL_VISIBLE_CARDS;

  // If a deep-linked patent sits beyond the current window, expand the window
  // far enough to include it so the scroll-into-view in PatentsTab can resolve
  // the target card. Done in render (not an effect) so the card exists on the
  // same paint the deep link is read.
  const requiredCount = useMemo(() => {
    if (!deepLinkPatent) return visibleCount;
    const index = sortedAnalyses.findIndex(
      (analysis) => analysis.patent_id === deepLinkPatent,
    );
    if (index < 0) return visibleCount;
    return Math.max(visibleCount, index + 1);
  }, [deepLinkPatent, sortedAnalyses, visibleCount]);

  const effectiveCount = Math.min(requiredCount, sortedAnalyses.length);
  const visibleAnalyses = sortedAnalyses.slice(0, effectiveCount);
  const remaining = sortedAnalyses.length - effectiveCount;

  return (
    <div ref={scrollRef} className="space-y-4">
      {visibleAnalyses.map((analysis) => (
        <div key={analysis.patent_id} data-patent-id={analysis.patent_id}>
          <PatentRiskCard
            analysis={analysis}
            analysisId={analysisId}
            canSubmitFeedback={canSubmitFeedback}
            narrative={report.patent_narratives?.[analysis.patent_id]}
            defaultExpanded={analysis.patent_id === deepLinkPatent}
          />
        </div>
      ))}
      {remaining > 0 && (
        <div className="flex justify-center pt-2">
          <Button
            variant="outline"
            size="sm"
            className="min-h-11"
            onClick={() =>
              setVisibleWindow((current) => {
                const currentCount =
                  current.signature === listSignature
                    ? current.count
                    : INITIAL_VISIBLE_CARDS;

                return {
                  signature: listSignature,
                  count:
                    Math.max(currentCount, effectiveCount) + CARD_BATCH_SIZE,
                };
              })
            }
          >
            Show more patents ({remaining} remaining)
          </Button>
        </div>
      )}
    </div>
  );
}
