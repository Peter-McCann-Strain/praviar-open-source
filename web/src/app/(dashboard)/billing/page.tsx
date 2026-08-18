"use client";

import Link from "next/link";
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  CalendarClock,
  CheckCircle2,
  CreditCard,
  FileText,
  LockKeyhole,
  PackagePlus,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { BillingHeader } from "@/components/billing/billing-header";
import { CreditPackCheckoutReconciliation } from "@/components/billing/credit-pack-reconciliation";
import { CreditCapacityRequestsCard } from "@/components/billing/credit-capacity-requests-card";
import { CreditPacksCard } from "@/components/billing/credit-packs-card";
import { CurrentPlanCard } from "@/components/billing/current-plan-card";
import {
  CREDIT_PACK_DETAILS,
  formatDate,
  formatCreditPackPrice,
  formatReportCreditCount,
  isAllowedStripeRedirectUrl,
  isCreditPackId,
} from "@/components/billing/helpers";
import { InvoiceHistoryCard } from "@/components/billing/invoice-history-card";
import { UpgradePlansCard } from "@/components/billing/upgrade-plans-card";
import { UsageCard } from "@/components/billing/usage-card";
import {
  hasClerk,
  isAdminOrgRole,
} from "@/components/layout/sidebar-constants";
import { AccountControlStatusState } from "@/components/shared/account-control-status-state";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";
import { Button } from "@/components/ui/button";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { useToastStore } from "@/stores/toast-store";
import { isAuthBoundaryError } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { motionAwareScrollBehavior } from "@/lib/motion-preferences";
import { cn } from "@/lib/utils";
import { WORKSPACE_SUPPORT_BOUNDARY_HREF } from "@/lib/support-boundary";
import {
  isStripeCheckoutSessionId,
  useBillingStatus,
  useCreateCheckout,
  useCreateCreditPackCheckout,
  useCreatePortalSession,
  useInvoices,
  useUsageSummary,
  type BillingStatus,
  type CreditPackId,
  type PlanTier,
  type UsageSummary,
} from "@/hooks/use-billing";

function redirectToStripe(value: string) {
  if (!isAllowedStripeRedirectUrl(value)) {
    throw new Error("Unexpected billing redirect URL.");
  }
  window.location.href = value;
}

function redirectToBillingDestination(value: string) {
  const safeLocalPath = resolveSafeBillingReturnPath(value);
  if (safeLocalPath) {
    window.location.href = safeLocalPath;
    return;
  }

  redirectToStripe(value);
}

function requireBillingRedirectUrl(
  value: string | null | undefined,
  context: string,
): string {
  const normalized = value?.trim();
  if (!normalized) {
    throw new Error(`${context} response did not include a redirect URL.`);
  }
  return normalized;
}

function getDisplayedRemainingAnalyses(usage: UsageSummary, plan: PlanTier) {
  if (plan === "enterprise" && usage.analyses_limit <= 0) {
    return null;
  }

  return Math.max(0, usage.analyses_limit - usage.analyses_used);
}

function formatBillingSnapshotTime(timestamp: number | null): string | null {
  if (!timestamp || !Number.isFinite(timestamp)) {
    return null;
  }

  return `${new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
    minute: "2-digit",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  }).format(new Date(timestamp))} UTC`;
}

type CheckoutReturnState = "success" | "cancelled" | null;

type BillingActionError =
  | { kind: "credit"; creditPackId: CreditPackId }
  | { kind: "plan"; planId: PlanTier }
  | { kind: "portal" };

function getCheckoutReturnState(value: string | null): CheckoutReturnState {
  return value === "success" || value === "cancelled" ? value : null;
}

function isDemoPortalReturn(value: string | null) {
  return value === "subscription";
}

function getDemoCreditPackId(value: string | null): CreditPackId | null {
  return isCreditPackId(value) ? value : null;
}

function getDemoCheckoutPlan(value: string | null): PlanTier | null {
  if (
    value === "free" ||
    value === "starter" ||
    value === "pro" ||
    value === "enterprise"
  ) {
    return value;
  }

  return null;
}

function getRequestedReportNeed(value: string | null): number | undefined {
  if (!value) {
    return undefined;
  }

  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return undefined;
  }

  return Math.min(parsed, 30);
}

function getReportNeedFromCreditPack(
  creditPackId: CreditPackId | null,
): number | undefined {
  return creditPackId ? CREDIT_PACK_DETAILS[creditPackId].credits : undefined;
}

const CREDIT_PACK_RECOMMENDATION_ORDER: CreditPackId[] = [
  "single_analysis",
  "portfolio_5",
  "diligence_15",
  "scale_30",
];

function getRecommendedCreditPackIdForNeed({
  availableReportCreditsBalance,
  reportNeed,
}: {
  availableReportCreditsBalance: number;
  reportNeed: number;
}): CreditPackId {
  const additionalCreditsNeeded = Math.max(
    reportNeed - availableReportCreditsBalance,
    1,
  );
  return (
    CREDIT_PACK_RECOMMENDATION_ORDER.find(
      (packId) =>
        CREDIT_PACK_DETAILS[packId].credits >= additionalCreditsNeeded,
    ) ?? "scale_30"
  );
}

function getRequestedCreditPackId(
  intent: string | null,
  pack: string | null,
  demoPack: string | null,
  checkoutPack: string | null,
): CreditPackId | null {
  if (isCreditPackId(demoPack)) {
    return demoPack;
  }

  if (intent === "credits" && isCreditPackId(checkoutPack)) {
    return checkoutPack;
  }

  if (intent !== "credits" || !isCreditPackId(pack)) {
    return null;
  }

  return pack;
}

function resolveSafeBillingReturnPath(value: string | null): string | null {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  if (
    !trimmed.startsWith("/") ||
    trimmed.startsWith("//") ||
    trimmed.includes("\\") ||
    trimmed.includes("\n") ||
    trimmed.includes("\r")
  ) {
    return null;
  }

  try {
    const sentinelOrigin = "https://praviar.local";
    const url = new URL(trimmed, sentinelOrigin);
    if (url.origin !== sentinelOrigin) {
      return null;
    }
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}

function resolveLaunchReturnHref(value: string | null): string {
  const returnPath = resolveSafeBillingReturnPath(value);
  if (!returnPath) {
    return "/analyses/new";
  }

  const url = new URL(returnPath, "https://praviar.local");
  return url.pathname === "/analyses/new" ? returnPath : "/analyses/new";
}

function buildCreditPackReturnUrl({
  creditPackId,
  returnPath,
  state,
}: {
  creditPackId: CreditPackId;
  returnPath: string;
  state: CheckoutReturnState;
}): string {
  const url = new URL(returnPath, window.location.origin);
  if (state) {
    url.searchParams.set("checkout", state);
  }
  url.searchParams.set("credit_pack", creditPackId);
  url.searchParams.set("intent", "credits");
  return url.toString();
}

function buildCreditPackBillingReturnPath(
  searchParams: URLSearchParams,
  creditPackId: CreditPackId,
): string {
  const explicitReturnPath = resolveSafeBillingReturnPath(
    searchParams.get("return_to"),
  );

  if (explicitReturnPath) {
    return explicitReturnPath;
  }

  const params = new URLSearchParams(searchParams);
  params.delete("checkout");
  params.delete("credit_pack");
  params.delete("return_to");
  params.set("intent", "credits");
  params.set("pack", creditPackId);

  return `/billing?${params.toString()}`;
}

export default function BillingPage() {
  if (hasClerk) {
    return <ClerkScopedBillingPage />;
  }

  return <BillingPageContent roleBillingActionsPermitted />;
}

function ClerkScopedBillingPage() {
  const { isLoaded, orgRole } = useAuth();

  if (!isLoaded) {
    return (
      <div className="mx-auto max-w-7xl space-y-5 animate-fade-up">
        <BillingHeader
          actionsDisabled
          hasSubscription={false}
          isManagingSubscription={false}
          onManageSubscription={() => undefined}
        />
        <AccountControlStatusState surface="billing" variant="auth" />
      </div>
    );
  }

  return (
    <BillingPageContent roleBillingActionsPermitted={isAdminOrgRole(orgRole)} />
  );
}

type BillingPageStatusVariant =
  | "auth"
  | "loading"
  | "restricted"
  | "temporary"
  | null;

function getBillingSearchState(searchParams: {
  get(name: string): string | null;
}) {
  const checkoutReturnState = getCheckoutReturnState(
    searchParams.get("checkout"),
  );
  const demoCreditPackId = DEMO_MODE_ENABLED
    ? getDemoCreditPackId(searchParams.get("demo_credit_pack"))
    : null;
  const checkoutSessionId = searchParams.get("checkout_session_id");
  const requestedCreditPackId = getRequestedCreditPackId(
    searchParams.get("intent"),
    searchParams.get("pack"),
    DEMO_MODE_ENABLED ? searchParams.get("demo_credit_pack") : null,
    searchParams.get("credit_pack"),
  );
  const creditIntentActive = searchParams.get("intent") === "credits";

  return {
    checkoutReturnState,
    demoCheckoutPlan: DEMO_MODE_ENABLED
      ? getDemoCheckoutPlan(searchParams.get("demo_checkout"))
      : null,
    demoCreditPackId,
    demoPortalReturn:
      DEMO_MODE_ENABLED && isDemoPortalReturn(searchParams.get("demo_portal")),
    checkoutSessionId,
    creditIntentActive,
    creditReconciliationActive:
      checkoutReturnState === "success" &&
      !demoCreditPackId &&
      isStripeCheckoutSessionId(checkoutSessionId),
    launchReturnHref: resolveLaunchReturnHref(searchParams.get("return_to")),
    requestedCreditPackId,
    requestedReportNeed:
      getRequestedReportNeed(searchParams.get("needed_reports")) ??
      getReportNeedFromCreditPack(requestedCreditPackId),
  };
}

type BillingSearchState = ReturnType<typeof getBillingSearchState>;

function getBillingActionState({
  billingStatus,
  checkoutPending,
  creditPackCheckoutPending,
  creditPackTarget,
  isPortalTargetPending,
  portalPending,
  roleBillingActionsPermitted,
  upgradeTarget,
}: {
  billingStatus: BillingStatus | undefined;
  checkoutPending: boolean;
  creditPackCheckoutPending: boolean;
  creditPackTarget: CreditPackId | null;
  isPortalTargetPending: boolean;
  portalPending: boolean;
  roleBillingActionsPermitted: boolean;
  upgradeTarget: PlanTier | null;
}) {
  const pending =
    checkoutPending ||
    creditPackCheckoutPending ||
    portalPending ||
    upgradeTarget !== null ||
    creditPackTarget !== null ||
    isPortalTargetPending;
  const permitted =
    billingStatus?.can_manage_billing ?? roleBillingActionsPermitted;

  return { controlsDisabled: pending || !permitted, pending, permitted };
}

function getBillingLoadState({
  billingStatus,
  billingStatusError,
  billingStatusLoading,
  invoiceData,
  invoiceError,
  usage,
  usageError,
  usageLoading,
}: {
  billingStatus: BillingStatus | undefined;
  billingStatusError: Error | null;
  billingStatusLoading: boolean;
  invoiceData: ReturnType<typeof useInvoices>["data"];
  invoiceError: Error | null;
  usage: UsageSummary | undefined;
  usageError: Error | null;
  usageLoading: boolean;
}) {
  const invoiceAccessRestricted = isAuthBoundaryError(invoiceError);
  const billingDataMissing = !billingStatus || !usage;
  const isLoading = billingStatusLoading || usageLoading;
  const billingAccessRestricted =
    isAuthBoundaryError(billingStatusError) || isAuthBoundaryError(usageError);
  const billingLoadError =
    (!billingStatus ? billingStatusError : null) ||
    (!usage ? usageError : null) ||
    (!isLoading && billingDataMissing
      ? new Error("Billing details could not be loaded.")
      : null);

  return {
    billingAccessRestricted,
    billingDataMissing,
    billingLoadError,
    invoiceAccessRestricted,
    isLoading,
    visibleInvoiceData: invoiceAccessRestricted ? undefined : invoiceData,
  };
}

type BillingLoadState = ReturnType<typeof getBillingLoadState>;

function getBillingPageStatus({
  billingStatus,
  loadState,
  token,
  usage,
}: {
  billingStatus: BillingStatus | undefined;
  loadState: BillingLoadState;
  token: string | null;
  usage: UsageSummary | undefined;
}): BillingPageStatusVariant {
  if (!token && loadState.billingDataMissing && !loadState.isLoading) {
    return "auth";
  }
  if (loadState.isLoading) return "loading";
  if (loadState.billingAccessRestricted) return "restricted";
  if (loadState.billingLoadError || !billingStatus || !usage) {
    return "temporary";
  }
  return null;
}

function BillingPageStatusView({
  onManageSubscription,
  onRetry,
  variant,
}: {
  onManageSubscription: () => void;
  onRetry: () => void;
  variant: Exclude<BillingPageStatusVariant, null>;
}) {
  return (
    <div className="mx-auto max-w-7xl space-y-5 animate-fade-up">
      <BillingHeader
        hasSubscription={false}
        isManagingSubscription={false}
        onManageSubscription={onManageSubscription}
      />
      {variant === "temporary" ? (
        <AccountControlStatusState
          surface="billing"
          variant="temporary"
          onRetry={onRetry}
        />
      ) : (
        <AccountControlStatusState surface="billing" variant={variant} />
      )}
    </div>
  );
}

function getLoadedBillingViewModel({
  billingStatus,
  billingStatusDataUpdatedAt,
  billingStatusError,
  searchState,
  usage,
  usageDataUpdatedAt,
  usageError,
}: {
  billingStatus: BillingStatus;
  billingStatusDataUpdatedAt: number;
  billingStatusError: Error | null;
  searchState: BillingSearchState;
  usage: UsageSummary;
  usageDataUpdatedAt: number;
  usageError: Error | null;
}) {
  const currentPlan = billingStatus.plan;
  const availableReportCreditsBalance = Math.max(
    getDisplayedRemainingAnalyses(usage, currentPlan) ?? 0,
    0,
  );
  const staleBillingSnapshotTimestamps = [
    billingStatusError ? billingStatusDataUpdatedAt : null,
    usageError ? usageDataUpdatedAt : null,
  ].filter(
    (timestamp): timestamp is number =>
      typeof timestamp === "number" && timestamp > 0,
  );

  return {
    availableReportCreditsBalance,
    currentPlan,
    hasStaleBillingWarning: Boolean(billingStatusError || usageError),
    showCreditPurchasing: currentPlan !== "enterprise",
    staleBillingSnapshotTime: formatBillingSnapshotTime(
      staleBillingSnapshotTimestamps.length > 0
        ? Math.min(...staleBillingSnapshotTimestamps)
        : null,
    ),
    visibleCheckoutReturnState:
      searchState.demoCreditPackId ||
      searchState.demoCheckoutPlan ||
      searchState.creditReconciliationActive
        ? null
        : searchState.checkoutReturnState,
  };
}

type LoadedBillingViewModel = ReturnType<typeof getLoadedBillingViewModel>;

function StaleBillingDataNotice({
  isVisible,
  onRetry,
  snapshotTime,
}: {
  isVisible: boolean;
  onRetry: () => void;
  snapshotTime: string | null;
}) {
  if (!isVisible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3"
      data-testid="billing-stale-data-notice"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          <TriangleAlert
            className="mt-0.5 h-4 w-4 shrink-0 text-warning"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              Billing data may be stale
            </p>
            <p className="mt-0.5 text-sm leading-6 text-[var(--text-secondary)]">
              Billing refresh failed. Existing subscription and usage data is
              still shown, and no plan or payment changes were made.
            </p>
            <p
              className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]"
              data-testid="billing-stale-data-age"
            >
              {snapshotTime
                ? `Showing unchanged data from ${snapshotTime}.`
                : "Showing the last unchanged billing snapshot; its confirmation time is unavailable."}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 w-full shrink-0 sm:w-auto"
          onClick={onRetry}
        >
          Retry billing data
        </Button>
      </div>
    </div>
  );
}

function BillingNarrativeSection({
  actionError,
  actionState,
  billingNarrativeRef,
  billingStatus,
  invoiceAccessRestricted,
  invoiceError,
  isPortalTargetPending,
  onManageSubscription,
  onRetryAction,
  onRetryBilling,
  onRetryInvoices,
  searchState,
  token,
  usage,
  viewModel,
  portalPending,
}: {
  actionError: BillingActionError | null;
  actionState: ReturnType<typeof getBillingActionState>;
  billingNarrativeRef: RefObject<HTMLDivElement | null>;
  billingStatus: BillingStatus;
  invoiceAccessRestricted: boolean;
  invoiceError: Error | null;
  isPortalTargetPending: boolean;
  onManageSubscription: () => void;
  onRetryAction: () => void;
  onRetryBilling: () => void;
  onRetryInvoices: () => void;
  portalPending: boolean;
  searchState: BillingSearchState;
  token: string | null;
  usage: UsageSummary;
  viewModel: LoadedBillingViewModel;
}) {
  return (
    <div
      ref={billingNarrativeRef}
      className="scroll-mt-20 space-y-6"
      data-testid="billing-page-narrative"
    >
      <BillingHeader
        actionsDisabled={actionState.controlsDisabled}
        hasSubscription={Boolean(billingStatus.stripe_subscription_id)}
        isManagingSubscription={portalPending || isPortalTargetPending}
        onManageSubscription={onManageSubscription}
      />
      <StaleBillingDataNotice
        isVisible={viewModel.hasStaleBillingWarning}
        onRetry={onRetryBilling}
        snapshotTime={viewModel.staleBillingSnapshotTime}
      />
      <BillingActionErrorNotice error={actionError} onRetry={onRetryAction} />
      <InvoiceAvailabilityNotice
        accessRestricted={invoiceAccessRestricted}
        error={invoiceError}
        onRetry={onRetryInvoices}
      />
      <DemoCheckoutNotice plan={searchState.demoCheckoutPlan} />
      <PortalReturnNotice isVisible={searchState.demoPortalReturn} />
      <CreditPackReturnNotice
        creditPackId={searchState.demoCreditPackId}
        isDemo
      />
      {searchState.creditReconciliationActive &&
      searchState.checkoutSessionId ? (
        <CreditPackCheckoutReconciliation
          currentConfirmedBalance={usage.purchased_credits_balance ?? 0}
          returnHref={searchState.launchReturnHref}
          sessionId={searchState.checkoutSessionId}
          surface="billing"
          token={token}
        />
      ) : null}
    </div>
  );
}

function BillingAccountDetails({
  actionState,
  billingStatus,
  invoiceData,
  invoiceError,
  invoiceLoading,
  onRetryInvoices,
  onUpgrade,
  upgradeTarget,
  usage,
  viewModel,
}: {
  actionState: ReturnType<typeof getBillingActionState>;
  billingStatus: BillingStatus;
  invoiceData: ReturnType<typeof useInvoices>["data"];
  invoiceError: Error | null;
  invoiceLoading: boolean;
  onRetryInvoices: () => void;
  onUpgrade: (planId: PlanTier) => void;
  upgradeTarget: PlanTier | null;
  usage: UsageSummary;
  viewModel: LoadedBillingViewModel;
}) {
  return (
    <MobileBillingDisclosure
      title="Subscription, usage & invoices"
      summary={`${viewModel.currentPlan} plan · ${formatReportCreditCount(viewModel.availableReportCreditsBalance)} available`}
    >
      <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)] xl:items-start">
        <div className="min-w-0 space-y-5">
          <div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
            <CurrentPlanCard
              billingStatus={billingStatus}
              currentPlan={viewModel.currentPlan}
            />
            <UsageCard usage={usage} />
          </div>
          {viewModel.currentPlan !== "enterprise" ? (
            <UpgradePlansCard
              actionsDisabled={actionState.controlsDisabled}
              currentPlan={viewModel.currentPlan}
              isCheckoutPending={actionState.pending}
              upgradeTarget={upgradeTarget}
              onUpgrade={onUpgrade}
            />
          ) : null}
          <InvoiceHistoryCard
            invoiceData={invoiceData}
            error={invoiceError}
            isLoading={invoiceLoading}
            onRetry={onRetryInvoices}
          />
        </div>
        <BillingGovernanceRail
          billingStatus={billingStatus}
          hasInvoices={Boolean(invoiceData?.invoices.length)}
        />
      </div>
    </MobileBillingDisclosure>
  );
}

function LoadedBillingPage({
  actionError,
  actionState,
  billingNarrativeRef,
  billingStatus,
  canStartAnalysis,
  creditPackTarget,
  invoiceAccessRestricted,
  invoiceData,
  invoiceError,
  invoiceLoading,
  isPortalTargetPending,
  onBuyCredits,
  onManageSubscription,
  onRetryAction,
  onRetryBilling,
  onRetryInvoices,
  onReviewCreditPacks,
  onUpgrade,
  portalPending,
  searchState,
  token,
  upgradeTarget,
  usage,
  viewModel,
}: {
  actionError: BillingActionError | null;
  actionState: ReturnType<typeof getBillingActionState>;
  billingNarrativeRef: RefObject<HTMLDivElement | null>;
  billingStatus: BillingStatus;
  canStartAnalysis: boolean;
  creditPackTarget: CreditPackId | null;
  invoiceAccessRestricted: boolean;
  invoiceData: ReturnType<typeof useInvoices>["data"];
  invoiceError: Error | null;
  invoiceLoading: boolean;
  isPortalTargetPending: boolean;
  onBuyCredits: (creditPackId: CreditPackId) => void;
  onManageSubscription: () => void;
  onRetryAction: () => void;
  onRetryBilling: () => void;
  onRetryInvoices: () => void;
  onReviewCreditPacks: () => void;
  onUpgrade: (planId: PlanTier) => void;
  portalPending: boolean;
  searchState: BillingSearchState;
  token: string | null;
  upgradeTarget: PlanTier | null;
  usage: UsageSummary;
  viewModel: LoadedBillingViewModel;
}) {
  const creditPacksCard = viewModel.showCreditPurchasing ? (
    <CreditPacksCard
      actionsDisabled={!actionState.permitted}
      availableReportCreditsBalance={viewModel.availableReportCreditsBalance}
      purchasedCreditsBalance={usage.purchased_credits_balance ?? 0}
      includedAnalysesLimit={
        usage.included_analyses_limit ?? usage.analyses_limit
      }
      initialReportNeed={searchState.requestedReportNeed}
      isCheckoutPending={actionState.pending}
      creditPackTarget={creditPackTarget}
      spotlightCreditPackId={searchState.requestedCreditPackId}
      launchReturnHref={searchState.launchReturnHref}
      canStartAnalysis={canStartAnalysis}
      onBuyCredits={onBuyCredits}
    />
  ) : null;

  return (
    <div className="mx-auto max-w-7xl space-y-6 animate-fade-up">
      <BillingActionAccessNotice isVisible={!actionState.permitted} />
      <CheckoutReturnNotice state={viewModel.visibleCheckoutReturnState} />
      {viewModel.showCreditPurchasing && searchState.creditIntentActive ? (
        <CreditIntentHero
          availableReportCreditsBalance={
            viewModel.availableReportCreditsBalance
          }
          requestedCreditPackId={searchState.requestedCreditPackId}
          reportNeed={searchState.requestedReportNeed ?? 1}
          isCheckoutPending={actionState.pending}
          actionsDisabled={!actionState.permitted}
          creditPackTarget={creditPackTarget}
          launchReturnHref={searchState.launchReturnHref}
          canStartAnalysis={canStartAnalysis}
          onBuyCredits={onBuyCredits}
        />
      ) : null}
      <BillingNarrativeSection
        actionError={actionError}
        actionState={actionState}
        billingNarrativeRef={billingNarrativeRef}
        billingStatus={billingStatus}
        invoiceAccessRestricted={invoiceAccessRestricted}
        invoiceError={invoiceError}
        isPortalTargetPending={isPortalTargetPending}
        onManageSubscription={onManageSubscription}
        onRetryAction={onRetryAction}
        onRetryBilling={onRetryBilling}
        onRetryInvoices={onRetryInvoices}
        portalPending={portalPending}
        searchState={searchState}
        token={token}
        usage={usage}
        viewModel={viewModel}
      />
      {searchState.creditIntentActive ? creditPacksCard : null}
      {viewModel.showCreditPurchasing ? (
        <BillingCapacityRunway
          usage={usage}
          billingStatus={billingStatus}
          isCheckoutPending={actionState.pending}
          creditPackTarget={creditPackTarget}
          onReviewCreditPacks={onReviewCreditPacks}
        />
      ) : null}
      {searchState.creditIntentActive ? null : creditPacksCard}
      {canStartAnalysis ? (
        <MobileBillingDisclosure
          title="Report Credit request workflow"
          summary="Review pending capacity requests and resolution status"
        >
          <CreditCapacityRequestsCard
            token={token}
            canResolve={actionState.permitted}
          />
        </MobileBillingDisclosure>
      ) : null}
      {searchState.demoCreditPackId ||
      (searchState.checkoutReturnState === "success" &&
        !searchState.creditIntentActive) ? (
        <BillingReconciliationStrip
          checkoutReturnState={
            searchState.demoCreditPackId
              ? null
              : searchState.checkoutReturnState
          }
          creditPackId={searchState.demoCreditPackId}
          isDemoCreditPack={Boolean(searchState.demoCreditPackId)}
          isInvoiceLoading={invoiceLoading}
          usage={usage}
        />
      ) : null}
      <BillingAccountDetails
        actionState={actionState}
        billingStatus={billingStatus}
        invoiceData={invoiceData}
        invoiceError={invoiceError}
        invoiceLoading={invoiceLoading}
        onRetryInvoices={onRetryInvoices}
        onUpgrade={onUpgrade}
        upgradeTarget={upgradeTarget}
        usage={usage}
        viewModel={viewModel}
      />
    </div>
  );
}

function BillingPageContent({
  roleBillingActionsPermitted,
}: {
  roleBillingActionsPermitted: boolean;
}) {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const searchParams = useSearchParams();
  const billingStatusQuery = useBillingStatus(token);
  const usageQuery = useUsageSummary(token);
  const invoiceQuery = useInvoices(token);
  const checkoutMutation = useCreateCheckout(token);
  const creditPackCheckoutMutation = useCreateCreditPackCheckout(token);
  const portalMutation = useCreatePortalSession(token);
  const [upgradeTarget, setUpgradeTarget] = useState<PlanTier | null>(null);
  const [creditPackTarget, setCreditPackTarget] = useState<CreditPackId | null>(
    null,
  );
  const [isPortalTargetPending, setIsPortalTargetPending] = useState(false);
  const [billingActionError, setBillingActionError] =
    useState<BillingActionError | null>(null);
  const billingNarrativeRef = useRef<HTMLDivElement>(null);
  const { addToast } = useToastStore();
  const searchState = getBillingSearchState(searchParams);
  const { checkoutReturnState, creditIntentActive, requestedCreditPackId } =
    searchState;
  const refetchBillingStatus = billingStatusQuery.refetch;
  const refetchUsage = usageQuery.refetch;
  const refetchInvoices = invoiceQuery.refetch;
  const actionState = getBillingActionState({
    billingStatus: billingStatusQuery.data,
    checkoutPending: checkoutMutation.isPending,
    creditPackCheckoutPending: creditPackCheckoutMutation.isPending,
    creditPackTarget,
    isPortalTargetPending,
    portalPending: portalMutation.isPending,
    roleBillingActionsPermitted,
    upgradeTarget,
  });
  const { controlsDisabled: billingControlsDisabled } = actionState;
  const canStartAnalysis = principal.data?.can_create_analysis === true;
  const billingStatus = billingStatusQuery.data;
  const usage = usageQuery.data;
  const loadState = getBillingLoadState({
    billingStatus,
    billingStatusError: billingStatusQuery.error,
    billingStatusLoading: billingStatusQuery.isLoading,
    invoiceData: invoiceQuery.data,
    invoiceError: invoiceQuery.error,
    usage,
    usageError: usageQuery.error,
    usageLoading: usageQuery.isLoading,
  });
  const {
    billingAccessRestricted,
    billingDataMissing,
    billingLoadError,
    isLoading,
  } = loadState;
  const hasBillingLoadError = Boolean(billingLoadError);

  useEffect(() => {
    if (
      checkoutReturnState !== "success" ||
      creditIntentActive ||
      isLoading ||
      invoiceQuery.isLoading
    ) {
      return;
    }

    void refetchBillingStatus();
    void refetchUsage();
    void refetchInvoices();
  }, [
    checkoutReturnState,
    creditIntentActive,
    invoiceQuery.isLoading,
    isLoading,
    refetchBillingStatus,
    refetchInvoices,
    refetchUsage,
  ]);

  useEffect(() => {
    if (
      !requestedCreditPackId ||
      creditIntentActive ||
      !billingStatus ||
      billingStatus.plan === "enterprise" ||
      isLoading ||
      billingDataMissing ||
      billingAccessRestricted ||
      hasBillingLoadError ||
      checkoutReturnState === "success"
    ) {
      return undefined;
    }

    const frame = window.requestAnimationFrame(() => {
      const creditPackRow = document.getElementById(
        `credit-pack-${requestedCreditPackId}`,
      );

      creditPackRow?.scrollIntoView?.({ block: "center" });
      creditPackRow?.focus?.({ preventScroll: true });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [
    billingAccessRestricted,
    billingDataMissing,
    billingStatus,
    creditIntentActive,
    checkoutReturnState,
    hasBillingLoadError,
    isLoading,
    requestedCreditPackId,
  ]);

  useEffect(() => {
    if (!billingActionError) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      billingNarrativeRef.current?.scrollIntoView({
        behavior: "auto",
        block: "start",
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [billingActionError]);

  const handleUpgrade = async (planId: PlanTier) => {
    if (billingControlsDisabled) {
      return;
    }

    setBillingActionError(null);
    setUpgradeTarget(planId);
    try {
      const result = await checkoutMutation.mutateAsync({ plan_id: planId });
      redirectToBillingDestination(
        requireBillingRedirectUrl(result.checkout_url, "Plan checkout"),
      );
    } catch {
      console.error("[BillingPage] Failed to start checkout");
      setBillingActionError({ kind: "plan", planId });
      addToast(
        "Could not start checkout. No plan changes have been made.",
        "error",
      );
    } finally {
      setUpgradeTarget(null);
    }
  };

  const handleManageSubscription = async () => {
    if (billingControlsDisabled) {
      return;
    }

    setBillingActionError(null);
    setIsPortalTargetPending(true);
    try {
      const result = await portalMutation.mutateAsync();
      redirectToBillingDestination(
        requireBillingRedirectUrl(result.portal_url, "Billing portal"),
      );
    } catch {
      console.error("[BillingPage] Failed to open subscription portal");
      setBillingActionError({ kind: "portal" });
      addToast(
        "Could not open the subscription portal. Your subscription is unchanged.",
        "error",
      );
    } finally {
      setIsPortalTargetPending(false);
    }
  };

  const handleBuyCredits = async (creditPackId: CreditPackId) => {
    if (billingControlsDisabled) {
      return;
    }

    let redirectingToCheckout = false;
    setBillingActionError(null);
    setCreditPackTarget(creditPackId);
    try {
      const creditCheckoutReturnPath = buildCreditPackBillingReturnPath(
        searchParams,
        creditPackId,
      );
      const checkoutRequest = {
        credit_pack_id: creditPackId,
        cancel_url: buildCreditPackReturnUrl({
          creditPackId,
          returnPath: creditCheckoutReturnPath,
          state: "cancelled",
        }),
        success_url: buildCreditPackReturnUrl({
          creditPackId,
          returnPath: creditCheckoutReturnPath,
          state: "success",
        }),
      };
      const result =
        await creditPackCheckoutMutation.mutateAsync(checkoutRequest);
      redirectToBillingDestination(
        requireBillingRedirectUrl(result.checkout_url, "Credit checkout"),
      );
      redirectingToCheckout = true;
    } catch {
      console.error("[BillingPage] Failed to start credit checkout");
      setBillingActionError({ kind: "credit", creditPackId });
      addToast(
        "Could not start credit checkout. No credits have been purchased.",
        "error",
      );
    } finally {
      if (!redirectingToCheckout) {
        setCreditPackTarget(null);
      }
    }
  };

  const retryBillingQueries = () => {
    void refetchBillingStatus();
    void refetchUsage();
    void refetchInvoices();
  };

  const retryBillingAction = () => {
    const failedAction = billingActionError;
    setBillingActionError(null);

    if (!failedAction) {
      return;
    }
    if (failedAction.kind === "credit") {
      void handleBuyCredits(failedAction.creditPackId);
      return;
    }
    if (failedAction.kind === "plan") {
      void handleUpgrade(failedAction.planId);
      return;
    }
    void handleManageSubscription();
  };

  const pageStatus = getBillingPageStatus({
    billingStatus,
    loadState,
    token,
    usage,
  });
  if (pageStatus || !billingStatus || !usage) {
    return (
      <BillingPageStatusView
        onManageSubscription={() => void handleManageSubscription()}
        onRetry={retryBillingQueries}
        variant={pageStatus ?? "temporary"}
      />
    );
  }

  const viewModel = getLoadedBillingViewModel({
    billingStatus,
    billingStatusDataUpdatedAt: billingStatusQuery.dataUpdatedAt,
    billingStatusError: billingStatusQuery.error,
    searchState,
    usage,
    usageDataUpdatedAt: usageQuery.dataUpdatedAt,
    usageError: usageQuery.error,
  });
  const retryInvoices = () => {
    void invoiceQuery.refetch();
  };
  const reviewCreditPacks = () => {
    const target =
      document.getElementById("credit-pack-options") ??
      document.getElementById("credit-packs");

    target?.scrollIntoView({
      block: "start",
      behavior: motionAwareScrollBehavior(),
    });
  };

  return (
    <LoadedBillingPage
      actionError={billingActionError}
      actionState={actionState}
      billingNarrativeRef={billingNarrativeRef}
      billingStatus={billingStatus}
      canStartAnalysis={canStartAnalysis}
      creditPackTarget={creditPackTarget}
      invoiceAccessRestricted={loadState.invoiceAccessRestricted}
      invoiceData={loadState.visibleInvoiceData}
      invoiceError={invoiceQuery.error}
      invoiceLoading={invoiceQuery.isLoading}
      isPortalTargetPending={isPortalTargetPending}
      onBuyCredits={handleBuyCredits}
      onManageSubscription={handleManageSubscription}
      onRetryAction={retryBillingAction}
      onRetryBilling={retryBillingQueries}
      onRetryInvoices={retryInvoices}
      onReviewCreditPacks={reviewCreditPacks}
      onUpgrade={handleUpgrade}
      portalPending={portalMutation.isPending}
      searchState={searchState}
      token={token}
      upgradeTarget={upgradeTarget}
      usage={usage}
      viewModel={viewModel}
    />
  );
}

function MobileBillingDisclosure({
  children,
  summary,
  title,
}: {
  children: ReactNode;
  summary: string;
  title: string;
}) {
  return (
    <ResponsiveDisclosure
      className="group"
      summary={
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3 text-left shadow-[var(--shadow-xs)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:hidden [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </span>
            <span className="mt-0.5 block text-xs capitalize leading-5 text-[var(--text-secondary)]">
              {summary}
            </span>
          </span>
          <ArrowRight
            className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-90"
            aria-hidden="true"
          />
        </summary>
      }
    >
      <div className="mt-3 sm:mt-0 sm:block">{children}</div>
    </ResponsiveDisclosure>
  );
}

function PortalReturnNotice({ isVisible }: { isVisible: boolean }) {
  if (!isVisible) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-brand-primary/20 bg-brand-primary/10 px-4 py-3"
    >
      <div className="flex items-start gap-2">
        <CreditCard
          className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Subscription portal preview
          </p>
          <p className="mt-0.5 text-sm leading-6 text-[var(--text-secondary)]">
            Demo portal navigation returned here. No subscription or credit
            changes were made.
          </p>
        </div>
      </div>
    </div>
  );
}

function DemoCheckoutNotice({ plan }: { plan: PlanTier | null }) {
  if (!plan) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-brand-primary/20 bg-brand-primary/10 px-4 py-3"
    >
      <div className="flex items-start gap-2">
        <CreditCard
          className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Subscription checkout preview complete
          </p>
          <p className="mt-0.5 text-sm leading-6 text-[var(--text-secondary)]">
            Demo checkout returned for the {plan} plan. Live checkout would
            reconcile the Stripe subscription, invoice, and Report Credit
            allowance before this page refreshes.
          </p>
        </div>
      </div>
    </div>
  );
}

function CreditPackReturnNotice({
  creditPackId,
  isDemo,
}: {
  creditPackId: CreditPackId | null;
  isDemo: boolean;
}) {
  if (!creditPackId) {
    return null;
  }

  const pack = CREDIT_PACK_DETAILS[creditPackId];

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-success/20 bg-success/10 px-4 py-3"
    >
      <div className="flex items-start gap-2">
        <CheckCircle2
          className="mt-0.5 h-4 w-4 shrink-0 text-success"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {isDemo
              ? "Credit checkout preview complete"
              : "Report Credit checkout returned"}
          </p>
          <p className="mt-0.5 text-sm leading-6 text-[var(--text-secondary)]">
            {pack.label} returned from {isDemo ? "demo" : "Stripe"} checkout.
            {isDemo
              ? " Live Stripe checkout reconciles"
              : " Praviar is reconciling"}{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {formatReportCreditCount(pack.credits)}
            </span>{" "}
            to the organization ledger after payment confirmation.
          </p>
        </div>
      </div>
    </div>
  );
}

function CheckoutReturnNotice({ state }: { state: CheckoutReturnState }) {
  if (!state) {
    return null;
  }

  const isSuccess = state === "success";
  const Icon = isSuccess ? CheckCircle2 : TriangleAlert;

  return (
    <div
      role="status"
      aria-live="polite"
      className={
        isSuccess
          ? "rounded-lg border border-success/20 bg-success/10 px-4 py-3"
          : "rounded-lg border border-warning/20 bg-warning/10 px-4 py-3"
      }
    >
      <div className="flex items-start gap-2">
        <Icon
          className={
            isSuccess
              ? "mt-0.5 h-4 w-4 shrink-0 text-success"
              : "mt-0.5 h-4 w-4 shrink-0 text-warning"
          }
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {isSuccess ? "Checkout returned" : "Checkout flow cancelled"}
          </p>
          <p className="mt-0.5 text-sm leading-6 text-[var(--text-secondary)]">
            {isSuccess
              ? "Praviar is refreshing authoritative billing and Report Credit balances. This return alone does not confirm a change."
              : "No billing or Report Credit changes are assumed from this browser return. Authoritative balances remain visible below."}
          </p>
        </div>
      </div>
    </div>
  );
}

function BillingActionAccessNotice({ isVisible }: { isVisible: boolean }) {
  if (!isVisible) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3"
      data-testid="billing-action-access-notice"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          <LockKeyhole
            className="mt-0.5 h-4 w-4 shrink-0 text-warning"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              Billing purchase controls require admin access
            </p>
            <p className="mt-0.5 text-sm leading-6 text-[var(--text-secondary)]">
              Subscription portal, plan checkout, and Report Credit checkout are
              disabled for this role. Ask an organization administrator to
              update your role. If no administrator is available, review the
              deployment-specific support boundary. Usage, invoices, and credit
              economics remain visible for review.
            </p>
          </div>
        </div>
        <Button
          asChild
          variant="outline"
          size="sm"
          className="min-h-11 w-full shrink-0 sm:w-auto"
        >
          <Link href={WORKSPACE_SUPPORT_BOUNDARY_HREF}>
            <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
            Review support boundary
          </Link>
        </Button>
      </div>
    </div>
  );
}

function BillingActionErrorNotice({
  error,
  onRetry,
}: {
  error: BillingActionError | null;
  onRetry: () => void;
}) {
  if (!error) {
    return null;
  }

  const title =
    error.kind === "credit"
      ? "Checkout not started"
      : error.kind === "plan"
        ? "Plan checkout did not start"
        : "Subscription portal did not open";
  const body =
    error.kind === "credit"
      ? "No credits have been purchased, and the workspace ledger is unchanged. Retry when Stripe checkout is available."
      : error.kind === "plan"
        ? "No plan changes have been made, and current access is unchanged. Retry when Stripe checkout is available."
        : "Your subscription is unchanged. Retry when the Stripe billing portal is available.";
  const retryLabel =
    error.kind === "credit"
      ? "Retry checkout"
      : error.kind === "plan"
        ? "Retry plan checkout"
        : "Retry billing portal";

  return (
    <div
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
      className="rounded-lg border border-error/25 bg-error/10 px-4 py-3"
      data-testid="billing-action-error-notice"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <TriangleAlert
            className="mt-0.5 h-5 w-5 shrink-0 text-error"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {body}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 shrink-0"
          onClick={onRetry}
        >
          {retryLabel}
        </Button>
      </div>
    </div>
  );
}

function InvoiceAvailabilityNotice({
  accessRestricted,
  error,
  onRetry,
}: {
  accessRestricted: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  if (!error) {
    return null;
  }

  return (
    <div
      role="alert"
      aria-live="polite"
      aria-atomic="true"
      className="rounded-lg border border-warning/25 bg-warning/10 px-4 py-3"
      data-testid="billing-invoice-status-notice"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <TriangleAlert
            className="mt-0.5 h-5 w-5 shrink-0 text-warning"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {accessRestricted
                ? "Invoice history access restricted"
                : "Invoice history temporarily unavailable"}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {accessRestricted
                ? "Your current session cannot view invoice records. Subscription, usage, and Report Credit balances remain visible; invoice data stays hidden until access is restored."
                : "Subscription, usage, and Report Credit balances remain visible. Invoice records are unchanged; retry the invoice ledger when the billing service is available."}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 shrink-0"
          onClick={onRetry}
        >
          Retry invoice history
        </Button>
      </div>
    </div>
  );
}

function CreditIntentHero({
  actionsDisabled,
  availableReportCreditsBalance,
  canStartAnalysis,
  requestedCreditPackId,
  reportNeed,
  isCheckoutPending,
  creditPackTarget,
  launchReturnHref,
  onBuyCredits,
}: {
  actionsDisabled: boolean;
  availableReportCreditsBalance: number;
  canStartAnalysis: boolean;
  requestedCreditPackId: CreditPackId | null;
  reportNeed: number;
  isCheckoutPending: boolean;
  creditPackTarget: CreditPackId | null;
  launchReturnHref: string;
  onBuyCredits: (creditPackId: CreditPackId) => void;
}) {
  const packId =
    requestedCreditPackId ??
    getRecommendedCreditPackIdForNeed({
      availableReportCreditsBalance,
      reportNeed,
    });
  const pack = CREDIT_PACK_DETAILS[packId];
  const effectiveRateCents = Math.round(pack.priceCents / pack.credits);
  const additionalCreditsNeeded = Math.max(
    reportNeed - availableReportCreditsBalance,
    0,
  );
  const isCoveredByBalance = additionalCreditsNeeded === 0;
  const priceLabel = formatCreditPackPrice(pack.priceCents);
  const perReportLabel = formatCreditPackPrice(effectiveRateCents);

  return (
    <section
      aria-label="Report Credit checkout"
      className="overflow-hidden rounded-lg border border-brand-primary/25 bg-[var(--bg-surface)] shadow-[var(--shadow-md)]"
      data-testid="billing-credit-intent-hero"
    >
      <div className="grid min-w-0 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,25rem)]">
        <div className="praviar-credit-ledger-field relative isolate overflow-hidden p-4 sm:p-5">
          <div
            className="pointer-events-none absolute inset-0 z-0 bg-[var(--bg-surface)]/62 backdrop-blur-[1px]"
            aria-hidden="true"
          />
          <div className="relative z-10 flex min-w-0 items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-brand-primary/25 bg-brand-primary/10 text-brand-primary shadow-[var(--shadow-xs)]">
              <PackagePlus className="h-4 w-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
                Report Credit checkout
              </p>
              <h2 className="mt-1 text-xl font-semibold leading-7 text-[var(--text-primary)] sm:text-2xl">
                {pack.label} for {priceLabel}
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                {isCoveredByBalance
                  ? `${formatReportCreditCount(
                      availableReportCreditsBalance,
                    )} already covers ${formatReportCreditCount(
                      reportNeed,
                    )}. Start now, or add a one-time Report Credit Pack for future capacity.`
                  : `Adds ${formatReportCreditCount(
                      pack.credits,
                    )} for ${formatReportCreditCount(
                      reportNeed,
                    )} at ${perReportLabel} per report. No subscription change required.`}
              </p>
              <dl className="mt-4 grid max-w-3xl grid-cols-1 gap-2 text-xs min-[360px]:grid-cols-3">
                <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 px-2.5 py-2 shadow-[var(--shadow-xs)] sm:px-3">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    Pack
                  </dt>
                  <dd className="mt-1 font-semibold text-[var(--text-primary)]">
                    {formatReportCreditCount(pack.credits)}
                  </dd>
                </div>
                <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 px-2.5 py-2 shadow-[var(--shadow-xs)] sm:px-3">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    Rate
                  </dt>
                  <dd className="mt-1 font-semibold text-[var(--text-primary)]">
                    {perReportLabel} / report
                  </dd>
                </div>
                <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 px-2.5 py-2 shadow-[var(--shadow-xs)] sm:px-3">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    Available
                  </dt>
                  <dd className="mt-1 font-semibold text-[var(--text-primary)]">
                    {formatReportCreditCount(availableReportCreditsBalance)}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </div>

        <div className="min-w-0 border-t border-[var(--border-subtle)] bg-[var(--surface-muted)]/42 p-4 sm:p-5 lg:border-l lg:border-t-0">
          <div className="grid h-full min-w-0 gap-4">
            <div className="min-w-0">
              <p
                className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]"
                data-testid="billing-credit-intent-terms"
              >
                Before checkout
              </p>
              <ul className="mt-2 grid gap-2 text-xs leading-5 text-[var(--text-secondary)]">
                <li className="flex min-w-0 items-center gap-2">
                  <LockKeyhole
                    className="h-3.5 w-3.5 shrink-0 text-brand-primary"
                    aria-hidden="true"
                  />
                  One-time Stripe checkout
                </li>
                <li className="flex min-w-0 items-center gap-2">
                  <ShieldCheck
                    className="h-3.5 w-3.5 shrink-0 text-brand-primary"
                    aria-hidden="true"
                  />
                  Included credits used first
                </li>
                <li className="flex min-w-0 items-center gap-2">
                  <CreditCard
                    className="h-3.5 w-3.5 shrink-0 text-brand-primary"
                    aria-hidden="true"
                  />
                  Tax and receipt in Stripe
                </li>
                <li className="flex min-w-0 items-center gap-2">
                  <FileText
                    className="h-3.5 w-3.5 shrink-0 text-brand-primary"
                    aria-hidden="true"
                  />
                  First-pass request, not a legal conclusion
                </li>
              </ul>
            </div>

            <div className="grid gap-2 self-end">
              {isCoveredByBalance ? (
                !canStartAnalysis ? (
                  <p
                    className="rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs font-semibold leading-5 text-[var(--text-primary)]"
                    role="note"
                  >
                    This role can review billing capacity but cannot start a new
                    analysis.
                  </p>
                ) : isCheckoutPending ? (
                  <Button
                    className="h-auto min-h-11 w-full gap-2 whitespace-normal py-2 text-center leading-5"
                    disabled
                  >
                    <ArrowRight
                      className="h-4 w-4 shrink-0"
                      aria-hidden="true"
                    />
                    Start analysis using existing capacity
                  </Button>
                ) : (
                  <Button
                    asChild
                    className="h-auto min-h-11 w-full gap-2 whitespace-normal py-2 text-center leading-5"
                    variant="outline"
                  >
                    <Link href={launchReturnHref}>
                      <ArrowRight
                        className="h-4 w-4 shrink-0"
                        aria-hidden="true"
                      />
                      Start analysis using existing capacity
                    </Link>
                  </Button>
                )
              ) : (
                <>
                  {actionsDisabled ? (
                    <p
                      className="rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs font-semibold leading-5 text-[var(--text-primary)]"
                      role="note"
                    >
                      A workspace administrator must purchase Report Credits.
                      Capacity and pack economics remain visible for review.
                    </p>
                  ) : (
                    <Button
                      className="min-h-11 w-full gap-2"
                      onClick={() => onBuyCredits(packId)}
                      loading={creditPackTarget === packId}
                      disabled={isCheckoutPending}
                      aria-label={`Buy ${pack.label}, ${formatReportCreditCount(
                        pack.credits,
                      )} for ${priceLabel}`}
                    >
                      <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
                      Buy {pack.shortLabel}
                    </Button>
                  )}
                </>
              )}
              {isCoveredByBalance && !actionsDisabled ? (
                <Button
                  className="min-h-11 w-full gap-2"
                  variant="outline"
                  onClick={() => onBuyCredits(packId)}
                  loading={creditPackTarget === packId}
                  disabled={actionsDisabled || isCheckoutPending}
                  aria-label={`Buy buffer ${pack.label}, ${formatReportCreditCount(
                    pack.credits,
                  )} for ${priceLabel}`}
                >
                  <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
                  Buy buffer: {pack.shortLabel}
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function BillingCapacityRunway({
  usage,
  billingStatus,
  isCheckoutPending,
  creditPackTarget,
  onReviewCreditPacks,
}: {
  usage: UsageSummary;
  billingStatus: BillingStatus;
  isCheckoutPending: boolean;
  creditPackTarget: CreditPackId | null;
  onReviewCreditPacks: () => void;
}) {
  const remaining = getDisplayedRemainingAnalyses(usage, billingStatus.plan);
  const includedLimit = usage.included_analyses_limit ?? usage.analyses_limit;
  const purchasedCredits = usage.purchased_credits_balance ?? 0;
  const planAllowanceUsed = Math.min(
    Math.max(usage.analyses_used - (usage.purchased_credits_used ?? 0), 0),
    includedLimit,
  );
  const includedRemaining = Math.max(includedLimit - planAllowanceUsed, 0);
  const capacityLabel =
    remaining === null
      ? "Capacity not set"
      : `${formatReportCreditCount(remaining)} left`;
  const urgency =
    remaining === null
      ? "Custom capacity is managed through your subscription terms."
      : remaining <= 0
        ? "Capacity is exhausted. Buy Report Credits before launching more FTO work."
        : remaining <= 5
          ? "Capacity is tight. A Portfolio Pack keeps the next diligence run moving."
          : "Capacity is healthy for near-term report launches.";
  const renewsLabel = billingStatus.cancel_at_period_end
    ? "Access through"
    : "Renews";
  const creditReviewLabel =
    remaining !== null && remaining <= 0
      ? "Buy Report Credits"
      : remaining !== null && remaining <= 5
        ? "Review packs"
        : "Review Report Credit Packs";

  return (
    <section
      aria-label="Capacity runway"
      className="overflow-hidden rounded-lg border border-brand-primary/18 bg-[var(--bg-surface)] shadow-[var(--shadow-sm)]"
    >
      <div
        className="relative grid gap-4 overflow-hidden p-4 sm:p-5 2xl:grid-cols-[minmax(13rem,0.55fr)_minmax(0,34rem)_auto] 2xl:items-center"
        data-testid="billing-capacity-runway-layout"
      >
        <div
          className="praviar-capacity-runway-field pointer-events-none absolute inset-0 opacity-35"
          aria-hidden="true"
          data-testid="billing-capacity-runway-field"
        />

        <div className="relative order-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
              <PackagePlus className="h-4 w-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                Capacity runway
              </h2>
              <p className="mt-0.5 text-xs leading-5 text-[var(--text-tertiary)]">
                {urgency}
              </p>
            </div>
          </div>
        </div>

        <div className="relative order-3 grid w-full min-w-0 overflow-hidden rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/82 shadow-[var(--shadow-xs)] sm:grid-cols-3 sm:divide-x sm:divide-[var(--border-subtle)] 2xl:order-2">
          <RunwayMetric
            label="Launch capacity"
            value={capacityLabel}
            detail={`${includedRemaining.toLocaleString()} included, ${formatReportCreditCount(purchasedCredits)}`}
          />
          <RunwayMetric
            label={renewsLabel}
            value={formatDate(billingStatus.current_period_end)}
            detail={
              billingStatus.cancel_at_period_end
                ? "No auto-renewal"
                : "Subscription window"
            }
            className="hidden sm:block"
          />
          <RunwayMetric
            label="Consumption order"
            value="Included Report Credits first"
            detail="Purchased Report Credits apply after plan allowance"
            className="hidden sm:block"
          />
        </div>

        <div className="relative order-2 flex items-center 2xl:order-3">
          <Button
            className="min-h-11 w-full gap-2 2xl:w-auto"
            variant={
              remaining !== null && remaining <= 5 ? "default" : "outline"
            }
            onClick={onReviewCreditPacks}
            loading={creditPackTarget !== null}
            disabled={isCheckoutPending}
          >
            <ArrowDown className="h-4 w-4" aria-hidden="true" />
            {creditReviewLabel}
          </Button>
        </div>
      </div>
    </section>
  );
}

function RunwayMetric({
  label,
  value,
  detail,
  className,
}: {
  label: string;
  value: string;
  detail: string;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0 px-3 py-2.5", className)}>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 min-w-0 break-words text-sm font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </p>
      <p className="mt-1 break-words text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
        {detail}
      </p>
    </div>
  );
}

function BillingReconciliationStrip({
  checkoutReturnState,
  creditPackId,
  isDemoCreditPack,
  isInvoiceLoading,
  usage,
}: {
  checkoutReturnState: CheckoutReturnState;
  creditPackId: CreditPackId | null;
  isDemoCreditPack: boolean;
  isInvoiceLoading: boolean;
  usage: UsageSummary;
}) {
  const returnedPack = creditPackId ? CREDIT_PACK_DETAILS[creditPackId] : null;
  const isStripeSuccess = checkoutReturnState === "success";

  if (!isStripeSuccess && !returnedPack) {
    return null;
  }

  const headline =
    isStripeSuccess && returnedPack
      ? `${returnedPack.label} purchase is reconciling`
      : isStripeSuccess
        ? "Refreshing balances and invoice records"
        : `${returnedPack?.label ?? "Credit pack"} preview ready`;
  const body = isStripeSuccess
    ? "The latest hosted Stripe checkout result is being reconciled against your organization ledger. Existing access remains unchanged while the balance refresh completes."
    : "This demo checkout return shows the ledger state Praviar presents after Stripe confirms a one-time Report Credit purchase.";
  const receiptsLabel = isStripeSuccess
    ? isInvoiceLoading
      ? "Checking hosted invoices"
      : "Stripe receipts ready"
    : "Preview receipt mapped";

  return (
    <section
      role="status"
      aria-live="polite"
      id="billing-action-access-notice"
      aria-label="Stripe reconciliation status"
      className="praviar-account-control-card grid gap-3 overflow-hidden p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
      data-praviar-billing-reconciliation
    >
      <div className="min-w-0">
        <p className="type-label-sm text-[var(--text-tertiary)]">
          Stripe reconciliation
        </p>
        <p className="mt-1 type-heading-sm text-[var(--text-primary)] [overflow-wrap:anywhere]">
          {headline}
        </p>
        <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
          {body}
        </p>
      </div>
      <div className="grid min-w-0 gap-2 sm:w-64">
        {returnedPack ? (
          <div className="praviar-account-metric-panel rounded-lg px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              {isDemoCreditPack ? "Pack return" : "Pack purchased"}
            </p>
            <p className="mt-1 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
              +{formatReportCreditCount(returnedPack.credits)}
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              {formatCreditPackPrice(returnedPack.priceCents)}{" "}
              {isDemoCreditPack ? "previewed" : "checkout"}
            </p>
          </div>
        ) : null}
        <div className="praviar-account-metric-panel rounded-lg px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Current Report Credit balance
          </p>
          <p className="mt-1 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {formatReportCreditCount(usage.purchased_credits_balance ?? 0)}
          </p>
        </div>
        <div className="praviar-account-metric-panel rounded-lg px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Receipts
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {receiptsLabel}
          </p>
        </div>
      </div>
    </section>
  );
}

function BillingGovernanceRail({
  billingStatus,
  hasInvoices,
}: {
  billingStatus: BillingStatus;
  hasInvoices: boolean;
}) {
  const renewalBody = billingStatus.current_period_end
    ? billingStatus.cancel_at_period_end
      ? `Current access remains through ${formatDate(billingStatus.current_period_end)}.`
      : `Next renewal is ${formatDate(billingStatus.current_period_end)}.`
    : "No subscription renewal is currently scheduled.";
  const governanceItems = [
    {
      title: "Stripe-hosted checkout",
      body: "Plan changes and payment collection happen in Stripe-hosted flows; Praviar does not store card details.",
      icon: CreditCard,
    },
    {
      title: "Invoice documents",
      body: hasInvoices
        ? "Invoice links open hosted records in a new tab."
        : "Invoice records appear here after the first successful payment.",
      icon: FileText,
    },
    {
      title: "Org-scoped billing",
      body: "Usage, invoices, and subscription controls are scoped to this organization.",
      icon: LockKeyhole,
    },
    {
      title: "Renewal posture",
      body: renewalBody,
      icon: CalendarClock,
    },
  ];

  return (
    <aside
      aria-label="Billing governance controls"
      className="min-w-0 space-y-4 xl:sticky xl:top-24"
    >
      <div className="praviar-account-control-card overflow-hidden">
        <div className="praviar-account-control-header border-b border-[var(--border-subtle)] px-5 py-4">
          <div className="flex items-center gap-2">
            <ShieldCheck
              className="h-4 w-4 text-brand-primary"
              aria-hidden="true"
            />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              Billing governance
            </h2>
          </div>
          <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
            Account-control safeguards for finance and admin users.
          </p>
        </div>
        <div className="divide-y divide-[var(--border-subtle)]">
          {governanceItems.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.title}
                className="flex items-start gap-3 px-5 py-4"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] text-brand-primary">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {item.title}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                    {item.body}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
