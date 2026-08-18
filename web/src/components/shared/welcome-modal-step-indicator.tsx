import { cn } from "@/lib/utils";

interface WelcomeModalStepIndicatorProps {
  current: number;
  onStepClick: (step: number) => void;
  total: number;
}

export function WelcomeModalStepIndicator({
  current,
  onStepClick,
  total,
}: WelcomeModalStepIndicatorProps) {
  return (
    <div className="flex items-center justify-center gap-2">
      {Array.from({ length: total }).map((_, index) => (
        <button
          key={index}
          onClick={() => onStepClick(index)}
          aria-label={`Go to step ${index + 1}`}
          aria-current={index === current ? "step" : undefined}
          className="group flex h-11 w-11 items-center justify-center rounded-full transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface-muted)]"
        >
          <span
            aria-hidden="true"
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold transition-all duration-200",
              index === current
                ? "border-brand-primary bg-brand-primary text-[var(--brand-paper)] shadow-[var(--shadow-xs)]"
                : "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-tertiary)] group-hover:border-brand-primary/40 group-hover:text-brand-primary",
            )}
          >
            {index + 1}
          </span>
        </button>
      ))}
    </div>
  );
}
