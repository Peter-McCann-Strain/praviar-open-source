import { type HTMLAttributes } from "react";
import { PraviarMark } from "@/components/icons/praviar-mark";
import { cn } from "@/lib/utils";

type PraviarLockupSurface = "light" | "dark";
type PraviarLockupSize = "sidebar" | "topbar" | "marketing" | "hero";

interface PraviarLockupProps extends HTMLAttributes<HTMLSpanElement> {
  decorative?: boolean;
  markLabel?: string;
  showWordmark?: boolean;
  size?: PraviarLockupSize;
  surface?: PraviarLockupSurface;
  tagline?: string;
  wordmark?: string;
  wordmarkClassName?: string;
}

const LOCKUP_SIZE_CLASS: Record<
  PraviarLockupSize,
  {
    root: string;
    markShell: string;
    markClassName: string;
    markSize: number;
    stack: string;
    tagline: string;
    wordmark: string;
  }
> = {
  sidebar: {
    root: "gap-3",
    markShell:
      "h-11 w-11 rounded-lg transition-transform duration-200 group-hover:scale-[1.02]",
    markClassName: "",
    markSize: 44,
    stack: "",
    tagline: "hidden",
    wordmark:
      "[font-family:var(--font-newsreader)] text-2xl font-semibold leading-none tracking-[0.01em]",
  },
  topbar: {
    root: "gap-2",
    markShell: "h-9 w-9 rounded-lg",
    markClassName: "",
    markSize: 36,
    stack: "",
    tagline: "hidden",
    wordmark:
      "[font-family:var(--font-newsreader)] text-xl font-semibold leading-none tracking-[0.01em] max-[360px]:hidden",
  },
  marketing: {
    root: "gap-3",
    markShell: "h-11 w-11 rounded-lg",
    markClassName: "",
    markSize: 44,
    stack: "flex-col",
    tagline: "text-xs font-semibold uppercase text-[var(--text-tertiary)]",
    wordmark:
      "[font-family:var(--font-newsreader)] text-xl font-semibold leading-none tracking-[0.01em]",
  },
  hero: {
    root: "gap-3 sm:gap-4",
    markShell: "h-14 w-14 rounded-lg sm:h-16 sm:w-16",
    markClassName: "h-14 w-14 sm:h-16 sm:w-16",
    markSize: 64,
    stack: "flex-col",
    tagline:
      "mt-1 text-xs font-semibold uppercase text-[var(--brand-primary)] sm:text-sm",
    wordmark:
      "[font-family:var(--font-newsreader)] text-3xl font-semibold leading-none tracking-[0.01em] sm:text-4xl",
  },
};

export function PraviarLockup({
  className,
  decorative = false,
  markLabel,
  showWordmark = true,
  size = "topbar",
  surface = "light",
  tagline,
  wordmark = "Praviar",
  wordmarkClassName,
  ...props
}: PraviarLockupProps) {
  const config = LOCKUP_SIZE_CLASS[size];
  const markVariant = surface === "dark" ? "onDark" : "onLight";
  const markOnlyAccessible = !showWordmark && !decorative;
  const wordmarkTone =
    surface === "dark"
      ? "text-[var(--surface-inverted-fg)]"
      : "text-[var(--text-primary)]";

  return (
    <span
      className={cn("inline-flex min-w-0 items-center", config.root, className)}
      data-praviar-lockup="canonical"
      role={markOnlyAccessible ? "img" : undefined}
      aria-label={markOnlyAccessible ? (markLabel ?? wordmark) : undefined}
      aria-hidden={!showWordmark && decorative ? "true" : undefined}
      translate="no"
      {...props}
    >
      <span
        className={cn(
          "praviar-lockup-mark-shell flex shrink-0 items-center justify-center",
          config.markShell,
        )}
        aria-hidden="true"
      >
        <PraviarMark
          size={config.markSize}
          variant={markVariant}
          className={config.markClassName}
          aria-hidden="true"
        />
      </span>
      {showWordmark && (
        <span className={cn("flex min-w-0", config.stack)}>
          <span
            className={cn(
              "min-w-0 truncate",
              config.wordmark,
              wordmarkTone,
              wordmarkClassName,
            )}
            data-praviar-wordmark
          >
            {wordmark}
          </span>
          {tagline && (
            <span className={config.tagline} data-praviar-lockup-tagline>
              {tagline}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
