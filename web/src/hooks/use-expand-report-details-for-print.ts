"use client";

import { useEffect } from "react";

/**
 * Native closed <details> descendants are omitted by Chromium print/PDF.
 * Temporarily expand only the disclosures that were closed, then restore the
 * exact interactive state after printing.
 */
export function useExpandReportDetailsForPrint(
  workspaceSelector = ".praviar-report-workspace",
) {
  useEffect(() => {
    const expandedForPrint: HTMLDetailsElement[] = [];

    const handleBeforePrint = () => {
      expandedForPrint.length = 0;
      document
        .querySelectorAll<HTMLDetailsElement>(`${workspaceSelector} details`)
        .forEach((detail) => {
          if (detail.open) return;
          detail.open = true;
          detail.dataset.praviarPrintExpanded = "true";
          expandedForPrint.push(detail);
        });
    };

    const handleAfterPrint = () => {
      expandedForPrint.forEach((detail) => {
        detail.open = false;
        delete detail.dataset.praviarPrintExpanded;
      });
      expandedForPrint.length = 0;
    };

    window.addEventListener("beforeprint", handleBeforePrint);
    window.addEventListener("afterprint", handleAfterPrint);
    return () => {
      handleAfterPrint();
      window.removeEventListener("beforeprint", handleBeforePrint);
      window.removeEventListener("afterprint", handleAfterPrint);
    };
  }, [workspaceSelector]);
}
