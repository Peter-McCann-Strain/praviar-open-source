"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ChevronDown, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useCreateMonitor } from "@/hooks/use-monitors";
import {
  SCHEDULE_OPTIONS,
  normalizeMonitorSchedule,
  titleCase,
} from "@/components/monitors/helpers";

interface CreateMonitorFormProps {
  onClose: () => void;
  initialCompoundName?: string;
  initialCompoundSmiles?: string;
  initialSchedule?: string;
  sourceContext?: {
    analysisId?: string;
    reportId?: string;
    trustMode?: string;
    exportReady?: boolean;
    routingModality?: string;
    routingUncertaintyCount?: number;
    claimArchetypes?: string[];
    doctrinePacks?: string[];
  };
}

export function CreateMonitorForm({
  onClose,
  initialCompoundName = "",
  initialCompoundSmiles = "",
  initialSchedule = "weekly",
  sourceContext,
}: CreateMonitorFormProps) {
  const [name, setName] = useState(initialCompoundName);
  const [smiles, setSmiles] = useState(initialCompoundSmiles);
  const [schedule, setSchedule] = useState(() =>
    normalizeMonitorSchedule(initialSchedule),
  );
  const [smilesError, setSmilesError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submissionLocked, setSubmissionLocked] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const createMonitor = useCreateMonitor();
  const smilesErrorId = "monitor-smiles-error";
  const formErrorId = "monitor-form-error";
  const isSubmitting = createMonitor.isPending || submissionLocked;
  const canResolveFromAnalysis = Boolean(sourceContext?.analysisId);

  useEffect(() => {
    nameInputRef.current?.focus();
  }, []);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }

    if (!smiles.trim() && !canResolveFromAnalysis) {
      setSmilesError(
        "Enter a compound SMILES string before creating a monitor.",
      );
      setFormError(null);
      return;
    }

    setSmilesError(null);
    setFormError(null);
    setSubmissionLocked(true);
    createMonitor.mutate(
      {
        analysis_id: sourceContext?.analysisId,
        compound_smiles: smiles.trim() || undefined,
        compound_name: name.trim() || undefined,
        schedule,
      },
      {
        onSuccess: () => {
          setSubmissionLocked(false);
          onClose();
        },
        onError: () => {
          console.error("[CreateMonitorForm] Failed to create monitor");
          setSubmissionLocked(false);
          setFormError(
            "Monitor could not be created. Existing monitors are unchanged. Please retry.",
          );
        },
      },
    );
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="praviar-glass-strip border-b border-[var(--border-default)]">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Monitoring setup
            </p>
            <CardTitle className="mt-1 text-base">Create New Monitor</CardTitle>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              Start a private watch for new patent events tied to this compound.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close create monitor form"
            className="ml-3 flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="p-4 sm:p-5">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="monitor-name"
              className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]"
            >
              Compound Name (optional)
            </label>
            <input
              ref={nameInputRef}
              id="monitor-name"
              type="text"
              value={name}
              disabled={isSubmitting}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Ibuprofen, Compound X"
              className="praviar-glass-field h-11 w-full rounded-md border border-[var(--border-emphasis)] px-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
            />
          </div>
          <div>
            <label
              htmlFor="monitor-smiles"
              className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]"
            >
              Compound SMILES
            </label>
            <input
              id="monitor-smiles"
              type="text"
              value={smiles}
              aria-describedby={smilesError ? smilesErrorId : undefined}
              aria-invalid={smilesError ? true : undefined}
              disabled={isSubmitting}
              onChange={(e) => {
                setSmiles(e.target.value);
                if (smilesError) setSmilesError(null);
              }}
              placeholder="e.g., CC(C)Cc1ccc(cc1)C(C)C(=O)O"
              className="praviar-glass-field h-11 w-full rounded-md border border-[var(--border-emphasis)] px-3 font-mono text-sm text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
            />
            <p className="mt-1.5 text-xs leading-5 text-[var(--text-tertiary)]">
              {canResolveFromAnalysis
                ? "Praviar can resolve the monitored compound from the source report."
                : "Praviar stores the normalized watch in your workspace after the monitor is created."}
            </p>
            {smilesError ? (
              <p
                id={smilesErrorId}
                role="alert"
                className="mt-1.5 text-xs text-error"
              >
                {smilesError}
              </p>
            ) : null}
          </div>
          <div>
            <label
              htmlFor="monitor-schedule"
              className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]"
            >
              Schedule
            </label>
            <div className="relative">
              <select
                id="monitor-schedule"
                value={schedule}
                disabled={isSubmitting}
                onChange={(e) =>
                  setSchedule(normalizeMonitorSchedule(e.target.value))
                }
                className="praviar-glass-field h-11 w-full cursor-pointer appearance-none rounded-md border border-[var(--border-emphasis)] px-3 pr-9 text-sm text-[var(--text-secondary)] focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
              >
                {SCHEDULE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]"
                aria-hidden="true"
              />
            </div>
          </div>
          {sourceContext ? (
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3">
              <p className="mb-2 text-xs font-semibold text-[var(--text-primary)]">
                Source report context
              </p>
              <div className="flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
                {sourceContext.trustMode ? (
                  <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2.5 py-1">
                    Trust: {titleCase(sourceContext.trustMode)}
                  </span>
                ) : null}
                {sourceContext.exportReady ? (
                  <span className="rounded-full border border-success/20 bg-success/10 px-2.5 py-1 text-success">
                    Export ready
                  </span>
                ) : null}
                {typeof sourceContext.routingUncertaintyCount === "number" ? (
                  <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2.5 py-1">
                    {sourceContext.routingUncertaintyCount} routing cautions
                  </span>
                ) : null}
                {sourceContext.claimArchetypes?.map((item) => (
                  <span
                    key={item}
                    className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2.5 py-1"
                  >
                    {item}
                  </span>
                ))}
                {sourceContext.doctrinePacks?.map((item) => (
                  <span
                    key={item}
                    className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2.5 py-1"
                  >
                    {item}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          {formError ? (
            <p id={formErrorId} role="alert" className="text-xs text-error">
              {formError}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              className="min-h-11"
              loading={isSubmitting}
            >
              Create Monitor
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
