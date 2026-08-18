"use client";

import { X } from "lucide-react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";

interface ShareDialogHeaderProps {
  onClose: () => void;
}

export function ShareDialogHeader({ onClose }: ShareDialogHeaderProps) {
  return (
    <>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close share dialog"
        className="absolute right-3 top-3 z-10 flex h-11 w-11 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_86%,transparent)] text-[var(--text-tertiary)] shadow-[var(--shadow-xs)] backdrop-blur-sm transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] sm:right-4 sm:top-4"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>

      <div className="flex min-w-0 items-start gap-2.5 pr-12 sm:gap-3">
        <PraviarMarkFrame size="dialog" />
        <div className="min-w-0">
          <h3
            id="share-dialog-title"
            className="text-lg font-semibold leading-6 text-[var(--text-primary)] sm:type-heading-sm"
          >
            Share governed report
          </h3>
          <p className="mt-0.5 text-xs leading-4 text-[var(--text-secondary)] sm:hidden">
            Mailbox-bound · read-only evidence
          </p>
          <p className="mt-1 hidden max-w-2xl text-sm leading-6 text-[var(--text-secondary)] sm:block">
            Create and manage mailbox-bound invitations with evidence boundaries
            intact.
          </p>
        </div>
      </div>
    </>
  );
}
