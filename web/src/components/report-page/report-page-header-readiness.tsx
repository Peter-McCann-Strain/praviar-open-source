"use client";

import type { ReactNode, RefObject } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  FileLock2,
  Info,
  Loader2,
  LockKeyhole,
  MessageSquareText,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ReportChatLaunchContext } from "@/components/report/chat-launch-context";
import type { RelianceLifecycleState } from "@/components/report-page/report-reliance-readiness";
import { cn } from "@/lib/utils";

export type ReadinessTone = "success" | "warning" | "danger" | "neutral";

export interface ReportReviewHandoffDraft {
  body: string;
  promote_to_under_review: true;
  review_note: string;
  target_id: string;
  target_type: "analysis" | "patent" | "claim";
}

export interface ReportReviewHandoffState {
  commentId?: string | null;
  error?: string | null;
  isPending?: boolean;
  reviewStatusLabel?: string | null;
}

export interface RelianceReadinessBlocker {
  detail: string;
  icon: ReactNode;
  label: string;
  tone: ReadinessTone;
}

export interface RelianceReadinessMetric {
  detail: string;
  icon: ReactNode;
  label: string;
  tone?: ReadinessTone;
  value: string;
}

export interface RelianceDecisionQueueItem {
  completion: string;
  detail: string;
  evidence: string;
  label: string;
  owner: string;
  priority: "P1" | "P2" | "P3";
  tone: ReadinessTone;
}

export interface RelianceReadinessModel {
  aiContext: ReportChatLaunchContext;
  blockers: RelianceReadinessBlocker[];
  decisionQueue: RelianceDecisionQueueItem[];
  exportAction: {
    ariaLabel: string;
    detail?: string;
    label: string;
    tone: "blocked" | "caveat" | "ready" | "verify";
  };
  handoffDraft: ReportReviewHandoffDraft;
  headline: string;
  lifecycleState: RelianceLifecycleState;
  metrics: RelianceReadinessMetric[];
  statusLabel: string;
  statusTone: ReadinessTone;
}

export function RelianceReadinessPanel({
  model,
  onAskAi,
  askAiButtonRef,
  onOpenComments,
  onPrepareHandoff,
  reviewHandoffState,
}: {
  model: RelianceReadinessModel;
  onAskAi?: (context?: ReportChatLaunchContext) => void;
  askAiButtonRef?: RefObject<HTMLButtonElement | null>;
  onOpenComments?: () => void;
  onPrepareHandoff?: (draft: ReportReviewHandoffDraft) => void;
  reviewHandoffState?: ReportReviewHandoffState;
}) {
  const handoffPending = reviewHandoffState?.isPending === true;
  const handoffCreated = Boolean(reviewHandoffState?.commentId);
  const handoffDisabled = !onPrepareHandoff || handoffPending || handoffCreated;

  return (
    <div
      id="report-reliance-readiness"
      className="praviar-provenance-map min-w-0 rounded-lg p-3 sm:p-4"
      data-testid="report-reliance-readiness"
    >
      <div className="flex min-w-0 flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
          <FileLock2 className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
            Report readiness console
          </p>
          <h2 className="mt-1 text-lg font-semibold leading-6 text-[var(--text-primary)]">
            Reliance readiness
          </h2>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {model.headline}
          </p>
        </div>
        <div
          className={cn(
            readinessStatusClass(model.statusTone),
            "mt-0 shrink-0",
          )}
          role="status"
          aria-label="Reliance readiness status"
        >
          {model.statusTone === "success" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : model.statusTone === "neutral" ? (
            <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : (
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          <span className="text-xs font-semibold">{model.statusLabel}</span>
        </div>
      </div>

      <ExportRecoveryBrief
        model={model}
        onAskAi={onAskAi}
        onPrepareHandoff={onPrepareHandoff}
        reviewHandoffState={reviewHandoffState}
      />

      <div
        role="group"
        aria-label="Authoritative reliance state"
        className="mt-3 grid gap-2 rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-elevated)_84%,transparent)] px-3 py-3 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,0.9fr)_minmax(0,1.2fr)_minmax(0,1.2fr)]"
      >
        <ReadinessStateDatum
          label="Authoritative state"
          value={model.lifecycleState.label}
          tone={model.lifecycleState.tone}
        />
        <ReadinessStateDatum label="Owner" value={model.lifecycleState.owner} />
        <ReadinessStateDatum
          label="Current blocker"
          value={model.lifecycleState.blocker}
        />
        <ReadinessStateDatum
          label="Next action"
          value={model.lifecycleState.nextAction}
        />
      </div>

      <div
        className="mt-3 rounded-md border border-brand-primary/20 bg-brand-primary/8 p-3"
        data-testid="report-decision-queue"
      >
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
              AI recovery plan
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              Prioritized from reliance gates, evidence scope, source audit, and
              reviewer state, with the proof and done state attached.
            </p>
          </div>
          <Badge variant="secondary" className="shrink-0 text-xs uppercase">
            {model.decisionQueue.length} actions
          </Badge>
        </div>
        <ol className="mt-3 grid gap-2 lg:grid-cols-3">
          {model.decisionQueue.map((item, index) => (
            <li
              key={`${item.priority}:${item.label}:${item.detail}`}
              className="grid min-w-0 grid-cols-[2.25rem_minmax(0,1fr)] gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 px-3 py-2"
            >
              <span className={readinessQueuePriorityClass(item.tone)}>
                <span className="sr-only">Priority {index + 1}</span>
                <span aria-hidden="true">{item.priority}</span>
              </span>
              <span className="min-w-0">
                <span className="block text-xs font-semibold text-[var(--text-primary)]">
                  {item.label}
                </span>
                <span className="mt-0.5 block text-xs leading-4 text-[var(--text-secondary)]">
                  {item.detail}
                </span>
                <span className="mt-1 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  Owner: {item.owner}
                </span>
                <span className="mt-2 block rounded-sm border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-elevated)_84%,transparent)] px-2 py-1 text-xs leading-4 text-[var(--text-secondary)]">
                  <span className="font-semibold text-[var(--text-primary)]">
                    Basis:
                  </span>{" "}
                  {item.evidence}
                </span>
                <span className="mt-1 block rounded-sm border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-elevated)_84%,transparent)] px-2 py-1 text-xs leading-4 text-[var(--text-secondary)]">
                  <span className="font-semibold text-[var(--text-primary)]">
                    Done:
                  </span>{" "}
                  {item.completion}
                </span>
              </span>
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-3" role="group" aria-label="Readiness signals">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          Readiness signals
        </p>
        <div className="grid gap-2 lg:grid-cols-3">
          {model.blockers.map((blocker) => (
            <div
              key={`${blocker.label}:${blocker.detail}`}
              className="grid grid-cols-[2rem_minmax(0,1fr)] items-start gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-3 py-2"
            >
              <span
                className={readinessIconClass(blocker.tone)}
                aria-hidden="true"
              >
                {blocker.icon}
              </span>
              <span className="min-w-0">
                <span className="block text-xs font-semibold text-[var(--text-primary)]">
                  {blocker.label}
                </span>
                <span className="mt-0.5 block text-xs leading-4 text-[var(--text-secondary)]">
                  {blocker.detail}
                </span>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {model.metrics.map((metric) => (
          <div
            key={metric.label}
            className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)] gap-2 rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-elevated)_80%,transparent)] px-3 py-2"
          >
            <span
              className={readinessIconClass(metric.tone ?? "neutral")}
              aria-hidden="true"
            >
              {metric.icon}
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                {metric.label}
              </span>
              <span className="mt-0.5 block text-sm font-semibold text-[var(--text-primary)]">
                {metric.value}
              </span>
              <span className="mt-0.5 block text-xs leading-4 text-[var(--text-secondary)]">
                {metric.detail}
              </span>
            </span>
          </div>
        ))}
      </div>

      <div
        className="mt-3 hidden grid-cols-3 gap-2 xl:grid"
        role="group"
        aria-label="Report review path"
      >
        {["Source audit", "Material review", "Counsel verify"].map((step) => (
          <div
            key={step}
            className="praviar-provenance-step rounded-md px-2 py-2 text-center"
          >
            <span className="block text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              {step}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <Button
          ref={askAiButtonRef}
          type="button"
          variant="outline"
          className="min-h-11 justify-between gap-2"
          onClick={() => onAskAi?.(model.aiContext)}
          disabled={!onAskAi}
          aria-label="AI-assisted gap check: reliance readiness"
          data-testid="report-reliance-ai-action"
        >
          <span className="inline-flex items-center gap-2">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            Check for gaps
          </span>
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Button>
        <Button
          type="button"
          className="min-h-11 justify-between gap-2"
          onClick={() => onPrepareHandoff?.(model.handoffDraft)}
          disabled={handoffDisabled}
        >
          <span className="inline-flex items-center gap-2">
            {handoffPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <FileCheck2 className="h-4 w-4" aria-hidden="true" />
            )}
            {handoffCreated
              ? "Handoff created"
              : handoffPending
                ? "Creating handoff"
                : "Create review handoff"}
          </span>
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>

      {reviewHandoffState?.commentId ? (
        <div
          className="mt-3 grid gap-2 rounded-md border border-success/25 bg-success/10 px-3 py-2 text-success sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
          role="status"
          aria-label="Review handoff status"
        >
          <span className="inline-flex min-w-0 items-start gap-2 text-xs leading-5">
            <CheckCircle2
              className="mt-0.5 h-4 w-4 shrink-0"
              aria-hidden="true"
            />
            <span className="min-w-0">
              <span className="block font-semibold">
                Review handoff created
              </span>
              <span className="block text-xs text-[var(--text-secondary)]">
                Comment {reviewHandoffState.commentId}
                {reviewHandoffState.reviewStatusLabel
                  ? `; ${reviewHandoffState.reviewStatusLabel}`
                  : ""}
              </span>
            </span>
          </span>
          {onOpenComments ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="min-h-10 justify-center gap-2 justify-self-start text-success sm:justify-self-end"
              onClick={onOpenComments}
            >
              <MessageSquareText className="h-4 w-4" aria-hidden="true" />
              Open comments tab
            </Button>
          ) : null}
        </div>
      ) : null}

      {reviewHandoffState?.error ? (
        <div
          className="mt-3 rounded-md border border-error/25 bg-error/10 px-3 py-2 text-xs leading-5 text-error"
          role="alert"
        >
          <span className="inline-flex items-start gap-2">
            <AlertTriangle
              className="mt-0.5 h-4 w-4 shrink-0"
              aria-hidden="true"
            />
            <span>
              <span className="block font-semibold">Review handoff failed</span>
              <span className="block text-[var(--text-secondary)]">
                {reviewHandoffState.error}
              </span>
            </span>
          </span>
        </div>
      ) : null}
    </div>
  );
}

function ExportRecoveryBrief({
  model,
  onAskAi,
  onPrepareHandoff,
  reviewHandoffState,
}: {
  model: RelianceReadinessModel;
  onAskAi?: (context?: ReportChatLaunchContext) => void;
  onPrepareHandoff?: (draft: ReportReviewHandoffDraft) => void;
  reviewHandoffState?: ReportReviewHandoffState;
}) {
  if (
    model.exportAction.tone !== "blocked" &&
    model.exportAction.tone !== "verify"
  ) {
    return null;
  }

  const firstAction = model.decisionQueue[0];
  const handoffPending = reviewHandoffState?.isPending === true;
  const handoffCreated = Boolean(reviewHandoffState?.commentId);
  const handoffDisabled = !onPrepareHandoff || handoffPending || handoffCreated;

  return (
    <section
      aria-label="Export recovery brief"
      className="mt-3 overflow-hidden rounded-md border border-error/25 bg-[color-mix(in_srgb,var(--bg-elevated)_88%,var(--color-error)_12%)] shadow-[var(--shadow-xs)]"
      data-testid="report-export-recovery-brief"
    >
      <div className="grid gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-error/25 bg-error/10 text-error">
              <LockKeyhole className="h-4 w-4" aria-hidden="true" />
            </span>
            <Badge
              variant="secondary"
              className="border-error/20 bg-error/10 text-xs uppercase text-error"
            >
              Export locked
            </Badge>
            <Badge variant="outline" className="text-xs uppercase">
              AI-assisted recovery
            </Badge>
          </div>
          <h3 className="mt-3 text-base font-semibold leading-6 text-[var(--text-primary)]">
            Resolve export blockers before evidence leaves Praviar
          </h3>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--text-secondary)]">
            AI can summarize the gap and prepare the handoff, but export still
            requires counsel mode, backend readiness, and persisted legal
            review. This recovery plan is decision support, not legal advice or
            a legal clearance opinion.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:min-w-[18rem] lg:grid-cols-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11 justify-between gap-2 border-brand-primary/25 bg-brand-primary/8"
            onClick={() => onAskAi?.(model.aiContext)}
            disabled={!onAskAi}
            aria-label="Run recovery check with AI"
            data-testid="report-export-recovery-ai-action"
          >
            <span className="inline-flex items-center gap-2">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              AI gap check
            </span>
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="min-h-11 justify-between gap-2"
            onClick={() => onPrepareHandoff?.(model.handoffDraft)}
            disabled={handoffDisabled}
            aria-label="Prepare recovery handoff from export recovery brief"
          >
            <span className="inline-flex items-center gap-2">
              {handoffPending ? (
                <Loader2
                  className="h-3.5 w-3.5 animate-spin"
                  aria-hidden="true"
                />
              ) : (
                <FileCheck2 className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {handoffCreated
                ? "Handoff created"
                : handoffPending
                  ? "Preparing handoff"
                  : "Prepare handoff"}
            </span>
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>

      <div className="grid border-t border-error/15 bg-[color-mix(in_srgb,var(--bg-surface)_76%,transparent)] sm:grid-cols-3">
        <ExportRecoveryDatum
          label="First blocker"
          value={model.exportAction.detail ?? model.lifecycleState.blocker}
          tone={model.lifecycleState.tone}
        />
        <ExportRecoveryDatum
          label="Owner"
          value={firstAction?.owner ?? model.lifecycleState.owner}
        />
        <ExportRecoveryDatum
          label="Done when"
          value={
            firstAction?.completion ?? "Readiness checks return no P1 blockers."
          }
          tone={firstAction?.tone ?? model.statusTone}
        />
      </div>
    </section>
  );
}

function ExportRecoveryDatum({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: ReadinessTone;
  value: string;
}) {
  return (
    <div className="min-w-0 border-t border-error/10 px-3 py-2 first:border-t-0 sm:border-l sm:border-t-0 sm:first:border-l-0">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 text-xs font-semibold leading-5 text-[var(--text-primary)]",
          tone === "danger" && "text-error",
          tone === "warning" && "text-warning",
          tone === "success" && "text-success",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function ReadinessStateDatum({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: ReadinessTone;
  value: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 line-clamp-2 text-xs font-semibold leading-5 text-[var(--text-primary)]",
          tone === "danger" && "text-error",
          tone === "warning" && "text-warning",
          tone === "success" && "text-success",
        )}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}

function readinessStatusClass(tone: ReadinessTone): string {
  const base =
    "mt-4 inline-flex min-h-8 items-center gap-2 rounded-full border px-3 py-1";
  if (tone === "danger")
    return `${base} border-error/30 bg-error/10 text-error`;
  if (tone === "warning")
    return `${base} border-warning/30 bg-warning/10 text-warning`;
  if (tone === "success")
    return `${base} border-success/30 bg-success/10 text-success`;
  return `${base} border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-secondary)]`;
}

function readinessIconClass(tone: ReadinessTone): string {
  const base =
    "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border";
  if (tone === "danger")
    return `${base} border-error/25 bg-error/10 text-error`;
  if (tone === "warning")
    return `${base} border-warning/25 bg-warning/10 text-warning`;
  if (tone === "success")
    return `${base} border-success/25 bg-success/10 text-success`;
  return `${base} border-brand-primary/15 bg-brand-primary/8 text-brand-primary`;
}

function readinessQueuePriorityClass(tone: ReadinessTone): string {
  const base =
    "flex h-8 w-8 items-center justify-center rounded-md border text-xs font-bold";
  if (tone === "danger")
    return `${base} border-error/25 bg-error/10 text-error`;
  if (tone === "warning")
    return `${base} border-warning/25 bg-warning/10 text-warning`;
  if (tone === "success")
    return `${base} border-success/25 bg-success/10 text-success`;
  return `${base} border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-secondary)]`;
}
