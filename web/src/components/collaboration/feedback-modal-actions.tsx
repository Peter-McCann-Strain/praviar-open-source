import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface FeedbackModalActionsProps {
  onCancel: () => void;
  onSubmit: () => void;
  isPending: boolean;
  submitDisabled: boolean;
}

export function FeedbackModalActions({
  onCancel,
  onSubmit,
  isPending,
  submitDisabled,
}: FeedbackModalActionsProps) {
  return (
    <div className="flex gap-3 pt-2 border-t border-[var(--border-default)]">
      <Button variant="outline" onClick={onCancel} className="flex-1">
        Cancel
      </Button>
      <Button
        onClick={onSubmit}
        disabled={isPending || submitDisabled}
        className="flex-1 gap-2"
      >
        {isPending ? (
          <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
        ) : null}
        {isPending ? "Submitting..." : "Submit Feedback"}
      </Button>
    </div>
  );
}
