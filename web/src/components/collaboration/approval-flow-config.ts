"use client";

import { Check, Clock, FileCheck, FileX } from "lucide-react";

export type ApprovalStatus =
  | "pending"
  | "under_review"
  | "approved"
  | "changes_requested";

export type PendingAction = "approve" | "request_changes" | null;

export const statusConfig: Record<
  ApprovalStatus,
  {
    icon: typeof Check;
    label: string;
    color: string;
    bg: string;
    border: string;
  }
> = {
  pending: {
    icon: Clock,
    label: "Pending Review",
    color: "text-[var(--text-tertiary)]",
    bg: "bg-[var(--surface-muted)]",
    border: "border-[var(--border-subtle)]",
  },
  under_review: {
    icon: FileCheck,
    label: "Under Review",
    color: "text-info",
    bg: "bg-info/10",
    border: "border-info/20",
  },
  approved: {
    icon: Check,
    label: "Approved",
    color: "text-success",
    bg: "bg-success/10",
    border: "border-success/20",
  },
  changes_requested: {
    icon: FileX,
    label: "Changes Requested",
    color: "text-warning",
    bg: "bg-warning/10",
    border: "border-warning/20",
  },
};

export function formatApprovalDate(approvedAt: string) {
  return new Date(approvedAt).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
