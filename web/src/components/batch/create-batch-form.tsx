"use client";

import { useRef, useState } from "react";
import { X } from "lucide-react";
import Link from "next/link";
import { useCreateBatch } from "@/hooks/use-batch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { APIError } from "@/lib/api-client";
import { PROBLEM_TYPES } from "@/lib/problem-types";

interface CreateBatchFormProps {
  onClose: () => void;
}

const MAX_COMPOUNDS = 50;
const MAX_COMPOUND_CHARS = 5000;
const BATCH_CAPACITY_ERROR_TYPE = PROBLEM_TYPES.analysisCapacityExhausted;

export function CreateBatchForm({ onClose }: CreateBatchFormProps) {
  const [name, setName] = useState("");
  const [compoundsText, setCompoundsText] = useState("");
  const [createSubmitted, setCreateSubmitted] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [capacityLaunchRejected, setCapacityLaunchRejected] = useState(false);
  const launchAttemptRef = useRef<{
    payloadFingerprint: string;
    idempotencyKey: string;
  } | null>(null);
  const createBatch = useCreateBatch();
  const controlsDisabled = createBatch.isPending || createSubmitted;

  const compounds = compoundsText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const compoundCount = compounds.length;

  const validationError =
    compoundCount > MAX_COMPOUNDS
      ? `Too many compounds (${compoundCount}/${MAX_COMPOUNDS} max).`
      : compounds.some((c) => c.length > MAX_COMPOUND_CHARS)
        ? `Each compound must be under ${MAX_COMPOUND_CHARS.toLocaleString()} characters.`
        : null;

  const canSubmit =
    name.trim().length > 0 &&
    compoundCount > 0 &&
    !validationError &&
    !controlsDisabled;

  const handleClose = () => {
    if (controlsDisabled) return;
    onClose();
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    const payload = { name: name.trim(), compounds };
    const payloadFingerprint = JSON.stringify(payload);
    if (launchAttemptRef.current?.payloadFingerprint !== payloadFingerprint) {
      launchAttemptRef.current = {
        payloadFingerprint,
        idempotencyKey: `batch-launch-${crypto.randomUUID()}`,
      };
    }
    const idempotencyKey = launchAttemptRef.current.idempotencyKey;
    setLaunchError(null);
    setCapacityLaunchRejected(false);
    setCreateSubmitted(true);
    createBatch.mutate(
      { ...payload, client_idempotency_key: idempotencyKey },
      {
        onSuccess: () => {
          launchAttemptRef.current = null;
          onClose();
        },
        onError: (error) => {
          const capacityExhausted =
            error instanceof APIError &&
            error.status === 429 &&
            error.telemetry.typeUri === BATCH_CAPACITY_ERROR_TYPE;
          setCapacityLaunchRejected(capacityExhausted);
          setLaunchError(
            capacityExhausted
              ? `No Report Credit capacity remains for this ${compoundCount}-compound batch. No batch or analyses were created.`
              : "The launch outcome could not be confirmed. Retry to reconcile this same batch without duplicate reports or charges.",
          );
        },
        onSettled: () => setCreateSubmitted(false),
      },
    );
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Create Batch Analysis</CardTitle>
          <button
            type="button"
            aria-label="Close batch form"
            onClick={handleClose}
            disabled={controlsDisabled}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="batch-name"
              className="mb-1 block type-label-sm text-[var(--text-secondary)]"
            >
              Batch Name
            </label>
            <input
              id="batch-name"
              type="text"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setLaunchError(null);
                setCapacityLaunchRejected(false);
              }}
              disabled={controlsDisabled}
              placeholder="e.g., Q1 Lead Compounds"
              className="h-11 w-full rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] disabled:cursor-not-allowed disabled:text-[var(--text-disabled)]"
            />
          </div>
          <div>
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <label
                htmlFor="batch-compounds"
                className="type-label-sm text-[var(--text-secondary)]"
              >
                Compounds
                <span className="sr-only"> (one per line)</span>
              </label>
              <span
                aria-live="polite"
                className="shrink-0 type-caption tabular-nums text-[var(--text-tertiary)]"
              >
                {compoundCount === 0
                  ? "0 compounds entered"
                  : `${compoundCount} compound${compoundCount !== 1 ? "s" : ""}`}
              </span>
            </div>
            <textarea
              id="batch-compounds"
              value={compoundsText}
              onChange={(event) => {
                setCompoundsText(event.target.value);
                setLaunchError(null);
                setCapacityLaunchRejected(false);
              }}
              disabled={controlsDisabled}
              placeholder="Paste compound names or SMILES here"
              rows={6}
              className="w-full resize-y rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 py-2 font-mono text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] disabled:cursor-not-allowed disabled:text-[var(--text-disabled)]"
            />
            <p className="mt-1 type-caption text-[var(--text-tertiary)]">
              One compound per line · names and SMILES accepted
            </p>
            {validationError && (
              <p className="mt-1 type-caption text-error">{validationError}</p>
            )}
            {launchError ? (
              <div
                className="mt-2 rounded-md border border-error/25 bg-error/5 p-3 text-error"
                role="alert"
              >
                <p className="type-caption leading-5">{launchError}</p>
                {capacityLaunchRejected ? (
                  <Button
                    asChild
                    variant="outline"
                    size="sm"
                    className="mt-2 min-h-11 border-error/30 text-[var(--text-primary)]"
                  >
                    <Link
                      href={`/billing?intent=credits&needed_reports=${compoundCount}&source=batch`}
                    >
                      Review Report Credits
                    </Link>
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11"
              onClick={handleClose}
              disabled={controlsDisabled}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              className="min-h-11"
              loading={controlsDisabled}
              disabled={!canSubmit}
            >
              Start Batch ({compoundCount})
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
