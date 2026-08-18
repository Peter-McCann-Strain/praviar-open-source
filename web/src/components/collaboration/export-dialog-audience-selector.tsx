"use client";

import { type KeyboardEvent, useRef } from "react";
import { CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  AUDIENCE_OPTIONS,
  getAudienceDescription,
  type ExportAudience,
} from "@/components/collaboration/export-dialog-constants";

interface ExportDialogAudienceSelectorProps {
  audience: ExportAudience;
  onAudienceChange: (audience: ExportAudience) => void;
  disabled?: boolean;
}

export function ExportDialogAudienceSelector({
  audience,
  onAudienceChange,
  disabled,
}: ExportDialogAudienceSelectorProps) {
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const moveSelection = (nextIndex: number) => {
    const nextOption = AUDIENCE_OPTIONS[nextIndex];
    if (!nextOption) {
      return;
    }

    onAudienceChange(nextOption.value);
    optionRefs.current[nextIndex]?.focus();
  };

  const handleKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) => {
    if (disabled) {
      return;
    }

    const lastIndex = AUDIENCE_OPTIONS.length - 1;
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
    <div className="space-y-2">
      <div
        className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3"
        role="radiogroup"
        aria-label="Report Audience"
      >
        {AUDIENCE_OPTIONS.map((option, index) => {
          const active = audience === option.value;
          return (
            <button
              key={option.value}
              ref={(node) => {
                optionRefs.current[index] = node;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              disabled={disabled}
              onKeyDown={(event) => handleKeyDown(event, index)}
              onClick={() => onAudienceChange(option.value)}
              className={cn(
                "inline-flex min-h-11 min-w-0 items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
                disabled && "pointer-events-none opacity-50",
                active
                  ? "border-brand-primary bg-brand-primary text-[var(--brand-paper)] shadow-[var(--shadow-xs)]"
                  : "border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-brand-primary/35 hover:bg-brand-primary/10 hover:text-brand-primary",
              )}
            >
              {active ? (
                <CheckCircle2
                  className="h-3.5 w-3.5 shrink-0"
                  aria-hidden="true"
                />
              ) : null}
              <span className="min-w-0 truncate">{option.label}</span>
            </button>
          );
        })}
      </div>
      <p className="text-xs leading-5 text-[var(--text-tertiary)]">
        {getAudienceDescription(audience)}
      </p>
    </div>
  );
}
