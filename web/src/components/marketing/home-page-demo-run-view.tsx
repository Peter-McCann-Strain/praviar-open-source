import { motion } from "motion/react";
import { SearchFunnel } from "@/components/charts/search-funnel";
import { TimingWaterfall } from "@/components/charts/timing-waterfall";
import type { DemoArtifactPayload } from "@/marketing/live-demo";

interface HomePageDemoViewProps {
  demoArtifact: DemoArtifactPayload;
  prefersReducedMotion: boolean;
}

export function HomePageDemoRunView({
  demoArtifact,
  prefersReducedMotion,
}: HomePageDemoViewProps) {
  return (
    <motion.div
      key="run"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: prefersReducedMotion ? 0 : 0.28 }}
      className="space-y-5"
    >
      <div className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          Search funnel
        </p>
        <div className="mt-4 h-[220px]">
          <SearchFunnel data={demoArtifact.searchFunnel} height={220} />
        </div>
      </div>
      <div className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          Timing breakdown
        </p>
        <div className="mt-4 h-[220px]">
          <TimingWaterfall data={demoArtifact.timing} height={220} />
        </div>
      </div>
    </motion.div>
  );
}
