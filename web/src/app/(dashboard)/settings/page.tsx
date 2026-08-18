"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { ApiKeysTable } from "@/components/settings/api-keys-table";
import { CreateApiKeyForm } from "@/components/settings/create-api-key-form";
import { ExternalSharingPolicyCard } from "@/components/settings/external-sharing-policy-card";
import { MutationRecoveryNotice } from "@/components/shared/mutation-recovery-notice";
import { NewApiKeyDisplay } from "@/components/settings/new-api-key-display";
import { SettingsAccessPostureStrip } from "@/components/settings/settings-access-posture-strip";
import { SettingsGovernanceRail } from "@/components/settings/settings-governance-rail";
import { SettingsPageHeader } from "@/components/settings/settings-page-header";
import { SettingsSummaryCards } from "@/components/settings/settings-summary-cards";
import { SSOSettings } from "@/components/settings/sso-settings";
import { AccountControlStatusState } from "@/components/shared/account-control-status-state";
import {
  hasClerk,
  isAdminOrgRole,
} from "@/components/layout/sidebar-constants";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { useAPIKeys, useRevokeAPIKey } from "@/hooks/use-api-keys";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import type { APIKeyResponse } from "@/hooks/use-api-keys";
import { useMutationRecovery } from "@/hooks/use-mutation-recovery";
import {
  isAPIKeyExpired,
  isAPIKeyExpiringSoon,
} from "@/components/settings/helpers";
import { isAuthBoundaryError } from "@/lib/api-client";

function reportAPIKeySettingsAccessRestriction() {
  console.error("[SettingsPage] API key settings access restricted");
}

function reportAPIKeySettingsLoadFailure() {
  console.error("[SettingsPage] Failed to load API key settings");
}

export default function SettingsPage() {
  if (hasClerk) {
    return <ClerkScopedSettingsPage />;
  }

  return <SettingsPageContent />;
}

function ClerkScopedSettingsPage() {
  const { isLoaded, orgRole } = useAuth();

  if (!isLoaded) {
    return <SettingsAccessState variant="auth" />;
  }

  if (!isAdminOrgRole(orgRole)) {
    return <SettingsAccessState variant="restricted" />;
  }

  return <SettingsPageContent />;
}

function SettingsAccessState({ variant }: { variant: "auth" | "restricted" }) {
  return (
    <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
      <SettingsPageHeader actionsDisabled onToggleCreate={() => undefined} />
      <AccountControlStatusState surface="settings" variant={variant} />
    </div>
  );
}

function SettingsPageContent() {
  const token = useAuthToken();
  const { data, isLoading, isFetching, error, refetch } = useAPIKeys();
  const revokeKey = useRevokeAPIKey();
  const revokeRecovery = useMutationRecovery<string>();
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);
  const [pendingRevokeId, setPendingRevokeId] = useState<string | null>(null);
  const [reconciledCreation, setReconciledCreation] =
    useState<APIKeyResponse | null>(null);
  useAuthBoundaryReset(() => {
    setShowCreate(false);
    setNewKey(null);
    setConfirmRevoke(null);
    setPendingRevokeId(null);
    setReconciledCreation(null);
  });
  const accessRestricted = isAuthBoundaryError(error);
  const authPending = !token && !data;
  const settingsLoadFailed = Boolean(
    !isLoading && !authPending && error && !data && !accessRestricted,
  );

  useErrorDiagnostic(
    !isLoading && !authPending && accessRestricted,
    error,
    reportAPIKeySettingsAccessRestriction,
  );
  useErrorDiagnostic(
    settingsLoadFailed,
    error,
    reportAPIKeySettingsLoadFailure,
  );

  const identitySignOnSection = (
    <section
      key="identity-sign-on"
      className="min-w-0 space-y-3"
      aria-labelledby="identity-sign-on-heading"
    >
      <div>
        <h2
          id="identity-sign-on-heading"
          className="type-heading-sm text-[var(--text-primary)]"
        >
          Identity & Sign-On
        </h2>
        <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
          Manage enterprise SSO handoff and enrolled identity domains.
        </p>
      </div>
      <SSOSettings />
    </section>
  );
  const externalCollaborationSection = (
    <section
      key="external-collaboration"
      className="min-w-0 space-y-3"
      aria-labelledby="external-collaboration-heading"
    >
      <div>
        <h2
          id="external-collaboration-heading"
          className="type-heading-sm text-[var(--text-primary)]"
        >
          External Collaboration
        </h2>
        <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
          Govern which exact recipient domains may receive external report
          invitations.
        </p>
      </div>
      <ExternalSharingPolicyCard />
    </section>
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <SettingsPageHeader
          actionsDisabled
          onToggleCreate={() => setShowCreate((current) => !current)}
        />
        <AccountControlStatusState surface="settings" variant="loading" />
      </div>
    );
  }

  if (authPending) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <SettingsPageHeader
          actionsDisabled
          onToggleCreate={() => setShowCreate((current) => !current)}
        />
        <AccountControlStatusState surface="settings" variant="auth" />
      </div>
    );
  }

  if (accessRestricted) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <SettingsPageHeader
          actionsDisabled
          onToggleCreate={() => setShowCreate((current) => !current)}
        />
        <AccountControlStatusState
          surface="settings"
          variant="restricted"
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <SettingsPageHeader
          actionsDisabled
          onToggleCreate={() => setShowCreate((current) => !current)}
        />
        <div className="grid min-w-0 gap-6">
          <div className="min-w-0 space-y-6">
            <section
              className="min-w-0 space-y-4"
              aria-labelledby="access-automation-heading"
            >
              <div>
                <h2
                  id="access-automation-heading"
                  className="type-heading-sm text-[var(--text-primary)]"
                >
                  Access & Automation
                </h2>
                <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
                  API key controls are isolated while identity and external
                  collaboration controls remain available.
                </p>
              </div>
              <AccountControlStatusState
                surface="settings"
                variant="temporary"
                onRetry={() => {
                  void refetch();
                }}
              />
            </section>
            {identitySignOnSection}
            {externalCollaborationSection}
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <SettingsPageHeader
          actionsDisabled
          onToggleCreate={() => setShowCreate((current) => !current)}
        />
        <AccountControlStatusState surface="settings" variant="auth" />
      </div>
    );
  }

  const expiredKeys = data.items.filter(
    (k: APIKeyResponse) => !k.revoked && isAPIKeyExpired(k.expires_at),
  );
  const expiringSoonKeys = data.items.filter(
    (k: APIKeyResponse) => !k.revoked && isAPIKeyExpiringSoon(k.expires_at),
  );
  const activeKeys = data.items.filter(
    (k: APIKeyResponse) => !k.revoked && !isAPIKeyExpired(k.expires_at),
  );
  const revokedKeys = data.items.filter((k: APIKeyResponse) => k.revoked);
  const neverUsedKeys = activeKeys.filter(
    (k: APIKeyResponse) => !k.last_used_at,
  );
  const revokeRequestInFlight = revokeKey.isPending || pendingRevokeId !== null;
  const revokeInFlight =
    revokeRequestInFlight || Boolean(revokeRecovery.recovery);
  const prioritizeApiKeyWorkflow =
    showCreate ||
    newKey !== null ||
    confirmRevoke !== null ||
    revokeInFlight ||
    reconciledCreation !== null;

  async function refreshApiKeyLedger() {
    const result = await refetch();
    if (result?.error) {
      throw result.error;
    }
    if (!result.data) {
      throw new Error("API key ledger refresh returned no authoritative data");
    }
    return result.data.items;
  }

  async function refreshAfterRevoke() {
    const attempt = revokeRecovery.beginAttempt();
    try {
      await refreshApiKeyLedger();
      revokeRecovery.clearRecoveryForAttempt(attempt);
    } catch {
      // Keep the recovery notice visible until authoritative state reloads.
    }
  }

  const accessAutomationSection = (
    <section
      key="access-automation"
      className="min-w-0 space-y-4"
      aria-labelledby="access-automation-heading"
    >
      <div>
        <h2
          id="access-automation-heading"
          className="type-heading-sm text-[var(--text-primary)]"
        >
          Access & Automation
        </h2>
        <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
          Issue, review, and revoke API keys used by approved automation.
        </p>
      </div>

      {newKey ? (
        <NewApiKeyDisplay apiKey={newKey} onDismiss={() => setNewKey(null)} />
      ) : null}

      {reconciledCreation ? (
        <MutationRecoveryNotice
          actionLabel="Review key revocation"
          actionPending={revokeRequestInFlight}
          dataTestId="api-key-create-reconciled"
          description={`The refreshed ledger contains a new key matching “${reconciledCreation.name}”. Without a server operation ID, Praviar cannot prove which creation attempt produced it or recover its one-time secret. Review the key prefix with your administrators and revoke it before generating a replacement.`}
          mode="outcome-unknown"
          onAction={() => {
            setConfirmRevoke(reconciledCreation.id);
          }}
          title="Matching API key requires review"
        />
      ) : null}

      {showCreate && !newKey ? (
        <CreateApiKeyForm
          existingKeyIds={data.items.map((key) => key.id)}
          onClose={() => setShowCreate(false)}
          onRefreshKeys={refreshApiKeyLedger}
          onReconciledCreation={(key) => {
            setReconciledCreation(key);
            setShowCreate(false);
          }}
          onCreated={(key) => {
            setNewKey(key);
            setShowCreate(false);
          }}
        />
      ) : null}

      {revokeRecovery.recovery ? (
        <MutationRecoveryNotice
          actionLabel="Refresh API key ledger"
          actionPending={isFetching}
          dataTestId="api-key-revoke-recovery"
          description={
            revokeRecovery.recovery.mode === "outcome-unknown"
              ? "Praviar could not confirm whether the key was revoked. Refresh authoritative key state before sending another revoke request."
              : "The revoke request was rejected. Refresh the API key ledger before deciding whether to try again."
          }
          dismissLabel="Keep key active"
          mode={revokeRecovery.recovery.mode}
          onAction={() => {
            void refreshAfterRevoke();
          }}
          onDismiss={
            revokeRecovery.recovery.mode === "failed"
              ? revokeRecovery.clearRecovery
              : undefined
          }
          title={
            revokeRecovery.recovery.mode === "outcome-unknown"
              ? "API key revocation outcome unconfirmed"
              : "API key was not revoked"
          }
        />
      ) : null}

      <ApiKeysTable
        items={data.items}
        confirmRevoke={confirmRevoke}
        onStartRevoke={setConfirmRevoke}
        onCancelRevoke={() => setConfirmRevoke(null)}
        onConfirmRevoke={(keyId) => {
          revokeRecovery.clearRecovery();
          const attempt = revokeRecovery.beginAttempt();
          setPendingRevokeId(keyId);
          revokeKey.mutate(keyId, {
            onSuccess: () => {
              if (!revokeRecovery.clearRecoveryForAttempt(attempt)) return;
              if (reconciledCreation?.id === keyId) {
                setReconciledCreation(null);
              }
            },
            onError: (mutationError) => {
              revokeRecovery.captureFailure(mutationError, keyId, attempt);
            },
            onSettled: () => {
              setConfirmRevoke(null);
              setPendingRevokeId(null);
            },
          });
        }}
        revokePending={revokeInFlight}
        pendingRevokeId={pendingRevokeId}
      />
    </section>
  );

  return (
    <div className="mx-auto min-w-0 max-w-6xl space-y-6 animate-fade-up">
      <SettingsPageHeader
        actionsDisabled={
          showCreate ||
          newKey !== null ||
          revokeInFlight ||
          reconciledCreation !== null
        }
        onToggleCreate={() => {
          if (reconciledCreation) return;
          setShowCreate(true);
          setNewKey(null);
        }}
      />

      <SettingsSummaryCards
        total={data.total}
        activeCount={activeKeys.length}
        revokedCount={revokedKeys.length}
        expiringSoonCount={expiringSoonKeys.length}
      />

      <SettingsAccessPostureStrip
        total={data.total}
        activeCount={activeKeys.length}
        expiredCount={expiredKeys.length}
        expiringSoonCount={expiringSoonKeys.length}
        neverUsedCount={neverUsedKeys.length}
        revokePending={revokeRequestInFlight}
        createOpen={showCreate || newKey !== null}
        refreshWarning={Boolean(error)}
      />

      <div
        className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start"
        data-testid="settings-governance-layout"
      >
        <div className="min-w-0 space-y-6">
          {prioritizeApiKeyWorkflow
            ? [accessAutomationSection, identitySignOnSection]
            : [identitySignOnSection, accessAutomationSection]}

          {externalCollaborationSection}
        </div>

        <SettingsGovernanceRail
          activeCount={activeKeys.length}
          expiredCount={expiredKeys.length}
          expiringSoonCount={expiringSoonKeys.length}
          neverUsedCount={neverUsedKeys.length}
          revokePending={revokeRequestInFlight}
          createOpen={showCreate || newKey !== null}
        />
      </div>
    </div>
  );
}
