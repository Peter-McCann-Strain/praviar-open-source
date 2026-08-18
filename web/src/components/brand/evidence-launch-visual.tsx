import { cn } from "@/lib/utils";

interface EvidenceLaunchVisualProps {
  className?: string;
  compact?: boolean;
  label?: string;
}

export function EvidenceLaunchVisual({
  className,
  compact = false,
  label = "Evidence launch map",
}: EvidenceLaunchVisualProps) {
  return (
    <figure
      aria-label={label}
      className={cn(
        "relative isolate overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)]",
        compact ? "min-h-[168px]" : "min-h-[224px]",
        className,
      )}
      data-praviar-visual="evidence-launch"
    >
      <svg
        aria-hidden="true"
        className="absolute inset-0 h-full w-full"
        fill="none"
        viewBox="0 0 640 360"
      >
        <rect
          width="640"
          height="360"
          fill="var(--surface-muted)"
          opacity="0.62"
        />
        <path
          d="M48 76H592M48 132H592M48 188H592M48 244H592M48 300H592M104 44V316M184 44V316M264 44V316M344 44V316M424 44V316M504 44V316"
          stroke="var(--border-subtle)"
          strokeOpacity="0.54"
          strokeWidth="1"
        />

        <g opacity="0.96">
          <path
            d="M78 82H186C196 82 204 90 204 100V178C204 188 196 196 186 196H78C68 196 60 188 60 178V100C60 90 68 82 78 82Z"
            fill="var(--surface-card)"
            stroke="var(--brand-primary)"
            strokeOpacity="0.84"
            strokeWidth="2"
          />
          <path
            d="M82 112H156M82 136H180M82 160H142"
            stroke="var(--brand-primary)"
            strokeLinecap="round"
            strokeOpacity="0.46"
            strokeWidth="7"
          />
          <rect
            x="82"
            y="176"
            width="44"
            height="12"
            rx="6"
            fill="var(--color-success)"
            opacity="0.46"
          />
          <rect
            x="134"
            y="176"
            width="44"
            height="12"
            rx="6"
            fill="var(--brand-primary)"
            opacity="0.42"
          />
          <circle cx="78" cy="82" r="6" fill="var(--brand-primary)" />
          <circle cx="204" cy="130" r="6" fill="var(--color-error)" />
          <circle cx="60" cy="178" r="6" fill="var(--color-success)" />
        </g>

        <g strokeLinecap="round" strokeWidth="3">
          <path
            d="M214 124C250 116 278 124 306 148"
            stroke="var(--brand-primary)"
            strokeOpacity="0.7"
          />
          <path
            d="M214 168C252 194 280 199 318 188"
            stroke="var(--color-success)"
            strokeOpacity="0.72"
          />
          <path
            d="M202 101C247 77 290 82 334 118"
            stroke="var(--color-info)"
            strokeOpacity="0.44"
          />
        </g>

        <g transform="translate(282 95)">
          <rect
            width="132"
            height="120"
            rx="14"
            fill="var(--surface-card)"
            stroke="var(--border-emphasis)"
            strokeOpacity="0.62"
            strokeWidth="2"
          />
          <rect
            x="16"
            y="18"
            width="100"
            height="18"
            rx="9"
            fill="var(--bg-base)"
            opacity="0.8"
          />
          <rect
            x="16"
            y="50"
            width="58"
            height="14"
            rx="7"
            fill="var(--brand-primary)"
            opacity="0.92"
          />
          <rect
            x="82"
            y="50"
            width="34"
            height="14"
            rx="7"
            fill="var(--color-error)"
            opacity="0.84"
          />
          <rect
            x="16"
            y="78"
            width="84"
            height="14"
            rx="7"
            fill="var(--color-success)"
            opacity="0.82"
          />
          <circle cx="106" cy="85" r="6" fill="var(--brand-primary)" />
          <path
            d="M25 102H62M74 102H108"
            stroke="var(--text-tertiary)"
            strokeLinecap="round"
            strokeOpacity="0.42"
            strokeWidth="5"
          />
        </g>

        <g transform="translate(454 70)">
          <rect
            width="124"
            height="158"
            rx="10"
            fill="var(--surface-card)"
            stroke="var(--border-default)"
            strokeWidth="2"
          />
          <path
            d="M18 34H93M18 59H106M18 84H83M18 109H101"
            stroke="var(--text-tertiary)"
            strokeOpacity="0.34"
            strokeLinecap="round"
            strokeWidth="7"
          />
          <rect
            x="18"
            y="122"
            width="40"
            height="14"
            rx="7"
            fill="var(--color-warning)"
            opacity="0.42"
          />
          <rect
            x="66"
            y="122"
            width="40"
            height="14"
            rx="7"
            fill="var(--brand-primary)"
            opacity="0.34"
          />
        </g>

        <g strokeLinecap="round" strokeWidth="3">
          <path
            d="M404 156C420 142 436 130 454 120"
            stroke="var(--brand-primary)"
            strokeOpacity="0.68"
          />
          <path
            d="M398 186C418 194 436 197 454 196"
            stroke="var(--color-error)"
            strokeOpacity="0.62"
          />
        </g>

        <g transform="translate(86 252)">
          <rect
            width="468"
            height="54"
            rx="12"
            fill="var(--bg-base)"
            opacity="0.48"
          />
          <circle cx="42" cy="27" r="10" fill="var(--brand-primary)" />
          <path
            d="M72 27H168M198 27H294M324 27H426"
            stroke="var(--border-emphasis)"
            strokeLinecap="round"
            strokeOpacity="0.58"
            strokeWidth="8"
          />
          <circle cx="184" cy="27" r="6" fill="var(--color-success)" />
          <circle cx="310" cy="27" r="6" fill="var(--color-error)" />
          <circle cx="442" cy="27" r="6" fill="var(--color-success)" />
        </g>
      </svg>
    </figure>
  );
}
