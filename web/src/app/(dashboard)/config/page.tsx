"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { LockKeyhole } from "lucide-react";
import { apiClient, isAuthBoundaryError } from "@/lib/api-client";
import {
  pipelineConfigToStore,
  storeToPipelineConfig,
} from "@/lib/pipeline-config";
import { ConfigEditPanel } from "@/components/config/config-edit-panel";
import { ConfigHeaderActions } from "@/components/config/config-header-actions";
import { ConfigPresetGrid } from "@/components/config/config-preset-grid";
import { ConfigReadOnlySummaryCard } from "@/components/config/config-read-only-summary-card";
import {
  getCoverageBudgetLabel,
  getConfigValidationIssues,
  getEnabledSources,
} from "@/components/config/helpers";
import {
  CONFIG_POLICY_BLOCKERS_ID,
  CONFIG_POLICY_STATUS_ID,
  CONFIG_RESET_WARNING_ID,
  ConfigGovernanceRail,
  ConfigStatusStrip,
} from "@/components/config/config-workspace-status";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";
import { useOrgDefaultConfig } from "@/hooks/use-config";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { useConfigStore } from "@/stores/config-store";
import { useToastStore } from "@/stores/toast-store";
import { authScopeKey } from "@/lib/query-keys";
import {
  hasClerk,
  isAdminOrgRole,
} from "@/components/layout/sidebar-constants";

function reportConfigurationDefaultsAccessRestriction() {
  console.error("[ConfigPage] Configuration defaults access restricted");
}

export default function ConfigPage() {
  if (hasClerk) {
    return <ClerkScopedConfigPage />;
  }

  return <ConfigPageContent canManageDefaults />;
}

function ClerkScopedConfigPage() {
  const { isLoaded, orgRole } = useAuth();

  if (!isLoaded) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
        <AppSurfaceHeader
          dataTestId="config-app-surface-header"
          eyebrow="Praviar control system"
          title="Configuration"
          description="Organization-wide default coverage, source, jurisdiction, and review settings."
          mobileDensity="compact"
        />
        <OperationalStatusFrame
          contextItems={[
            "Organization role pending",
            "No policy values exposed",
            "Mutation controls locked",
          ]}
          dataTestId="config-role-status-loading"
          description="Praviar is confirming your organization role before loading policy defaults or enabling control-plane actions."
          eyebrow="Configuration access"
          headingLevel={1}
          icon={LockKeyhole}
          isPending
          recoveryBody="Configuration opens after the authenticated organization role is available."
          recoveryTitle="Confirming policy authority"
          title="Checking configuration access"
          titleId="config-role-status-loading-title"
          tone="default"
        />
      </div>
    );
  }

  return <ConfigPageContent canManageDefaults={isAdminOrgRole(orgRole)} />;
}

function ConfigPageContent({
  canManageDefaults: roleCanManageDefaults,
}: {
  canManageDefaults: boolean;
}) {
  const config = useConfigStore();
  const toast = useToastStore();
  const token = useAuthToken();
  const authScope = authScopeKey(token);
  const defaultsQuery = useOrgDefaultConfig(token);
  const canManageDefaults =
    defaultsQuery.data?.can_manage ?? roleCanManageDefaults;
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [resetPending, setResetPending] = useState(false);
  const enabledSources = getEnabledSources(config);
  const validationIssues = getConfigValidationIssues(config);
  const defaultsLoading = Boolean(token && defaultsQuery.isLoading);
  const defaultsAccessRestricted = Boolean(
    token && isAuthBoundaryError(defaultsQuery.error),
  );
  const defaultsUnavailable = Boolean(
    token &&
    defaultsQuery.isError &&
    (!defaultsQuery.data || defaultsAccessRestricted),
  );
  const defaultsHydratedForScope =
    !token || config.hydratedAuthScope === authScope;
  const awaitingScopedHydration = Boolean(
    token && !defaultsHydratedForScope && !defaultsQuery.isError,
  );
  const canSave =
    canManageDefaults &&
    Boolean(token) &&
    validationIssues.length === 0 &&
    !saving &&
    !resetPending &&
    !defaultsLoading &&
    !defaultsUnavailable &&
    defaultsHydratedForScope;
  const hasPolicyBlockers =
    validationIssues.length > 0 ||
    !token ||
    defaultsLoading ||
    awaitingScopedHydration ||
    defaultsUnavailable ||
    resetPending;
  const saveDescriptionId = hasPolicyBlockers
    ? `${CONFIG_POLICY_STATUS_ID} ${CONFIG_POLICY_BLOCKERS_ID}`
    : CONFIG_POLICY_STATUS_ID;
  const retryDefaultsLoad = () => {
    void defaultsQuery.refetch?.();
  };

  useErrorDiagnostic(
    defaultsAccessRestricted,
    defaultsQuery.error,
    reportConfigurationDefaultsAccessRestriction,
  );

  useEffect(() => {
    if (
      !token ||
      config.hydratedAuthScope === authScope ||
      defaultsQuery.isLoading ||
      defaultsQuery.isError
    ) {
      return;
    }

    if (defaultsQuery.data?.config) {
      config.hydrateConfig(
        pipelineConfigToStore(defaultsQuery.data.config),
        authScope,
      );
    }
  }, [
    authScope,
    config,
    config.hydratedAuthScope,
    defaultsQuery.data,
    defaultsQuery.isError,
    defaultsQuery.isLoading,
    token,
  ]);

  const handleArmReset = () => {
    if (!canManageDefaults) {
      return;
    }
    setResetPending(true);
    toast.addToast("Confirm reset to restore default policy values", "info");
  };

  const handleReset = () => {
    if (saving || !canManageDefaults) {
      return;
    }
    config.reset();
    setResetPending(false);
    toast.addToast("Configuration reset to defaults", "info");
  };

  const handleSaveDefaults = async () => {
    if (saving || !canManageDefaults) {
      return;
    }

    if (defaultsLoading) {
      toast.addToast("Loading organization defaults before saving", "info");
      return;
    }

    if (defaultsUnavailable) {
      toast.addToast(
        "Organization defaults could not be loaded. Existing defaults were not changed.",
        "error",
      );
      return;
    }

    if (validationIssues.length > 0) {
      setEditing(true);
      toast.addToast("Resolve configuration issues before saving", "error");
      return;
    }

    if (!token) {
      toast.addToast("Sign in to save organization defaults", "error");
      return;
    }

    setSaving(true);
    try {
      const configPayload = storeToPipelineConfig(config);
      await apiClient("/configs/defaults", {
        method: "PUT",
        token,
        body: JSON.stringify({
          ...configPayload,
          hitl_enabled: config.hitlEnabled,
          hitl_checkpoints: config.hitlCheckpoints,
          hitl_auto_skip_minutes: config.hitlAutoSkipMinutes,
        }),
      });
      setResetPending(false);
      toast.addToast("Default configuration saved", "success");
    } catch {
      toast.addToast(
        "Failed to save configuration - please try again",
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  if (defaultsAccessRestricted) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
        <AppSurfaceHeader
          dataTestId="config-app-surface-header"
          eyebrow="Praviar control system"
          title="Configuration"
          description="Organization-wide default coverage, source, jurisdiction, and review settings."
          mobileDensity="compact"
        />
        <OperationalStatusFrame
          actionLabel="Retry configuration load"
          contextItems={[
            "Cached defaults hidden",
            "No configuration values exposed",
            "Save and reset controls locked",
          ]}
          dataTestId="config-defaults-status-restricted"
          description="Your current session is not authorized to view or update organization default configuration. Cached policy values are hidden until access is confirmed again."
          eyebrow="Configuration access"
          headingLevel={1}
          icon={LockKeyhole}
          isPending={false}
          onRetry={retryDefaultsLoad}
          recoveryBody="A retry requests a fresh authorization check before organization default coverage, source, jurisdiction, and review settings are shown."
          recoveryTitle="Confirm configuration access"
          title="Configuration defaults access restricted"
          titleId="config-defaults-status-restricted-title"
          tone="error"
        />
      </div>
    );
  }

  if (defaultsLoading || awaitingScopedHydration) {
    return (
      <ConfigDefaultsBoundaryState
        variant="loading"
        onRetry={retryDefaultsLoad}
      />
    );
  }

  if (defaultsUnavailable) {
    return (
      <ConfigDefaultsBoundaryState
        variant="unavailable"
        onRetry={retryDefaultsLoad}
      />
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
      <AppSurfaceHeader
        dataTestId="config-app-surface-header"
        eyebrow="Praviar control system"
        title="Configuration"
        description="Organization-wide default coverage, source, jurisdiction, and review settings."
        mobileDensity="compact"
        mobileMetricColumns="three"
        metrics={[
          {
            label: "Coverage",
            value: getCoverageBudgetLabel(config.searchMaxRankedResults),
          },
          {
            label: "Sources",
            value: `${enabledSources.length} enabled`,
            tone: enabledSources.length > 0 ? "success" : "destructive",
          },
          {
            label: "Jurisdictions",
            value: `${config.searchJurisdictions.length} selected`,
            tone:
              config.searchJurisdictions.length > 0 ? "success" : "destructive",
          },
        ]}
        actions={
          canManageDefaults ? (
            <ConfigHeaderActions
              saving={saving}
              canSave={canSave}
              resetPending={resetPending}
              saveDescriptionId={saveDescriptionId}
              resetDescriptionId={CONFIG_RESET_WARNING_ID}
              onArmReset={handleArmReset}
              onReset={handleReset}
              onSave={handleSaveDefaults}
            />
          ) : undefined
        }
      />

      <ConfigStatusStrip
        config={config}
        enabledSources={enabledSources}
        validationIssues={validationIssues}
        authenticated={Boolean(token)}
        saving={saving}
        editing={editing}
        resetPending={resetPending}
        defaultsLoading={defaultsLoading}
        defaultsUnavailable={defaultsUnavailable}
        canManageDefaults={canManageDefaults}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          {canManageDefaults ? <ConfigPresetGrid config={config} /> : null}

          {canManageDefaults && editing ? (
            <ConfigEditPanel
              config={config}
              onCollapse={() => setEditing(false)}
            />
          ) : (
            <ConfigReadOnlySummaryCard
              config={config}
              enabledSources={enabledSources}
              onEdit={canManageDefaults ? () => setEditing(true) : undefined}
            />
          )}
        </div>
        <ConfigGovernanceRail
          config={config}
          saving={saving}
          editing={editing}
          resetPending={resetPending}
          canManageDefaults={canManageDefaults}
        />
      </div>
    </div>
  );
}

function ConfigDefaultsBoundaryState({
  variant,
  onRetry,
}: {
  variant: "loading" | "unavailable";
  onRetry: () => void;
}) {
  const loading = variant === "loading";

  return (
    <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
      <AppSurfaceHeader
        dataTestId="config-app-surface-header"
        eyebrow="Praviar control system"
        title="Configuration"
        description="Organization-wide default coverage, source, jurisdiction, and review settings."
        mobileDensity="compact"
      />
      <OperationalStatusFrame
        actionLabel={loading ? undefined : "Retry configuration load"}
        contextItems={
          loading
            ? [
                "Organization defaults requested",
                "Stored values withheld",
                "Mutation controls locked",
              ]
            : [
                "Stored values withheld",
                "No configuration changes made",
                "Mutation controls locked",
              ]
        }
        dataTestId={`config-defaults-status-${variant}`}
        description={
          loading
            ? "Praviar is loading the current organization policy before showing values or enabling changes."
            : "Organization defaults could not be loaded. Existing policy remains unchanged, and cached values are hidden until a fresh response succeeds."
        }
        eyebrow="Configuration access"
        headingLevel={1}
        icon={LockKeyhole}
        isPending={loading}
        onRetry={loading ? undefined : onRetry}
        recoveryBody={
          loading
            ? "The policy workspace opens after the tenant-scoped defaults are available."
            : "Retry to request a fresh tenant-scoped policy without changing existing defaults."
        }
        recoveryTitle={
          loading ? "Loading tenant policy" : "Restore configuration access"
        }
        title={
          loading
            ? "Loading organization defaults"
            : "Configuration defaults unavailable"
        }
        titleId={`config-defaults-status-${variant}-title`}
        tone={loading ? "default" : "error"}
      />
    </div>
  );
}
