"use client";

import { Flag, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useFlagAnalysis } from "@/hooks/use-flag";
import { useToastStore } from "@/stores/toast-store";
import { logError } from "@/lib/error-logger";

interface FlagButtonProps {
  analysisId: string;
  isFlagged?: boolean;
  className?: string;
  variant?: "default" | "outline" | "ghost";
  size?: "default" | "sm" | "lg";
}

export function FlagButton({
  analysisId,
  isFlagged = false,
  className,
  variant = "outline",
  size = "default",
}: FlagButtonProps) {
  const token = useAuthToken();
  const toast = useToastStore();
  const flagMutation = useFlagAnalysis(token);

  const handleFlag = async () => {
    if (isFlagged) {
      toast.addToast("Already flagged for review", "info");
      return;
    }
    try {
      await flagMutation.mutateAsync(analysisId);
      toast.addToast("Flagged for review — team notified", "warning");
    } catch (err) {
      logError(err, {
        source: "FlagButton",
        extra: { action: "flag_analysis" },
      });
      toast.addToast("Failed to flag — please try again", "error");
    }
  };

  return (
    <Button
      variant={variant}
      size={size}
      className={className}
      onClick={handleFlag}
      disabled={flagMutation.isPending || isFlagged}
    >
      {flagMutation.isPending ? (
        <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none mr-2" />
      ) : (
        <Flag className="h-4 w-4 text-warning mr-2" />
      )}
      {isFlagged
        ? "Flagged"
        : flagMutation.isPending
          ? "Flagging..."
          : "Flag for Review"}
    </Button>
  );
}
