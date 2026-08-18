"use client";

import { type KeyboardEvent, useRef } from "react";
import { cn } from "@/lib/utils";
import { FORMAT_OPTIONS, type ExportFormat } from "./export-dialog-constants";

interface ExportDialogFormatOptionsProps {
  selectedFormat: ExportFormat;
  onSelect: (format: ExportFormat) => void;
  disabled?: boolean;
  formatRestrictions?: Partial<Record<ExportFormat, string>>;
}

export function ExportDialogFormatOptions({
  selectedFormat,
  onSelect,
  disabled,
  formatRestrictions = {},
}: ExportDialogFormatOptionsProps) {
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const moveSelection = (nextIndex: number) => {
    for (let offset = 0; offset < FORMAT_OPTIONS.length; offset += 1) {
      const candidateIndex =
        (((nextIndex + offset) % FORMAT_OPTIONS.length) +
          FORMAT_OPTIONS.length) %
        FORMAT_OPTIONS.length;
      const nextOption = FORMAT_OPTIONS[candidateIndex];
      if (!nextOption || formatRestrictions[nextOption.value]) {
        continue;
      }

      onSelect(nextOption.value);
      optionRefs.current[candidateIndex]?.focus();
      return;
    }
  };

  const handleKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) => {
    if (disabled) {
      return;
    }

    const lastIndex = FORMAT_OPTIONS.length - 1;
    switch (event.key) {
      case "ArrowDown":
      case "ArrowRight": {
        event.preventDefault();
        moveSelection(currentIndex === lastIndex ? 0 : currentIndex + 1);
        break;
      }
      case "ArrowLeft":
      case "ArrowUp": {
        event.preventDefault();
        moveSelection(currentIndex === 0 ? lastIndex : currentIndex - 1);
        break;
      }
      case "End": {
        event.preventDefault();
        moveSelection(lastIndex);
        break;
      }
      case "Home": {
        event.preventDefault();
        moveSelection(0);
        break;
      }
      default:
        break;
    }
  };

  return (
    <div className="space-y-2" role="radiogroup" aria-label="Export format">
      {FORMAT_OPTIONS.map((formatOption, index) => {
        const Icon = formatOption.icon;
        const active = selectedFormat === formatOption.value;
        const restriction = formatRestrictions[formatOption.value];
        const optionDisabled = Boolean(disabled || restriction);
        const restrictionId = restriction
          ? `export-format-${formatOption.value}-restriction`
          : undefined;

        return (
          <button
            key={formatOption.value}
            ref={(node) => {
              optionRefs.current[index] = node;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            aria-describedby={restrictionId}
            tabIndex={active ? 0 : -1}
            onKeyDown={(event) => handleKeyDown(event, index)}
            onClick={() => {
              if (restriction) {
                return;
              }
              onSelect(formatOption.value);
            }}
            disabled={optionDisabled}
            className={cn(
              "flex min-h-20 w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
              optionDisabled && "cursor-not-allowed opacity-55",
              active
                ? "border-brand-primary bg-brand-primary/10 shadow-[var(--shadow-xs)]"
                : "border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_76%,transparent)] hover:border-[var(--border-emphasis)] hover:bg-[var(--surface-muted)]",
            )}
          >
            <span
              className={cn(
                "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border",
                active
                  ? "border-brand-primary/25 bg-brand-primary text-[var(--brand-paper)]"
                  : "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-brand-primary",
              )}
              aria-hidden="true"
            >
              <Icon className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  "text-sm font-medium",
                  active ? "text-brand-primary" : "text-[var(--text-primary)]",
                )}
              >
                {formatOption.label}
              </p>
              <p className="text-xs text-[var(--text-tertiary)]">
                {formatOption.description}
              </p>
              {restriction ? (
                <p
                  id={restrictionId}
                  className="mt-1 text-xs font-medium text-warning"
                >
                  {restriction}
                </p>
              ) : null}
            </div>
            <span
              aria-hidden="true"
              className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                active
                  ? "border-brand-primary bg-brand-primary"
                  : "border-[var(--border-emphasis)] bg-[var(--bg-surface)]",
              )}
            >
              {active ? (
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--brand-paper)]" />
              ) : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}
