import type { ReactNode } from "react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";

function DashboardLoadingDisclosure({
  children,
  testId,
}: {
  children: ReactNode;
  testId: string;
}) {
  return (
    <section
      className="min-w-0 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] sm:overflow-visible sm:rounded-none sm:border-0 sm:bg-transparent"
      data-testid={testId}
    >
      <div className="flex min-h-16 items-center justify-between gap-3 px-4 py-3 sm:hidden">
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton width={152} height={14} borderRadius={4} />
          <Skeleton width="min(17rem, 82%)" height={10} borderRadius={3} />
        </div>
        <Skeleton width={28} height={28} borderRadius={7} />
      </div>
      <div className="hidden border-t border-[var(--border-subtle)] p-3 sm:block sm:border-0 sm:p-0">
        {children}
      </div>
    </section>
  );
}

function DashboardHeaderLoading() {
  return (
    <header
      className="praviar-dashboard-command-deck relative isolate -mx-4 overflow-hidden border-y border-[var(--border-default)] px-4 py-4 shadow-[var(--shadow-xs)] sm:mx-0 sm:rounded-lg sm:border sm:px-5 sm:py-5"
      data-praviar-dashboard-loading-header
    >
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div className="flex min-w-0 items-start gap-3 sm:gap-4">
          <PraviarMarkFrame size="lg" className="max-[359px]:hidden" />
          <div className="min-w-0 flex-1">
            <Skeleton width="min(18rem, 82%)" height={10} borderRadius={3} />
            <Skeleton
              width="min(16rem, 74%)"
              height={28}
              borderRadius={7}
              style={{ marginTop: 8 }}
            />
            <Skeleton
              width="min(38rem, 94%)"
              height={14}
              borderRadius={4}
              style={{ marginTop: 8 }}
            />
          </div>
        </div>
        <Skeleton
          className="hidden lg:block"
          width={132}
          height={44}
          borderRadius={8}
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 min-[420px]:grid-cols-3 sm:[grid-template-columns:repeat(auto-fit,minmax(10.5rem,1fr))] xl:max-w-5xl">
        {Array.from({ length: 5 }).map((_, index) => (
          <div
            key={index}
            className={`min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 px-2 py-2 sm:px-3 ${
              index > 2 ? "hidden sm:block" : ""
            }`}
          >
            <Skeleton width="64%" height={10} borderRadius={3} />
            <Skeleton
              width="46%"
              height={18}
              borderRadius={5}
              style={{ marginTop: 6 }}
            />
            <Skeleton
              width="76%"
              height={10}
              borderRadius={3}
              style={{ marginTop: 6 }}
            />
          </div>
        ))}
      </div>
    </header>
  );
}

function SetupReadinessLoading() {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-xs)]">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_repeat(3,minmax(8rem,0.32fr))]">
        <div className="space-y-2">
          <Skeleton width={132} height={12} borderRadius={4} />
          <Skeleton width="min(24rem, 86%)" height={10} borderRadius={3} />
        </div>
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} height={48} borderRadius={8} />
        ))}
      </div>
    </div>
  );
}

function ExecutiveDecisionBriefLoading() {
  return (
    <section
      className="praviar-surface-premium relative isolate overflow-hidden rounded-lg border border-[var(--card-border)]"
      data-testid="dashboard-loading-executive-decision-brief"
    >
      <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,0.46fr)]">
        <div className="min-w-0">
          <div className="grid gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/38 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:px-5">
            <div className="min-w-0 space-y-2">
              <Skeleton width={152} height={10} borderRadius={3} />
              <Skeleton width="min(30rem, 88%)" height={26} borderRadius={6} />
              <Skeleton width="min(40rem, 96%)" height={12} borderRadius={4} />
            </div>
            <div className="grid w-full gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 py-2 sm:w-48">
              <Skeleton height={12} borderRadius={4} />
              <Skeleton width="72%" height={12} borderRadius={4} />
            </div>
          </div>

          <div className="grid gap-px bg-[var(--border-subtle)] sm:grid-cols-2 2xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className="min-w-0 bg-[var(--bg-surface)]/78 px-4 py-4 sm:px-5"
              >
                <div className="flex items-start gap-3">
                  <Skeleton width={40} height={40} borderRadius={8} />
                  <div className="min-w-0 flex-1 space-y-2">
                    <Skeleton width="68%" height={10} borderRadius={3} />
                    <Skeleton width="42%" height={24} borderRadius={6} />
                  </div>
                </div>
                <Skeleton
                  height={10}
                  borderRadius={3}
                  style={{ marginTop: 14 }}
                />
                <Skeleton
                  width="78%"
                  height={10}
                  borderRadius={3}
                  style={{ marginTop: 6 }}
                />
              </div>
            ))}
          </div>
        </div>

        <aside className="min-w-0 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-4 sm:p-5 xl:border-l xl:border-t-0">
          <div className="flex items-start gap-3">
            <Skeleton width={40} height={40} borderRadius={8} />
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton width={92} height={10} borderRadius={3} />
              <Skeleton width="84%" height={18} borderRadius={5} />
              <Skeleton height={10} borderRadius={3} />
            </div>
          </div>
          <Skeleton height={44} borderRadius={8} style={{ marginTop: 16 }} />
          <div className="mt-4 grid gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} height={40} borderRadius={8} />
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}

function AiDisclosureLoading() {
  return (
    <div
      className="flex min-h-14 items-center gap-3 overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)] px-4 py-3 sm:px-5"
      data-praviar-dashboard-loading-ai-disclosure
    >
      <Skeleton width={36} height={36} borderRadius={8} />
      <div className="min-w-0 flex-1 space-y-2">
        <Skeleton width="min(21rem, 78%)" height={14} borderRadius={4} />
        <Skeleton width="min(34rem, 90%)" height={10} borderRadius={3} />
      </div>
      <Skeleton width={24} height={24} borderRadius={6} />
    </div>
  );
}

function LegalWorkloadLoading() {
  return (
    <section
      className="min-w-0 overflow-hidden rounded-lg border border-brand-primary/15 bg-gradient-to-br from-brand-primary/5 via-transparent to-transparent shadow-[var(--shadow-sm)]"
      data-testid="dashboard-loading-legal-workload"
    >
      <div className="h-1 bg-gradient-to-r from-brand-primary via-brand-primary/30 to-transparent" />
      <div className="flex flex-wrap items-start justify-between gap-4 p-5">
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton width={168} height={10} borderRadius={3} />
          <Skeleton width={196} height={18} borderRadius={5} />
          <Skeleton width="min(34rem, 92%)" height={10} borderRadius={3} />
        </div>
        <div className="w-28 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-4 py-3">
          <Skeleton height={10} borderRadius={3} />
          <Skeleton
            width="52%"
            height={24}
            borderRadius={6}
            style={{ marginTop: 8, marginLeft: "auto" }}
          />
        </div>
      </div>

      <div className="space-y-4 px-5 pb-5">
        <div className="grid min-w-0 gap-3 xl:grid-cols-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <div
              key={index}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-4"
            >
              <Skeleton width={136} height={14} borderRadius={4} />
              <div className="mt-3 flex flex-wrap gap-2">
                {[72, 84, 92, 76].map((width) => (
                  <Skeleton
                    key={width}
                    width={width}
                    height={24}
                    borderRadius={999}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} height={48} borderRadius={8} />
          ))}
        </div>
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} height={80} borderRadius={8} />
          ))}
        </div>
      </div>
    </section>
  );
}

function RiskDocketLoading() {
  return (
    <div
      className="grid grid-cols-1 gap-3 lg:grid-cols-3"
      data-praviar-dashboard-loading-risk-docket
    >
      <div className="rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)] p-5">
        <Skeleton width={112} height={10} borderRadius={3} />
        <Skeleton
          width={148}
          height={16}
          borderRadius={4}
          style={{ marginTop: 8 }}
        />
        <Skeleton
          className="mx-auto"
          width="min(190px, 58vw)"
          height="min(190px, 58vw)"
          circle
          style={{ marginTop: 20 }}
        />
      </div>
      <div className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)] lg:col-span-2">
        <div className="border-b border-[var(--border-subtle)] p-5">
          <Skeleton width={116} height={10} borderRadius={3} />
          <Skeleton
            width={156}
            height={16}
            borderRadius={4}
            style={{ marginTop: 8 }}
          />
        </div>
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="grid gap-3 border-b border-[var(--border-subtle)] px-5 py-4 last:border-0 md:grid-cols-[minmax(0,1fr)_minmax(9rem,14rem)_6rem_7rem]"
          >
            <div className="space-y-2">
              <Skeleton width="68%" height={14} borderRadius={4} />
              <Skeleton width="92%" height={10} borderRadius={3} />
            </div>
            <Skeleton height={24} borderRadius={6} />
            <Skeleton height={24} borderRadius={999} />
            <Skeleton height={12} borderRadius={4} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DashboardLoading() {
  return (
    <section
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-atomic="true"
      className="space-y-6"
      data-praviar-dashboard-loading-workspace
      data-praviar-app-state="loading"
    >
      <span className="sr-only">Loading dashboard workspace</span>

      <div aria-hidden="true" className="space-y-6">
        <DashboardHeaderLoading />
        <DashboardLoadingDisclosure testId="dashboard-loading-setup-disclosure">
          <SetupReadinessLoading />
        </DashboardLoadingDisclosure>
        <section
          className="space-y-4"
          data-testid="dashboard-loading-today-workbench"
        >
          <ExecutiveDecisionBriefLoading />
          <AiDisclosureLoading />
          <DashboardLoadingDisclosure testId="dashboard-loading-legal-review-disclosure">
            <LegalWorkloadLoading />
          </DashboardLoadingDisclosure>
        </section>
        <DashboardLoadingDisclosure testId="dashboard-loading-risk-docket-disclosure">
          <RiskDocketLoading />
        </DashboardLoadingDisclosure>
      </div>
    </section>
  );
}
