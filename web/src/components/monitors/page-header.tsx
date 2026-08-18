"use client";

import type { RefObject } from "react";
import { Plus } from "lucide-react";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { Button } from "@/components/ui/button";

interface MonitorsPageHeaderProps {
  onCreateClick: () => void;
  createButtonRef?: RefObject<HTMLButtonElement | null>;
  actionsDisabled?: boolean;
}

export function MonitorsPageHeader({
  onCreateClick,
  createButtonRef,
  actionsDisabled = false,
}: MonitorsPageHeaderProps) {
  return (
    <AppSurfaceHeader
      dataTestId="monitors-app-surface-header"
      eyebrow="Praviar monitoring workspace"
      title="Patent monitoring workspace"
      description="Track patent landscape changes for watched compounds without treating monitoring as a clearance opinion."
      metrics={[
        { label: "Signal", value: "Landscape change" },
        { label: "Cadence", value: "Scheduled watches" },
        { label: "Review", value: "Human handoff" },
      ]}
      actions={
        <Button
          ref={createButtonRef}
          className="min-h-11 w-full gap-2 bg-[var(--brand-ink)] hover:bg-[var(--brand-primary-dim)] lg:w-auto"
          disabled={actionsDisabled}
          onClick={onCreateClick}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New Monitor
        </Button>
      }
    />
  );
}
