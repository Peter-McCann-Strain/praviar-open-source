"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuditLogsTab } from "@/components/admin-dashboard/audit-logs-tab";
import { resolveAdminTab, TABS } from "@/components/admin-dashboard/helpers";
import { MetricsTab } from "@/components/admin-dashboard/metrics-tab";
import { OrganizationsTab } from "@/components/admin-dashboard/organizations-tab";
import { OverviewTab } from "@/components/admin-dashboard/overview-tab";
import { TasksTab } from "@/components/admin-dashboard/tasks-tab";
import { UsersTab } from "@/components/admin-dashboard/users-tab";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function AdminPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState(() => resolveAdminTab(null));

  useEffect(() => {
    const syncFromLocation = () => {
      setActiveTab(
        resolveAdminTab(new URLSearchParams(window.location.search).get("tab")),
      );
    };
    syncFromLocation();
    window.addEventListener("popstate", syncFromLocation);
    return () => window.removeEventListener("popstate", syncFromLocation);
  }, []);

  function handleTabChange(value: string) {
    const tab = resolveAdminTab(value);
    const nextSearchParams = new URLSearchParams(window.location.search);
    setActiveTab(tab);

    if (tab === "overview") {
      nextSearchParams.delete("tab");
    } else {
      nextSearchParams.set("tab", tab);
    }

    const query = nextSearchParams.toString();
    router.replace(query ? `/admin?${query}` : "/admin", { scroll: false });
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
      <AppSurfaceHeader
        dataTestId="admin-app-surface-header"
        eyebrow="Praviar platform governance"
        title="Platform Admin"
        description="System health, user management, audit trails, and platform metrics for governed FTO operations."
        mobileDensity="compact"
        metrics={[
          { label: "Health", value: "Service checks" },
          { label: "Access", value: "User roles" },
          { label: "Audit", value: "Task ledger" },
        ]}
      />

      <Tabs
        value={activeTab}
        onValueChange={handleTabChange}
        className="space-y-6"
      >
        <TabsList
          aria-label="Admin dashboard sections"
          className="grid w-full grid-cols-2 justify-stretch overflow-visible sm:grid-cols-3 lg:inline-flex lg:w-auto lg:justify-start lg:overflow-x-auto"
        >
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const tabId = `admin-tab-${tab.id}`;
            const panelId = `admin-panel-${tab.id}`;
            return (
              <TabsTrigger
                key={tab.id}
                id={tabId}
                value={tab.id}
                aria-controls={panelId}
                className="min-h-11 w-full shrink-0 px-3 lg:w-auto"
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {tab.label}
              </TabsTrigger>
            );
          })}
        </TabsList>

        <TabsContent
          id="admin-panel-overview"
          value="overview"
          aria-labelledby="admin-tab-overview"
        >
          <OverviewTab />
        </TabsContent>
        <TabsContent
          id="admin-panel-organizations"
          value="organizations"
          aria-labelledby="admin-tab-organizations"
        >
          <OrganizationsTab />
        </TabsContent>
        <TabsContent
          id="admin-panel-users"
          value="users"
          aria-labelledby="admin-tab-users"
        >
          <UsersTab />
        </TabsContent>
        <TabsContent
          id="admin-panel-metrics"
          value="metrics"
          aria-labelledby="admin-tab-metrics"
        >
          <MetricsTab />
        </TabsContent>
        <TabsContent
          id="admin-panel-audit-logs"
          value="audit-logs"
          aria-labelledby="admin-tab-audit-logs"
        >
          <AuditLogsTab />
        </TabsContent>
        <TabsContent
          id="admin-panel-tasks"
          value="tasks"
          aria-labelledby="admin-tab-tasks"
        >
          <TasksTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
