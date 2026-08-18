import { Plus } from "lucide-react";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { Button } from "@/components/ui/button";

interface BatchPageHeaderProps {
  onToggleCreate: () => void;
  actionsDisabled?: boolean;
  createOpen?: boolean;
}

export function BatchPageHeader({
  onToggleCreate,
  actionsDisabled = false,
  createOpen = false,
}: BatchPageHeaderProps) {
  return (
    <AppSurfaceHeader
      dataTestId="batch-app-surface-header"
      eyebrow="Praviar portfolio screening"
      title="Diligence portfolio workspace"
      description="Run patent screening across compound portfolios with explicit human-review status."
      markSize="sm"
      mobileDensity="compact"
      actions={
        <Button
          className="min-h-11 w-full gap-2 sm:w-auto"
          disabled={actionsDisabled}
          onClick={onToggleCreate}
          aria-expanded={createOpen}
          aria-controls="create-batch-panel"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {createOpen ? "Close batch setup" : "New Batch"}
        </Button>
      }
    />
  );
}
