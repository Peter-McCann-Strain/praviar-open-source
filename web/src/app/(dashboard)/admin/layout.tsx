"use client";

import { useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { LockKeyhole } from "lucide-react";
import {
  hasClerk,
  isAdminOrgRole,
} from "@/components/layout/sidebar-constants";
import { AdminStatusState } from "@/components/admin-dashboard/helpers";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useClientReady } from "@/hooks/use-client-ready";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const governedChildren = (
    <PrincipalAdminAccessGate>{children}</PrincipalAdminAccessGate>
  );
  if (!hasClerk) {
    return governedChildren;
  }

  return <AdminAccessGate>{governedChildren}</AdminAccessGate>;
}

function PrincipalAdminAccessGate({ children }: { children: React.ReactNode }) {
  const clientReady = useClientReady();
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);

  if (
    !clientReady ||
    (!principal.data && (principal.isLoading || principal.isFetching))
  ) {
    return (
      <div className="space-y-5 animate-fade-up">
        <AdminStatusState surface="overview" variant="auth" />
      </div>
    );
  }

  if (!principal.data) {
    return (
      <OperationalStatusFrame
        actionLabel="Retry access check"
        contextItems={[
          "No platform records disclosed",
          "No administrative action submitted",
          "Application authority was not inferred",
        ]}
        dataTestId="platform-admin-access-unavailable"
        description="Praviar could not load the authoritative application-role snapshot, so platform administration remains closed until the access check succeeds."
        eyebrow="Platform administration"
        icon={LockKeyhole}
        isPending={false}
        onRetry={() => {
          void principal.refetch();
        }}
        recoveryBody="Retry the capability check. If it continues to fail, verify the session or contact an existing platform administrator."
        recoveryTitle="Restore the access check"
        title="Platform admin access check unavailable"
        titleId="platform-admin-access-unavailable-title"
        tone="warning"
      />
    );
  }

  if (principal.data?.can_view_platform_admin !== true) {
    return (
      <OperationalStatusFrame
        contextItems={[
          "No platform records disclosed",
          "No administrative action submitted",
          "Workspace data remains unchanged",
        ]}
        dataTestId="platform-admin-access-restricted"
        description="The organization membership is valid, but this application role does not include platform-administration authority."
        eyebrow="Platform administration"
        icon={LockKeyhole}
        isPending={false}
        onRetry={() => {
          void principal.refetch();
        }}
        recoveryBody="Ask an existing platform administrator to update the application role, then retry the authorization check."
        recoveryTitle="Request platform-admin access"
        title="Platform admin access restricted"
        titleId="platform-admin-access-restricted-title"
        tone="error"
      />
    );
  }

  return <>{children}</>;
}

function AdminAccessGate({ children }: { children: React.ReactNode }) {
  const { isLoaded, orgRole } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoaded && !isAdminOrgRole(orgRole)) {
      router.replace("/dashboard");
    }
  }, [isLoaded, orgRole, router]);

  if (!isLoaded) {
    return (
      <div className="space-y-5 animate-fade-up">
        <AdminStatusState surface="overview" variant="auth" />
      </div>
    );
  }

  if (!isAdminOrgRole(orgRole ?? null)) {
    return (
      <section
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="mx-auto max-w-3xl rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-6 text-center shadow-[var(--shadow-sm)]"
        data-testid="admin-redirecting-status"
      >
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          Redirecting to dashboard
        </p>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          Your current workspace role does not include admin controls.
        </p>
      </section>
    );
  }

  return <>{children}</>;
}
