"use client";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  SCHEDULE_OPTIONS,
  normalizeMonitorSchedule,
  type MonitorSchedule,
} from "@/components/monitors/helpers";
import { cn } from "@/lib/utils";

interface WatchToggleProps {
  analysisId: string;
  enabled?: boolean;
  isPending?: boolean;
  schedule?: string;
  onToggle?: (enabled: boolean, schedule: string) => void;
  className?: string;
}

export function WatchToggle({
  enabled = false,
  isPending = false,
  schedule = "weekly",
  onToggle,
  className,
}: WatchToggleProps) {
  const frequency = normalizeMonitorSchedule(schedule);

  const handleToggle = () => {
    onToggle?.(!enabled, frequency);
  };

  const handleFrequencyChange = (nextFrequency: MonitorSchedule) => {
    if (enabled) {
      onToggle?.(true, nextFrequency);
    }
  };

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Button
        variant={enabled ? "default" : "outline"}
        size="sm"
        onClick={handleToggle}
        disabled={isPending}
        aria-pressed={enabled}
        aria-label={enabled ? "Watching" : "Watch"}
        title={
          enabled
            ? "Disable watch alerts for this analysis"
            : "Enable watch alerts for this analysis"
        }
        className={cn(
          "min-h-11 gap-1.5",
          enabled && "bg-brand-primary-dim hover:bg-brand-primary-hover",
        )}
      >
        {enabled ? (
          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <EyeOff className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        {enabled ? "Watching" : "Watch"}
      </Button>

      {enabled && (
        <select
          value={frequency}
          aria-label="Watch frequency"
          disabled={isPending}
          onChange={(e) =>
            handleFrequencyChange(normalizeMonitorSchedule(e.target.value))
          }
          className="min-h-11 rounded border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 py-2 text-xs text-[var(--text-secondary)]"
        >
          {SCHEDULE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}

      {enabled && (
        <span
          className="flex items-center gap-1"
          role="status"
          aria-live="polite"
        >
          <span
            className="h-2 w-2 rounded-full bg-success animate-pulse motion-reduce:animate-none"
            aria-hidden="true"
          />
          <span className="text-xs text-[var(--text-tertiary)]">Active</span>
        </span>
      )}
    </div>
  );
}
