"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { CheckpointGate } from "@/components/pipeline/checkpoint-gate";
import {
  Dialog,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useSubmitCheckpointDecision } from "@/hooks/use-checkpoint-decisions";
import { cn } from "@/lib/utils";
import type { CheckpointState } from "@/stores/pipeline-store";

interface CheckpointOverlayProps {
  analysisId: string;
  activeCheckpoint: CheckpointState | null;
  onClose: () => void;
}

export const CHECKPOINT_DECISION_ERROR_MESSAGE =
  "Checkpoint decision was not saved. Existing pipeline and review state are unchanged.";

export function CheckpointOverlay({
  analysisId,
  activeCheckpoint,
  onClose,
}: CheckpointOverlayProps) {
  const token = useAuthToken();
  const submitDecision = useSubmitCheckpointDecision(analysisId, token);

  if (!activeCheckpoint) {
    return null;
  }

  const canDismissLocally = !activeCheckpoint.requires_response;
  const checkpointId =
    activeCheckpoint.checkpoint_id ?? activeCheckpoint.checkpoint_type;
  const submit = (decision: "approve" | "reject") => {
    const isIdentityReview =
      activeCheckpoint.checkpoint_type === "identity_review";
    const isReportReview = activeCheckpoint.checkpoint_type === "report_review";
    const reportPayloadDigest =
      typeof activeCheckpoint.context.review_payload_sha256 === "string"
        ? activeCheckpoint.context.review_payload_sha256
        : "unavailable";
    submitDecision.mutate(
      {
        checkpointId,
        checkpointType: activeCheckpoint.checkpoint_type,
        decision,
        reviewPayloadSha256:
          isReportReview && decision === "approve"
            ? reportPayloadDigest
            : undefined,
        note:
          decision === "reject"
            ? isIdentityReview
              ? "Resolved identity rejected; downstream search must not proceed."
              : "Rejected from checkpoint overlay."
            : isIdentityReview
              ? "Reviewer attested to the fingerprint-bound resolved identity, derived search envelope, and disclosed variant limitations."
              : isReportReview
                ? `Reviewer attested to the bounded report draft and claim-source ledger bound to review payload SHA-256 ${reportPayloadDigest}.`
                : "",
      },
      {
        onSuccess: onClose,
      },
    );
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && canDismissLocally) {
          onClose();
        }
      }}
    >
      <DialogPortal>
        <DialogOverlay />
        <DialogPrimitive.Content
          className={cn(
            "fixed left-[50%] top-[50%] z-50 max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] translate-x-[-50%] translate-y-[-50%] overflow-y-auto overscroll-contain duration-200",
            activeCheckpoint.checkpoint_type === "identity_review" ||
              activeCheckpoint.checkpoint_type === "report_review"
              ? "max-w-3xl"
              : "max-w-lg",
            "focus:outline-none data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
          )}
          onEscapeKeyDown={(event) => {
            if (!canDismissLocally) {
              event.preventDefault();
            }
          }}
          onPointerDownOutside={(event) => {
            if (!canDismissLocally) {
              event.preventDefault();
            }
          }}
        >
          <DialogTitle className="sr-only">Human review checkpoint</DialogTitle>
          <DialogDescription className="sr-only">
            Review this checkpoint and submit a server-persisted decision before
            the pipeline continues.
          </DialogDescription>
          <CheckpointGate
            type={activeCheckpoint.checkpoint_type}
            data={activeCheckpoint.context}
            onApprove={() => submit("approve")}
            onReject={() => submit("reject")}
            isSubmitting={submitDecision.isPending}
            errorMessage={
              submitDecision.error
                ? CHECKPOINT_DECISION_ERROR_MESSAGE
                : undefined
            }
          />
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
