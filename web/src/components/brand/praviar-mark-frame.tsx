import { type HTMLAttributes } from "react";

import { PraviarMark } from "@/components/icons/praviar-mark";
import { cn } from "@/lib/utils";

type PraviarMarkFrameSize = "xs" | "sm" | "md" | "lg" | "dialog" | "hero";
type PraviarMarkFrameSurface = "light" | "dark";

interface PraviarMarkFrameProps extends HTMLAttributes<HTMLSpanElement> {
  decorative?: boolean;
  label?: string;
  markClassName?: string;
  size?: PraviarMarkFrameSize;
  surface?: PraviarMarkFrameSurface;
}

const FRAME_SIZE: Record<
  PraviarMarkFrameSize,
  { markClassName?: string; markSize: number; root: string }
> = {
  xs: { markSize: 28, root: "h-9 w-9" },
  sm: { markSize: 32, root: "h-10 w-10" },
  dialog: { markSize: 32, root: "h-11 w-11" },
  md: { markSize: 40, root: "h-12 w-12" },
  lg: { markSize: 44, root: "h-14 w-14" },
  hero: {
    markClassName: "h-8 w-8 sm:h-11 sm:w-11",
    markSize: 40,
    root: "h-10 w-10 sm:h-14 sm:w-14",
  },
};

const LIGHT_SURFACE_CLASS = "praviar-brand-mark-shell";
const INVERTED_SURFACE_CLASS =
  "praviar-brand-mark-shell praviar-brand-mark-shell-dark text-[var(--surface-inverted-fg)]";

function getSurfaceClass(surface: PraviarMarkFrameSurface): string {
  return surface === "dark" ? INVERTED_SURFACE_CLASS : LIGHT_SURFACE_CLASS;
}

export function PraviarMarkFrame({
  className,
  decorative = true,
  label = "Praviar",
  markClassName,
  size = "md",
  surface = "light",
  ...props
}: PraviarMarkFrameProps) {
  const config = FRAME_SIZE[size];
  const markVariant = surface === "dark" ? "onDark" : "onLight";

  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-lg",
        config.root,
        getSurfaceClass(surface),
        className,
      )}
      data-praviar-mark-frame={surface}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? "true" : undefined}
      aria-label={decorative ? undefined : label}
      {...props}
    >
      <PraviarMark
        size={config.markSize}
        variant={markVariant}
        className={cn(config.markClassName, markClassName)}
        aria-hidden="true"
      />
    </span>
  );
}
