"use client";

import { useRef, useState } from "react";
import { CalendarClock, ShieldCheck, X } from "lucide-react";
import { useCreateAPIKey } from "@/hooks/use-api-keys";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import type {
  APIKeyResponse,
  APIKeyScope,
  CreateAPIKeyPayload,
} from "@/hooks/use-api-keys";
import { useMutationRecovery } from "@/hooks/use-mutation-recovery";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MutationRecoveryNotice } from "@/components/shared/mutation-recovery-notice";

interface CreateApiKeyFormProps {
  existingKeyIds: string[];
  onClose: () => void;
  onCreated: (key: string) => void;
  onRefreshKeys: () => Promise<APIKeyResponse[]>;
  onReconciledCreation: (key: APIKeyResponse) => void;
}

const DEFAULT_SCOPES: APIKeyScope[] = ["analyses:read", "reports:read"];

const SCOPE_OPTIONS: Array<{
  value: APIKeyScope;
  label: string;
  detail: string;
}> = [
  {
    value: "analyses:read",
    label: "Read analyses",
    detail: "List cases, status, and matter metadata.",
  },
  {
    value: "analyses:write",
    label: "Create analyses",
    detail: "Start new FTO runs from approved systems.",
  },
  {
    value: "reports:read",
    label: "Read reports",
    detail: "Retrieve decision packets and evidence summaries.",
  },
  {
    value: "reports:export",
    label: "Export reports",
    detail: "Generate governed PDF, CSV, XLSX, and JSON exports.",
  },
  {
    value: "monitors:manage",
    label: "Manage monitors",
    detail: "Create and update patent-monitoring jobs.",
  },
];

const EXPIRY_OPTIONS = [
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
  { value: 180, label: "180 days" },
  { value: 365, label: "365 days" },
];

export function CreateApiKeyForm({
  existingKeyIds,
  onClose,
  onCreated,
  onRefreshKeys,
  onReconciledCreation,
}: CreateApiKeyFormProps) {
  const [name, setName] = useState("");
  const [selectedScopes, setSelectedScopes] =
    useState<APIKeyScope[]>(DEFAULT_SCOPES);
  const [expiryDays, setExpiryDays] = useState(90);
  const [createSubmitted, setCreateSubmitted] = useState(false);
  const [refreshSubmitted, setRefreshSubmitted] = useState(false);
  const createKey = useCreateAPIKey();
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const createRecovery = useMutationRecovery<CreateAPIKeyPayload>();
  const baselineKeyIdsRef = useRef<Set<string> | null>(null);
  const createRequestPending = createKey.isPending || createSubmitted;
  const controlsLocked =
    createRequestPending ||
    refreshSubmitted ||
    Boolean(createRecovery.recovery);
  const canSubmit = name.trim().length > 0 && selectedScopes.length > 0;
  const scopeOptions = principal.data?.api_key_report_export_scope_available
    ? SCOPE_OPTIONS
    : SCOPE_OPTIONS.filter((option) => option.value !== "reports:export");

  const toggleScope = (scope: APIKeyScope) => {
    setSelectedScopes((current) =>
      current.includes(scope)
        ? current.filter((item) => item !== scope)
        : [...current, scope],
    );
  };

  function submitCreate(payload: CreateAPIKeyPayload) {
    createRecovery.clearRecovery();
    const attempt = createRecovery.beginAttempt();
    baselineKeyIdsRef.current = new Set(existingKeyIds);
    setCreateSubmitted(true);
    createKey.mutate(payload, {
      onSuccess: (data) => {
        if (!createRecovery.clearRecoveryForAttempt(attempt)) return;
        onCreated(data.secret_key);
      },
      onError: (mutationError) => {
        console.error("[CreateApiKeyForm] Failed to create API key");
        createRecovery.captureFailure(mutationError, payload, attempt);
      },
      onSettled: () => {
        setCreateSubmitted(false);
      },
    });
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit || controlsLocked) return;
    submitCreate({
      name: name.trim(),
      scopes: selectedScopes,
      expires_at: new Date(Date.now() + expiryDays * 86_400_000).toISOString(),
    });
  };

  async function refreshKeysBeforeAnotherCreate() {
    const recovery = createRecovery.recovery;
    if (!recovery) return;
    const attempt = createRecovery.beginAttempt();
    setRefreshSubmitted(true);
    try {
      const keys = await onRefreshKeys();
      if (!createRecovery.isAttemptCurrent(attempt)) return;
      const matchingKey = findReconciledAPIKey(
        keys,
        recovery.variables,
        baselineKeyIdsRef.current,
      );
      if (matchingKey) {
        createRecovery.clearRecoveryForAttempt(attempt);
        onReconciledCreation(matchingKey);
        return;
      }
      createRecovery.clearRecoveryForAttempt(attempt);
    } catch {
      // Keep the outcome-unknown notice visible until the ledger refreshes.
    } finally {
      setRefreshSubmitted(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm" role="heading" aria-level={3}>
            Create new API key
          </CardTitle>
          <button
            type="button"
            onClick={onClose}
            disabled={controlsLocked}
            aria-label="Close create API key form"
            className="flex h-11 w-11 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] disabled:pointer-events-none disabled:opacity-50"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </CardHeader>
      <CardContent>
        {createRecovery.recovery ? (
          <div className="mb-5">
            <MutationRecoveryNotice
              actionLabel={
                createRecovery.recovery.mode === "outcome-unknown"
                  ? "Refresh API key ledger"
                  : "Review request"
              }
              actionPending={refreshSubmitted}
              dataTestId="api-key-create-recovery"
              description={
                createRecovery.recovery.mode === "outcome-unknown"
                  ? "Praviar could not confirm whether the key was created. Refresh the API key ledger before generating another key. If creation committed, the one-time secret cannot be recovered and the new key should be revoked before replacement."
                  : "The API key request was rejected before a key was returned. Review the preserved name, scope, and expiry before submitting again."
              }
              mode={createRecovery.recovery.mode}
              onAction={() => {
                if (createRecovery.recovery?.mode === "outcome-unknown") {
                  void refreshKeysBeforeAnotherCreate();
                } else {
                  createRecovery.clearRecovery();
                }
              }}
              title={
                createRecovery.recovery.mode === "outcome-unknown"
                  ? "API key creation outcome unconfirmed"
                  : "API key was not created"
              }
            />
          </div>
        ) : null}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label
              htmlFor="api-key-name"
              className="mb-1 block type-label-sm text-[var(--text-secondary)]"
            >
              Key Name
            </label>
            <input
              id="api-key-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g., Production API, CI/CD Pipeline"
              disabled={controlsLocked}
              className="h-11 w-full rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 type-caption text-[var(--text-tertiary)]">
              Choose a descriptive name to identify this key later
            </p>
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <div>
              <label
                htmlFor="api-key-expiry"
                className="mb-1 flex items-center gap-2 type-label-sm text-[var(--text-secondary)]"
              >
                <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
                Expiry
              </label>
              <select
                id="api-key-expiry"
                value={expiryDays}
                onChange={(event) => setExpiryDays(Number(event.target.value))}
                disabled={controlsLocked}
                className="h-11 w-full rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {EXPIRY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 type-caption text-[var(--text-tertiary)]">
                Keys expire automatically and can be revoked sooner.
              </p>
            </div>
            <div
              className="rounded-lg border border-brand-primary/20 bg-brand-primary/10 p-3"
              aria-live="polite"
            >
              <div className="flex items-start gap-2">
                <ShieldCheck
                  className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {selectedScopes.length} scoped permission
                    {selectedScopes.length === 1 ? "" : "s"}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                    Select only the work this automation needs for the next{" "}
                    {expiryDays} days.
                  </p>
                </div>
              </div>
            </div>
          </div>
          <fieldset className="space-y-2">
            <legend className="type-label-sm text-[var(--text-secondary)]">
              Scope
            </legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {scopeOptions.map((scope) => {
                const checked = selectedScopes.includes(scope.value);
                return (
                  <label
                    key={scope.value}
                    className={`flex min-h-[5.5rem] cursor-pointer gap-3 rounded-lg border p-3 transition-colors ${
                      checked
                        ? "border-brand-primary/35 bg-brand-primary/10"
                        : "border-[var(--border-subtle)] bg-[var(--surface-muted)]/65 hover:border-[var(--border-emphasis)]"
                    } ${controlsLocked ? "cursor-not-allowed opacity-60" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={controlsLocked}
                      onChange={() => toggleScope(scope.value)}
                      aria-label={`Toggle ${scope.label} scope`}
                      className="mt-1 h-4 w-4 rounded border-[var(--border-emphasis)] accent-[var(--brand-primary)]"
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-[var(--text-primary)]">
                        {scope.label}
                      </span>
                      <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">
                        {scope.detail}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11"
              onClick={onClose}
              disabled={controlsLocked}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              className="min-h-11"
              loading={createRequestPending}
              disabled={!canSubmit || controlsLocked}
            >
              Generate Key
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function findReconciledAPIKey(
  keys: APIKeyResponse[],
  payload: CreateAPIKeyPayload,
  baselineKeyIds: ReadonlySet<string> | null,
): APIKeyResponse | null {
  if (baselineKeyIds === null) return null;
  const expectedScopes = [...payload.scopes].sort().join("|");
  const expectedExpiry = Date.parse(payload.expires_at);

  return (
    keys.find((key) => {
      const expiresAt = Date.parse(key.expires_at);
      return (
        !key.revoked &&
        !baselineKeyIds.has(key.id) &&
        key.name === payload.name &&
        [...key.scopes].sort().join("|") === expectedScopes &&
        Number.isFinite(expectedExpiry) &&
        Number.isFinite(expiresAt) &&
        Math.abs(expiresAt - expectedExpiry) <= 1_000
      );
    }) ?? null
  );
}
