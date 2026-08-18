"use client";

import { cn } from "@/lib/utils";
import {
  type ExportAudience,
  hasExportContentSection,
  isRequiredExportSection,
  isSectionRequiredForAudience,
  SECTION_OPTIONS,
  type ExportSection,
} from "./export-dialog-constants";

interface ExportDialogSectionSelectorProps {
  audience: ExportAudience;
  selectedSections: Set<ExportSection>;
  onToggle: (sectionId: ExportSection) => void;
  disabled?: boolean;
}

export function ExportDialogSectionSelector({
  audience,
  selectedSections,
  onToggle,
  disabled,
}: ExportDialogSectionSelectorProps) {
  const hasContent = hasExportContentSection(selectedSections);

  return (
    <div className="space-y-3">
      <div className="flex min-w-0 flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h4
            id="export-sections-heading"
            className="text-sm font-semibold text-[var(--text-primary)]"
          >
            3. Select sections to include
          </h4>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            Defaults include provenance, review posture, and run metadata for
            downstream reliance review.
          </p>
        </div>
        <p className="text-xs font-semibold text-brand-primary">
          {selectedSections.size} of {SECTION_OPTIONS.length} sections selected
        </p>
      </div>
      {!hasContent ? (
        <p
          role="status"
          className="rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs font-semibold leading-5 text-warning"
        >
          Select at least one report content section; provenance-only packets
          are kept as audit records, not export deliverables.
        </p>
      ) : null}
      <div className="divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)] lg:max-h-72 lg:overflow-y-auto">
        {SECTION_OPTIONS.map((section) => {
          const checked = selectedSections.has(section.id);
          const required = isRequiredExportSection(section.id);
          const requiredForAudience = isSectionRequiredForAudience(
            section.id,
            audience,
          );
          return (
            <label
              key={section.id}
              className={cn(
                "flex min-h-12 items-start gap-3 px-3 py-2.5 transition-colors first:rounded-t-lg last:rounded-b-lg",
                required || requiredForAudience || disabled
                  ? "cursor-not-allowed"
                  : "cursor-pointer hover:bg-[var(--surface-muted)]",
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled || required || requiredForAudience}
                onChange={() => onToggle(section.id)}
                className="mt-0.5 h-4 w-4 cursor-pointer rounded border-[var(--border-emphasis)] bg-[var(--surface-hover)] text-brand-primary accent-brand-primary focus:ring-brand-primary focus:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <span className="min-w-0 flex-1">
                <span className="flex min-w-0 flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "block text-sm font-medium",
                      checked
                        ? "text-[var(--text-primary)]"
                        : "text-[var(--text-tertiary)]",
                    )}
                  >
                    {section.label}
                  </span>
                  {required ? (
                    <span className="inline-flex rounded-full border border-brand-primary/20 bg-brand-primary/8 px-2 py-0.5 text-xs font-semibold uppercase tracking-[0.12em] text-brand-primary">
                      Required
                    </span>
                  ) : null}
                  {requiredForAudience && !required ? (
                    <span className="inline-flex rounded-full border border-brand-accent/25 bg-brand-accent/10 px-2 py-0.5 text-xs font-semibold uppercase tracking-[0.12em] text-brand-accent">
                      Required for audience
                    </span>
                  ) : null}
                </span>
                <span className="mt-0.5 block text-xs leading-5 text-[var(--text-tertiary)]">
                  {section.description}
                </span>
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
