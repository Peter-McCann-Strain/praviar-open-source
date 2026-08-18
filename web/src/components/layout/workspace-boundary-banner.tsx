import { ShieldCheck, TestTube2 } from "lucide-react";

type WorkspaceBoundaryMode = "demo" | "dev-bypass";

interface WorkspaceBoundaryBannerProps {
  mode: WorkspaceBoundaryMode;
}

const COPY: Record<
  WorkspaceBoundaryMode,
  {
    compactDetail: string;
    detail: string;
    eyebrow: string;
    label: string;
  }
> = {
  demo: {
    compactDetail: "Synthetic review data · not legal clearance.",
    detail:
      "Synthetic workspace data is available for product review. Treat reports as first-pass examples, not legal clearance opinions.",
    eyebrow: "Demo workspace",
    label: "Synthetic data visible",
  },
  "dev-bypass": {
    compactDetail: "Auth bypass active · production sign-in still required.",
    detail:
      "Development auth bypass is active. Tenant-scoped production authentication is still required for real evidence and counsel reliance.",
    eyebrow: "Development workspace",
    label: "Auth bypass active",
  },
};

export function WorkspaceBoundaryBanner({
  mode,
}: WorkspaceBoundaryBannerProps) {
  const copy = COPY[mode];
  const Icon = mode === "demo" ? TestTube2 : ShieldCheck;

  return (
    <aside
      aria-label="Workspace data boundary"
      className="border-b border-brand-primary/15 bg-[color-mix(in_srgb,var(--brand-primary)_8%,var(--bg-base))] px-3 py-2 text-[var(--text-primary)] sm:px-5 sm:py-2.5 md:px-6"
      data-testid="workspace-boundary-banner"
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary sm:mt-0.5 sm:h-8 sm:w-8">
            <Icon className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              {copy.eyebrow}
            </p>
            <p className="mt-0.5 text-xs leading-4 text-[var(--text-secondary)] sm:hidden">
              {copy.compactDetail}
            </p>
            <p className="mt-0.5 hidden text-sm leading-5 text-[var(--text-secondary)] sm:block">
              {copy.detail}
            </p>
          </div>
        </div>
        <span className="hidden w-fit shrink-0 items-center rounded-full border border-brand-primary/20 bg-[var(--surface-card)] px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-brand-primary shadow-[var(--shadow-xs)] sm:inline-flex">
          {copy.label}
        </span>
      </div>
    </aside>
  );
}
