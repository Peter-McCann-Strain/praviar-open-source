import {
  AlertTriangle,
  Atom,
  CheckCircle,
  FileText,
  Filter,
  Microscope,
  Scale,
  Search,
  ShieldX,
} from "lucide-react";
import { formatNumber } from "@/lib/utils";
import type {
  AnyStepPayload,
  Step2Payload,
  Step3Payload,
  Step4Payload,
  Step5Payload,
  Step6Payload,
  Step7Payload,
  Step8Payload,
  Step1Payload,
} from "@/types/pipeline";

export const STEP_ICONS = [
  Atom,
  Search,
  Filter,
  Microscope,
  Scale,
  ShieldX,
  CheckCircle,
  FileText,
];

export const STEP_LABELS = [
  "Resolving Compound",
  "Searching Patent Databases",
  "Triaging Patents",
  "Deep Claim Analysis",
  "Doctrine of Equivalents",
  "Invalidity Assessment",
  "Cross-Verification",
  "Generating Report",
];

export const TOTAL_PIPELINE_STEPS = STEP_LABELS.length;

export function clampPipelineStep(step: number): number {
  if (!Number.isFinite(step)) {
    return 0;
  }

  return Math.min(TOTAL_PIPELINE_STEPS, Math.max(0, Math.trunc(step)));
}

export function getPipelineStepLabel(step: number): string {
  const safeStep = clampPipelineStep(step);
  return safeStep > 0 ? STEP_LABELS[safeStep - 1] : "Queued";
}

export function getStepMicrocopy(
  stepNum: number,
  payload: AnyStepPayload | undefined,
): string | null {
  if (!payload) {
    return null;
  }

  switch (stepNum) {
    case 1: {
      const stepPayload = payload as Step1Payload;
      return stepPayload.compound_name
        ? `Resolved: ${stepPayload.compound_name}`
        : null;
    }
    case 2: {
      const stepPayload = payload as Step2Payload;
      if (
        stepPayload.patents_found != null &&
        stepPayload.sources_completed?.length
      ) {
        return `Found ${formatNumber(stepPayload.patents_found)} patents from ${stepPayload.sources_completed.length} source${stepPayload.sources_completed.length !== 1 ? "s" : ""}`;
      }
      return stepPayload.patents_found != null
        ? `Found ${formatNumber(stepPayload.patents_found)} patents`
        : null;
    }
    case 3: {
      const stepPayload = payload as Step3Payload;
      return stepPayload.relevant != null && stepPayload.total != null
        ? `${formatNumber(stepPayload.relevant)} of ${formatNumber(stepPayload.total)} patents passed relevance triage`
        : null;
    }
    case 4: {
      const stepPayload = payload as Step4Payload;
      if (
        stepPayload.analyzed != null &&
        stepPayload.total != null &&
        stepPayload.current_patent
      ) {
        return `Mapping patent ${formatNumber(stepPayload.analyzed)} of ${formatNumber(stepPayload.total)}: ${stepPayload.current_patent}`;
      }
      return stepPayload.analyzed != null && stepPayload.total != null
        ? `Mapped ${formatNumber(stepPayload.analyzed)} of ${formatNumber(stepPayload.total)} patent analyses`
        : null;
    }
    case 5: {
      const stepPayload = payload as Step5Payload;
      return stepPayload.assessments != null
        ? `${stepPayload.assessments} equivalence assessment${stepPayload.assessments !== 1 ? "s" : ""}`
        : null;
    }
    case 6: {
      const stepPayload = payload as Step6Payload;
      return stepPayload.assessed != null
        ? `${stepPayload.assessed} invalidity defense${stepPayload.assessed !== 1 ? "s" : ""} identified`
        : null;
    }
    case 7: {
      const stepPayload = payload as Step7Payload;
      return stepPayload.checks_passed != null
        ? `${stepPayload.checks_passed} verification check${stepPayload.checks_passed !== 1 ? "s" : ""} passed`
        : null;
    }
    case 8: {
      const stepPayload = payload as Step8Payload;
      return stepPayload.format
        ? `Generating ${stepPayload.format} report`
        : null;
    }
    default:
      return null;
  }
}

export function getStepBadgeCount(
  stepNum: number,
  payload: AnyStepPayload | undefined,
): string | null {
  if (!payload) {
    return null;
  }

  switch (stepNum) {
    case 2:
      return (payload as Step2Payload).patents_found != null
        ? formatNumber((payload as Step2Payload).patents_found!)
        : null;
    case 3:
      return (payload as Step3Payload).relevant != null
        ? formatNumber((payload as Step3Payload).relevant!)
        : null;
    case 4:
      return (payload as Step4Payload).analyzed != null
        ? formatNumber((payload as Step4Payload).analyzed!)
        : null;
    case 5:
      return (payload as Step5Payload).assessments != null
        ? String((payload as Step5Payload).assessments)
        : null;
    case 6:
      return (payload as Step6Payload).assessed != null
        ? String((payload as Step6Payload).assessed)
        : null;
    default:
      return null;
  }
}

export function getStep4Progress(
  payload: AnyStepPayload | undefined,
): { analyzed: number; total: number } | null {
  if (!payload) {
    return null;
  }

  const stepPayload = payload as Step4Payload;
  return stepPayload.analyzed != null &&
    stepPayload.total != null &&
    stepPayload.total > 0
    ? { analyzed: stepPayload.analyzed, total: stepPayload.total }
    : null;
}

export function formatElapsed(milliseconds: number): string {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export { AlertTriangle };
