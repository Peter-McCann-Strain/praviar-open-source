import { Skeleton } from "@/components/shared/loading-skeleton";
import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";

const SUMMARY_ITEMS = ["Subscription", "Renewal", "Capacity", "Report Credits"];
const TRUST_ITEMS = [
  "Stripe-hosted checkout",
  "No card storage",
  "Report Credits before checkout",
];
const CREDIT_PACK_ROWS = [
  "Single Report Credit",
  "Portfolio Pack",
  "Diligence Pack",
  "Scale Pack",
];

export default function Loading() {
  return (
    <RouteLoadingFrame
      className="mx-auto max-w-7xl"
      label="Loading billing controls"
      eyebrow="Billing"
      title="Preparing billing controls"
      description="Loading subscription state, Report Credit Packs, invoices, and account controls."
    >
      <div className="space-y-6">
        <BillingHeaderSkeleton />
        <BillingCapacityRunwaySkeleton />
        <CreditLedgerSkeleton />
        <BillingTrustSkeleton />
        <BillingSummarySkeleton />

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)] xl:items-start">
          <div className="space-y-5">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <AccountControlCardSkeleton titleWidth="w-36" />
              <AccountControlCardSkeleton titleWidth="w-28" />
            </div>

            <PlanControlsSkeleton />
            <InvoiceHistorySkeleton />
          </div>

          <BillingGovernanceSkeleton />
        </div>
      </div>
    </RouteLoadingFrame>
  );
}

function BillingHeaderSkeleton() {
  return (
    <section className="praviar-control-plane-header rounded-lg border border-[var(--border-subtle)] px-4 py-5 shadow-[var(--shadow-sm)] sm:px-6">
      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div className="flex min-w-0 items-start gap-4">
          <Skeleton className="h-12 w-12 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3 w-48 max-w-full" />
            <Skeleton className="h-9 w-36 max-w-full" />
            <Skeleton className="h-4 w-[32rem] max-w-full" />
          </div>
        </div>
        <Skeleton className="h-11 w-full lg:w-44" />
      </div>
    </section>
  );
}

function BillingTrustSkeleton() {
  return (
    <section
      aria-label="Loading trusted billing controls"
      className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)] shadow-[var(--shadow-xs)]"
    >
      <div className="grid gap-0 md:grid-cols-[minmax(0,1.1fr)_minmax(0,1.9fr)]">
        <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 p-4 md:border-b-0 md:border-r md:p-5">
          <div className="flex min-w-0 items-start gap-3">
            <Skeleton className="h-10 w-10 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-4 w-40 max-w-full" />
              <Skeleton className="h-3 w-64 max-w-full" />
            </div>
          </div>
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-3 md:p-5">
          {TRUST_ITEMS.map((item) => (
            <div key={item} className="flex min-w-0 items-start gap-3">
              <Skeleton className="mt-0.5 h-8 w-8 shrink-0 rounded-md" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-3 w-28 max-w-full" />
                <Skeleton className="h-3 w-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function BillingSummarySkeleton() {
  return (
    <section
      aria-label="Loading billing account summary"
      className="praviar-account-control-card rounded-lg p-3 sm:p-4"
    >
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {SUMMARY_ITEMS.map((item) => (
          <div
            key={item}
            className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 px-4 py-3"
          >
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-3 h-5 w-32 max-w-full" />
            <Skeleton className="mt-2 h-3 w-full" />
          </div>
        ))}
      </div>
    </section>
  );
}

function BillingCapacityRunwaySkeleton() {
  return (
    <section
      aria-label="Loading capacity runway"
      className="rounded-lg border border-brand-primary/20 bg-[var(--bg-surface)] shadow-[var(--shadow-sm)]"
    >
      <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_auto]">
        <div className="relative overflow-hidden p-4 sm:p-5">
          <div
            className="praviar-capacity-runway-field pointer-events-none absolute inset-0 opacity-75"
            aria-hidden="true"
            data-testid="billing-loading-capacity-runway-field"
          />
          <div className="relative grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,34rem)] xl:items-center">
            <div className="flex min-w-0 items-center gap-3">
              <Skeleton className="h-9 w-9 shrink-0 rounded-lg" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-4 w-36 max-w-full" />
                <Skeleton className="h-3 w-72 max-w-full" />
              </div>
            </div>
            <div className="grid w-full min-w-0 gap-3 sm:grid-cols-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  key={index}
                  className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-3 py-2 shadow-[var(--shadow-xs)]"
                >
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="mt-3 h-5 w-36 max-w-full" />
                  <Skeleton className="mt-2 h-3 w-full" />
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="flex items-center border-t border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 p-4 xl:border-l xl:border-t-0">
          <Skeleton className="h-11 w-full xl:w-40" />
        </div>
      </div>
    </section>
  );
}

function AccountControlCardSkeleton({ titleWidth }: { titleWidth: string }) {
  return (
    <section className="praviar-account-control-card overflow-hidden">
      <div className="praviar-account-control-header border-b border-[var(--border-subtle)] px-5 py-4">
        <Skeleton className={`h-4 ${titleWidth}`} />
        <Skeleton className="mt-2 h-3 w-56 max-w-full" />
      </div>
      <div className="space-y-4 p-5">
        <Skeleton className="h-8 w-40 max-w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    </section>
  );
}

function CreditLedgerSkeleton() {
  return (
    <section className="praviar-account-control-card overflow-hidden">
      <div className="praviar-credit-ledger-field relative isolate overflow-hidden border-b border-[var(--border-subtle)] p-5 sm:p-6">
        <div
          className="pointer-events-none absolute inset-0 z-0 bg-[var(--bg-surface)]/54 backdrop-blur-[1px]"
          aria-hidden="true"
          data-testid="billing-loading-credit-ledger-field-scrim"
        />
        <div className="relative z-10 grid gap-6 lg:grid-cols-[minmax(0,1fr)_25rem] lg:items-start">
          <div className="flex min-w-0 items-start gap-3">
            <Skeleton className="h-10 w-10 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1 space-y-3">
              <Skeleton className="h-7 w-56 max-w-full" />
              <Skeleton className="h-4 w-[38rem] max-w-full" />
              <div className="flex max-w-3xl flex-wrap items-center gap-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <Skeleton key={index} className="h-8 w-32 max-w-full" />
                ))}
              </div>
            </div>
          </div>
          <div className="grid w-full gap-2 sm:grid-cols-3 lg:grid-cols-1">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-16 w-full" />
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-4 p-5 sm:p-6">
        <div className="grid gap-3 border-b border-[var(--border-subtle)] pb-5 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="min-w-0 space-y-2">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-6 w-36 max-w-full" />
              <Skeleton className="h-3 w-full" />
            </div>
          ))}
        </div>
        <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
          <div className="hidden grid-cols-[minmax(13rem,1.25fr)_0.62fr_0.72fr_0.72fr_minmax(9rem,0.9fr)] gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 px-4 py-2 lg:grid">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-3 w-20" />
            ))}
          </div>
          <div className="divide-y divide-[var(--border-subtle)]">
            {CREDIT_PACK_ROWS.map((row) => (
              <div
                key={row}
                className="grid min-w-0 gap-3 border-l-4 border-transparent p-4 lg:grid-cols-[minmax(13rem,1.25fr)_0.62fr_0.72fr_0.72fr_minmax(9rem,0.9fr)] lg:items-center"
              >
                <div className="min-w-0 space-y-2">
                  <Skeleton className="h-4 w-44 max-w-full" />
                  <Skeleton className="h-3 w-32 max-w-full" />
                  <Skeleton className="h-3 w-full" />
                </div>
                {Array.from({ length: 3 }).map((_, index) => (
                  <Skeleton key={index} className="h-5 w-24 max-w-full" />
                ))}
                <Skeleton className="h-10 w-full lg:ml-auto lg:w-32" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function PlanControlsSkeleton() {
  return (
    <section className="praviar-account-control-card overflow-hidden">
      <div className="praviar-account-control-header border-b border-[var(--border-subtle)] px-5 py-4">
        <Skeleton className="h-5 w-44 max-w-full" />
        <Skeleton className="mt-2 h-3 w-72 max-w-full" />
      </div>
      <div className="grid gap-4 p-5 sm:p-6 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-48 w-full" />
        ))}
      </div>
    </section>
  );
}

function InvoiceHistorySkeleton() {
  return (
    <section className="praviar-account-control-card overflow-hidden">
      <div className="praviar-account-control-header border-b border-[var(--border-subtle)] px-5 py-4">
        <Skeleton className="h-5 w-36" />
        <Skeleton className="mt-2 h-3 w-64 max-w-full" />
      </div>
      <div className="space-y-3 p-5">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-10 w-full" />
        ))}
      </div>
    </section>
  );
}

function BillingGovernanceSkeleton() {
  return (
    <aside className="space-y-4">
      <section className="praviar-account-control-card overflow-hidden">
        <div className="praviar-account-control-header border-b border-[var(--border-subtle)] px-5 py-4">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="mt-2 h-3 w-56 max-w-full" />
        </div>
        <div className="space-y-4 p-5">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="flex min-w-0 gap-3">
              <Skeleton className="h-9 w-9 shrink-0 rounded-lg" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-4 w-32 max-w-full" />
                <Skeleton className="h-3 w-full" />
              </div>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}
