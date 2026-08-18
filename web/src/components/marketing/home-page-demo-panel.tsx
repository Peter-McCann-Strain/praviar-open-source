import { AnimatePresence } from "motion/react";
import type { KeyboardEvent } from "react";
import { RiskBadge } from "@/components/shared/risk-badge";
import { PraviarMark } from "@/components/icons/praviar-mark";
import type { DemoArtifactPayload } from "@/marketing/live-demo";
import { cn } from "@/lib/utils";
import { HomePageDemoClaimView } from "@/components/marketing/home-page-demo-claim-view";
import { HomePageDemoRunView } from "@/components/marketing/home-page-demo-run-view";
import { HomePageDemoSummaryView } from "@/components/marketing/home-page-demo-summary-view";
import { getSamplePriorityLabel } from "@/components/marketing/home-page-helpers";

export type ArtifactView = "summary" | "claim" | "run";

const ARTIFACT_VIEWS: ArtifactView[] = ["summary", "claim", "run"];

interface HomePageDemoPanelProps {
  artifactView: ArtifactView;
  demoArtifact: DemoArtifactPayload;
  prefersReducedMotion: boolean;
  setArtifactView: (view: ArtifactView) => void;
}

export function HomePageDemoPanel({
  artifactView,
  demoArtifact,
  prefersReducedMotion,
  setArtifactView,
}: HomePageDemoPanelProps) {
  const activeTabId = `homepage-demo-tab-${artifactView}`;
  const activePanelId = `homepage-demo-panel-${artifactView}`;

  const activateArtifactView = (view: ArtifactView) => {
    setArtifactView(view);
    document.getElementById(`homepage-demo-tab-${view}`)?.focus();
  };

  const handleArtifactTabKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    view: ArtifactView,
  ) => {
    const currentIndex = ARTIFACT_VIEWS.indexOf(view);
    if (currentIndex === -1) return;

    if (event.key === "ArrowRight") {
      event.preventDefault();
      activateArtifactView(
        ARTIFACT_VIEWS[(currentIndex + 1) % ARTIFACT_VIEWS.length],
      );
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      activateArtifactView(
        ARTIFACT_VIEWS[
          (currentIndex - 1 + ARTIFACT_VIEWS.length) % ARTIFACT_VIEWS.length
        ],
      );
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      activateArtifactView(ARTIFACT_VIEWS[0]);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      activateArtifactView(ARTIFACT_VIEWS[ARTIFACT_VIEWS.length - 1]);
    }
  };

  return (
    <div className="relative isolate" data-testid="homepage-demo-panel">
      <div
        aria-hidden="true"
        className="praviar-evidence-field-pattern absolute -inset-1 -z-10 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] opacity-75"
        data-testid="homepage-demo-panel-underlay"
      />
      <div className="praviar-evidence-paper relative overflow-hidden rounded-lg border border-[var(--border-default)] shadow-[var(--shadow-lg)]">
        <div className="praviar-glass-strip border-b border-[var(--border-default)] px-4 py-4 sm:px-6 sm:py-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center">
                <PraviarMark size={36} variant="onLight" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                  Fictional sample report
                </p>
                <h2 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
                  {demoArtifact.compoundName}
                </h2>
              </div>
            </div>
            <RiskBadge
              risk={demoArtifact.verdict}
              size="lg"
              showIcon
              label={getSamplePriorityLabel(demoArtifact.verdict)}
              className="shadow-none"
            />
            <span
              className="min-w-0 max-w-full truncate rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 py-1 font-mono text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]"
              title={demoArtifact.sourceReference}
            >
              {demoArtifact.sourceReference}
            </span>
          </div>
          <div
            aria-label="Sample report views"
            className="mt-4 flex flex-wrap gap-2"
            role="tablist"
          >
            {ARTIFACT_VIEWS.map((view) => (
              <button
                aria-controls={`homepage-demo-panel-${view}`}
                aria-selected={artifactView === view}
                id={`homepage-demo-tab-${view}`}
                key={view}
                className={cn(
                  "min-h-11 rounded-full px-4 py-2 text-sm font-medium capitalize transition-colors",
                  artifactView === view
                    ? "bg-[var(--surface-inverted)] text-[var(--surface-inverted-fg)]"
                    : "bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                )}
                onClick={() => setArtifactView(view)}
                onKeyDown={(event) => handleArtifactTabKeyDown(event, view)}
                role="tab"
                tabIndex={artifactView === view ? 0 : -1}
                type="button"
              >
                {view}
              </button>
            ))}
          </div>
        </div>

        <div
          aria-labelledby={activeTabId}
          className="min-h-[360px] p-4 sm:p-5 md:min-h-[480px]"
          id={activePanelId}
          role="tabpanel"
          tabIndex={0}
        >
          <AnimatePresence mode="wait">
            {artifactView === "summary" && (
              <HomePageDemoSummaryView
                demoArtifact={demoArtifact}
                prefersReducedMotion={prefersReducedMotion}
              />
            )}

            {artifactView === "claim" && (
              <HomePageDemoClaimView
                demoArtifact={demoArtifact}
                prefersReducedMotion={prefersReducedMotion}
              />
            )}

            {artifactView === "run" && (
              <HomePageDemoRunView
                demoArtifact={demoArtifact}
                prefersReducedMotion={prefersReducedMotion}
              />
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
