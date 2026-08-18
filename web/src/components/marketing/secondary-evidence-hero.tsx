import Image from "next/image";
import type { ReactNode } from "react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { cn } from "@/lib/utils";

interface HeroProofItem {
  label: string;
  value: string;
}

interface HeroVisualItem {
  label: string;
  value: string;
}

interface SecondaryEvidenceHeroProps {
  eyebrow: string;
  title: string;
  description: string;
  proofItems?: HeroProofItem[];
  actions?: ReactNode;
  visualEyebrow: string;
  visualTitle: string;
  visualItems: HeroVisualItem[];
  visualFooter: string;
  visualSrc?: string;
  className?: string;
  fieldClassName?: string;
}

export function SecondaryEvidenceHero({
  eyebrow,
  title,
  description,
  proofItems = [],
  actions,
  visualEyebrow,
  visualTitle,
  visualItems,
  visualFooter,
  visualSrc = "/brand/visuals/praviar-sample-report-field.svg",
  className,
  fieldClassName = "praviar-secondary-hero-field",
}: SecondaryEvidenceHeroProps) {
  return (
    <section
      className={cn(
        fieldClassName,
        "px-4 pb-12 pt-10 sm:px-6 md:pb-18 md:pt-16",
        className,
      )}
    >
      <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[0.94fr_1.06fr] lg:items-center">
        <div className="max-w-3xl space-y-5">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)] sm:text-sm">
            {eyebrow}
          </p>
          <h1 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)] sm:text-5xl md:text-6xl">
            {title}
          </h1>
          <p className="max-w-2xl text-base leading-7 text-[var(--text-secondary)] sm:text-lg sm:leading-8">
            {description}
          </p>
          {actions ? (
            <div className="flex flex-col gap-3 sm:flex-row">{actions}</div>
          ) : null}
        </div>

        <div className="relative min-h-[300px] overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--surface-inverted)] shadow-[var(--shadow-lg)] sm:min-h-[360px]">
          <Image
            src={visualSrc}
            alt=""
            fill
            loading="eager"
            sizes="(min-width: 1024px) 48vw, 100vw"
            className="object-cover opacity-75"
            unoptimized
          />
          <div className="praviar-ink-evidence-overlay absolute inset-0" />
          <div className="relative flex min-h-[300px] flex-col justify-between p-5 text-[var(--surface-inverted-fg)] sm:min-h-[360px] sm:p-6">
            <div className="space-y-5">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <PraviarMarkFrame surface="dark" size="sm" />
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--surface-inverted-fg-subtle)]">
                    {visualEyebrow}
                  </p>
                </div>
                <span className="praviar-ink-pill rounded-full px-3 py-1 text-xs font-semibold uppercase text-[var(--surface-inverted-fg-muted)]">
                  FTO
                </span>
              </div>

              <div className="max-w-md space-y-3">
                <h2 className="text-2xl font-semibold leading-tight text-[var(--surface-inverted-fg)] sm:text-3xl">
                  {visualTitle}
                </h2>
                <div className="praviar-ink-glass praviar-ink-divide rounded-lg">
                  {visualItems.map((item) => (
                    <div
                      key={item.label}
                      className="grid gap-1 px-4 py-3 sm:grid-cols-[7rem_1fr] sm:items-center"
                    >
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--surface-inverted-fg-subtle)]">
                        {item.label}
                      </p>
                      <p className="text-sm font-medium text-[var(--surface-inverted-fg)]">
                        {item.value}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
              {proofItems.length > 0 ? (
                <div className="grid gap-2 sm:grid-cols-3">
                  {proofItems.map((item) => (
                    <div
                      key={item.label}
                      className="praviar-ink-chip rounded-lg px-3 py-2"
                    >
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--surface-inverted-fg-subtle)]">
                        {item.label}
                      </p>
                      <p className="mt-1 text-sm font-semibold text-[var(--surface-inverted-fg)]">
                        {item.value}
                      </p>
                    </div>
                  ))}
                </div>
              ) : null}
              <p className="text-xs leading-5 text-[var(--surface-inverted-fg-subtle)] sm:max-w-[14rem] sm:text-right">
                {visualFooter}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
