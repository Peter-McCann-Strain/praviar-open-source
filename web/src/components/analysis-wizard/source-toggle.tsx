"use client";

import { useId } from "react";

interface SourceToggleProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}

export function SourceToggle({
  label,
  description,
  checked,
  onChange,
}: SourceToggleProps) {
  const inputId = useId();

  return (
    <label
      htmlFor={inputId}
      className="flex cursor-pointer items-center gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-3.5 transition-colors hover:border-[var(--border-emphasis)]"
    >
      <input
        id={inputId}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-brand-primary"
      />
      <div className="min-w-0 flex-1">
        <span className="text-sm font-medium text-[var(--text-primary)]">
          {label}
        </span>
        <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">
          {description}
        </p>
      </div>
    </label>
  );
}
