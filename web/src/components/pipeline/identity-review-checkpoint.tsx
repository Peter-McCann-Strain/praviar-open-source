"use client";

import { useId, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  CircleAlert,
  Database,
  Fingerprint,
  GitCompareArrows,
  Layers3,
  LockKeyhole,
  Search,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface IdentityReviewCheckpointProps {
  data: Record<string, unknown>;
  onApprove: () => void;
  onReject: () => void;
  isSubmitting?: boolean;
  errorMessage?: string;
}

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};
}

function asString(value: unknown, fallback = "Not available"): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function asBoolean(value: unknown): boolean {
  return value === true;
}

function recordList(value: unknown): UnknownRecord[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is UnknownRecord =>
          item !== null && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

const COMPARISON_LABELS: Record<string, string> = {
  exact_match: "Exact match",
  normalized_match: "Normalized match",
  resolved_from_identifier: "Resolved record differs in presentation",
  different: "Structure differs",
  not_comparable: "Manual comparison required",
};

const VARIANT_STATUS_LABELS: Record<string, string> = {
  candidate_detected: "Candidate detected",
  declared: "Product form declared",
  derived_search_form: "Derived lane included",
  no_distinct_form: "No distinct lane",
  not_applicable: "Not represented for this asset",
  not_detected: "No common motif detected",
  not_modeled: "Not modeled",
  unavailable: "Unavailable",
};

function IdentityValue({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 text-sm leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]",
          mono && "font-mono text-xs",
        )}
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}

export function IdentityReviewCheckpoint({
  data,
  onApprove,
  onReject,
  isSubmitting = false,
  errorMessage,
}: IdentityReviewCheckpointProps) {
  const attestationId = useId();
  const [attested, setAttested] = useState(false);
  const comparison = asRecord(data.comparison);
  const resolved = asRecord(data.resolved_identity);
  const searchLanes = recordList(data.search_envelope);
  const variants = recordList(data.variant_assessments);
  const comparisonAttention = asBoolean(comparison.requires_attention);
  const authoritative = asBoolean(resolved.authoritative_record_present);
  const fingerprint = asString(data.identity_fingerprint, "");
  const sourceRecord = asString(resolved.source_record_id, "");
  const molecularWeight =
    typeof resolved.molecular_weight === "number"
      ? resolved.molecular_weight.toLocaleString(undefined, {
          maximumFractionDigits: 4,
        })
      : "Not available";

  return (
    <Card
      className="overflow-hidden border-brand-primary/25 bg-[var(--surface-card)] shadow-[var(--shadow-lg)]"
      data-testid="identity-review-checkpoint"
    >
      <CardHeader className="space-y-3 border-b border-[var(--border-subtle)] bg-[var(--surface-glass)] p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-primary/10 text-brand-primary">
            <Fingerprint className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
              Mandatory identity gate
            </p>
            <CardTitle className="mt-1 text-base text-[var(--text-primary)] sm:text-lg">
              Approve the resolved compound before search
            </CardTitle>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] sm:text-sm">
              Patent retrieval is blocked until a reviewer accepts this exact,
              fingerprint-bound identity and its search-envelope limitations.
            </p>
          </div>
          <span className="hidden shrink-0 items-center gap-1.5 rounded-md border border-warning/30 bg-warning/10 px-2 py-1 text-xs font-semibold text-warning sm:inline-flex">
            <LockKeyhole className="h-3.5 w-3.5" aria-hidden="true" />
            Search blocked
          </span>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-medium",
              authoritative
                ? "border-success/25 bg-success/10 text-success"
                : "border-error/25 bg-error/10 text-error",
            )}
          >
            {authoritative ? (
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <CircleAlert className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {authoritative
              ? asString(resolved.source_authority, "Authoritative source")
              : "Authoritative record missing"}
          </span>
          {sourceRecord ? (
            <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-default)] bg-[var(--surface-subtle)] px-2 py-1 text-[var(--text-secondary)]">
              <Database className="h-3.5 w-3.5" aria-hidden="true" />
              {sourceRecord}
            </span>
          ) : null}
          {fingerprint ? (
            <span
              className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-[var(--border-default)] bg-[var(--surface-subtle)] px-2 py-1 font-mono text-[var(--text-secondary)]"
              title={fingerprint}
            >
              SHA-256 {fingerprint.slice(0, 12)}
            </span>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-4 sm:p-5">
        <section aria-labelledby="identity-comparison-title">
          <div className="mb-2 flex items-center gap-2">
            <GitCompareArrows
              className="h-4 w-4 text-brand-primary"
              aria-hidden="true"
            />
            <h3
              id="identity-comparison-title"
              className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]"
            >
              Submitted → resolved
            </h3>
          </div>
          <div
            className={cn(
              "grid gap-3 rounded-lg border p-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center",
              comparisonAttention
                ? "border-warning/35 bg-warning/[0.05]"
                : "border-success/25 bg-success/[0.04]",
            )}
          >
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                Submitted {asString(data.input_type, "identifier")}
              </p>
              <p className="mt-1 font-mono text-xs leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                {asString(comparison.submitted_value)}
              </p>
            </div>
            <ArrowRight
              className="hidden h-4 w-4 text-[var(--text-tertiary)] sm:block"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                Resolved identity
              </p>
              <p className="mt-1 text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                {asString(resolved.name)}
              </p>
              {asString(comparison.resolved_value, "") !==
              asString(resolved.name, "") ? (
                <p className="mt-1 font-mono text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                  {asString(comparison.resolved_value)}
                </p>
              ) : null}
            </div>
            <div className="sm:col-span-3">
              <p
                className={cn(
                  "inline-flex items-center gap-1.5 text-xs font-semibold",
                  comparisonAttention ? "text-warning" : "text-success",
                )}
              >
                {comparisonAttention ? (
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {COMPARISON_LABELS[asString(comparison.outcome, "")] ??
                  "Manual comparison required"}
              </p>
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                {asString(comparison.detail)}
              </p>
            </div>
          </div>
        </section>

        <section
          aria-labelledby="resolved-record-title"
          className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-subtle)] p-3"
        >
          <div className="mb-3 flex items-center gap-2">
            <BadgeCheck
              className="h-4 w-4 text-brand-primary"
              aria-hidden="true"
            />
            <h3
              id="resolved-record-title"
              className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]"
            >
              Canonical record
            </h3>
          </div>
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <IdentityValue
              label="Canonical SMILES"
              value={asString(resolved.canonical_smiles)}
              mono
            />
            <IdentityValue
              label="InChIKey"
              value={asString(resolved.inchi_key)}
              mono
            />
            <IdentityValue
              label="Formula / mass"
              value={`${asString(resolved.molecular_formula)} · ${molecularWeight}`}
            />
            <IdentityValue
              label="Compound class"
              value={asString(resolved.compound_type).replaceAll("_", " ")}
            />
            <IdentityValue
              label="CAS records"
              value={
                stringList(resolved.cas_numbers).join(", ") || "Not returned"
              }
              mono
            />
            <IdentityValue
              label="Declared product form"
              value={asString(data.product_form_declaration, "Not declared")}
            />
          </dl>
        </section>

        <section aria-labelledby="search-envelope-title">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Search
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              <h3
                id="search-envelope-title"
                className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]"
              >
                Exact search envelope
              </h3>
            </div>
            <span className="text-xs tabular-nums text-[var(--text-tertiary)]">
              {searchLanes.filter((lane) => asBoolean(lane.enabled)).length}/
              {searchLanes.length} lanes active
            </span>
          </div>
          <div className="max-h-56 space-y-2 overflow-y-auto overscroll-contain pr-1">
            {searchLanes.map((lane, index) => {
              const values = stringList(lane.values);
              const enabled = asBoolean(lane.enabled);
              return (
                <article
                  key={asString(lane.lane_id, `lane-${index}`)}
                  className={cn(
                    "rounded-lg border p-3",
                    enabled
                      ? "border-[var(--border-emphasis)] bg-[var(--surface-card)]"
                      : "border-[var(--border-subtle)] bg-[var(--surface-muted)] opacity-75",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-[var(--text-primary)]">
                        {asString(lane.label)}
                      </p>
                      <p className="mt-1 font-mono text-xs leading-4 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                        {values.slice(0, 3).join(" · ")}
                        {Number(lane.total_value_count ?? values.length) >
                        values.slice(0, 3).length
                          ? ` · +${Number(lane.total_value_count) - values.slice(0, 3).length} more`
                          : ""}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "shrink-0 rounded-md border px-1.5 py-0.5 text-xs font-semibold uppercase tracking-[0.08em]",
                        enabled
                          ? "border-success/25 bg-success/10 text-success"
                          : "border-[var(--border-default)] text-[var(--text-tertiary)]",
                      )}
                    >
                      {enabled ? "Active" : "Source off"}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-4 text-[var(--text-tertiary)]">
                    {asString(lane.purpose)} Sources:{" "}
                    {stringList(lane.sources).join(", ") || "Not configured"}.
                  </p>
                </article>
              );
            })}
          </div>
        </section>

        <section aria-labelledby="variant-review-title">
          <div className="mb-2 flex items-center gap-2">
            <Layers3
              className="h-4 w-4 text-brand-primary"
              aria-hidden="true"
            />
            <h3
              id="variant-review-title"
              className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]"
            >
              Variant coverage and limits
            </h3>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {variants.map((variant, index) => {
              const needsAttention = asBoolean(variant.requires_attention);
              const declaredValue = asString(variant.declared_value, "");
              const derivedValue = asString(variant.derived_value, "");
              return (
                <article
                  key={asString(variant.variant, `variant-${index}`)}
                  className={cn(
                    "rounded-lg border p-3",
                    needsAttention
                      ? "border-warning/30 bg-warning/[0.04]"
                      : "border-[var(--border-default)] bg-[var(--surface-subtle)]",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-semibold text-[var(--text-primary)]">
                      {asString(variant.label)}
                    </p>
                    <span
                      className={cn(
                        "shrink-0 text-xs font-semibold uppercase tracking-[0.08em]",
                        needsAttention
                          ? "text-warning"
                          : "text-[var(--text-tertiary)]",
                      )}
                    >
                      {VARIANT_STATUS_LABELS[asString(variant.status, "")] ??
                        asString(variant.status)}
                    </span>
                  </div>
                  {declaredValue || derivedValue ? (
                    <p className="mt-1 font-mono text-xs leading-4 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                      {declaredValue || derivedValue}
                    </p>
                  ) : null}
                  <p className="mt-2 text-xs leading-4 text-[var(--text-secondary)]">
                    {asString(variant.search_effect)}
                  </p>
                  <p className="mt-1 text-xs leading-4 text-[var(--text-tertiary)]">
                    Limit: {asString(variant.limitation)}
                  </p>
                </article>
              );
            })}
          </div>
        </section>

        <label
          htmlFor={attestationId}
          className="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-brand-primary/25 bg-brand-primary/[0.05] p-3 focus-within:ring-2 focus-within:ring-brand-primary/70 focus-within:ring-offset-2 focus-within:ring-offset-[var(--bg-base)]"
        >
          <input
            id={attestationId}
            type="checkbox"
            checked={attested}
            onChange={(event) => setAttested(event.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-brand-primary focus-visible:outline-none"
          />
          <span className="text-xs leading-5 text-[var(--text-primary)]">
            {asString(data.approval_attestation)}
          </span>
        </label>

        <div className="grid gap-2 min-[420px]:grid-cols-2">
          <Button
            onClick={onApprove}
            className="min-h-11 w-full gap-2"
            disabled={isSubmitting || !attested || !authoritative}
          >
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            Approve identity &amp; start search
          </Button>
          <Button
            variant="outline"
            onClick={onReject}
            className="min-h-11 w-full gap-2 border-error/30 text-error hover:bg-error/5"
            disabled={isSubmitting}
          >
            <XCircle className="h-4 w-4" aria-hidden="true" />
            Reject identity &amp; stop
          </Button>
        </div>
        {!authoritative ? (
          <p
            className="flex items-start gap-2 text-xs leading-5 text-error"
            role="alert"
          >
            <CircleAlert
              className="mt-0.5 h-4 w-4 shrink-0"
              aria-hidden="true"
            />
            Approval is unavailable because no authoritative PubChem or FDA
            Purple Book record is bound to this result.
          </p>
        ) : null}
        {errorMessage ? (
          <p className="text-xs text-error" role="alert">
            {errorMessage}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
