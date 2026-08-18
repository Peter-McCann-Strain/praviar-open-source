import { forwardRef, type SVGProps } from "react";
import markData from "./praviar-mark-data.json";

type PraviarMarkVariant = "color" | "onLight" | "onDark";

interface PraviarMarkProps extends SVGProps<SVGSVGElement> {
  size?: number | string;
  variant?: PraviarMarkVariant;
}

const markBandPaths = markData.paths.bands as [string, string, string, string];

export const PRAVIAR_MARK_ID = markData.id;
export const PRAVIAR_MARK_VIEWBOX = markData.viewBox;
export const PRAVIAR_MARK_TILE_PATH = markData.paths.tile;
export const PRAVIAR_MARK_INK_PATH = markData.paths.ink;
export const PRAVIAR_MARK_BAND_PATHS = markBandPaths;

export const PRAVIAR_MARK_COLOR_FILLS = {
  paper: `var(--praviar-mark-paper, ${markData.palette.paper})`,
  ink: `var(--praviar-mark-ink, ${markData.palette.ink})`,
  mint: `var(--praviar-mark-band-2, ${markData.palette.mint})`,
  teal: `var(--praviar-mark-band-1, ${markData.palette.teal})`,
  copper: `var(--praviar-mark-copper, ${markData.palette.copper})`,
  softMint: `var(--praviar-mark-soft-mint, ${markData.palette.softMint})`,
} as const;

export const PRAVIAR_MARK_ON_LIGHT_FILLS = {
  paper: markData.palette.paper,
  ink: markData.palette.ink,
  mint: markData.palette.mint,
  teal: markData.palette.teal,
  copper: markData.palette.copper,
  softMint: markData.palette.softMint,
} as const;

export const PRAVIAR_MARK_ON_DARK_FILLS = PRAVIAR_MARK_ON_LIGHT_FILLS;

export const PRAVIAR_MARK_ON_LIGHT_OUTLINE = markData.outline.onLight;

export const PraviarMark = forwardRef<SVGSVGElement, PraviarMarkProps>(
  ({ size = 24, className, variant = "color", ...props }, ref) => {
    const fills = getPraviarMarkFills(variant);

    return (
      <svg
        ref={ref}
        width={size}
        height={size}
        viewBox={PRAVIAR_MARK_VIEWBOX}
        className={className}
        data-praviar-mark={PRAVIAR_MARK_ID}
        aria-hidden="true"
        {...props}
      >
        <path
          d={PRAVIAR_MARK_TILE_PATH}
          fill={fills.paper}
          stroke={
            variant === "onLight" ? PRAVIAR_MARK_ON_LIGHT_OUTLINE : "none"
          }
          strokeWidth={variant === "onLight" ? 4 : 0}
        />
        <path d={PRAVIAR_MARK_INK_PATH} fill={fills.ink} />
        <path d={PRAVIAR_MARK_BAND_PATHS[0]} fill={fills.mint} />
        <path d={PRAVIAR_MARK_BAND_PATHS[1]} fill={fills.teal} />
        <path d={PRAVIAR_MARK_BAND_PATHS[2]} fill={fills.copper} />
        <path d={PRAVIAR_MARK_BAND_PATHS[3]} fill={fills.softMint} />
      </svg>
    );
  },
);

PraviarMark.displayName = "PraviarMark";

function getPraviarMarkFills(variant: PraviarMarkVariant) {
  if (variant === "onLight") {
    return PRAVIAR_MARK_ON_LIGHT_FILLS;
  }

  if (variant === "onDark") {
    return PRAVIAR_MARK_ON_DARK_FILLS;
  }

  return PRAVIAR_MARK_COLOR_FILLS;
}

export default PraviarMark;
