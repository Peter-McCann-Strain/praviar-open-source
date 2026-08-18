"use client";

import { useRef } from "react";

interface MobileLegalDocumentNavProps {
  sections: Array<{
    id: string;
    title: string;
  }>;
}

export function MobileLegalDocumentNav({
  sections,
}: MobileLegalDocumentNavProps) {
  const disclosureRef = useRef<HTMLDetailsElement>(null);

  return (
    <details
      ref={disclosureRef}
      className="group praviar-glass-panel-soft rounded-lg !bg-[var(--bg-surface)] p-4 shadow-[0_14px_34px_rgba(11,31,36,0.16)] ring-1 ring-[var(--border-subtle)]"
      data-testid="mobile-legal-section-nav"
    >
      <summary
        role="button"
        aria-controls="mobile-legal-document-section-links"
        aria-label="Jump to a section"
        className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold text-[var(--text-primary)] marker:content-none"
      >
        <span>Jump to a section</span>
        <span aria-hidden="true">
          <span className="group-open:hidden">＋</span>
          <span className="hidden group-open:inline">−</span>
        </span>
      </summary>
      <nav
        id="mobile-legal-document-section-links"
        aria-label="Mobile legal document sections"
        className="mt-3 max-h-[min(70dvh,32rem)] overflow-y-auto overscroll-contain pr-1"
      >
        <ol className="space-y-1 text-sm">
          {sections.map((section) => (
            <li key={section.id}>
              <a
                href={`#mobile-${section.id}`}
                onClick={(event) => {
                  event.preventDefault();
                  const destination = document.getElementById(
                    `mobile-${section.id}`,
                  );
                  if (destination instanceof HTMLDetailsElement) {
                    destination.open = true;
                    disclosureRef.current?.removeAttribute("open");
                    window.history.pushState(null, "", `#mobile-${section.id}`);
                    destination.scrollIntoView?.({ block: "start" });
                    const focusDestination = () => {
                      destination
                        .querySelector<HTMLElement>("summary")
                        ?.focus({ preventScroll: true });
                    };
                    if (typeof window.requestAnimationFrame === "function") {
                      window.requestAnimationFrame(focusDestination);
                    } else {
                      focusDestination();
                    }
                  }
                }}
                className="flex min-h-11 items-center rounded-md px-3 leading-5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
              >
                {section.title}
              </a>
            </li>
          ))}
        </ol>
      </nav>
    </details>
  );
}
