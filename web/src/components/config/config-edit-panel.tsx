"use client";

import { Button } from "@/components/ui/button";
import { type ConfigStore } from "@/components/config/helpers";
import { AnalysisScopeSection } from "@/components/config/analysis-scope-section";
import { HitlSection } from "@/components/config/hitl-section";
import { JurisdictionsThinkingSection } from "@/components/config/jurisdictions-thinking-section";
import { PatentSourcesSection } from "@/components/config/patent-sources-section";
import { SearchDepthSection } from "@/components/config/search-depth-section";

interface ConfigEditPanelProps {
  config: ConfigStore;
  onCollapse: () => void;
}

export function ConfigEditPanel({ config, onCollapse }: ConfigEditPanelProps) {
  return (
    <section className="space-y-4" aria-label="Edit configuration defaults">
      <div className="praviar-glass-strip flex flex-col gap-3 rounded-lg border border-[var(--border-default)] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Draft mode
          </p>
          <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
            Review coverage, evidence, and legal checkpoints before saving
            organization defaults.
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="min-h-11 w-full sm:w-auto"
          onClick={onCollapse}
        >
          Return to summary
        </Button>
      </div>

      <SearchDepthSection config={config} />
      <PatentSourcesSection config={config} />
      <AnalysisScopeSection config={config} />
      <JurisdictionsThinkingSection config={config} />
      <HitlSection config={config} />
    </section>
  );
}
