import { Loader2, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ShareAccessBody, ShareAccessPanel } from "./share-access-panel";

type ShareStatusVariant = "error" | "expired" | "not-found";

interface ShareStatusStateProps {
  variant: ShareStatusVariant;
  description?: string;
  className?: string;
  showBrand?: boolean;
  onRetry?: () => void;
  retrying?: boolean;
}

const SHARE_STATUS_COPY: Record<
  ShareStatusVariant,
  { title: string; description: string }
> = {
  error: {
    title: "Shared report temporarily unavailable",
    description:
      "We could not load this read-only report view right now. Ask the sender to confirm the link, or try again shortly.",
  },
  expired: {
    title: "Share link expired",
    description:
      "This read-only link is no longer valid. Ask the sender to generate a fresh link from the report workspace.",
  },
  "not-found": {
    title: "Report not available",
    description:
      "This shared report could not be found. The link may have expired, been revoked, or been copied incorrectly.",
  },
};

export function ShareStatusState({
  variant,
  description,
  className,
  showBrand,
  onRetry,
  retrying = false,
}: ShareStatusStateProps) {
  const copy = SHARE_STATUS_COPY[variant];

  return (
    <ShareAccessPanel
      variant={variant}
      title={copy.title}
      description={description ?? copy.description}
      role="alert"
      className={cn(className)}
      showBrand={showBrand}
    >
      {variant === "error" && onRetry ? (
        <ShareAccessBody>
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4 text-sm leading-6">
            <p className="font-semibold text-[var(--text-primary)]">
              Retry or share this reference
            </p>
            <p className="mt-1 text-[var(--text-secondary)]">
              Retry the access check now. If it still fails, give the generic
              reference below to the sender or your deployment operator. Ask the
              sender to replace the link when needed.
            </p>
            <p className="praviar-code-surface mt-3 rounded-lg px-3 py-2 font-mono text-xs text-[var(--text-tertiary)]">
              Share access check
            </p>
            <div className="mt-4">
              <Button
                type="button"
                className="min-h-11 gap-2"
                onClick={onRetry}
                disabled={retrying}
              >
                {retrying ? (
                  <Loader2
                    aria-hidden="true"
                    className="h-4 w-4 animate-spin motion-reduce:animate-none"
                  />
                ) : (
                  <RotateCw aria-hidden="true" className="h-4 w-4" />
                )}
                {retrying ? "Checking link..." : "Retry access check"}
              </Button>
            </div>
            <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
              Share only this generic reference; do not send the private share
              token through an unverified channel.
            </p>
          </div>
        </ShareAccessBody>
      ) : undefined}
    </ShareAccessPanel>
  );
}
