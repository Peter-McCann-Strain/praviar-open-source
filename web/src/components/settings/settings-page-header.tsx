import { Plus } from "lucide-react";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { Button } from "@/components/ui/button";

interface SettingsPageHeaderProps {
  onToggleCreate: () => void;
  actionsDisabled?: boolean;
}

export function SettingsPageHeader({
  actionsDisabled = false,
  onToggleCreate,
}: SettingsPageHeaderProps) {
  return (
    <AppSurfaceHeader
      dataTestId="settings-app-surface-header"
      eyebrow="Access control plane"
      title="Settings"
      description="Govern API keys, identity handoff, and notification policies for approved FTO work."
      mobileDensity="compact"
      metrics={[
        { label: "Scope", value: "Organization" },
        { label: "Rotation", value: "90-day review" },
        { label: "Evidence", value: "Audit retained" },
      ]}
      actions={
        <Button
          className="min-h-11 w-full gap-2 lg:w-auto"
          disabled={actionsDisabled}
          onClick={onToggleCreate}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New API Key
        </Button>
      }
    />
  );
}
