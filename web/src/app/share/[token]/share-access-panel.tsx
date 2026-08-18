import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  KeyRound,
  Link2Off,
  CircleDashed,
  type LucideIcon,
} from "lucide-react";
import { PraviarLockup } from "@/components/brand/praviar-lockup";
import { BRAND } from "@/marketing/content";
import { cn } from "@/lib/utils";

type ShareAccessTone = "default" | "warning" | "error";
type ShareAccessVariant = "verification" | "expired" | "not-found" | "error";
type ShareAccessStepState = "verified" | "attention" | "issue" | "pending";

interface ShareAccessPanelProps {
  variant: ShareAccessVariant;
  title: string;
  description: string;
  children?: ReactNode;
  className?: string;
  contentFirstOnMobile?: boolean;
  role?: "alert" | "region";
  showBrand?: boolean;
}

const SUPPORT_REFERENCE = "Share access check";

const VARIANT_META: Record<
  ShareAccessVariant,
  {
    icon: LucideIcon;
    tone: ShareAccessTone;
    eyebrow: string;
    steps: { label: string; detail: string }[];
  }
> = {
  verification: {
    icon: KeyRound,
    tone: "default",
    eyebrow: "Secure report access",
    steps: [
      {
        label: "Link received",
        detail:
          "No report lookup or recipient disclosure occurs until a code is requested.",
      },
      {
        label: "Recipient check required",
        detail:
          "A one-time code is submitted for delivery only to the sender-selected mailbox.",
      },
      {
        label: "Read-only after unlock",
        detail: "Opening the report does not grant workspace edit privileges.",
      },
    ],
  },
  expired: {
    icon: Clock3,
    tone: "warning",
    eyebrow: "Link no longer valid",
    steps: [
      {
        label: "Link checked",
        detail: "The access check reached Praviar successfully.",
      },
      {
        label: "Share window closed",
        detail: "The sender-managed expiry or revocation has taken effect.",
      },
      {
        label: "Fresh link required",
        detail: "Ask the sender to generate a new read-only share.",
      },
    ],
  },
  "not-found": {
    icon: Link2Off,
    tone: "warning",
    eyebrow: "Shared report unavailable",
    steps: [
      {
        label: "Link checked",
        detail: "The access check completed, but no active packet matched.",
      },
      {
        label: "Sender-managed access",
        detail: "The share may be revoked, expired, or copied incorrectly.",
      },
      {
        label: "Confirm before retrying",
        detail: "Use a fresh link from the report owner.",
      },
    ],
  },
  error: {
    icon: AlertTriangle,
    tone: "error",
    eyebrow: "Shared report unavailable",
    steps: [
      {
        label: "Access check started",
        detail: "The public link was received by the shared report surface.",
      },
      {
        label: "Temporary issue",
        detail: "The report service did not return a usable response.",
      },
      {
        label: "Retry or notify sender",
        detail: "Try again shortly, then share the access reference if needed.",
      },
    ],
  },
};

export function ShareAccessPanel({
  variant,
  title,
  description,
  children,
  className,
  contentFirstOnMobile = false,
  role = "region",
  showBrand = true,
}: ShareAccessPanelProps) {
  const meta = VARIANT_META[variant];
  const Icon = meta.icon;

  return (
    <section
      role={role}
      aria-labelledby={`share-access-${variant}-title`}
      className={cn(
        "light praviar-share-access-panel overflow-hidden rounded-lg border border-[var(--border-default)] shadow-[var(--shadow-lg)]",
        className,
      )}
      data-praviar-share-access={variant}
    >
      <div className="praviar-glass-strip border-b border-[var(--border-default)] px-5 py-5 sm:px-6">
        <div
          className={cn(
            "flex min-w-0 flex-col gap-4",
            showBrand && "sm:flex-row sm:items-start",
          )}
        >
          {showBrand ? (
            <PraviarLockup
              size="marketing"
              wordmark={BRAND.name}
              tagline={BRAND.tagline}
              className="w-full sm:w-auto sm:shrink-0"
            />
          ) : null}
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              {meta.eyebrow}
            </p>
            <h1
              id={`share-access-${variant}-title`}
              className="mt-1 type-heading-xl text-[var(--text-primary)] [overflow-wrap:anywhere]"
            >
              {title}
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
              {description}
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-0 lg:grid-cols-[0.92fr_1.08fr]">
        <div
          className={cn(
            "praviar-glass-strip border-b border-[var(--border-default)] p-5 sm:p-6 lg:border-b-0 lg:border-r",
            contentFirstOnMobile && "order-2 lg:order-1",
          )}
        >
          <div
            className={cn(
              "flex h-14 w-14 items-center justify-center rounded-lg border",
              meta.tone === "error" && "border-error/25 bg-error/10 text-error",
              meta.tone === "warning" &&
                "border-warning/25 bg-warning/10 text-warning",
              meta.tone === "default" && "border-info/25 bg-info/10 text-info",
            )}
          >
            <Icon className="h-6 w-6" aria-hidden="true" />
          </div>

          <ol className="mt-5 grid gap-3" data-praviar-share-access-steps>
            {meta.steps.map((step, index) => {
              const state =
                variant === "verification"
                  ? "pending"
                  : getShareAccessStepState(
                      meta.tone,
                      index,
                      meta.steps.length,
                    );
              return (
                <ShareAccessStep key={step.label} state={state}>
                  <span
                    className={cn(
                      "mt-0.5 flex h-5 w-5 items-center justify-center",
                      getShareAccessStepIconClass(state),
                    )}
                  >
                    {renderShareAccessStepIcon(state)}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-[var(--text-primary)]">
                      {step.label}
                    </span>
                    <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                      {step.detail}
                    </span>
                  </span>
                </ShareAccessStep>
              );
            })}
          </ol>

          <p className="mt-5 text-xs leading-5 text-[var(--text-tertiary)]">
            Public share links only expose a read-only report after access is
            checked. Full workspace actions remain behind authenticated team
            access.
          </p>
        </div>

        <div
          className={cn(
            "praviar-glass-strip border-0 p-5 sm:p-6",
            contentFirstOnMobile && "order-1 lg:order-2",
          )}
        >
          {children ?? <ShareAccessRecovery variant={variant} />}
        </div>
      </div>
    </section>
  );
}

function ShareAccessStep({
  children,
  state,
}: {
  children: ReactNode;
  state: ShareAccessStepState;
}) {
  return (
    <li
      className="praviar-glass-chip grid grid-cols-[1.5rem_minmax(0,1fr)] gap-3 rounded-lg px-3 py-2.5"
      data-praviar-share-access-step-state={state}
    >
      {children}
    </li>
  );
}

function getShareAccessStepState(
  tone: ShareAccessTone,
  index: number,
  total: number,
): ShareAccessStepState {
  const isLast = index === total - 1;

  if (tone === "error") {
    if (index === 0) return "verified";
    return index === 1 ? "issue" : "attention";
  }

  if (tone === "warning" && isLast) {
    return "attention";
  }

  return isLast ? "pending" : "verified";
}

function renderShareAccessStepIcon(state: ShareAccessStepState) {
  if (state === "issue") {
    return <AlertTriangle className="h-4 w-4" aria-hidden="true" />;
  }

  const StepIcon = state === "verified" ? CheckCircle2 : CircleDashed;
  return <StepIcon className="h-4 w-4" aria-hidden="true" />;
}

function getShareAccessStepIconClass(state: ShareAccessStepState) {
  if (state === "issue") {
    return "text-error";
  }

  if (state === "attention") {
    return "text-warning";
  }

  if (state === "verified") {
    return "text-[var(--brand-primary)]";
  }

  return "text-[var(--text-tertiary)]";
}

export function ShareAccessBody({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-sm">{children}</div>;
}

function ShareAccessRecovery({ variant }: { variant: ShareAccessVariant }) {
  const recoveryCopy: Record<
    ShareAccessVariant,
    { title: string; body: string; reference?: string }
  > = {
    verification: {
      title: "Verify the intended mailbox",
      body: "Request a one-time code. If you cannot access the selected mailbox, ask the sender to issue a grant to the correct recipient.",
    },
    expired: {
      title: "Request a fresh link",
      body: "Ask the sender to generate a new read-only link from the report workspace.",
    },
    "not-found": {
      title: "Confirm the link with the sender",
      body: "The link may have been revoked, copied incorrectly, or removed from the workspace.",
    },
    error: {
      title: "Retry or send this reference",
      body: "Try the link again shortly. If it still fails, share the access reference with the sender.",
      reference: SUPPORT_REFERENCE,
    },
  };
  const copy = recoveryCopy[variant];

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4 text-sm leading-6">
      <p className="font-semibold text-[var(--text-primary)]">{copy.title}</p>
      <p className="mt-1 text-[var(--text-secondary)]">{copy.body}</p>
      {copy.reference ? (
        <p className="praviar-code-surface mt-3 rounded-lg px-3 py-2 font-mono text-xs text-[var(--text-tertiary)]">
          {copy.reference}
        </p>
      ) : null}
    </div>
  );
}
