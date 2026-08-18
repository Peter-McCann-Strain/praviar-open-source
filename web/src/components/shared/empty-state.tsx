import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ShieldCheck } from "lucide-react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface EmptyStateAction {
  label: string;
  href?: string;
  onClick?: () => void;
}

interface EmptyStateExample {
  label: string;
  value: string;
}

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: EmptyStateAction;
  contextItems?: string[];
  examples?: EmptyStateExample[];
  className?: string;
  headingLevel?: 1 | 2 | 3;
  onExampleClick?: (value: string) => void;
  surface?: "field" | "embedded";
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  contextItems,
  examples,
  className,
  headingLevel = 3,
  onExampleClick,
  surface = "field",
}: EmptyStateProps) {
  const Heading = `h${headingLevel}` as "h1" | "h2" | "h3";

  return (
    <section
      aria-label={title}
      className={cn(
        surface === "field"
          ? "praviar-operational-field relative isolate overflow-hidden rounded-lg px-5 py-10 text-center sm:px-6"
          : "relative isolate overflow-hidden px-5 py-10 text-center sm:px-6",
        className,
      )}
    >
      <div
        aria-hidden="true"
        className="praviar-evidence-field-pattern pointer-events-none absolute inset-0 -z-10"
      />

      <PraviarMarkFrame className="mx-auto" size="lg" />

      <div className="mx-auto mt-3 flex h-10 w-10 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10">
        <Icon className="h-5 w-5 text-brand-primary" aria-hidden="true" />
      </div>

      <Heading className="mt-4 type-heading-md text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {title}
      </Heading>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--text-secondary)]">
        {description}
      </p>

      {contextItems && contextItems.length > 0 ? (
        <div className="mx-auto mt-5 grid max-w-2xl gap-2 sm:grid-cols-3">
          {contextItems.map((item) => (
            <div
              key={item}
              className="praviar-glass-chip flex min-w-0 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs text-[var(--text-secondary)]"
            >
              <ShieldCheck
                className="h-3.5 w-3.5 shrink-0 text-brand-primary"
                aria-hidden="true"
              />
              <span className="min-w-0">{item}</span>
            </div>
          ))}
        </div>
      ) : null}

      {action &&
        (action.href ? (
          <Button asChild className="mt-6 min-h-11 gap-2">
            <Link href={action.href}>{action.label}</Link>
          </Button>
        ) : (
          <Button
            type="button"
            className="mt-6 min-h-11 gap-2"
            onClick={action.onClick}
          >
            {action.label}
          </Button>
        ))}

      {examples && examples.length > 0 && (
        <div className="mt-6 space-y-2">
          <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">
            Try an example
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {examples.map((example) => (
              <button
                key={example.value}
                type="button"
                onClick={() => onExampleClick?.(example.value)}
                className="inline-flex min-h-11 items-center rounded-md border border-[var(--border-default)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:border-brand-primary/30 hover:bg-brand-primary/5 hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 sm:py-1.5"
              >
                {example.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
