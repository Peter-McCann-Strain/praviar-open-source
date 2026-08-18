"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, ClipboardCheck, RotateCcw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { summarizeReviewerDecisions } from "@/components/report/claim-decision-matrix-model";
import { getReviewLedgerSummary } from "@/components/report/review-ledger-summary";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import { isAuthBoundaryError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import {
  useCreateReviewerDecision,
  useReviewerDecisions,
  type Decision,
  type FindingType,
  type ReviewerDecision,
} from "@/hooks/use-reviewer-decisions";

export interface ReviewerDecisionPanelProps {
  open: boolean;
  onClose: () => void;
  analysisId: string;
  token: string | null;
  /** Report payload — the panel reads `patents`/`analyses` to enumerate findings. */
  report: unknown;
  initialFindingRef?: string;
  reviewStatus?: AnalysisReviewStatusResponse;
}

interface FindingRow {
  key: string;
  finding_type: FindingType;
  finding_ref: string;
  label: string;
  subtitle?: string;
  required_reviews: number;
}

interface ReviewerDecisionDraft {
  decision: Decision | null;
  edited_text: string;
  note: string;
}

type SaveRecoveryMode = "outcome_unknown" | "reconciling" | "retry_safe";

function recordString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value.trim() : "";
}

function recordNumberLabel(
  record: Record<string, unknown>,
  key: string,
): string {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value)
    ? String(value)
    : "";
}

function reportReviewContext(report: unknown): {
  compoundName: string;
  disclaimer: string;
} {
  if (!report || typeof report !== "object") {
    return {
      compoundName: "Report identity unavailable",
      disclaimer: "Research boundary unavailable",
    };
  }
  const record = report as Record<string, unknown>;
  const compound =
    record.compound && typeof record.compound === "object"
      ? (record.compound as Record<string, unknown>)
      : null;
  const candidate =
    (compound &&
      (recordString(compound, "name") ||
        recordString(compound, "display_name"))) ||
    recordString(record, "compound_name");
  const disclaimer = recordString(record, "disclaimer");
  return {
    compoundName: candidate
      ? Array.from(candidate.replace(/\s+/gu, " ")).slice(0, 160).join("")
      : "Report identity unavailable",
    disclaimer: disclaimer
      ? Array.from(disclaimer.replace(/\s+/gu, " ")).slice(0, 320).join("")
      : "Research boundary unavailable",
  };
}

/**
 * Reads a report payload and produces a deterministic list of findings
 * the reviewer can decide on.
 */
function extractFindings(report: unknown): FindingRow[] {
  const rows: FindingRow[] = [];
  if (!report || typeof report !== "object") return rows;
  const rec = report as Record<string, unknown>;
  const seen = new Set<string>();
  const pushRow = (row: FindingRow) => {
    if (seen.has(row.key)) return;
    seen.add(row.key);
    rows.push(row);
  };
  const patents = Array.isArray(rec.patent_analyses)
    ? rec.patent_analyses
    : Array.isArray(rec.patents)
      ? rec.patents
      : Array.isArray(rec.analyses)
        ? rec.analyses
        : [];
  for (const entry of patents) {
    if (!entry || typeof entry !== "object") continue;
    const e = entry as Record<string, unknown>;
    const pid =
      recordString(e, "patent_id") ||
      recordString(e, "id") ||
      recordString(e, "publication_number") ||
      recordString(e, "patent_number") ||
      null;
    if (!pid) continue;
    const assignee =
      typeof e.assignee === "string" && e.assignee ? e.assignee : undefined;
    const risk =
      typeof e.risk_level === "string" && e.risk_level
        ? e.risk_level.toLowerCase()
        : undefined;
    const requiredReviews = risk === "high" ? 2 : risk === "medium" ? 1 : 0;
    pushRow({
      key: `patent:${pid}`,
      finding_type: "patent",
      finding_ref: pid,
      label: pid,
      subtitle: [assignee, risk && `${risk.toUpperCase()} risk`]
        .filter(Boolean)
        .join(" · "),
      required_reviews: requiredReviews,
    });
  }
  const sourceMap =
    rec.claim_source_span_map && typeof rec.claim_source_span_map === "object"
      ? (rec.claim_source_span_map as Record<string, unknown>)
      : null;
  const sourceEntries = Array.isArray(sourceMap?.entries)
    ? sourceMap.entries
    : [];
  for (const entry of sourceEntries) {
    if (!entry || typeof entry !== "object") continue;
    const e = entry as Record<string, unknown>;
    const assertionId = recordString(e, "assertion_id");
    if (!assertionId) continue;
    const supportStatus = recordString(e, "support_status").toLowerCase();
    const customerVisible = e.customer_visible !== false;
    const reviewRequired =
      e.review_required === true || supportStatus === "needs_review";
    if (!customerVisible || !reviewRequired) continue;

    const patentId = recordString(e, "patent_id");
    const claimNumber = recordNumberLabel(e, "claim_number");
    const elementNumber = recordNumberLabel(e, "element_number");
    const assertionText = recordString(e, "assertion_text");
    const claimLabel = claimNumber ? `Claim ${claimNumber}` : "Claim assertion";
    const elementLabel = elementNumber ? ` element ${elementNumber}` : "";
    const label = `${claimLabel}${elementLabel}`;
    pushRow({
      key: `claim_element:${assertionId}`,
      finding_type: "claim_element",
      finding_ref: assertionId,
      label,
      subtitle: [
        patentId,
        supportStatus === "needs_review" ? "NEEDS REVIEW" : "REVIEW REQUIRED",
        assertionText,
      ]
        .filter(Boolean)
        .join(" · "),
      required_reviews: 1,
    });
  }
  return rows;
}

function decisionsFor(
  row: FindingRow,
  existing: ReviewerDecision[] | undefined,
): ReviewerDecision[] {
  if (!existing) return [];
  return existing.filter(
    (d) =>
      d.finding_type === row.finding_type && d.finding_ref === row.finding_ref,
  );
}

function decisionMatchesDraft(
  decision: ReviewerDecision,
  row: FindingRow,
  draft: ReviewerDecisionDraft,
) {
  return (
    decision.finding_type === row.finding_type &&
    decision.finding_ref === row.finding_ref &&
    decision.decision === draft.decision &&
    decision.note === draft.note &&
    decision.edited_text === draft.edited_text
  );
}

const REVIEW_SUMMARY_STYLES = {
  accepted: "border-success/40 bg-success/10 text-success",
  conflict: "border-error/40 bg-error/10 text-error",
  edited: "border-warning/40 bg-warning/10 text-warning",
  not_required:
    "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-secondary)]",
  pending: "border-warning/40 bg-warning/10 text-warning",
  rejected: "border-error/40 bg-error/10 text-error",
  unknown:
    "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-secondary)]",
} as const;

const PERSISTED_DECISION_LABELS: Record<Decision, string> = {
  accept: "Accepted",
  edit: "Edited",
  reject: "Rejected",
};

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function ReviewerDecisionPanel({
  open,
  onClose,
  analysisId,
  token,
  report,
  initialFindingRef,
  reviewStatus,
}: ReviewerDecisionPanelProps) {
  const {
    data,
    error: decisionsError,
    isLoading: decisionsLoading,
    refetch: refetchDecisions,
  } = useReviewerDecisions(analysisId, token);
  const create = useCreateReviewerDecision(analysisId, token);
  const decisionsAccessRestricted = isAuthBoundaryError(decisionsError);
  const decisionData = decisionsAccessRestricted ? undefined : data;

  const findings = React.useMemo(() => extractFindings(report), [report]);
  const reportContext = React.useMemo(
    () => reportReviewContext(report),
    [report],
  );
  const panelFindingCoverage = React.useMemo(() => {
    if (!decisionData) return null;
    return {
      decided: findings.filter(
        (row) => decisionsFor(row, decisionData.items).length > 0,
      ).length,
      total: findings.length,
    };
  }, [decisionData, findings]);
  const panelReviewStatus = React.useMemo(() => {
    if (!reviewStatus || !decisionData || !panelFindingCoverage) {
      return reviewStatus;
    }

    return {
      ...reviewStatus,
      decision_counts: decisionData.counts,
      findings_total: panelFindingCoverage.total,
      findings_reviewed: panelFindingCoverage.decided,
      completion_pct:
        panelFindingCoverage.total > 0
          ? Math.round(
              (panelFindingCoverage.decided / panelFindingCoverage.total) *
                10_000,
            ) / 100
          : 0,
    };
  }, [decisionData, panelFindingCoverage, reviewStatus]);
  const ledgerSummary = React.useMemo(
    () =>
      getReviewLedgerSummary({
        decisionCounts: decisionData?.counts,
        reviewStatus: panelReviewStatus,
      }),
    [decisionData?.counts, panelReviewStatus],
  );
  const [draftDecisions, setDraftDecisions] = React.useState<
    Record<string, ReviewerDecisionDraft>
  >({});
  const [saveRecoveries, setSaveRecoveries] = React.useState<
    Record<string, SaveRecoveryMode>
  >({});
  const [pendingKey, setPendingKey] = React.useState<string | null>(null);
  const decisionSaveInFlight = create.isPending || pendingKey !== null;
  const decisionsUnavailable = Boolean(decisionsError && !decisionData);
  const decisionControlsDisabled =
    decisionSaveInFlight || decisionsLoading || Boolean(decisionsError);
  const decisionMixLabel = decisionsLoading
    ? "Loading decision ledger"
    : decisionsUnavailable
      ? "Decision ledger unavailable"
      : (ledgerSummary.decisionMixLabel ?? "No reviewer decisions recorded");
  const panelCoverageLabel = decisionsLoading
    ? "Loading panel decision coverage"
    : decisionsUnavailable
      ? "Panel decision coverage unavailable"
      : panelFindingCoverage
        ? `${panelFindingCoverage.decided.toLocaleString()} / ${panelFindingCoverage.total.toLocaleString()} panel findings decided`
        : "Decision coverage pending";
  const clearDraftDecisions = React.useCallback(() => {
    setDraftDecisions({});
    setSaveRecoveries({});
  }, []);
  useAuthBoundaryReset(clearDraftDecisions);

  const dialogRef = React.useRef<HTMLDivElement>(null);
  const overlayRef = React.useRef<HTMLDivElement>(null);
  const previouslyFocusedRef = React.useRef<HTMLElement | null>(null);
  const titleId = React.useId();
  const descriptionId = React.useId();

  React.useEffect(() => {
    if (!open) return;
    previouslyFocusedRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousBodyOverflow = document.body.style.overflow;
    const overlay = overlayRef.current;
    document.body.style.overflow = "hidden";
    const backgroundSiblings = overlay
      ? Array.from(document.body.children)
          .filter(
            (element): element is HTMLElement =>
              element instanceof HTMLElement &&
              element !== overlay &&
              !element.contains(overlay),
          )
          .map((element) => ({
            element,
            inert: element.inert,
            ariaHidden: element.getAttribute("aria-hidden"),
          }))
      : [];
    for (const sibling of backgroundSiblings) {
      sibling.element.inert = true;
      sibling.element.setAttribute("aria-hidden", "true");
    }
    if (dialogRef.current) {
      dialogRef.current.scrollTop = 0;
    }
    const animationFrame = window.requestAnimationFrame(() => {
      const targetedFinding = initialFindingRef
        ? Array.from(
            dialogRef.current?.querySelectorAll<HTMLElement>(
              "[data-reviewer-finding-ref]",
            ) ?? [],
          ).find(
            (element) =>
              element.dataset.reviewerFindingRef === initialFindingRef,
          )
        : null;
      const closeButton = dialogRef.current?.querySelector<HTMLElement>(
        "[data-autofocus='reviewer-panel-close']",
      );
      (targetedFinding ?? closeButton ?? dialogRef.current)?.focus({
        preventScroll: true,
      });
      targetedFinding?.scrollIntoView?.({ block: "center" });
    });
    return () => {
      window.cancelAnimationFrame(animationFrame);
      for (const sibling of backgroundSiblings) {
        sibling.element.inert = sibling.inert;
        if (sibling.ariaHidden === null) {
          sibling.element.removeAttribute("aria-hidden");
        } else {
          sibling.element.setAttribute("aria-hidden", sibling.ariaHidden);
        }
      }
      document.body.style.overflow = previousBodyOverflow;
      previouslyFocusedRef.current?.focus({ preventScroll: true });
      previouslyFocusedRef.current = null;
    };
  }, [initialFindingRef, open]);

  if (!open || typeof document === "undefined") return null;

  const focusableElements = () =>
    Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ??
        [],
    ).filter((element) => element.getAttribute("aria-hidden") !== "true");

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = focusableElements();
    if (focusable.length === 0) {
      event.preventDefault();
      dialogRef.current?.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const setDraft = (key: string, patch: Partial<ReviewerDecisionDraft>) =>
    setDraftDecisions((prev) => ({
      ...prev,
      [key]: {
        // The ledger does not identify which entry belongs to the signed-in
        // reviewer. Never seed a writable draft from another person's record.
        decision: prev[key]?.decision ?? null,
        note: prev[key]?.note ?? "",
        edited_text: prev[key]?.edited_text ?? "",
        ...patch,
      },
    }));

  const handleSubmit = async (row: FindingRow) => {
    if (decisionSaveInFlight) return;
    const draft = draftDecisions[row.key];
    if (!draft?.decision) return;
    if (
      saveRecoveries[row.key] === "outcome_unknown" ||
      saveRecoveries[row.key] === "reconciling"
    ) {
      return;
    }
    if (draft.decision === "edit" && !draft.edited_text.trim()) {
      return; // guard — button should be disabled in this state
    }
    setSaveRecoveries((previous) => {
      const next = { ...previous };
      delete next[row.key];
      return next;
    });
    setPendingKey(row.key);
    try {
      await create.mutateAsync({
        finding_type: row.finding_type,
        finding_ref: row.finding_ref,
        decision: draft.decision,
        note: draft.note,
        edited_text: draft.edited_text,
      });
      setDraftDecisions((prev) => {
        const next = { ...prev };
        delete next[row.key];
        return next;
      });
    } catch {
      setSaveRecoveries((previous) => ({
        ...previous,
        [row.key]: "outcome_unknown",
      }));
      // A transport or 5xx failure can arrive after the server committed the
      // decision. Preserve the draft and require a ledger read before retrying.
    } finally {
      setPendingKey(null);
    }
  };

  const handleReconcile = async (row: FindingRow) => {
    if (decisionSaveInFlight) return;
    const draft = draftDecisions[row.key];
    if (!draft?.decision) return;

    setSaveRecoveries((previous) => ({
      ...previous,
      [row.key]: "reconciling",
    }));
    setPendingKey(row.key);
    try {
      const result = await refetchDecisions();
      if (result.error || !result.data) {
        setSaveRecoveries((previous) => ({
          ...previous,
          [row.key]: "outcome_unknown",
        }));
        return;
      }

      const wasCommitted = result.data.items.some((decision) =>
        decisionMatchesDraft(decision, row, draft),
      );
      if (wasCommitted) {
        setDraftDecisions((previous) => {
          const next = { ...previous };
          delete next[row.key];
          return next;
        });
        setSaveRecoveries((previous) => {
          const next = { ...previous };
          delete next[row.key];
          return next;
        });
        return;
      }

      setSaveRecoveries((previous) => ({
        ...previous,
        [row.key]: "retry_safe",
      }));
    } catch {
      setSaveRecoveries((previous) => ({
        ...previous,
        [row.key]: "outcome_unknown",
      }));
    } finally {
      setPendingKey(null);
    }
  };

  const panel = (
    <div
      ref={overlayRef}
      data-testid="reviewer-decision-panel"
      className="praviar-overlay-scrim praviar-overlay-scrim-strong pointer-events-auto fixed inset-0 z-[200] isolate flex items-center justify-center overscroll-contain p-4 sm:p-6"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-busy={decisionSaveInFlight}
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="praviar-dialog-panel relative z-[1] max-h-[calc(100dvh-3rem)] w-full max-w-3xl overflow-auto overscroll-contain rounded-lg focus:outline-none"
      >
        <header className="praviar-glass-strip sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-[var(--border-default)] px-4 py-3 sm:items-center sm:px-5">
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-semibold">
              Review findings
            </h2>
            <p
              id={descriptionId}
              className="text-xs text-[var(--text-secondary)]"
            >
              Accept, reject, or edit each finding. Your decisions are stored
              per-analysis and visible to other reviewers on this org.
            </p>
            <div
              role="note"
              aria-label="Review context"
              className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
              data-testid="reviewer-report-context"
            >
              <span
                className="max-w-full truncate font-semibold text-[var(--text-primary)]"
                data-testid="reviewer-report-compound"
                title={reportContext.compoundName}
              >
                {reportContext.compoundName}
              </span>
              <span className="text-[var(--text-tertiary)]" aria-hidden="true">
                ·
              </span>
              <span className="font-medium text-brand-primary">
                {reportContext.disclaimer}
              </span>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            type="button"
            className="h-11 min-h-11 w-11 min-w-11 shrink-0 rounded-lg"
            onClick={onClose}
            aria-label="Close reviewer panel"
            data-testid="reviewer-decision-panel-close"
            data-autofocus="reviewer-panel-close"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </header>

        <div
          className="border-b border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-elevated)_82%,transparent)] px-4 py-3 sm:px-5"
          role="status"
          aria-label="Review ledger summary"
        >
          <div className="grid gap-2 sm:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)] sm:items-center">
            <span
              className="hidden h-9 w-9 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary sm:flex"
              aria-hidden="true"
            >
              <ClipboardCheck className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Decision ledger scope
              </span>
              <span className="mt-0.5 block text-sm font-semibold text-[var(--text-primary)]">
                {panelCoverageLabel}
              </span>
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Decision mix
              </span>
              <span className="mt-0.5 block text-sm font-semibold text-[var(--text-primary)]">
                {decisionMixLabel}
              </span>
            </span>
          </div>
        </div>

        {decisionsUnavailable ? (
          <div
            role="alert"
            aria-labelledby="reviewer-decisions-load-error-title"
            className="border-b border-[var(--border-default)] bg-error/10 px-5 py-4"
            data-testid="reviewer-decisions-load-error"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle
                className="mt-0.5 h-5 w-5 shrink-0 text-error"
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p
                  id="reviewer-decisions-load-error-title"
                  className="font-semibold text-[var(--text-primary)]"
                >
                  {decisionsAccessRestricted
                    ? "Reviewer decisions access restricted"
                    : "Reviewer decisions temporarily unavailable"}
                </p>
                <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                  {decisionsAccessRestricted
                    ? "Your current session is not authorized to view or update reviewer decisions. Cached decision state is hidden until access is confirmed again."
                    : "Praviar could not load the reviewer decision ledger. Decision controls stay locked so the panel does not imply findings are undecided."}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-3 min-h-11 w-full gap-2 sm:w-auto"
                  onClick={() => {
                    void refetchDecisions();
                  }}
                >
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                  Retry decision load
                </Button>
              </div>
            </div>
          </div>
        ) : null}

        <ul className="divide-y divide-[var(--border-default)]">
          {findings.length === 0 ? (
            <li className="px-5 py-8 text-sm text-[var(--text-secondary)]">
              No findings available to review.
            </li>
          ) : null}
          {decisionsError && decisionData ? (
            <li
              role="status"
              className="border-b border-warning/20 bg-warning/10 px-5 py-3 text-sm leading-6 text-[var(--text-secondary)]"
              data-testid="reviewer-decisions-refresh-warning"
            >
              Reviewer decision refresh failed. Existing decisions remain
              visible for reference, but decision controls are locked until the
              ledger refreshes.
            </li>
          ) : null}
          {findings.map((row) => {
            const matchingDecisions = decisionsFor(row, decisionData?.items);
            const decisionSummary =
              summarizeReviewerDecisions(matchingDecisions);
            const reviewCount = decisionSummary.reviewCount;
            const reviewComplete =
              row.required_reviews > 0 && reviewCount >= row.required_reviews;
            const draft = draftDecisions[row.key];
            const current: Decision | null = draft?.decision ?? null;
            const note = draft?.note ?? "";
            const editedText = draft?.edited_text ?? "";
            const saveRecovery = saveRecoveries[row.key];
            const requiresRationale =
              current === "reject" ||
              current === "edit" ||
              (current === "accept" && row.required_reviews > 1);
            const canSubmit =
              current !== null &&
              (current !== "edit" || editedText.trim().length > 0) &&
              (!requiresRationale || note.trim().length > 0);
            return (
              <li
                key={row.key}
                className="px-4 py-4 sm:px-5"
                data-testid={`reviewer-finding-${row.finding_ref}`}
                data-reviewer-finding-ref={row.finding_ref}
                tabIndex={-1}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                  <div className="min-w-0">
                    <div className="break-all font-mono text-sm font-medium [overflow-wrap:anywhere]">
                      {row.label}
                    </div>
                    {row.subtitle ? (
                      <div className="text-xs text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                        {row.subtitle}
                      </div>
                    ) : null}
                    {matchingDecisions.length > 0 ? (
                      <div
                        className={cn(
                          "mt-1 inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold",
                          REVIEW_SUMMARY_STYLES[decisionSummary.state],
                        )}
                        data-testid="reviewer-finding-existing"
                      >
                        {decisionSummary.label}
                      </div>
                    ) : null}
                    {row.required_reviews > 0 ? (
                      <div
                        className={cn(
                          "mt-1 inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold",
                          reviewComplete
                            ? "border-success/40 bg-success/10 text-success"
                            : "border-warning/40 bg-warning/10 text-warning",
                        )}
                        data-testid={`reviewer-review-progress-${row.finding_ref}`}
                      >
                        {reviewCount}/{row.required_reviews} reviews
                      </div>
                    ) : null}
                    {matchingDecisions.length > 0 ? (
                      <ul
                        aria-label={`Saved reviewer decisions for ${row.label}`}
                        className="mt-2 grid gap-2"
                        data-testid={`reviewer-persisted-decisions-${row.finding_ref}`}
                      >
                        {matchingDecisions.map((decision) => {
                          const noteLabel =
                            decision.decision === "accept"
                              ? "Saved note"
                              : "Saved rationale";

                          return (
                            <li
                              key={decision.id}
                              className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]"
                              data-testid={`reviewer-persisted-decision-${decision.id}`}
                            >
                              <div className="font-semibold text-[var(--text-primary)]">
                                {PERSISTED_DECISION_LABELS[decision.decision]}
                              </div>
                              {decision.note.trim() ? (
                                <p className="mt-1 [overflow-wrap:anywhere]">
                                  <span className="font-medium text-[var(--text-primary)]">
                                    {noteLabel}:
                                  </span>{" "}
                                  {decision.note}
                                </p>
                              ) : (
                                <p className="mt-1 text-[var(--text-tertiary)]">
                                  No reviewer note was recorded.
                                </p>
                              )}
                              {decision.edited_text.trim() ? (
                                <p className="mt-1 [overflow-wrap:anywhere]">
                                  <span className="font-medium text-[var(--text-primary)]">
                                    Saved finding text:
                                  </span>{" "}
                                  {decision.edited_text}
                                </p>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    ) : null}
                  </div>

                  <div
                    className="grid w-full grid-cols-3 gap-2 sm:flex sm:w-auto sm:flex-wrap sm:justify-end"
                    role="radiogroup"
                    aria-label={`Decision for ${row.label}`}
                  >
                    {(["accept", "reject", "edit"] as Decision[]).map(
                      (option) => (
                        <Button
                          key={option}
                          type="button"
                          role="radio"
                          aria-checked={current === option}
                          size="sm"
                          variant={current === option ? "default" : "outline"}
                          className="min-h-11 w-full sm:w-auto"
                          disabled={decisionControlsDisabled}
                          onClick={() =>
                            setDraft(row.key, { decision: option })
                          }
                          data-testid={`reviewer-decision-${row.finding_ref}-${option}`}
                        >
                          {option}
                        </Button>
                      ),
                    )}
                  </div>
                </div>

                {current === "edit" ? (
                  <label className="mt-3 block text-xs font-medium text-[var(--text-secondary)]">
                    Edited finding text (required)
                    <textarea
                      className="praviar-glass-field mt-1 w-full rounded-md p-2 text-sm text-[var(--text-primary)] [overflow-wrap:anywhere]"
                      disabled={decisionControlsDisabled}
                      rows={3}
                      value={editedText}
                      onChange={(e) =>
                        setDraft(row.key, { edited_text: e.target.value })
                      }
                      data-testid={`reviewer-edit-${row.finding_ref}`}
                    />
                  </label>
                ) : null}

                <label className="mt-3 block text-xs font-medium text-[var(--text-secondary)]">
                  {requiresRationale
                    ? "Decision rationale (required)"
                    : "Decision note (optional)"}
                  <textarea
                    className="praviar-glass-field mt-1 w-full rounded-md p-2 text-sm text-[var(--text-primary)] [overflow-wrap:anywhere]"
                    disabled={decisionControlsDisabled}
                    rows={2}
                    value={note}
                    onChange={(e) =>
                      setDraft(row.key, { note: e.target.value })
                    }
                    data-testid={`reviewer-note-${row.finding_ref}`}
                  />
                </label>

                {saveRecovery ? (
                  <div
                    role="alert"
                    aria-live="polite"
                    className={cn(
                      "mt-3 rounded-md border px-3 py-2.5 text-xs leading-5 text-[var(--text-secondary)]",
                      saveRecovery === "retry_safe"
                        ? "border-error/30 bg-error/10"
                        : "border-warning/30 bg-warning/10",
                    )}
                    data-testid={`reviewer-save-error-${row.finding_ref}`}
                  >
                    {saveRecovery === "retry_safe" ? (
                      <>
                        <span className="font-semibold text-error">
                          Decision not found after ledger refresh.
                        </span>{" "}
                        Your selected decision and note are preserved. It is now
                        safe to retry the save.
                      </>
                    ) : (
                      <>
                        <span className="font-semibold text-warning">
                          Save outcome unknown.
                        </span>{" "}
                        {saveRecovery === "reconciling"
                          ? "Checking the reviewer ledger for the submitted decision."
                          : "The server may have recorded this decision. Check the reviewer ledger before retrying."}
                      </>
                    )}
                  </div>
                ) : null}

                <div className="mt-3 flex justify-end">
                  <Button
                    type="button"
                    size="sm"
                    className="min-h-11 px-4"
                    onClick={() => {
                      if (saveRecovery === "outcome_unknown") {
                        void handleReconcile(row);
                        return;
                      }
                      void handleSubmit(row);
                    }}
                    disabled={!draft || !canSubmit || decisionControlsDisabled}
                    data-testid={`reviewer-submit-${row.finding_ref}`}
                  >
                    {saveRecovery === "reconciling"
                      ? "Checking ledger..."
                      : pendingKey === row.key
                        ? "Saving..."
                        : saveRecovery === "outcome_unknown"
                          ? "Check decision ledger"
                          : saveRecovery === "retry_safe"
                            ? "Retry save"
                            : "Save my decision"}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );

  return createPortal(panel, document.body);
}

export default ReviewerDecisionPanel;
