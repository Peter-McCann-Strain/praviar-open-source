import {
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface FeedbackModalHeaderProps {
  patentId: string;
}

export function FeedbackModalHeader({ patentId }: FeedbackModalHeaderProps) {
  return (
    <DialogHeader>
      <DialogTitle>Structured Feedback</DialogTitle>
      <DialogDescription>
        {patentId ? (
          <>
            Provide feedback on the AI assessment for{" "}
            <span className="font-mono text-[var(--text-primary)]">
              {patentId}
            </span>
          </>
        ) : (
          "Provide report-level feedback on this AI-assisted FTO assessment."
        )}
      </DialogDescription>
    </DialogHeader>
  );
}
