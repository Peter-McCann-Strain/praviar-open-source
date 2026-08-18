"use client";

import { useUIStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

export function DashboardContent({ children }: { children: React.ReactNode }) {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);

  return (
    <div
      className={cn(
        "praviar-app-field flex min-h-screen flex-1 min-w-0 flex-col transition-all duration-300",
        // No left padding on mobile — sidebar overlays instead
        sidebarOpen ? "lg:pl-[256px]" : "lg:pl-[64px]",
      )}
    >
      {children}
    </div>
  );
}
