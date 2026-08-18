"use client";

/** Insert a page break before this element when printing. */
export function PrintPageBreak() {
  return <div className="print-page-break" aria-hidden="true" />;
}

/** Wrap content that should not be split across pages. */
export function PrintAvoidBreak({ children }: { children: React.ReactNode }) {
  return <div className="print-avoid-break">{children}</div>;
}
