"use client";

import type { ReactNode } from "react";

export function PageTransition({ children }: { children: ReactNode }) {
  return (
    <div className="animate-fade-up" data-praviar-page-transition>
      {children}
    </div>
  );
}
