import { CheckCircle2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export interface AIRecoveryBriefProps {
  ariaLabel?: string;
  className?: string;
  items: string[];
  note?: string;
  title?: string;
}

export function AIRecoveryBrief({
  ariaLabel,
  className,
  items,
  note,
  title = "AI recovery brief",
}: AIRecoveryBriefProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section
      aria-label={ariaLabel ?? title}
      className={cn(
        "mt-4 rounded-lg border border-brand-primary/15 bg-brand-primary/5 p-3",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <Sparkles
          className="h-4 w-4 shrink-0 text-brand-primary"
          aria-hidden="true"
        />
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
          {title}
        </p>
      </div>
      <ul className="mt-2 grid gap-2">
        {items.map((item) => (
          <li key={item} className="flex min-w-0 gap-2 text-sm leading-5">
            <CheckCircle2
              className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-primary"
              aria-hidden="true"
            />
            <span className="min-w-0 text-[var(--text-secondary)]">{item}</span>
          </li>
        ))}
      </ul>
      {note ? (
        <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
          {note}
        </p>
      ) : null}
    </section>
  );
}
