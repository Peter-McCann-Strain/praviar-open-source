"use client";

import { useEffect, useCallback, useMemo, useRef } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { X, ExternalLink } from "lucide-react";
import { useClientReady } from "@/hooks/use-client-ready";
import { SPRING_SNAPPY } from "@/lib/spring-presets";
import type { CitationRef } from "@/types/citation";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/**
 * Return the URL only if it uses an http(s) scheme, otherwise undefined.
 * Defends against javascript:/data: URIs should citation.url ever be populated
 * from server data in the future.
 */
function safeExternalHref(url: string | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url, "https://example.invalid");
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? url
      : undefined;
  } catch {
    return undefined;
  }
}

interface CitationPanelProps {
  /** The citation to display, or null to hide */
  citation: CitationRef | null;
  /** Full text of the patent/source to display with highlighted passage */
  sourceText?: string;
  /** Report context used only when it contains explicit display-safe boundary copy. */
  report?: unknown;
  /** Called when the panel should close */
  onClose: () => void;
  /** Called when "Open in Patent Drawer" is clicked */
  onOpenPatent?: (patentId: string) => void;
}

/**
 * Side-by-side citation panel that slides in from the right.
 * Shows the full source text with the cited passage highlighted.
 */
export function CitationPanel({
  citation,
  sourceText,
  report,
  onClose,
  onOpenPatent,
}: CitationPanelProps) {
  const portalReady = useClientReady();
  const panelRef = useRef<HTMLElement>(null);
  const safeUrl = useMemo(
    () => safeExternalHref(citation?.url),
    [citation?.url],
  );
  const reportContext = useMemo(() => readReportContext(report), [report]);

  const handlePanelKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLElement>) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;

      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => element.getAttribute("aria-hidden") !== "true");
      if (focusable.length === 0) {
        e.preventDefault();
        panelRef.current.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === panelRef.current)) {
        e.preventDefault();
        last.focus();
      } else if (
        !e.shiftKey &&
        (active === last || active === panelRef.current)
      ) {
        e.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  // Move focus into the panel when it opens, and restore it to the element
  // that had focus (typically the citation superscript that opened the panel)
  // when it closes, so keyboard users are not dumped back to <body>.
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (citation && portalReady) {
      previouslyFocusedRef.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      panelRef.current?.focus();
      return () => {
        previouslyFocusedRef.current?.focus();
      };
    }
  }, [citation, portalReady]);

  if (!portalReady) return null;

  return createPortal(
    <AnimatePresence>
      {citation && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="praviar-overlay-scrim-soft fixed inset-0 z-[60]"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.aside
            ref={panelRef}
            tabIndex={-1}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={SPRING_SNAPPY}
            className="praviar-dialog-panel fixed bottom-0 right-0 z-[70] flex max-h-[calc(100dvh-1rem)] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border-r-0 outline-none sm:top-0 sm:max-h-none sm:rounded-none sm:border-y-0"
            role="dialog"
            aria-modal="true"
            aria-label="Citation source"
            onKeyDown={handlePanelKeyDown}
          >
            {/* Header */}
            <div className="praviar-glass-strip flex items-center justify-between gap-3 border-b border-[var(--border-default)] p-4">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded bg-brand-primary/10 text-xs font-bold text-brand-primary">
                  {citation.index}
                </span>
                {citation.patentId && (
                  <span className="patent-id min-w-0 break-all font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {citation.patentId}
                  </span>
                )}
                {citation.claimNumber && (
                  <span className="shrink-0 text-xs text-[var(--text-tertiary)]">
                    Claim {citation.claimNumber}
                  </span>
                )}
                {citation.elementNumber && (
                  <span className="shrink-0 text-xs text-[var(--text-tertiary)]">
                    Element {citation.elementNumber}
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={onClose}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
                aria-label="Close citation panel"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>

            {reportContext ? (
              <div
                role="note"
                aria-label="Citation report context"
                className="border-b border-[var(--border-default)] bg-brand-primary/5 px-4 py-3 text-xs"
                data-testid="citation-report-context"
              >
                <p className="font-semibold text-[var(--text-primary)]">
                  {reportContext.compoundName}
                </p>
                <p className="mt-1 leading-5 text-[var(--text-secondary)]">
                  {reportContext.disclaimer}
                </p>
              </div>
            ) : null}

            {/* Content */}
            <div className="max-h-[calc(100dvh-9rem)] space-y-4 overflow-y-auto p-4 sm:max-h-none sm:flex-1">
              {/* Cited passage */}
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                  Cited Passage
                </h3>
                <div className="rounded-lg border border-warning/20 bg-warning/5 p-3">
                  <p className="break-words text-sm leading-relaxed text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {citation.text}
                  </p>
                </div>
              </div>

              {/* Source context */}
              {sourceText && (
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                    Full Source
                  </h3>
                  <div className="praviar-code-surface max-h-[400px] overflow-y-auto rounded-lg p-3">
                    <HighlightedText
                      fullText={sourceText}
                      highlightText={citation.text}
                    />
                  </div>
                </div>
              )}

              {/* Section reference */}
              <div className="break-words text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                Source: {citation.section}
              </div>
            </div>

            {/* Footer actions */}
            <div className="praviar-glass-strip flex gap-2 border-t border-[var(--border-default)] p-4">
              {citation.patentId && onOpenPatent && (
                <button
                  type="button"
                  onClick={() => {
                    onOpenPatent(citation.patentId!);
                    onClose();
                  }}
                  className="flex min-h-11 flex-1 items-center justify-center gap-2 rounded-lg bg-brand-primary-dim px-3 py-2 text-sm font-medium text-[var(--brand-paper)] transition-colors hover:bg-brand-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
                >
                  Open in Patent Drawer
                </button>
              )}
              {safeUrl && (
                <a
                  href={safeUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex min-h-11 items-center justify-center gap-1.5 rounded-lg border border-[var(--border-emphasis)] px-3 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
                >
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  External
                </a>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>,
    document.body,
  );
}

function readReportContext(
  report: unknown,
): { compoundName: string; disclaimer: string } | null {
  if (!report || typeof report !== "object") return null;
  const record = report as Record<string, unknown>;
  const compound =
    record.compound && typeof record.compound === "object"
      ? (record.compound as Record<string, unknown>)
      : null;
  const compoundName = compound?.name;
  const disclaimer = record.disclaimer;
  if (typeof compoundName !== "string" || typeof disclaimer !== "string") {
    return null;
  }
  const normalizedName = compoundName.trim().replace(/\s+/gu, " ");
  const normalizedDisclaimer = disclaimer.trim().replace(/\s+/gu, " ");
  if (!normalizedName || !normalizedDisclaimer) return null;
  return {
    compoundName: Array.from(normalizedName).slice(0, 160).join(""),
    disclaimer: Array.from(normalizedDisclaimer).slice(0, 320).join(""),
  };
}

/** Renders text with a highlighted substring */
function HighlightedText({
  fullText,
  highlightText,
}: {
  fullText: string;
  highlightText: string;
}) {
  const idx = fullText.toLowerCase().indexOf(highlightText.toLowerCase());
  if (idx === -1) {
    return (
      <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-[var(--text-secondary)] [overflow-wrap:anywhere]">
        {fullText}
      </p>
    );
  }

  const before = fullText.slice(0, idx);
  const match = fullText.slice(idx, idx + highlightText.length);
  const after = fullText.slice(idx + highlightText.length);

  return (
    <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-[var(--text-secondary)] [overflow-wrap:anywhere]">
      {before}
      <mark className="bg-warning/20 text-[var(--text-primary)] rounded px-0.5">
        {match}
      </mark>
      {after}
    </p>
  );
}
