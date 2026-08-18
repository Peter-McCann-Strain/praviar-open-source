import {
  FileQuestion,
  Loader2,
  MessageSquare,
  Route,
  SearchCheck,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import type { ReportChatLaunchContext } from "@/components/report/chat-launch-context";
import type { ChatWorkspaceMetadata } from "@/hooks/use-report-chat";
import { cn } from "@/lib/utils";

interface ChatPanelEmptyStateProps {
  canRunLaunchAction?: boolean;
  isLaunchActionPending?: boolean;
  launchContext?: ReportChatLaunchContext | null;
  onLaunchAction?: () => void;
  onSuggestionClick: (suggestion: string) => void;
  patentId?: string;
  suggestions: string[];
  workspaceMeta?: ChatWorkspaceMetadata | null;
}

export function ChatPanelEmptyState({
  canRunLaunchAction = true,
  isLaunchActionPending = false,
  launchContext,
  onLaunchAction,
  onSuggestionClick,
  patentId,
  suggestions,
  workspaceMeta,
}: ChatPanelEmptyStateProps) {
  const promptCards = buildPromptCards(patentId, suggestions);
  const hasLaunchContext = Boolean(launchContext);
  const scopeLabel =
    workspaceMeta?.capability_label ??
    workspaceMeta?.evidence_mode ??
    "Report-grounded answers";
  const sourceLabel =
    workspaceMeta?.source_coverage ??
    workspaceMeta?.scope_label ??
    "Current report record";

  return (
    <div className="flex min-h-full flex-col justify-start gap-3">
      {!hasLaunchContext ? (
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-glass)] p-4 shadow-[var(--shadow-xs)]">
          <div className="flex items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
              <MessageSquare className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {patentId
                  ? `Patent-grounded AI review for ${patentId}`
                  : "Report-grounded AI review"}
              </p>
              <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                Ask for evidence, uncertainty, design-around leads, and counsel
                handoff questions while staying inside the governed report
                record.
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <TrustPill icon={ShieldCheck} label={scopeLabel} />
            <TrustPill icon={SearchCheck} label={sourceLabel} />
          </div>
        </div>
      ) : null}

      {launchContext ? (
        <ChatPanelLaunchContextCard
          canRunLaunchAction={canRunLaunchAction}
          compact
          isLaunchActionPending={isLaunchActionPending}
          launchContext={launchContext}
          onLaunchAction={onLaunchAction}
        />
      ) : null}

      <div
        className={cn(
          "grid gap-2",
          hasLaunchContext ? "grid-cols-1" : "sm:grid-cols-2",
        )}
        aria-label="Report AI suggested prompts"
      >
        {promptCards.map(({ icon: Icon, label, prompt, tone }) => (
          <button
            key={prompt}
            type="button"
            aria-label={prompt}
            onClick={() => onSuggestionClick(prompt)}
            className={cn(
              "group flex min-h-14 min-w-0 items-start gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70",
              "border-[var(--border-subtle)] bg-[var(--surface-card)] hover:border-[var(--border-emphasis)] hover:bg-[var(--surface-hover)]",
            )}
          >
            <span
              className={cn(
                "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
                tone === "primary" &&
                  "border-brand-primary/25 bg-brand-primary/10 text-brand-primary",
                tone === "copper" &&
                  "border-brand-secondary/30 bg-brand-secondary/10 text-[var(--text-primary)]",
                tone === "neutral" &&
                  "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-secondary)]",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-semibold text-[var(--text-primary)]">
                {label}
              </span>
              <span className="mt-1 line-clamp-3 text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                {prompt}
              </span>
            </span>
          </button>
        ))}
      </div>

      {hasLaunchContext ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <TrustPill icon={ShieldCheck} label={scopeLabel} />
          <TrustPill icon={SearchCheck} label={sourceLabel} />
        </div>
      ) : null}
    </div>
  );
}

export function ChatPanelLaunchContextCard({
  canRunLaunchAction = true,
  compact = false,
  isLaunchActionPending = false,
  launchContext,
  onLaunchAction,
}: {
  canRunLaunchAction?: boolean;
  compact?: boolean;
  isLaunchActionPending?: boolean;
  launchContext: ReportChatLaunchContext;
  onLaunchAction?: () => void;
}) {
  const statusLabel = launchContext.actionLabel ?? "Suggested task";
  const metadataItems = launchContext.metadata ?? [];
  const visibleMetadataItems = compact
    ? metadataItems.slice(0, 3)
    : metadataItems;
  const hiddenMetadataCount = compact
    ? Math.max(metadataItems.length - visibleMetadataItems.length, 0)
    : 0;

  return (
    <div
      className={cn(
        "rounded-lg border border-brand-primary/20 bg-brand-primary/5",
        compact
          ? "sticky top-0 z-10 p-3 shadow-[var(--shadow-xs)] backdrop-blur-xl"
          : "p-4",
      )}
      data-praviar-chat-launch-context
    >
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
            {launchContext.actionLabel ? "AI task context" : "Launch context"}
          </p>
          <h3 className="mt-1 text-sm font-semibold leading-6 text-[var(--text-primary)]">
            {launchContext.title}
          </h3>
        </div>
        {onLaunchAction ? (
          <button
            type="button"
            onClick={onLaunchAction}
            disabled={isLaunchActionPending}
            className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-md border border-brand-primary/25 bg-brand-primary px-3 py-1 text-xs font-semibold uppercase tracking-[0.1em] text-[var(--brand-paper)] transition-colors hover:bg-brand-primary-dim disabled:cursor-not-allowed disabled:border-[var(--border-subtle)] disabled:bg-[var(--surface-muted)] disabled:text-[var(--text-disabled)]"
            aria-label={canRunLaunchAction ? statusLabel : "Stage prompt"}
          >
            {isLaunchActionPending ? (
              <Loader2
                className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            ) : (
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {canRunLaunchAction ? statusLabel : "Stage prompt"}
          </button>
        ) : (
          <span className="inline-flex min-h-7 shrink-0 items-center rounded-md border border-brand-primary/20 bg-[var(--bg-surface)]/78 px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.1em] text-brand-primary">
            {statusLabel}
          </span>
        )}
      </div>
      <p
        className={cn(
          "mt-1 text-[var(--text-secondary)] [overflow-wrap:anywhere]",
          compact ? "line-clamp-2 text-xs leading-4" : "text-xs leading-5",
        )}
      >
        {launchContext.description}
      </p>
      {metadataItems.length ? (
        <dl
          className={cn(
            "mt-3 gap-2",
            compact ? "flex flex-wrap gap-1.5" : "grid sm:grid-cols-3",
          )}
        >
          {visibleMetadataItems.map((item) => (
            <div
              key={`${item.label}-${item.value}`}
              className={cn(
                "min-w-0 rounded-md border border-brand-primary/15 bg-[var(--bg-surface)]/78",
                compact ? "px-2 py-1" : "px-3 py-2",
              )}
            >
              <dt
                className={cn(
                  "truncate font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]",
                  compact ? "text-xs" : "text-xs",
                )}
              >
                {item.label}
              </dt>
              <dd
                className={cn(
                  "truncate font-semibold text-[var(--text-primary)]",
                  compact ? "mt-0.5 max-w-[8rem] text-xs" : "mt-1 text-xs",
                )}
              >
                {item.value}
              </dd>
            </div>
          ))}
          {hiddenMetadataCount > 0 ? (
            <div className="min-w-0 rounded-md border border-brand-primary/15 bg-[var(--bg-surface)]/78 px-2 py-1">
              <dt className="sr-only">Additional context</dt>
              <dd className="text-xs font-semibold text-[var(--text-primary)]">
                +{hiddenMetadataCount} more
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </div>
  );
}

type PromptCardTone = "primary" | "copper" | "neutral";

interface PromptCard {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
  prompt: string;
  tone: PromptCardTone;
}

function buildPromptCards(
  patentId: string | undefined,
  suggestions: string[],
): PromptCard[] {
  const [first, second, third, fourth] = suggestions;

  if (patentId) {
    return [
      {
        icon: SearchCheck,
        label: "Claim evidence",
        prompt: first ?? "What are the key claims in this patent?",
        tone: "primary",
      },
      {
        icon: ShieldCheck,
        label: "Risk posture",
        prompt: second ?? "What is the infringement risk for our compound?",
        tone: "copper",
      },
      {
        icon: Route,
        label: "Design-around",
        prompt: third ?? "Are there design-around strategies?",
        tone: "neutral",
      },
      {
        icon: FileQuestion,
        label: "Counsel handoff",
        prompt:
          fourth ?? "What questions should counsel review for this patent?",
        tone: "neutral",
      },
    ];
  }

  return [
    {
      icon: ShieldCheck,
      label: "Material risks",
      prompt: first ?? "Which patents pose the highest risk?",
      tone: "primary",
    },
    {
      icon: SearchCheck,
      label: "Evidence basis",
      prompt: second ?? "Summarize the key findings",
      tone: "copper",
    },
    {
      icon: Route,
      label: "Design-around",
      prompt: third ?? "What design-around strategies are available?",
      tone: "neutral",
    },
    {
      icon: FileQuestion,
      label: "Counsel handoff",
      prompt: fourth ?? "Compare the blocking patents",
      tone: "neutral",
    },
  ];
}

function TrustPill({
  icon: Icon,
  label,
}: {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
}) {
  return (
    <span className="inline-flex min-h-10 min-w-0 items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
      <Icon
        className="h-3.5 w-3.5 shrink-0 text-brand-primary"
        aria-hidden="true"
      />
      <span className="min-w-0 truncate">{label}</span>
    </span>
  );
}
