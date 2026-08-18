"use client";

import { useCallback, useState } from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { SPRING_GENTLE } from "@/lib/spring-presets";
import { Card, CardContent } from "@/components/ui/card";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import {
  AnalysisTable,
  FlowArrow,
  HardFilterTable,
  PatentSearchBar,
  RankingCutTable,
  StageCard,
  TriageTable,
} from "@/components/report/funnel-explorer-parts";
import type { PipelineAuditTrail } from "@praviar/shared-types";
import {
  FUNNEL_STAGES,
  getFunnelStageCounts,
  searchPatentInFunnel,
  type FunnelStage,
} from "@/components/report/funnel-explorer-helpers";

interface FunnelExplorerProps {
  audit: PipelineAuditTrail;
}

export function FunnelExplorer({ audit }: FunnelExplorerProps) {
  const [selectedStage, setSelectedStage] = useState<FunnelStage | null>(null);
  const [searchResult, setSearchResult] = useState<string | null>(null);
  const stageCounts = getFunnelStageCounts(audit);
  const resetPrivateFunnelState = useCallback(() => {
    setSelectedStage(null);
    setSearchResult(null);
  }, []);
  useAuthBoundaryReset(resetPrivateFunnelState);

  const handleSearch = (query: string) => {
    const result = searchPatentInFunnel(audit, query);
    if (!result.searchResult) {
      return;
    }
    setSearchResult(result.searchResult);
    if (result.selectedStage) {
      setSelectedStage(result.selectedStage);
    }
  };

  return (
    <Card>
      <CardContent className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Pipeline Funnel Explorer
          </h3>
          <p className="text-xs text-[var(--text-disabled)]">
            Click a stage to drill down
          </p>
        </div>

        {/* Patent search */}
        <PatentSearchBar
          onSearch={handleSearch}
          searchResult={searchResult}
          onClear={() => setSearchResult(null)}
        />

        {/* Funnel stages */}
        <div className="space-y-0">
          {FUNNEL_STAGES.map((stage, index) => {
            const prevCount =
              index > 0 ? stageCounts[FUNNEL_STAGES[index - 1].id] : null;
            return (
              <div key={stage.id}>
                {index > 0 && <FlowArrow />}
                <StageCard
                  stage={stage}
                  count={stageCounts[stage.id]}
                  prevCount={prevCount}
                  isSelected={selectedStage === stage.id}
                  onClick={() =>
                    setSelectedStage(
                      selectedStage === stage.id ? null : stage.id,
                    )
                  }
                />
              </div>
            );
          })}
        </div>

        {/* Drill-down panel */}
        <AnimatePresence>
          {selectedStage && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={SPRING_GENTLE}
              className="overflow-hidden"
            >
              <div className="praviar-glass-panel-soft mt-2 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                    {
                      FUNNEL_STAGES.find((stage) => stage.id === selectedStage)
                        ?.label
                    }{" "}
                    — Details
                  </h4>
                  <button
                    type="button"
                    onClick={() => setSelectedStage(null)}
                    className="flex h-11 w-11 items-center justify-center rounded-md hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                    aria-label={`Close ${
                      FUNNEL_STAGES.find((stage) => stage.id === selectedStage)
                        ?.label ?? "funnel"
                    } details`}
                  >
                    <X
                      className="h-3.5 w-3.5 text-[var(--text-tertiary)]"
                      aria-hidden="true"
                    />
                  </button>
                </div>

                {selectedStage === "hard_filter" && (
                  <HardFilterTable entries={audit.search_funnel} />
                )}
                {selectedStage === "triaged" && (
                  <TriageTable entries={audit.triage_audit} />
                )}
                {selectedStage === "analyzed" && (
                  <AnalysisTable entries={audit.analysis_audit} />
                )}
                {selectedStage === "ranked" && (
                  <RankingCutTable entries={audit.search_funnel} />
                )}
                {selectedStage === "discovered" && (
                  <p className="text-xs text-[var(--text-tertiary)]">
                    {stageCounts.discovered.toLocaleString()} patents discovered
                    across all sources. Use the patent search above to find a
                    specific patent.
                  </p>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </CardContent>
    </Card>
  );
}
