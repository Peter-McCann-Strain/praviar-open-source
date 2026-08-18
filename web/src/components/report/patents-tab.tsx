"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { PatentDetailDrawer } from "@/components/report/patent-detail-drawer";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import { PatentDataTable } from "@/components/report/patent-data-table";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { motionAwareScrollBehavior } from "@/lib/motion-preferences";
import type { FTOReport } from "@praviar/shared-types";
import {
  getPatentRiskData,
  getPatentRows,
  getSortedPatentAnalyses,
} from "./patents-tab-helpers";
import { normalizeReportPatentDetail } from "./patent-detail-normalizer";
import {
  PatentsAccessRestricted,
  PatentsCardList,
  PatentsTabSummary,
  PatentsViewModeToggle,
} from "./patents-tab-sections";

interface PatentsTabProps {
  report: FTOReport;
  analysisId?: string;
  canSubmitFeedback?: boolean;
}

export function PatentsTab({
  report,
  analysisId,
  canSubmitFeedback = true,
}: PatentsTabProps) {
  const searchParams = useSearchParams();
  const deepLinkPatent = searchParams.get("patent");
  const scrollRef = useRef<HTMLDivElement>(null);
  const [selectedPatentId, setSelectedPatentId] = useState<string | null>(null);
  const [dismissedDeepLinkPatent, setDismissedDeepLinkPatent] = useState<
    string | null
  >(null);
  // Retained separately from `selectedPatentId` so the drawer's contents stay
  // resolvable while AnimatePresence plays the exit animation. Closing the
  // drawer sets `selectedPatentId` to null (driving `open=false`) but keeps
  // `lastViewedPatentId` populated until a new patent is opened, so the drawer
  // body does not blank out mid-transition.
  const [lastViewedPatentId, setLastViewedPatentId] = useState<string | null>(
    null,
  );
  const [viewMode, setViewMode] = useState<"cards" | "table">("cards");
  const sorted = getSortedPatentAnalyses(report);
  const openPatent = useCallback((patentId: string) => {
    setSelectedPatentId(patentId);
    setLastViewedPatentId(patentId);
  }, []);
  const clearSelectedPatent = useCallback(() => {
    setSelectedPatentId(null);
    setLastViewedPatentId(null);
    setDismissedDeepLinkPatent(null);
  }, []);
  useAuthBoundaryReset(clearSelectedPatent);
  const activeDeepLinkPatentId =
    deepLinkPatent &&
    dismissedDeepLinkPatent !== deepLinkPatent &&
    (report.patent_details?.[deepLinkPatent] ||
      sorted.some((analysis) => analysis.patent_id === deepLinkPatent))
      ? deepLinkPatent
      : null;
  const drawerPatentId =
    selectedPatentId ?? activeDeepLinkPatentId ?? lastViewedPatentId;
  const drawerOpen = Boolean(selectedPatentId ?? activeDeepLinkPatentId);
  const closePatentDrawer = useCallback(() => {
    if (activeDeepLinkPatentId) {
      setDismissedDeepLinkPatent(activeDeepLinkPatentId);
    }
    setSelectedPatentId(null);
  }, [activeDeepLinkPatentId]);

  // Deep-link: scroll the matching card into view as spatial context while the
  // URL-derived drawer state opens the full patent record when details exist.
  useEffect(() => {
    if (!deepLinkPatent) {
      return;
    }

    if (scrollRef.current) {
      try {
        const el = scrollRef.current.querySelector(
          `[data-patent-id="${CSS.escape(deepLinkPatent)}"]`,
        );
        if (el) {
          el.scrollIntoView({
            behavior: motionAwareScrollBehavior(),
            block: "center",
          });
        }
      } catch {
        // Malformed deepLinkPatent — ignore rather than crashing the tab
      }
    }
  }, [deepLinkPatent]);

  const riskData = getPatentRiskData(report);
  const drawerAnalysis = drawerPatentId
    ? (sorted.find((analysis) => analysis.patent_id === drawerPatentId) ?? null)
    : null;
  const drawerPatent = drawerPatentId
    ? normalizeReportPatentDetail({
        analysis: drawerAnalysis,
        patentId: drawerPatentId,
        rawDetail: report.patent_details?.[drawerPatentId],
      })
    : null;

  return (
    <div className="space-y-6">
      <PatentsTabSummary
        report={report}
        riskData={riskData}
        sortedAnalyses={sorted}
        analysisId={analysisId}
        onPatentSelect={openPatent}
      />

      <ReportMobileDisclosure
        label={`Inspect ${sorted.length.toLocaleString()} detailed patent records`}
        description="Open the detailed registry or evidence cards. Unreported fields remain explicitly unreported."
        testId="patent-registry-disclosure"
      >
        <div className="space-y-6">
          {report.patent_analyses.length === 0 &&
            report.total_patents_found > 0 && (
              <PatentsAccessRestricted
                totalPatentsFound={report.total_patents_found}
              />
            )}

          <PatentsViewModeToggle viewMode={viewMode} onChange={setViewMode} />

          {viewMode === "table" ? (
            <PatentDataTable
              patents={getPatentRows(report, sorted)}
              onPatentClick={openPatent}
            />
          ) : (
            <PatentsCardList
              sortedAnalyses={sorted}
              report={report}
              analysisId={analysisId}
              canSubmitFeedback={canSubmitFeedback}
              deepLinkPatent={deepLinkPatent}
              scrollRef={scrollRef}
            />
          )}
        </div>
      </ReportMobileDisclosure>

      <PatentDetailDrawer
        patent={drawerPatent}
        analysis={drawerAnalysis}
        open={drawerOpen}
        onClose={closePatentDrawer}
      />
    </div>
  );
}
