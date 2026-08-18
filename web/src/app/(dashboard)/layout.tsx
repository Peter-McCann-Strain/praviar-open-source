import type { Metadata } from "next";
import { Suspense } from "react";
import { SessionRecoveryBanner } from "@/components/auth/session-recovery-banner";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { WorkspaceBoundaryBanner } from "@/components/layout/workspace-boundary-banner";
import { ToastContainer } from "@/components/ui/toast";
import { DashboardContent } from "@/components/layout/dashboard-content";
import { CommandPalette } from "@/components/shared/command-palette";
import { PageTransition } from "@/components/shared/page-transition";
import { WelcomeModal } from "@/components/shared/welcome-modal";
import { DEMO_MODE_ENABLED, DEV_AUTH_BYPASS_ENABLED } from "@/lib/constants";
import { OrganizationWorkspaceBoundary } from "@/components/auth/organization-workspace-boundary";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const boundaryMode = DEMO_MODE_ENABLED
    ? "demo"
    : DEV_AUTH_BYPASS_ENABLED
      ? "dev-bypass"
      : null;

  return (
    <OrganizationWorkspaceBoundary>
      <div className="flex min-h-screen">
        <Sidebar />
        <DashboardContent>
          <Topbar />
          <Suspense fallback={null}>
            <SessionRecoveryBanner />
          </Suspense>
          {boundaryMode ? (
            <WorkspaceBoundaryBanner mode={boundaryMode} />
          ) : null}
          <main id="main-content" className="flex-1 p-4 sm:p-5 md:p-6">
            <PageTransition>{children}</PageTransition>
          </main>
        </DashboardContent>
        <ToastContainer />
        <CommandPalette />
        <WelcomeModal
          suppressBillingRoutes
          suppressReportRoutes
          suppressControlPlaneRoutes
          suppressShowcaseRoutes
        />
      </div>
    </OrganizationWorkspaceBoundary>
  );
}
