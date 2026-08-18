"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Globe2,
  Loader2,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  useExternalSharingPolicy,
  useUpdateExternalSharingPolicy,
} from "@/hooks/use-external-sharing-policy";
import type {
  ExternalSharingPolicyMode,
  ExternalSharingPolicyUpdate,
} from "@/hooks/use-external-sharing-policy";
import { APIError, isAuthBoundaryError } from "@/lib/api-client";
import { useToastStore } from "@/stores/toast-store";

function splitDomains(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\s,]+/)
        .map((domain) => domain.trim())
        .filter(Boolean),
    ),
  );
}

function firstInvalidDomain(domains: string[]): string | null {
  return (
    domains.find(
      (domain) =>
        domain.includes("*") ||
        domain.startsWith(".") ||
        domain.includes("://") ||
        domain.includes("@") ||
        domain.includes("/") ||
        domain.includes("\\") ||
        !domain.replace(/\.$/, "").includes("."),
    ) ?? null
  );
}

export function ExternalSharingPolicyCard() {
  const { data, error, isLoading, refetch } = useExternalSharingPolicy();
  const updatePolicy = useUpdateExternalSharingPolicy();
  const { addToast } = useToastStore();
  const [expanded, setExpanded] = useState(false);
  const [draftMode, setDraftMode] = useState<ExternalSharingPolicyMode | null>(
    null,
  );
  const [draftDomainText, setDraftDomainText] = useState<string | null>(null);
  const [reviewingDestructiveChange, setReviewingDestructiveChange] =
    useState(false);
  const [authoritativePreview, setAuthoritativePreview] =
    useState<ExternalSharingPolicyUpdate | null>(null);
  const reviewTriggerRef = useRef<HTMLButtonElement>(null);
  const cancelReviewRef = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const accessRestricted = isAuthBoundaryError(error);
  const policy = accessRestricted ? undefined : data;
  const mode = draftMode ?? policy?.mode ?? "open";
  const domainText =
    draftDomainText ?? policy?.approved_domains.join("\n") ?? "";
  const domains = useMemo(() => splitDomains(domainText), [domainText]);
  const invalidDomain = firstInvalidDomain(domains);

  useEffect(() => {
    if (reviewingDestructiveChange) cancelReviewRef.current?.focus();
  }, [reviewingDestructiveChange]);

  const cancelDestructiveReview = () => {
    setReviewingDestructiveChange(false);
    setAuthoritativePreview(null);
    window.setTimeout(() => reviewTriggerRef.current?.focus(), 0);
  };

  const savePolicy = (confirmDestructive: boolean, proposalDigest?: string) => {
    if (!policy || invalidDomain || updatePolicy.isPending) return;
    updatePolicy.mutate(
      {
        mode,
        approved_domains: mode === "open" ? [] : domains,
        expected_version: policy.version,
        confirm_destructive: confirmDestructive,
        ...(proposalDigest ? { proposal_digest: proposalDigest } : {}),
      },
      {
        onSuccess: (updated: ExternalSharingPolicyUpdate) => {
          if (updated.status === "confirmation_required") {
            setAuthoritativePreview(updated);
            setReviewingDestructiveChange(true);
            return;
          }
          const expectedRevocations = confirmDestructive
            ? updated.impact.total_grant_count
            : 0;
          if (
            expectedRevocations > 0 &&
            updated.revoked_grant_count !== expectedRevocations
          ) {
            setDraftMode(null);
            setDraftDomainText(null);
            setReviewingDestructiveChange(false);
            setAuthoritativePreview(null);
            void refetch();
            addToast(
              "Policy enforcement returned inconsistent recipient-impact counts. The authoritative policy is being reloaded before any success is claimed.",
              "error",
            );
            return;
          }
          setDraftMode(updated.mode);
          setDraftDomainText(updated.approved_domains.join("\n"));
          setReviewingDestructiveChange(false);
          setAuthoritativePreview(null);
          const suffix =
            updated.revoked_grant_count > 0
              ? ` ${updated.revoked_grant_count} disallowed grant${updated.revoked_grant_count === 1 ? " was" : "s were"} revoked.`
              : " No active grants required revocation.";
          window.setTimeout(() => {
            const trigger = reviewTriggerRef.current;
            if (trigger && !trigger.disabled) trigger.focus();
            else cardRef.current?.focus();
            addToast(`External sharing policy enforced.${suffix}`, "success");
          }, 0);
        },
        onError: (mutationError) => {
          if (
            mutationError instanceof APIError &&
            mutationError.status === 409
          ) {
            setDraftMode(null);
            setDraftDomainText(null);
            setReviewingDestructiveChange(false);
            setAuthoritativePreview(null);
            void refetch();
            addToast(
              "Policy version or recipient impact changed while you were reviewing. The latest authoritative state is being reloaded; review it before retrying.",
              "error",
            );
            return;
          }
          setDraftMode(null);
          setDraftDomainText(null);
          setReviewingDestructiveChange(false);
          setAuthoritativePreview(null);
          void refetch();
          addToast(
            "Policy update outcome could not be confirmed. The authoritative policy is being reloaded; review it before retrying.",
            "error",
          );
        },
      },
    );
  };

  const statusUnavailable = Boolean(error && !policy);
  const changed =
    Boolean(policy) &&
    (mode !== policy?.mode ||
      JSON.stringify(mode === "open" ? [] : domains) !==
        JSON.stringify(policy?.approved_domains ?? []));
  const destructiveChange =
    policy !== undefined &&
    mode === "approved_domains_only" &&
    (policy.mode === "open" ||
      policy.approved_domains.some((domain) => !domains.includes(domain)));

  return (
    <Card
      ref={cardRef}
      id="external-sharing-policy"
      className="scroll-mt-20"
      tabIndex={-1}
    >
      <CardHeader className="flex flex-col gap-4 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <ShieldCheck
            className="h-5 w-5 flex-none text-[var(--text-tertiary)]"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <CardTitle
              className="text-sm leading-snug"
              role="heading"
              aria-level={3}
            >
              External recipient domains
            </CardTitle>
            <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">
              Admin-enforced policy for mailbox-bound report invitations
            </p>
          </div>
        </div>
        <div className="flex flex-none flex-wrap items-center gap-3">
          {isLoading ? (
            <Loader2
              className="h-4 w-4 animate-spin text-[var(--text-tertiary)] motion-reduce:animate-none"
              aria-label="Loading external sharing policy"
            />
          ) : statusUnavailable ? (
            <Badge variant="secondary" className="gap-1">
              <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              Unavailable
            </Badge>
          ) : policy?.mode === "approved_domains_only" ? (
            <Badge variant="success" className="gap-1">
              <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
              Approved domains only
            </Badge>
          ) : (
            <Badge variant="secondary">Any valid domain</Badge>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11 gap-1"
            onClick={() => setExpanded((current) => !current)}
            aria-expanded={expanded}
            aria-controls="external-sharing-policy-details"
          >
            {expanded ? (
              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {expanded ? "Hide" : "Manage"}
          </Button>
        </div>
      </CardHeader>

      {expanded ? (
        <CardContent
          id="external-sharing-policy-details"
          className="space-y-5 pt-0"
          role="region"
          aria-label="External sharing policy details"
        >
          {error ? (
            <div
              role="alert"
              className="rounded-lg border border-error/20 bg-error/10 px-4 py-3"
            >
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {accessRestricted
                  ? "External sharing policy restricted"
                  : "External sharing policy unavailable"}
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                {accessRestricted
                  ? "Your current session cannot view or update this organization policy. Cached policy details are hidden."
                  : "The current policy could not be confirmed, so policy changes stay locked and no access state is inferred."}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-3 min-h-11 gap-2"
                onClick={() => void refetch()}
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Retry policy load
              </Button>
            </div>
          ) : null}

          {policy && !isLoading ? (
            <>
              <fieldset className="space-y-3">
                <legend className="text-sm font-semibold text-[var(--text-primary)]">
                  Who can receive external reports?
                </legend>
                <label className="relative flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-[var(--border-default)] p-3">
                  <input
                    type="radio"
                    name="external-sharing-mode"
                    value="open"
                    checked={mode === "open"}
                    onChange={() => {
                      setDraftMode("open");
                      setReviewingDestructiveChange(false);
                      setAuthoritativePreview(null);
                    }}
                    disabled={updatePolicy.isPending}
                    className="absolute inset-0 z-10 h-full w-full cursor-pointer appearance-none rounded-lg opacity-0 focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 disabled:cursor-not-allowed"
                  />
                  <span
                    aria-hidden="true"
                    className="mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-[var(--border-emphasis)]"
                  >
                    {mode === "open" ? (
                      <span className="h-2 w-2 rounded-full bg-brand-primary" />
                    ) : null}
                  </span>
                  <span>
                    <span className="block text-sm font-semibold text-[var(--text-primary)]">
                      Any valid recipient domain
                    </span>
                    <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                      Every invitation remains mailbox-verified, report-bound,
                      view-limited, and revocable.
                    </span>
                  </span>
                </label>
                <label className="relative flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-[var(--border-default)] p-3">
                  <input
                    type="radio"
                    name="external-sharing-mode"
                    value="approved_domains_only"
                    checked={mode === "approved_domains_only"}
                    onChange={() => {
                      setDraftMode("approved_domains_only");
                      setReviewingDestructiveChange(false);
                      setAuthoritativePreview(null);
                    }}
                    disabled={updatePolicy.isPending}
                    className="absolute inset-0 z-10 h-full w-full cursor-pointer appearance-none rounded-lg opacity-0 focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 disabled:cursor-not-allowed"
                  />
                  <span
                    aria-hidden="true"
                    className="mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-[var(--border-emphasis)]"
                  >
                    {mode === "approved_domains_only" ? (
                      <span className="h-2 w-2 rounded-full bg-brand-primary" />
                    ) : null}
                  </span>
                  <span>
                    <span className="block text-sm font-semibold text-[var(--text-primary)]">
                      Approved exact domains only
                    </span>
                    <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                      Subdomains are separate domains. Wildcards and suffix
                      rules are never accepted.
                    </span>
                  </span>
                </label>
              </fieldset>

              {mode === "approved_domains_only" ? (
                <div>
                  <label
                    htmlFor="external-sharing-domains"
                    className="mb-1.5 flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]"
                  >
                    <Globe2 className="h-4 w-4" aria-hidden="true" />
                    Approved domains
                  </label>
                  <Textarea
                    id="external-sharing-domains"
                    value={domainText}
                    onChange={(event) => {
                      setDraftDomainText(event.target.value);
                      setReviewingDestructiveChange(false);
                      setAuthoritativePreview(null);
                    }}
                    placeholder={"outside-counsel.com\npartner-biotech.example"}
                    rows={4}
                    disabled={updatePolicy.isPending}
                    error={Boolean(invalidDomain)}
                    errorId="external-sharing-domain-error"
                    errorMessage={
                      invalidDomain
                        ? `${invalidDomain} is not an exact fully qualified domain.`
                        : undefined
                    }
                  />
                  <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                    One domain per line or comma separated. Unicode domains are
                    normalized to exact IDNA form by the server.
                  </p>
                  {domains.length === 0 ? (
                    <p className="mt-2 rounded-lg border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                      An empty approved list blocks all new invitations and
                      revokes every active external grant.
                    </p>
                  ) : null}
                </div>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-4">
                <p className="max-w-2xl text-xs leading-5 text-[var(--text-secondary)]">
                  Tightening this policy immediately revokes disallowed active
                  grants and invalidates their verification codes and access
                  proofs.
                </p>
                {reviewingDestructiveChange ? (
                  <div
                    className="w-full space-y-3 rounded-lg border border-error/25 bg-error/10 p-4"
                    role="alertdialog"
                    aria-modal="false"
                    aria-labelledby="external-sharing-confirmation-title"
                    aria-describedby="external-sharing-confirmation-description"
                  >
                    <div>
                      <p
                        id="external-sharing-confirmation-title"
                        className="text-sm font-semibold text-[var(--text-primary)]"
                      >
                        Confirm destructive policy enforcement
                      </p>
                      <p
                        id="external-sharing-confirmation-description"
                        className="mt-1 text-xs leading-5 text-[var(--text-secondary)]"
                      >
                        The locked server preview found exactly{" "}
                        <strong>
                          {authoritativePreview?.impact.active_grant_count ?? 0}
                        </strong>{" "}
                        active and{" "}
                        <strong>
                          {authoritativePreview?.impact.pending_grant_count ??
                            0}
                        </strong>{" "}
                        delivery-pending grants ({" "}
                        {authoritativePreview?.impact.total_grant_count ?? 0}{" "}
                        total). They will be revoked immediately and their
                        verification codes and access proofs invalidated.
                      </p>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button
                        ref={cancelReviewRef}
                        type="button"
                        variant="ghost"
                        className="min-h-11"
                        onClick={cancelDestructiveReview}
                        disabled={updatePolicy.isPending}
                      >
                        Cancel policy change
                      </Button>
                      <Button
                        type="button"
                        variant="destructive"
                        className="min-h-11"
                        onClick={() =>
                          savePolicy(
                            true,
                            authoritativePreview?.proposal_digest ?? undefined,
                          )
                        }
                        loading={updatePolicy.isPending}
                        disabled={
                          Boolean(invalidDomain) ||
                          updatePolicy.isPending ||
                          !authoritativePreview?.proposal_digest
                        }
                      >
                        Confirm and enforce policy
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Button
                    ref={reviewTriggerRef}
                    type="button"
                    className="min-h-11"
                    onClick={() => {
                      if (destructiveChange) {
                        savePolicy(false);
                        return;
                      }
                      savePolicy(false);
                    }}
                    loading={updatePolicy.isPending}
                    disabled={
                      !changed ||
                      Boolean(invalidDomain) ||
                      updatePolicy.isPending
                    }
                  >
                    {destructiveChange
                      ? "Review and enforce policy"
                      : "Save and enforce policy"}
                  </Button>
                )}
              </div>
            </>
          ) : null}
        </CardContent>
      ) : null}
    </Card>
  );
}
