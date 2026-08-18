"use client";

import { useEffect, useRef } from "react";

export function useExportDialogFocusTrap(
  open: boolean,
  onClose: () => void,
  dialogRef: React.RefObject<HTMLDivElement | null>,
) {
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  // Keep the latest onClose in a ref so the trap effect depends only on
  // [open, dialogRef]. Callers commonly pass an inline arrow for onClose; if it
  // were in the dependency array, every parent re-render (e.g. the export-status
  // poll updating jobStatus) would tear down and re-run this effect, and the
  // cleanup's previouslyFocusedRef.current?.focus() would yank focus out of the
  // open dialog back to the trigger on every poll tick.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    previouslyFocusedRef.current = document.activeElement as HTMLElement;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onCloseRef.current();
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) return;

      const focusable = getDialogFocusableElements(dialogRef.current);

      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
        return;
      }

      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    const timer = setTimeout(() => {
      if (!dialogRef.current) return;
      if (dialogRef.current.contains(document.activeElement)) return;
      const first = getDialogFocusableElements(dialogRef.current)[0];
      first?.focus();
    }, 0);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      clearTimeout(timer);
      if (previouslyFocusedRef.current?.isConnected) {
        previouslyFocusedRef.current.focus();
      } else {
        document
          .querySelector<HTMLElement>("[data-praviar-mobile-actions-trigger]")
          ?.focus();
      }
      previouslyFocusedRef.current = null;
    };
  }, [dialogRef, open]);
}

const FOCUSABLE_SELECTOR =
  'summary, button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function getDialogFocusableElements(dialog: HTMLElement): HTMLElement[] {
  return Array.from(
    dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((element) => !isHiddenInsideClosedDetails(element));
}

function isHiddenInsideClosedDetails(element: HTMLElement): boolean {
  const closedDetails = element.closest("details:not([open])");
  if (!closedDetails) return false;
  return element.tagName !== "SUMMARY";
}
