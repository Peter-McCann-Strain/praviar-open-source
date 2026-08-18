import type { ReactNode } from "react";
import { PraviarMark } from "@/components/icons/praviar-mark";
import { MobileLegalDocumentNav } from "@/components/marketing/mobile-legal-document-nav";

export interface LegalDocumentSection {
  id: string;
  title: string;
  children: ReactNode;
}

export interface LegalDocumentHighlight {
  label: string;
  value: string;
}

interface LegalDocumentPageProps {
  documentLabel: string;
  title: string;
  description: string;
  lastUpdated: string;
  primaryActionHref: string;
  primaryActionLabel: string;
  postureTitle: string;
  postureNote: string;
  highlights: LegalDocumentHighlight[];
  sections: LegalDocumentSection[];
}

export function LegalDocumentPage({
  documentLabel,
  title,
  description,
  lastUpdated,
  primaryActionHref,
  primaryActionLabel,
  postureTitle,
  postureNote,
  highlights,
  sections,
}: LegalDocumentPageProps) {
  return (
    <div className="overflow-x-clip">
      <section
        id="legal-document-top"
        className="praviar-legal-hero-field border-b border-[var(--border-default)]"
        aria-labelledby="legal-document-title"
      >
        <div className="mx-auto grid max-w-7xl gap-8 px-4 py-12 sm:px-6 sm:py-16 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-end">
          <div className="max-w-3xl">
            <div className="mb-6 flex items-center gap-3 text-[var(--brand-primary)]">
              <span className="flex h-11 w-11 items-center justify-center">
                <PraviarMark
                  className="h-9 w-9"
                  variant="onLight"
                  aria-hidden="true"
                />
              </span>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--text-tertiary)]">
                {documentLabel}
              </p>
            </div>

            <h1
              id="legal-document-title"
              className="max-w-3xl text-4xl font-semibold leading-tight text-[var(--text-primary)] sm:text-5xl"
            >
              {title}
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-[var(--text-secondary)] sm:text-lg sm:leading-8">
              {description}
            </p>

            <div className="mt-7 flex flex-wrap gap-3 text-sm text-[var(--text-secondary)]">
              <span className="praviar-glass-pill inline-flex min-h-10 items-center rounded-lg px-3 font-medium">
                Last updated: {lastUpdated}
              </span>
              <a
                href={primaryActionHref}
                className="praviar-glass-pill inline-flex min-h-11 items-center rounded-lg px-4 font-medium text-[var(--brand-primary)] transition-colors hover:border-[var(--brand-primary)]"
              >
                {primaryActionLabel}
              </a>
            </div>
          </div>

          <aside
            className="praviar-glass-panel rounded-lg p-5"
            aria-label={`${title} overview`}
          >
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              {postureTitle}
            </p>
            <dl className="mt-5 space-y-4">
              {highlights.map((item) => (
                <div
                  key={item.label}
                  className="border-t border-[var(--border-subtle)] pt-4 first:border-t-0 first:pt-0"
                >
                  <dt className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    {item.label}
                  </dt>
                  <dd className="mt-1 text-sm leading-6 text-[var(--text-primary)]">
                    {item.value}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3 text-xs leading-5 text-[var(--text-secondary)]">
              {postureNote}
            </p>
          </aside>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-6 lg:grid-cols-[260px_minmax(0,1fr)] lg:py-14">
        <aside
          className="sticky top-20 z-20 self-start lg:top-28"
          data-testid="legal-document-section-nav-shell"
        >
          <div className="lg:hidden">
            <MobileLegalDocumentNav
              sections={sections.map(({ id, title: sectionTitle }) => ({
                id,
                title: sectionTitle,
              }))}
            />
          </div>
          <nav
            aria-label="Legal document sections"
            className="praviar-glass-panel-soft hidden rounded-lg p-4 lg:block lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              Sections
            </p>
            <ol className="mt-3 space-y-1 text-sm">
              {sections.map((section) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    className="flex min-h-11 items-center rounded-md px-3 leading-5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                  >
                    {section.title}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        </aside>

        <article
          data-testid="mobile-legal-document"
          className="praviar-glass-panel min-w-0 rounded-lg p-3 text-base leading-7 text-[var(--text-secondary)] [overflow-wrap:anywhere] sm:p-5 lg:hidden print:hidden"
        >
          <div className="space-y-3">
            {sections.map((section, index) => (
              <details
                key={section.id}
                id={`mobile-${section.id}`}
                className="group scroll-mt-40 rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_78%,transparent)] px-4 py-2"
                open={index === 0}
              >
                <summary
                  role="button"
                  aria-controls={`mobile-${section.id}-content`}
                  className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 font-semibold leading-6 text-[var(--text-primary)] marker:content-none"
                >
                  <span>{section.title}</span>
                  <span
                    className="shrink-0 text-[var(--text-tertiary)]"
                    aria-hidden="true"
                  >
                    <span className="group-open:hidden">＋</span>
                    <span className="hidden group-open:inline">−</span>
                  </span>
                </summary>
                <div
                  id={`mobile-${section.id}-content`}
                  className="space-y-4 border-t border-[var(--border-subtle)] pb-3 pt-4"
                >
                  {section.children}
                </div>
              </details>
            ))}
            <a
              href="#legal-document-top"
              className="inline-flex min-h-11 items-center rounded-md px-3 text-sm font-medium text-[var(--brand-primary)] underline decoration-[color:rgba(var(--brand-primary-rgb),0.35)] underline-offset-4 hover:decoration-[var(--brand-primary)]"
            >
              Back to top
            </a>
          </div>
        </article>

        <article
          data-testid="legal-document"
          className="praviar-glass-panel hidden min-w-0 rounded-lg px-5 py-7 text-base leading-7 text-[var(--text-secondary)] [overflow-wrap:anywhere] sm:px-8 sm:py-9 lg:block print:block"
        >
          <div className="mx-auto max-w-[72ch] space-y-10">
            {sections.map((section) => (
              <section
                key={section.id}
                id={section.id}
                className="scroll-mt-28"
              >
                <h2 className="text-2xl font-semibold leading-tight text-[var(--text-primary)]">
                  {section.title}
                </h2>
                <div className="mt-4 space-y-4">{section.children}</div>
              </section>
            ))}
          </div>
        </article>
      </section>
    </div>
  );
}
