"use client";

import {
  use,
  useEffect,
  useRef,
  useState,
  Suspense,
  type RefObject,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useExpandReportDetailsForPrint } from "@/hooks/use-expand-report-details-for-print";
import {
  usePrincipalCapabilities,
  type ApplicationRole,
} from "@/hooks/use-principal-capabilities";
import { useReport } from "@/hooks/use-report";
import { useAnalysis } from "@/hooks/use-analysis";
import {
  useAnalysisReviewStatus,
  type AnalysisReviewStatusResponse,
} from "@/hooks/use-analysis-review-status";
import { useReviewerDecisions } from "@/hooks/use-reviewer-decisions";
import { useClaimedUseReceipts } from "@/hooks/use-claimed-use-receipts";
import { ApiResponseValidationError } from "@/lib/validators";
import { APIError, isAuthBoundaryError } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { useComments } from "@/hooks/use-comments";
import { REVIEW_HANDOFF_ERROR_MESSAGE } from "@/hooks/report-interaction-copy";
import { ChatPanel } from "@/components/report/chat-panel";
import { mapChatCitationToCitationRef } from "@/components/report/chat-citation-mapping";
import { CitationPanel } from "@/components/report/citation-panel";
import { ReportSearchBar } from "@/components/report/report-search-bar";
import { ReportSearchResults } from "@/components/report/report-search-results";
import {
  useReportWorkspaceSummary,
  type ReportWorkspaceSummaryResponse,
} from "@/hooks/use-report-workspace-summary";
import { useReportSearch } from "@/hooks/use-report-search";
import {
  useReviewHandoff,
  type ReviewHandoffResponse,
} from "@/hooks/use-review-handoff";
import { useToastStore, type Toast } from "@/stores/toast-store";
import { ReportPageDialogs } from "@/components/report-page/report-page-dialogs";
import { ReportWatchControlProvider } from "@/components/report-page/use-report-watch-control";
import {
  ReportPageHeader,
  type ReportReviewHandoffDraft,
} from "@/components/report-page/report-page-header";
import { ReportStatusState } from "@/components/report-page/report-status-state";
import { ReportWorkspaceLoading } from "@/components/report-loading/report-workspace-loading";
import { ReportPageTabContent } from "@/components/report-page/report-page-tab-content";
import { ReportPageTabs } from "@/components/report-page/report-page-tabs";
import { ReportReviewLifecycleControl } from "@/components/report-page/report-review-lifecycle-control";
import { ReportSectionContextStrip } from "@/components/report-page/report-section-context-strip";
import { MobileReportCommandBar } from "@/components/report-page/mobile-report-command-bar";
import {
  getKnownExportReadinessBlockers,
  getReportSourceHealthReadiness,
  getWorkspaceBlockingJurisdictions,
  getWorkspaceExportReady,
} from "@/components/report-page/report-reliance-readiness";
import { motionAwareScrollBehavior } from "@/lib/motion-preferences";
import { canManageReportCollaboration } from "@/lib/report-permissions";
import type { ReportChatLaunchContext } from "@/components/report/chat-launch-context";
import type { ChatCitation } from "@/hooks/use-report-chat";
import type { CitationRef } from "@/types/citation";
import {
  getOverflowTabs,
  PRIMARY_TABS,
  resolveReportTab,
  type ReportTabId,
} from "@/components/report-page/tabs";
import type { FTOReport } from "@praviar/shared-types";
import { getReportReference } from "@/components/report-page/report-command-summary";

type ReportAiUrlContext =
  | "blocker_brief"
  | "external_readout"
  | "review_questions";

type ExportCapabilityState = "loading" | "ready" | "unavailable";
type CreatedReviewHandoff = {
  commentId: string;
  reviewStatusLabel: string;
} | null;
type ClaimedUseReceiptState = Pick<
  ReturnType<typeof useClaimedUseReceipts>,
  "data" | "error" | "isError" | "isLoading"
>;

interface ReportWorkspaceView {
  addToast: (message: string, type?: Toast["type"]) => void;
  analysis: ReturnType<typeof useAnalysis>["data"];
  authoritativeUserRole: ApplicationRole | undefined;
  canExportReport: boolean;
  canManageCollaboration: boolean;
  canResolveReview: boolean;
  chatLaunchContext: ReportChatLaunchContext | null;
  chatOpen: boolean;
  chatPatentId: string | null;
  claimedUseReceiptState: ClaimedUseReceiptState;
  claimedUseReceiptsQuery: ReturnType<typeof useClaimedUseReceipts>;
  clearReportSearch: () => void;
  closeReportChat: () => void;
  createReviewHandoff: (draft: ReportReviewHandoffDraft) => Promise<void>;
  createdHandoff: CreatedReviewHandoff;
  exportCapabilityState: ExportCapabilityState;
  exportOpen: boolean;
  feedbackOpen: boolean;
  focusActiveSectionSearch: () => void;
  handleChatOpenChange: (nextOpen: boolean) => void;
  handleChatReviewHandoffSuccess: (response: ReviewHandoffResponse) => void;
  hasReasoningTraces: boolean;
  id: string;
  monitorOpen: boolean;
  openExportDialog: () => void;
  openFeedbackDialog: () => void;
  openPatentFromSearch: (patentId: string) => void;
  openReportAiFromHeader: (context?: ReportChatLaunchContext) => void;
  openReportAiFromWorkspace: (context?: ReportChatLaunchContext) => void;
  openReportChatFromMobile: () => void;
  openShareDialog: () => void;
  overflowTabs: ReturnType<typeof getOverflowTabs>;
  principal: ReturnType<typeof usePrincipalCapabilities>;
  refetchAnalysis: ReturnType<typeof useAnalysis>["refetch"];
  report: FTOReport;
  reportSearch: ReturnType<typeof useReportSearch>;
  reportSearchParam: string | null;
  reviewHandoff: ReturnType<typeof useReviewHandoff>;
  reviewerDecisionsQuery: ReturnType<typeof useReviewerDecisions>;
  reviewStatus: AnalysisReviewStatusResponse | undefined;
  reviewStatusQuery: ReturnType<typeof useAnalysisReviewStatus>;
  selectedCitation: CitationRef | null;
  setExportOpen: (open: boolean) => void;
  setFeedbackOpen: (open: boolean) => void;
  setMonitorOpen: (open: boolean) => void;
  setSelectedCitation: (citation: CitationRef | null) => void;
  setShareOpen: (open: boolean) => void;
  setTab: (tab: ReportTabId) => void;
  shareOpen: boolean;
  submitReportSearch: (query: string) => Promise<void>;
  tab: ReportTabId;
  tabCounts: Record<string, number>;
  tabLabelId: string;
  token: ReturnType<typeof useAuthToken>;
  workspaceSummary: ReportWorkspaceSummaryResponse | undefined;
  workspaceSummaryQuery: ReturnType<typeof useReportWorkspaceSummary>;
  askAboutPatent: (patentId: string) => void;
  openChatCitation: (citation: ChatCitation, displayIndex?: number) => void;
}

function resolveExportCapabilityState(
  principal: ReturnType<typeof usePrincipalCapabilities>,
): ExportCapabilityState {
  if (!principal.data && (principal.isLoading || principal.isFetching)) {
    return "loading";
  }
  if (principal.isError || !principal.data) return "unavailable";
  return "ready";
}

function resolveReportErrorStatus(error: unknown): unknown {
  if (!error || typeof error !== "object" || !("status" in error)) {
    return undefined;
  }
  return (error as { status?: unknown }).status;
}

function buildReportTabCounts(
  report: FTOReport,
  comments: ReturnType<typeof useComments>["data"],
  workspaceSummary: ReportWorkspaceSummaryResponse | undefined,
): Record<string, number> {
  const claimCount =
    report.patent_analyses?.reduce(
      (sum, patent) => sum + (patent.claims_analyzed?.length ?? 0),
      0,
    ) ?? 0;
  const drawingsCount =
    report.drawing_analyses?.reduce(
      (sum, patent) => sum + (patent.structures?.length ?? 0),
      0,
    ) ?? 0;
  const evidenceCount =
    report.source_health?.entries?.length ||
    report.search_sources_used?.length ||
    workspaceSummary?.evidence_scope?.sources_considered?.length ||
    0;

  return {
    patents: report.patent_analyses?.length ?? 0,
    claims: claimCount,
    evidence: evidenceCount,
    drawings: drawingsCount,
    invalidity: report.invalidity_assessments?.length ?? 0,
    comments: comments?.length ?? 0,
  };
}

function resolveTabLabelId(tab: ReportTabId): string {
  return PRIMARY_TABS.some((tabConfig) => tabConfig.id === tab)
    ? `tab-${tab}`
    : `overflow-tab-${tab}`;
}

function ReportUnavailableState({
  analysis,
  id,
  isLoading,
  reportError,
  retryReportLoad,
  token,
}: {
  analysis: ReturnType<typeof useAnalysis>["data"];
  id: string;
  isLoading: boolean;
  reportError: unknown;
  retryReportLoad: () => void;
  token: ReturnType<typeof useAuthToken>;
}) {
  if (isLoading) return <ReportWorkspaceLoading />;

  if (!reportError && !DEMO_MODE_ENABLED && !token) {
    return <ReportStatusState variant="auth" className="my-8" />;
  }

  const reportStatusContext = {
    analysisId: id,
    analysisStatus: analysis?.status,
    analysisUpdatedAt: analysis?.updated_at,
    currentStep: analysis?.current_step,
    totalPatentsFound: analysis?.total_patents_found,
  };
  if (reportError instanceof ApiResponseValidationError) {
    return (
      <ReportStatusState
        variant="validation"
        {...reportStatusContext}
        detail={reportError.issues}
        onRetry={retryReportLoad}
        className="my-8"
      />
    );
  }
  if (isAuthBoundaryError(reportError)) {
    return resolveReportErrorStatus(reportError) === 401 ? (
      <ReportStatusState
        variant="auth"
        onRetry={retryReportLoad}
        className="my-8"
      />
    ) : (
      <ReportStatusState variant="forbidden" className="my-8" />
    );
  }
  if (reportError instanceof APIError && reportError.status === 403) {
    return <ReportStatusState variant="forbidden" className="my-8" />;
  }
  if (reportError instanceof APIError && reportError.status === 401) {
    return (
      <ReportStatusState
        variant="auth"
        onRetry={retryReportLoad}
        className="my-8"
      />
    );
  }
  if (reportError instanceof APIError && reportError.status === 404) {
    return (
      <ReportStatusState
        variant="missing"
        {...reportStatusContext}
        analysisStatus={analysis?.status}
        onRetry={retryReportLoad}
        className="my-8"
      />
    );
  }
  if (
    reportError instanceof APIError &&
    (reportError.status >= 500 || reportError.status === 0)
  ) {
    return (
      <ReportStatusState
        variant="temporary"
        {...reportStatusContext}
        onRetry={retryReportLoad}
        className="my-8"
      />
    );
  }
  if (reportError) {
    return (
      <ReportStatusState
        variant="temporary"
        {...reportStatusContext}
        onRetry={retryReportLoad}
        className="my-8"
      />
    );
  }
  return (
    <ReportStatusState
      variant="missing"
      {...reportStatusContext}
      analysisStatus={analysis?.status}
      onRetry={retryReportLoad}
      className="my-8"
    />
  );
}

function ReportWorkspaceNavigation({
  mobileAskButtonRef,
  reportSearchRef,
  view,
}: {
  mobileAskButtonRef: RefObject<HTMLButtonElement | null>;
  reportSearchRef: RefObject<HTMLDivElement | null>;
  view: ReportWorkspaceView;
}) {
  return (
    <>
      <ReportPageTabs
        tab={view.tab}
        overflowTabs={view.overflowTabs}
        tabCounts={view.tabCounts}
        onTabChange={view.setTab}
      />
      <MobileReportCommandBar
        analysisId={view.id}
        token={view.token}
        report={view.report}
        chatOpen={view.chatOpen}
        shareActive={view.analysis?.share_active}
        shareRecipientBound={view.analysis?.share_recipient_bound}
        shareViewCount={view.analysis?.share_view_count}
        shareLastViewedAt={view.analysis?.share_last_viewed_at}
        reviewStatus={view.reviewStatus}
        reviewStatusLoading={view.reviewStatusQuery.isLoading}
        reviewerDecisions={view.reviewerDecisionsQuery.data}
        reviewerDecisionsLoading={view.reviewerDecisionsQuery.isLoading}
        workspaceSummary={view.workspaceSummary}
        workspaceSummaryLoading={view.workspaceSummaryQuery.isLoading}
        askButtonRef={mobileAskButtonRef}
        currentUserRole={view.authoritativeUserRole}
        canExportReport={view.canExportReport}
        onAsk={view.openReportChatFromMobile}
        onSearch={view.focusActiveSectionSearch}
        onExport={view.openExportDialog}
        onShare={view.openShareDialog}
        onMonitorPlan={() => view.setMonitorOpen(true)}
        onFeedback={view.openFeedbackDialog}
        onRequestCounsel={() => view.setTab("comments")}
        onReviewOpen={view.closeReportChat}
      />
      <ReportSectionContextStrip
        tab={view.tab}
        tabCounts={view.tabCounts}
        hasReasoningTraces={view.hasReasoningTraces}
        onAskAi={view.openReportAiFromWorkspace}
        onSearch={view.focusActiveSectionSearch}
      />
      {view.tab !== "evidence" ? (
        <div ref={reportSearchRef}>
          <ReportSearchBar
            key={view.reportSearchParam ?? "report-search-empty"}
            onSearch={view.submitReportSearch}
            onClear={view.clearReportSearch}
            isSearching={view.reportSearch.isSearching}
            interpretedQuery={view.reportSearch.interpretedQuery}
            initialQuery={view.reportSearchParam ?? ""}
            resultCount={
              view.reportSearch.interpretedQuery
                ? view.reportSearch.totalResults
                : undefined
            }
            error={view.reportSearch.error}
            className="mb-4"
          />
          <ReportSearchResults
            results={view.reportSearch.results}
            totalResults={view.reportSearch.totalResults}
            interpretedQuery={view.reportSearch.interpretedQuery}
            failedQuery={view.reportSearch.failedQuery}
            isShowingPreviousResults={
              view.reportSearch.isShowingPreviousResults
            }
            resultQuery={view.reportSearch.resultQuery}
            onOpenPatent={view.openPatentFromSearch}
            onAskAboutPatent={view.askAboutPatent}
          />
        </div>
      ) : null}
    </>
  );
}

function ReportWorkspaceHeader({
  headerAskButtonRef,
  mobileAskButtonRef,
  reportSearchRef,
  view,
}: {
  headerAskButtonRef: RefObject<HTMLButtonElement | null>;
  mobileAskButtonRef: RefObject<HTMLButtonElement | null>;
  reportSearchRef: RefObject<HTMLDivElement | null>;
  view: ReportWorkspaceView;
}) {
  return (
    <ReportPageHeader
      analysisId={view.id}
      token={view.token}
      report={view.report}
      sectionNavigation={
        <ReportWorkspaceNavigation
          mobileAskButtonRef={mobileAskButtonRef}
          reportSearchRef={reportSearchRef}
          view={view}
        />
      }
      showDecisionCockpit={view.tab === "overview"}
      shareActive={view.analysis?.share_active}
      shareRecipientBound={view.analysis?.share_recipient_bound}
      shareViewCount={view.analysis?.share_view_count}
      shareLastViewedAt={view.analysis?.share_last_viewed_at}
      onExport={view.openExportDialog}
      onShare={view.openShareDialog}
      onMonitorPlan={() => view.setMonitorOpen(true)}
      onFeedback={view.openFeedbackDialog}
      onReviewOpen={view.closeReportChat}
      onAskAi={view.openReportAiFromHeader}
      askAiButtonRef={headerAskButtonRef}
      onOpenComments={() => view.setTab("comments")}
      onPrepareHandoff={view.createReviewHandoff}
      reviewHandoffState={{
        commentId: view.createdHandoff?.commentId ?? null,
        error: view.reviewHandoff.isError ? REVIEW_HANDOFF_ERROR_MESSAGE : null,
        isPending: view.reviewHandoff.isPending,
        reviewStatusLabel: view.createdHandoff?.reviewStatusLabel ?? null,
      }}
      reviewerDecisions={view.reviewerDecisionsQuery.data}
      reviewerDecisionsLoading={view.reviewerDecisionsQuery.isLoading}
      reviewStatus={view.reviewStatus}
      reviewStatusLoading={view.reviewStatusQuery.isLoading}
      workspaceSummary={view.workspaceSummary}
      workspaceSummaryLoading={view.workspaceSummaryQuery.isLoading}
      currentUserRole={view.authoritativeUserRole}
      canExportReport={view.canExportReport}
    />
  );
}

function ReportWorkspaceLifecycle({ view }: { view: ReportWorkspaceView }) {
  if (!view.canResolveReview) return null;

  return (
    <details className="group sm:contents" data-no-print>
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border-emphasis)] bg-[var(--surface-card)] px-4 py-3 text-left shadow-[var(--shadow-sm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:hidden [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-[var(--text-primary)]">
            Legal lifecycle decision
          </span>
          <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
            Open reviewer status, consequences, and the governed audit note.
          </span>
        </span>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="mt-3 hidden group-open:block sm:mt-0 sm:block">
        <ReportReviewLifecycleControl
          analysisId={view.id}
          status={view.reviewStatus}
          statusError={Boolean(
            view.reviewStatusQuery.error && !view.reviewStatusQuery.data,
          )}
          statusLoading={
            !view.reviewStatusQuery.data &&
            (view.reviewStatusQuery.isLoading ||
              view.reviewStatusQuery.isFetching)
          }
          onRefresh={() =>
            Promise.all([
              view.reviewStatusQuery.refetch(),
              view.workspaceSummaryQuery.refetch(),
              view.refetchAnalysis(),
            ])
          }
        />
      </div>
    </details>
  );
}

function ReportWorkspacePanels({
  chatReturnFocusRef,
  view,
}: {
  chatReturnFocusRef: RefObject<HTMLElement | null>;
  view: ReportWorkspaceView;
}) {
  const reviewReceiptState = view.canResolveReview
    ? view.claimedUseReceiptState
    : undefined;

  return (
    <>
      <ReportPageTabContent
        analysisId={view.id}
        tab={view.tab}
        labelId={view.tabLabelId}
        report={view.report}
        reviewStatus={view.reviewStatus}
        reviewStatusLoading={view.reviewStatusQuery.isLoading}
        reviewerDecisions={view.reviewerDecisionsQuery.data}
        reviewerDecisionsLoading={view.reviewerDecisionsQuery.isLoading}
        reviewerDecisionsUnavailable={
          !view.canResolveReview ||
          Boolean(
            view.reviewerDecisionsQuery.error &&
            !view.reviewerDecisionsQuery.data,
          )
        }
        token={view.token}
        initialEvidenceQuery={view.reportSearchParam ?? ""}
        workspaceSummary={view.workspaceSummary}
        workspaceSummaryLoading={view.workspaceSummaryQuery.isLoading}
        onReviewHandoffSuccess={view.handleChatReviewHandoffSuccess}
        canManageCollaboration={view.canManageCollaboration}
        claimedUseReceiptState={reviewReceiptState}
        currentUserRole={view.authoritativeUserRole}
        onRetryClaimedUseReceipts={() => {
          void view.claimedUseReceiptsQuery.refetch();
        }}
      />
      <ReportPageDialogs
        reportId={view.id}
        report={view.report}
        exportOpen={view.exportOpen}
        shareOpen={view.shareOpen}
        feedbackOpen={view.feedbackOpen}
        monitorOpen={view.monitorOpen}
        shareActive={view.analysis?.share_active}
        shareRecipientBound={view.analysis?.share_recipient_bound}
        shareViewCount={view.analysis?.share_view_count}
        shareLastViewedAt={view.analysis?.share_last_viewed_at}
        reviewStatus={view.reviewStatus}
        reviewStatusLoading={view.reviewStatusQuery.isLoading}
        reviewerDecisions={view.reviewerDecisionsQuery.data}
        reviewerDecisionsLoading={view.reviewerDecisionsQuery.isLoading}
        workspaceSummary={view.workspaceSummary}
        workspaceSummaryLoading={view.workspaceSummaryQuery.isLoading}
        currentUserRole={view.authoritativeUserRole}
        currentUserRoleState={view.exportCapabilityState}
        claimedUseReceiptState={reviewReceiptState}
        onExportRoleRetry={() => {
          void view.principal.refetch();
        }}
        onShareStateRefresh={() => {
          void view.refetchAnalysis();
        }}
        onExportClose={() => view.setExportOpen(false)}
        onShareClose={() => view.setShareOpen(false)}
        onFeedbackChange={view.setFeedbackOpen}
        onMonitorChange={view.setMonitorOpen}
      />
      <ChatPanel
        key={view.id}
        analysisId={view.id}
        token={view.token}
        launchContext={view.chatLaunchContext}
        patentId={view.chatPatentId ?? undefined}
        open={view.chatOpen}
        onOpenChange={view.handleChatOpenChange}
        launcherClassName="max-lg:hidden"
        returnFocusRef={chatReturnFocusRef}
        onCitationClick={view.openChatCitation}
        onCreateReviewHandoff={view.createReviewHandoff}
        onReviewHandoffSuccess={view.handleChatReviewHandoffSuccess}
        reviewHandoffError={
          view.reviewHandoff.isError ? REVIEW_HANDOFF_ERROR_MESSAGE : null
        }
        reviewHandoffPending={view.reviewHandoff.isPending}
        reviewHandoffSuccessLabel={
          view.createdHandoff
            ? `Brief sent to review: ${view.createdHandoff.reviewStatusLabel}`
            : null
        }
      />
      <CitationPanel
        citation={view.selectedCitation}
        report={view.report}
        onClose={() => view.setSelectedCitation(null)}
        onOpenPatent={(patentId) => {
          view.setSelectedCitation(null);
          view.openPatentFromSearch(patentId);
        }}
      />
    </>
  );
}

function ReportWorkspaceLayout({
  chatReturnFocusRef,
  headerAskButtonRef,
  mobileAskButtonRef,
  reportSearchRef,
  view,
}: {
  chatReturnFocusRef: RefObject<HTMLElement | null>;
  headerAskButtonRef: RefObject<HTMLButtonElement | null>;
  mobileAskButtonRef: RefObject<HTMLButtonElement | null>;
  reportSearchRef: RefObject<HTMLDivElement | null>;
  view: ReportWorkspaceView;
}) {
  return (
    <ReportWatchControlProvider analysisId={view.id} report={view.report}>
      <div className="praviar-report-workspace mx-auto w-full min-w-0 max-w-[90rem] space-y-6 overflow-x-clip">
        <ReportWorkspaceHeader
          headerAskButtonRef={headerAskButtonRef}
          mobileAskButtonRef={mobileAskButtonRef}
          reportSearchRef={reportSearchRef}
          view={view}
        />
        <ReportWorkspaceLifecycle view={view} />
        <ReportWorkspacePanels
          chatReturnFocusRef={chatReturnFocusRef}
          view={view}
        />
      </div>
    </ReportWatchControlProvider>
  );
}

function ReportContent({ id }: { id: string }) {
  useExpandReportDetailsForPrint();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [exportOpen, setExportOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [monitorOpen, setMonitorOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatPatentId, setChatPatentId] = useState<string | null>(null);
  const [chatLaunchContext, setChatLaunchContext] =
    useState<ReportChatLaunchContext | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<CitationRef | null>(
    null,
  );
  const [createdHandoff, setCreatedHandoff] =
    useState<CreatedReviewHandoff>(null);
  const reportSearchRef = useRef<HTMLDivElement>(null);
  const headerAskButtonRef = useRef<HTMLButtonElement>(null);
  const mobileAskButtonRef = useRef<HTMLButtonElement>(null);
  const chatReturnFocusRef = useRef<HTMLElement | null>(null);
  const chatFocusRestorePendingRef = useRef(false);
  const chatReturnFocusRequestedRef = useRef(false);
  const chatReturnFocusSourceRef = useRef<"header" | "mobile" | null>(null);
  const appliedUrlAiContextRef = useRef<string | null>(null);
  const appliedUrlSearchRef = useRef<string | null>(null);
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const {
    data: apiReport,
    isLoading,
    error: reportError,
    refetch: refetchReport,
  } = useReport(id, token);
  const { data: analysis, refetch: refetchAnalysis } = useAnalysis(id, token);
  const reportAccessRestricted = isAuthBoundaryError(reportError);
  const report: FTOReport | null = reportAccessRestricted
    ? null
    : (apiReport ?? null);
  const exportCapabilityState = resolveExportCapabilityState(principal);
  const canExportReport = principal.data?.can_export_report === true;
  const canResolveReview = principal.data?.can_resolve_review === true;
  const authoritativeUserRole = principal.data?.role;
  const reportReady = Boolean(report);
  const reportInteractionToken = reportReady ? token : null;
  const canManageCollaboration = canManageReportCollaboration(
    authoritativeUserRole,
  );
  const { data: comments } = useComments(id, reportInteractionToken);
  const workspaceSummaryQuery = useReportWorkspaceSummary(
    reportReady ? id : null,
  );
  const reviewStatusQuery = useAnalysisReviewStatus(
    reportReady && canResolveReview ? id : "",
  );
  const reviewerDecisionsQuery = useReviewerDecisions(
    id,
    canResolveReview ? reportInteractionToken : null,
  );
  const claimedUseReceiptsQuery = useClaimedUseReceipts(
    id,
    canResolveReview ? reportInteractionToken : null,
    reportReady && canResolveReview,
  );
  const claimedUseReceiptState = {
    data: claimedUseReceiptsQuery.data,
    error: claimedUseReceiptsQuery.error,
    isError: claimedUseReceiptsQuery.isError,
    isLoading: claimedUseReceiptsQuery.isLoading,
  };
  const workspaceSummary = workspaceSummaryQuery.data;
  const reviewStatus = reviewStatusQuery.data;
  const reviewHandoff = useReviewHandoff(id, reportInteractionToken);
  const addToast = useToastStore((state) => state.addToast);

  const reportSearch = useReportSearch(id, reportInteractionToken);
  const runReportSearch = reportSearch.search;

  const hasReasoningTraces = (report?.reasoning_traces?.length ?? 0) > 0;
  const overflowTabs = getOverflowTabs(hasReasoningTraces);
  const reportAiContextParam = resolveReportAiUrlContextParam(
    searchParams.get("ai_context"),
    searchParams.get("assistant"),
  );
  const reportSearchParam = resolveReportSearchParam(
    searchParams.get("search"),
  );
  const tab = resolveReportTab(searchParams.get("tab"), overflowTabs);
  const tabLabelId = resolveTabLabelId(tab);
  const retryReportLoad = () => {
    void refetchReport();
  };

  useEffect(() => {
    if (!report) return;
    const launchContext = buildReportAiUrlLaunchContext(reportAiContextParam, {
      analysis,
      report,
      analysisId: id,
      reportId: getReportReference(report),
      reviewStatus,
    });
    if (!launchContext) return;

    const launchKey = `${id}:${reportAiContextParam}:${report.generated_at ?? ""}`;
    if (appliedUrlAiContextRef.current === launchKey) return;

    appliedUrlAiContextRef.current = launchKey;
    setChatPatentId(null);
    setChatLaunchContext(launchContext);
    setChatOpen(true);
  }, [analysis, id, report, reportAiContextParam, reviewStatus]);

  useEffect(() => {
    if (!report || !reportSearchParam || tab === "evidence") return;

    const searchKey = `${id}:${reportSearchParam}`;
    if (appliedUrlSearchRef.current === searchKey) return;

    appliedUrlSearchRef.current = searchKey;
    void runReportSearch(reportSearchParam);
    window.requestAnimationFrame(() => {
      reportSearchRef.current?.scrollIntoView({
        behavior: motionAwareScrollBehavior(),
        block: "center",
      });
      reportSearchRef.current?.querySelector("input")?.focus();
    });
  }, [id, report, reportSearchParam, runReportSearch, tab]);

  useEffect(() => {
    if (chatOpen || !chatFocusRestorePendingRef.current) return;

    const getReturnFocusTarget = () => {
      if (chatReturnFocusRef.current?.isConnected) {
        return chatReturnFocusRef.current;
      }
      if (chatReturnFocusSourceRef.current === "mobile") {
        return mobileAskButtonRef.current;
      }
      if (chatReturnFocusSourceRef.current === "header") {
        return headerAskButtonRef.current;
      }
      return null;
    };

    let attempts = 0;
    const focusReturnTarget = () => {
      attempts += 1;
      const target = getReturnFocusTarget();
      if (!target) {
        if (attempts >= 4) {
          chatFocusRestorePendingRef.current = false;
          chatReturnFocusRequestedRef.current = false;
          chatReturnFocusSourceRef.current = null;
        }
        return;
      }
      target.focus();
      chatFocusRestorePendingRef.current = false;
      chatReturnFocusRequestedRef.current = false;
      chatReturnFocusSourceRef.current = null;
    };

    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      focusReturnTarget();
      secondFrame = window.requestAnimationFrame(focusReturnTarget);
    });
    const fallback = window.setTimeout(focusReturnTarget, 80);
    const finalFallback = window.setTimeout(focusReturnTarget, 160);

    return () => {
      window.cancelAnimationFrame(firstFrame);
      window.cancelAnimationFrame(secondFrame);
      window.clearTimeout(fallback);
      window.clearTimeout(finalFallback);
    };
  }, [chatOpen]);

  const handleChatOpenChange = (nextOpen: boolean) => {
    chatFocusRestorePendingRef.current =
      !nextOpen && chatReturnFocusRequestedRef.current;
    setChatOpen(nextOpen);
  };

  if (!report) {
    return (
      <ReportUnavailableState
        analysis={analysis}
        id={id}
        isLoading={isLoading}
        reportError={reportError}
        retryReportLoad={retryReportLoad}
        token={token}
      />
    );
  }

  const setTab = (nextTab: ReportTabId) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", nextTab);
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const replaceReportSearchParams = (params: URLSearchParams) => {
    const query = params.toString();
    router.replace(query ? `?${query}` : `/analyses/${id}/report`, {
      scroll: false,
    });
  };

  const clearReportSearch = () => {
    reportSearch.clear();
    appliedUrlSearchRef.current = null;

    if (!searchParams.has("search")) return;
    const params = new URLSearchParams(searchParams.toString());
    params.delete("search");
    replaceReportSearchParams(params);
  };

  const submitReportSearch = async (query: string) => {
    const normalizedQuery = resolveReportSearchParam(query);
    if (!normalizedQuery) {
      clearReportSearch();
      return;
    }

    appliedUrlSearchRef.current = `${id}:${normalizedQuery}`;
    const responsePromise = runReportSearch(normalizedQuery);

    const params = new URLSearchParams(searchParams.toString());
    params.set("search", normalizedQuery);
    if (searchParams.get("search") !== normalizedQuery) {
      replaceReportSearchParams(params);
    }

    const response = await responsePromise;
    const exactPatentId = response
      ? findUniquePublicationIdMatch(normalizedQuery, response.results)
      : null;
    if (!exactPatentId) return;

    params.set("tab", "patents");
    params.set("patent", exactPatentId);
    replaceReportSearchParams(params);
  };

  const completeReviewHandoff = (response: ReviewHandoffResponse) => {
    const reviewStatusLabel = formatReviewStatusLabel(
      response.review_status.status,
    );
    setCreatedHandoff({
      commentId: response.comment_id,
      reviewStatusLabel,
    });
    addToast("Review handoff created", "success");
    setTab("comments");
  };

  const createReviewHandoff = async (draft: ReportReviewHandoffDraft) => {
    setChatOpen(false);
    setCreatedHandoff(null);
    try {
      const response = await reviewHandoff.mutateAsync(draft);
      completeReviewHandoff(response);
    } catch {
      addToast(REVIEW_HANDOFF_ERROR_MESSAGE, "error");
    }
  };

  const handleChatReviewHandoffSuccess = (response: ReviewHandoffResponse) => {
    setChatOpen(false);
    completeReviewHandoff(response);
  };

  const focusReportSearch = () => {
    reportSearchRef.current?.scrollIntoView({
      block: "center",
      behavior: motionAwareScrollBehavior(),
    });
    requestAnimationFrame(() => {
      reportSearchRef.current?.querySelector("input")?.focus();
    });
  };
  const focusActiveSectionSearch = () => {
    if (tab === "evidence") {
      const evidenceSearchInput = document.getElementById(
        "report-evidence-workbench-query",
      ) as HTMLInputElement | null;
      const mobileDisclosure = evidenceSearchInput?.closest("details");
      if (mobileDisclosure && !mobileDisclosure.open) {
        mobileDisclosure.open = true;
      }
      evidenceSearchInput?.scrollIntoView({
        block: "center",
        behavior: motionAwareScrollBehavior(),
      });
      requestAnimationFrame(() => evidenceSearchInput?.focus());
      return;
    }

    focusReportSearch();
  };

  const openExportDialog = () => {
    setChatOpen(false);
    if (exportCapabilityState === "loading") {
      addToast(
        "Confirming export access. Try export again in a moment.",
        "info",
      );
      return;
    }
    if (exportCapabilityState === "unavailable") {
      addToast(
        "Export access is unavailable. Refresh capabilities before preparing a packet.",
        "error",
      );
      void principal.refetch();
      return;
    }
    if (!canExportReport) {
      addToast(
        "Report export is not enabled for your application role or the current risk-access policy.",
        "info",
      );
      return;
    }
    setExportOpen(true);
  };

  const openShareDialog = () => {
    setChatOpen(false);
    if (!canManageCollaboration) {
      addToast(
        "Only patent counsel or an organization administrator can share reports.",
        "info",
      );
      return;
    }
    setShareOpen(true);
  };

  const openFeedbackDialog = () => {
    setChatOpen(false);
    if (!canManageCollaboration) {
      addToast(
        "Attorney feedback is available to patent counsel and organization administrators.",
        "info",
      );
      return;
    }
    setFeedbackOpen(true);
  };

  const closeReportChat = () => {
    chatFocusRestorePendingRef.current = false;
    chatReturnFocusRequestedRef.current = false;
    chatReturnFocusSourceRef.current = null;
    setChatOpen(false);
  };

  const openPatentFromSearch = (patentId: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "patents");
    params.set("patent", patentId);
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const askAboutPatent = (patentId: string) => {
    chatReturnFocusRef.current = null;
    chatReturnFocusRequestedRef.current = false;
    chatReturnFocusSourceRef.current = null;
    setChatPatentId(patentId);
    setChatLaunchContext({
      actionLabel: "Generating patent review",
      description:
        "Opened from reviewed evidence search results in this generated report packet.",
      intent: "patent",
      launchId: createChatLaunchId(),
      metadata: [{ label: "Patent", value: patentId }],
      prompt: `Review patent ${patentId} in this FTO report. Summarize the key claims, risk posture, evidence basis, uncertainty, and counsel follow-up questions using only report-grounded evidence.`,
      title: `Patent ${patentId}`,
    });
    setChatOpen(true);
  };
  const openChatCitation = (citation: ChatCitation, displayIndex?: number) => {
    setSelectedCitation(mapChatCitationToCitationRef(citation, displayIndex));
  };

  const tabCounts = buildReportTabCounts(report, comments, workspaceSummary);
  const openReportAi = (context?: ReportChatLaunchContext) => {
    setChatPatentId(null);
    setChatLaunchContext(prepareChatLaunchContext(context));
    setChatOpen(true);
  };
  const openReportAiFromHeader = (context?: ReportChatLaunchContext) => {
    chatReturnFocusRef.current = headerAskButtonRef.current;
    chatReturnFocusRequestedRef.current = true;
    chatReturnFocusSourceRef.current = "header";
    openReportAi(context);
  };
  const openReportAiFromWorkspace = (context?: ReportChatLaunchContext) => {
    chatReturnFocusRef.current = null;
    chatReturnFocusRequestedRef.current = false;
    chatReturnFocusSourceRef.current = null;
    openReportAi(context);
  };
  const openReportChatFromMobile = () => {
    chatReturnFocusRef.current = mobileAskButtonRef.current;
    chatReturnFocusRequestedRef.current = true;
    chatReturnFocusSourceRef.current = "mobile";
    openReportAi(
      buildReportVerificationLaunchContext({
        report,
        analysisId: id,
        reportId: getReportReference(report),
        reviewStatus,
        workspaceSummary,
      }),
    );
  };

  const view: ReportWorkspaceView = {
    addToast,
    analysis,
    askAboutPatent,
    authoritativeUserRole,
    canExportReport,
    canManageCollaboration,
    canResolveReview,
    chatLaunchContext,
    chatOpen,
    chatPatentId,
    claimedUseReceiptState,
    claimedUseReceiptsQuery,
    clearReportSearch,
    closeReportChat,
    createReviewHandoff,
    createdHandoff,
    exportCapabilityState,
    exportOpen,
    feedbackOpen,
    focusActiveSectionSearch,
    handleChatOpenChange,
    handleChatReviewHandoffSuccess,
    hasReasoningTraces,
    id,
    monitorOpen,
    openChatCitation,
    openExportDialog,
    openFeedbackDialog,
    openPatentFromSearch,
    openReportAiFromHeader,
    openReportAiFromWorkspace,
    openReportChatFromMobile,
    openShareDialog,
    overflowTabs,
    principal,
    refetchAnalysis,
    report,
    reportSearch,
    reportSearchParam,
    reviewHandoff,
    reviewerDecisionsQuery,
    reviewStatus,
    reviewStatusQuery,
    selectedCitation,
    setExportOpen,
    setFeedbackOpen,
    setMonitorOpen,
    setSelectedCitation,
    setShareOpen,
    setTab,
    shareOpen,
    submitReportSearch,
    tab,
    tabCounts,
    tabLabelId,
    token,
    workspaceSummary,
    workspaceSummaryQuery,
  };

  return (
    <ReportWorkspaceLayout
      chatReturnFocusRef={chatReturnFocusRef}
      headerAskButtonRef={headerAskButtonRef}
      mobileAskButtonRef={mobileAskButtonRef}
      reportSearchRef={reportSearchRef}
      view={view}
    />
  );
}

function formatReviewStatusLabel(status?: string | null): string {
  const normalized = String(status ?? "")
    .trim()
    .replaceAll("_", " ");
  if (!normalized) return "review status updated";
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function prepareChatLaunchContext(
  context?: ReportChatLaunchContext,
): ReportChatLaunchContext | null {
  if (!context) return null;
  return {
    ...context,
    launchId: context.launchId ?? createChatLaunchId(),
  };
}

function createChatLaunchId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `launch-${Date.now()}`;
}

function buildReviewProgressSummary(
  reviewStatus?: {
    findings_reviewed?: number;
    findings_total?: number;
    status?: string;
  } | null,
): string {
  if (reviewStatus?.findings_total === undefined) {
    return reviewStatus?.status ?? "review state pending";
  }
  return `${(reviewStatus.findings_reviewed ?? 0).toLocaleString()} / ${reviewStatus.findings_total.toLocaleString()} findings reviewed`;
}

function buildVerificationReadinessSummary(
  reviewStatus?: AnalysisReviewStatusResponse | null,
  workspaceSummary?: ReportWorkspaceSummaryResponse | null,
): string {
  const readinessBlockers = getKnownExportReadinessBlockers({
    reviewStatus: reviewStatus ?? undefined,
    workspaceSummary: workspaceSummary ?? undefined,
  });
  if (readinessBlockers.length > 0) {
    return readinessBlockers
      .map((blocker) => `${blocker.label}: ${blocker.detail}`)
      .join(" | ");
  }
  return getWorkspaceExportReady(workspaceSummary ?? undefined) === true
    ? "No known readiness blockers; backend export checks still run at start."
    : "Export readiness is not loaded.";
}

function buildVerificationJurisdictionSummary(
  workspaceSummary?: ReportWorkspaceSummaryResponse | null,
): string {
  const blockingJurisdictions = getWorkspaceBlockingJurisdictions(
    workspaceSummary ?? undefined,
  );
  const targetJurisdictions = Array.isArray(
    workspaceSummary?.target_jurisdictions,
  )
    ? workspaceSummary.target_jurisdictions
        .map((jurisdiction) => jurisdiction.trim().toUpperCase())
        .filter(Boolean)
    : [];
  if (targetJurisdictions.length > 0) return targetJurisdictions.join(", ");
  if (blockingJurisdictions.length > 0) {
    return blockingJurisdictions.join(", ");
  }
  return "not reported";
}

function buildReportVerificationLaunchContext({
  analysisId,
  report,
  reportId,
  reviewStatus,
  workspaceSummary,
}: {
  analysisId: string;
  report: FTOReport;
  reportId: string;
  reviewStatus?: AnalysisReviewStatusResponse | null;
  workspaceSummary?: ReportWorkspaceSummaryResponse | null;
}): ReportChatLaunchContext {
  const compoundName = report.compound?.name ?? "this compound";
  const risk = String(report.risk_summary?.overall_risk ?? "unknown");
  const blockerCount = report.risk_summary?.blocking_patents_count ?? 0;
  const patentCount =
    report.patent_analyses?.length ??
    report.risk_summary?.total_patents_analyzed ??
    report.total_patents_found ??
    0;
  const reviewSummary = buildReviewProgressSummary(reviewStatus);
  const sourceHealth = getReportSourceHealthReadiness(report);
  const readinessSummary = buildVerificationReadinessSummary(
    reviewStatus,
    workspaceSummary,
  );
  const jurisdictionSummary =
    buildVerificationJurisdictionSummary(workspaceSummary);

  return {
    actionLabel: "Checking reliance gaps",
    description:
      "Opened from the mobile report command bar for an AI-assisted critique of reliance gaps before export, share, or counsel handoff.",
    intent: "report",
    metadata: [
      { label: "Report", value: reportId },
      { label: "Analysis", value: analysisId },
      { label: "Compound", value: compoundName },
      { label: "Risk", value: risk },
      { label: "Blockers", value: blockerCount.toLocaleString() },
      { label: "Patents", value: patentCount.toLocaleString() },
      { label: "Review", value: reviewSummary },
      { label: "Export readiness", value: readinessSummary },
      {
        label: "Source audit",
        value: `${sourceHealth.value} - ${sourceHealth.detail}`,
      },
      { label: "Jurisdictions", value: jurisdictionSummary },
    ],
    prompt: `Critique the reliance readiness for ${compoundName}. Start with export readiness, counsel review status, source-health caveats, material blockers, jurisdiction scope, unresolved uncertainty, and follow-up questions. Use only this generated report packet, separate decision support from legal clearance, and do not present the critique as independent verification.`,
    title: `${compoundName} reliance gap check`,
  };
}

function buildReportAiUrlLaunchContext(
  rawContext: string | null,
  {
    analysis,
    report,
    analysisId,
    reportId,
    reviewStatus,
  }: {
    analysis?: {
      share_active?: boolean | null;
      share_view_count?: number | null;
    } | null;
    report: FTOReport;
    analysisId: string;
    reportId: string;
    reviewStatus?: {
      findings_reviewed?: number;
      findings_total?: number;
      status?: string;
    } | null;
  },
): ReportChatLaunchContext | null {
  if (!isReportAiUrlContext(rawContext)) return null;

  const compoundName = report.compound?.name ?? "this compound";
  const risk = String(report.risk_summary?.overall_risk ?? "unknown");
  const blockerCount = report.risk_summary?.blocking_patents_count ?? 0;
  const patentCount =
    report.patent_analyses?.length ??
    report.risk_summary?.total_patents_analyzed ??
    report.total_patents_found ??
    0;
  const metadata = [
    { label: "Report", value: reportId },
    { label: "Analysis", value: analysisId },
    { label: "Compound", value: compoundName },
    { label: "Risk", value: risk },
    { label: "Blockers", value: blockerCount.toLocaleString() },
    { label: "Patents", value: patentCount.toLocaleString() },
  ];

  if (rawContext === "blocker_brief") {
    return {
      actionLabel: "Generating blocker brief",
      description:
        "Opened from dashboard AI command queue for high-risk blocker triage.",
      intent: "report",
      metadata,
      prompt: `Draft a source-grounded blocking-patent brief for ${compoundName}. Focus on active or blocking patent families, claim elements, expiry or legal status, design-around assumptions, unresolved uncertainty, and counsel follow-up. Use only this generated report packet and cite evidence sections when available.`,
      title: `${compoundName} blocker brief`,
    };
  }

  if (rawContext === "review_questions") {
    const reviewSummary = buildReviewProgressSummary(reviewStatus);

    return {
      actionLabel: "Preparing reviewer questions",
      description:
        "Opened from dashboard AI command queue to turn caveats into reviewer-ready prompts.",
      intent: "report",
      metadata: [...metadata, { label: "Review", value: reviewSummary }],
      prompt: `Prepare reviewer questions for ${compoundName}. Convert unresolved caveats, evidence gaps, blocker assumptions, and any changes-requested items into concise source-linked questions with owner-ready follow-ups. Keep the output grounded in this report packet.`,
      title: `${compoundName} reviewer questions`,
    };
  }

  return {
    actionLabel: "Summarizing shared readout",
    description:
      "Opened from dashboard AI command queue for a shared-packet readout.",
    intent: "report",
    metadata: [
      ...metadata,
      {
        label: "Share",
        value: analysis?.share_active
          ? `${(analysis.share_view_count ?? 0).toLocaleString()} views`
          : "not active",
      },
    ],
    prompt: `Summarize the external readout for ${compoundName}. Explain what a recipient can rely on, what remains outside the shared packet, material risk movements, caveats, and recommended next handoff steps. Do not imply legal clearance.`,
    title: `${compoundName} external readout`,
  };
}

function isReportAiUrlContext(
  value: string | null,
): value is ReportAiUrlContext {
  return (
    value === "blocker_brief" ||
    value === "review_questions" ||
    value === "external_readout"
  );
}

function resolveReportAiUrlContextParam(
  rawContext: string | null,
  legacyAssistant: string | null,
): ReportAiUrlContext | null {
  if (isReportAiUrlContext(rawContext)) {
    return rawContext;
  }

  if (legacyAssistant === "answers") return "blocker_brief";
  if (legacyAssistant === "evidence") return "review_questions";
  if (legacyAssistant === "monitor") return "external_readout";

  return null;
}

function resolveReportSearchParam(rawSearch: string | null): string | null {
  const trimmedSearch = rawSearch?.trim();
  if (!trimmedSearch) return null;

  return trimmedSearch.slice(0, 160);
}

function findUniquePublicationIdMatch(
  query: string,
  results: Array<{ patent_id: string }>,
): string | null {
  const normalizedQuery = normalizePublicationSearchToken(query);
  if (!/^[A-Z]{2,4}\d{6,}[A-Z]?\d?$/.test(normalizedQuery)) return null;

  const matches = Array.from(
    new Set(
      results
        .map((result) => result.patent_id.trim())
        .filter((patentId) => {
          const normalizedPatentId = normalizePublicationSearchToken(patentId);
          return (
            normalizedPatentId === normalizedQuery ||
            normalizedPatentId.startsWith(normalizedQuery)
          );
        }),
    ),
  );
  return matches.length === 1 ? matches[0] : null;
}

function normalizePublicationSearchToken(value: string) {
  return value.toUpperCase().replace(/[\s._/-]+/g, "");
}

export default function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <Suspense fallback={<ReportWorkspaceLoading />}>
      <ReportContent key={id} id={id} />
    </Suspense>
  );
}
