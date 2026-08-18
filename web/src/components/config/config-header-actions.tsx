"use client";

import { AlertTriangle, Loader2, RotateCcw, Save } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ConfigHeaderActionsProps {
  saving: boolean;
  canSave: boolean;
  resetPending: boolean;
  saveDescriptionId?: string;
  resetDescriptionId?: string;
  onArmReset: () => void;
  onReset: () => void;
  onSave: () => void;
}

export function ConfigHeaderActions({
  saving,
  canSave,
  resetPending,
  saveDescriptionId,
  resetDescriptionId,
  onArmReset,
  onReset,
  onSave,
}: ConfigHeaderActionsProps) {
  return (
    <div className="flex w-full min-w-0 gap-2 sm:w-auto">
      <Button
        type="button"
        variant={resetPending ? "destructive" : "outline"}
        className="min-h-11 min-w-0 flex-1 gap-1.5 px-2 sm:flex-none sm:gap-2 sm:px-4"
        onClick={resetPending ? onReset : onArmReset}
        disabled={saving}
        aria-label={
          resetPending
            ? "Confirm reset configuration defaults"
            : "Prepare to reset configuration defaults"
        }
        aria-describedby={resetPending ? resetDescriptionId : undefined}
      >
        {resetPending ? (
          <AlertTriangle aria-hidden="true" className="h-4 w-4" />
        ) : (
          <RotateCcw aria-hidden="true" className="h-4 w-4" />
        )}
        {resetPending ? "Confirm Reset" : "Reset"}
      </Button>
      <Button
        type="button"
        className="min-h-11 min-w-0 flex-1 gap-1.5 px-2 sm:flex-none sm:gap-2 sm:px-4"
        onClick={onSave}
        disabled={saving || !canSave}
        aria-describedby={saveDescriptionId}
      >
        {saving ? (
          <Loader2
            aria-hidden="true"
            className="h-4 w-4 animate-spin motion-reduce:animate-none"
          />
        ) : (
          <Save aria-hidden="true" className="h-4 w-4" />
        )}
        {saving ? "Saving..." : "Save Defaults"}
      </Button>
    </div>
  );
}
