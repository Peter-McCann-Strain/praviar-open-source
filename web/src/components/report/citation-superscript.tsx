"use client";

import { useState, useCallback } from "react";
import {
  useFloating,
  autoUpdate,
  offset,
  flip,
  shift,
  useHover,
  useFocus,
  useDismiss,
  useRole,
  useInteractions,
  FloatingPortal,
} from "@floating-ui/react";
import { motion, AnimatePresence } from "motion/react";
import { SPRING_SNAPPY } from "@/lib/spring-presets";
import type { CitationRef } from "@/types/citation";

interface CitationSuperscriptProps {
  index: number;
  citation?: CitationRef;
  onClick?: (index: number) => void;
}

export function CitationSuperscript({
  index,
  citation,
  onClick,
}: CitationSuperscriptProps) {
  const [isOpen, setIsOpen] = useState(false);

  const { refs, floatingStyles, context } = useFloating({
    open: isOpen,
    onOpenChange: setIsOpen,
    middleware: [offset(6), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
    placement: "top",
  });
  const setReference = useCallback(
    (node: HTMLButtonElement | null) => {
      refs.setReference(node);
    },
    [refs],
  );
  const setFloating = useCallback(
    (node: HTMLDivElement | null) => {
      refs.setFloating(node);
    },
    [refs],
  );

  const hover = useHover(context, { delay: { open: 200, close: 100 } });
  const focus = useFocus(context);
  const dismiss = useDismiss(context);
  const role = useRole(context, { role: "tooltip" });

  const { getReferenceProps, getFloatingProps } = useInteractions([
    hover,
    focus,
    dismiss,
    role,
  ]);

  const handleClick = useCallback(() => {
    onClick?.(index);
  }, [onClick, index]);

  return (
    <>
      <button
        ref={setReference}
        {...getReferenceProps()}
        onClick={handleClick}
        className="mx-1 inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center rounded-full bg-brand-primary/10 align-middle text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/20 hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60"
        aria-label={`Citation ${index}`}
      >
        {index}
      </button>

      <FloatingPortal>
        <AnimatePresence>
          {isOpen && citation && (
            <motion.div
              ref={setFloating}
              style={floatingStyles}
              {...getFloatingProps()}
              initial={{ opacity: 0, y: 4, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.96 }}
              transition={SPRING_SNAPPY}
              className="z-50 w-[280px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 shadow-lg shadow-[var(--shadow-lg)]"
            >
              {/* Patent ID header */}
              {citation.patentId && (
                <div className="flex items-center gap-2 mb-2">
                  <span className="patent-id text-brand-primary font-semibold">
                    {citation.patentId}
                  </span>
                  {citation.claimNumber && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--surface-active)] text-[var(--text-secondary)]">
                      Claim {citation.claimNumber}
                    </span>
                  )}
                </div>
              )}

              {/* Cited text */}
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed line-clamp-3">
                {citation.text}
              </p>

              {/* Section reference */}
              <div className="mt-2 pt-2 border-t border-[var(--border-subtle)] flex items-center justify-between">
                <span className="text-xs text-[var(--text-tertiary)]">
                  {citation.section}
                </span>
                <button
                  onClick={handleClick}
                  className="text-xs text-brand-primary hover:text-brand-primary font-medium"
                >
                  View source
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </FloatingPortal>
    </>
  );
}
