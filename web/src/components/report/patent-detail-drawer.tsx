"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { useClientReady } from "@/hooks/use-client-ready";
import { SPRING_SNAPPY } from "@/lib/spring-presets";
import type { PatentHit, PatentAnalysis } from "@praviar/shared-types";
import { getPatentLinks } from "./patent-detail-drawer-helpers";
import {
  PatentDetailDrawerHeader,
  PatentDetailDrawerSections,
} from "./patent-detail-drawer-sections";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

interface PatentDetailDrawerProps {
  patent: PatentHit | null;
  analysis: PatentAnalysis | null;
  open: boolean;
  onClose: () => void;
}

function getFocusableElements(container: HTMLElement) {
  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((element) => !element.hasAttribute("aria-hidden"));
}

export function PatentDetailDrawer({
  patent,
  analysis,
  open,
  onClose,
}: PatentDetailDrawerProps) {
  const portalReady = useClientReady();
  const [expandedClaimsPatentId, setExpandedClaimsPatentId] = useState<
    string | null
  >(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocusedElementRef = useRef<HTMLElement | null>(null);
  const currentPatentId = patent?.patent_id ?? null;
  const claimsExpanded =
    currentPatentId !== null && expandedClaimsPatentId === currentPatentId;

  // Focus management — keyed on open only so patent swaps don't trigger an
  // intermediate focus restoration that yanks the user's focus mid-interaction.
  useEffect(() => {
    if (!open) return;
    previouslyFocusedElementRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    panelRef.current?.focus();
    return () => {
      previouslyFocusedElementRef.current?.focus();
      previouslyFocusedElementRef.current = null;
    };
  }, [open, portalReady]);

  const handleDialogKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }

      if (event.key !== "Tab" || !panelRef.current) return;

      const focusableElements = getFocusableElements(panelRef.current);
      if (focusableElements.length === 0) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      const activeElement = document.activeElement;

      if (
        event.shiftKey &&
        (activeElement === firstElement || activeElement === panelRef.current)
      ) {
        event.preventDefault();
        lastElement.focus();
        return;
      }

      if (!event.shiftKey && activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    },
    [onClose],
  );
  const handleClaimsExpandedChange = useCallback(
    (expanded: boolean) => {
      setExpandedClaimsPatentId(
        expanded && currentPatentId ? currentPatentId : null,
      );
    },
    [currentPatentId],
  );

  const links = patent ? getPatentLinks(patent.patent_id) : null;

  if (!portalReady) return null;

  return createPortal(
    <AnimatePresence>
      {open && patent && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            aria-hidden="true"
            className="praviar-overlay-scrim fixed inset-0 z-[60]"
            onClick={onClose}
          />

          {/* Drawer panel */}
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label={`Patent details for ${patent.patent_id}`}
            tabIndex={-1}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={SPRING_SNAPPY}
            className="praviar-dialog-panel fixed bottom-0 right-0 top-0 z-[70] w-full max-w-lg overflow-y-auto"
            onKeyDown={handleDialogKeyDown}
          >
            <PatentDetailDrawerHeader
              patent={patent}
              analysis={analysis}
              patentLinks={links!}
              onClose={onClose}
            />
            <PatentDetailDrawerSections
              patent={patent}
              claimsExpanded={claimsExpanded}
              onClaimsExpandedChange={handleClaimsExpandedChange}
            />
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body,
  );
}
