"use client";

import type { PipelineStep } from "@/stores/pipeline-store";
import type {
  Step2Payload,
  Step3Payload,
  Step4Payload,
  StepPayloadMap,
  StepNumber,
} from "@/types/pipeline";
import {
  getStep4Progress,
  getStepBadgeCount,
  getStepMicrocopy,
} from "@/components/analysis-detail/helpers";

export type ProgressPayloads = Partial<{
  [K in StepNumber]: StepPayloadMap[K];
}>;

export interface ProgressStepViewModel {
  badgeCount: string | null;
  durationLabel: string | null;
  isActive: boolean;
  isDone: boolean;
  isFailed: boolean;
  hasCoverageGap: boolean;
  isPending: boolean;
  message: string | undefined;
  step4Progress: ReturnType<typeof getStep4Progress> | null;
  stepNum: number;
}

export function buildLiveResults(progressPayloads: ProgressPayloads) {
  const items: {
    id: string;
    label: string;
    detail?: string;
    badge?: { text: string; color: string };
  }[] = [];

  const searchPayload = progressPayloads[2];
  if (searchPayload && (searchPayload as Step2Payload).patents_found != null) {
    items.push({
      id: "search",
      label: `${(searchPayload as Step2Payload).patents_found} patents discovered`,
      detail: (searchPayload as Step2Payload).message,
    });
  }

  const triagePayload = progressPayloads[3];
  if (triagePayload && (triagePayload as Step3Payload).relevant != null) {
    const total = (triagePayload as Step3Payload).total;
    items.push({
      id: "triage",
      label: `${(triagePayload as Step3Payload).relevant} patents relevant`,
      detail:
        total != null
          ? `of ${total} triaged`
          : ((triagePayload as Step3Payload).message ?? "triage total pending"),
    });
  }

  const analysisPayload = progressPayloads[4];
  if (analysisPayload && (analysisPayload as Step4Payload).current_patent) {
    const analyzed = (analysisPayload as Step4Payload).analyzed;
    const total = (analysisPayload as Step4Payload).total;
    items.push({
      id: `analyze-${analyzed ?? "active"}`,
      label: (analysisPayload as Step4Payload).current_patent!,
      detail:
        analyzed != null && total != null
          ? `Mapping patent ${analyzed}/${total}`
          : analyzed != null
            ? `Mapping patent ${analyzed}; total pending`
            : "Mapping active patent",
      badge: {
        text: "In Progress",
        color: "bg-brand-primary/20 text-brand-primary",
      },
    });
  }

  return items;
}

export function buildStepViewModel({
  currentStep,
  formatDuration,
  hasLiveData,
  isComplete,
  isFailed,
  isRunning,
  liveStep,
  invalidityAssessmentsCount,
  progress,
  stepNum,
}: {
  currentStep: number;
  formatDuration: (seconds: number) => string;
  hasLiveData: boolean;
  isComplete: boolean;
  isFailed: boolean;
  isRunning: boolean;
  liveStep: PipelineStep | null;
  invalidityAssessmentsCount?: number | null;
  progress: ProgressPayloads[StepNumber];
  stepNum: number;
}) {
  const stepStatus = liveStep?.status;
  const isActive = hasLiveData
    ? stepStatus === "running"
    : isRunning && stepNum === currentStep;
  const isDone = hasLiveData
    ? stepStatus === "completed"
    : stepNum < currentStep || isComplete;
  const isPending = hasLiveData
    ? stepStatus === "pending"
    : stepNum > currentStep && !isComplete;
  const isFailedStep = hasLiveData
    ? stepStatus === "failed"
    : isFailed && stepNum === currentStep;
  const hasCoverageGap =
    stepNum === 6 && isDone && invalidityAssessmentsCount === 0;
  const progressMessage =
    getStepMicrocopy(stepNum, progress) ?? progress?.message;
  const badgeCount = isDone ? getStepBadgeCount(stepNum, progress) : null;
  const step4Progress =
    stepNum === 4 && isActive ? getStep4Progress(progress) : null;

  let durationLabel: string | null = null;
  if (hasCoverageGap) {
    durationLabel = "No output";
  } else if (isDone && liveStep?.startedAt && liveStep?.completedAt) {
    durationLabel = formatDuration(
      (new Date(liveStep.completedAt).getTime() -
        new Date(liveStep.startedAt).getTime()) /
        1000,
    );
  } else if (isDone) {
    durationLabel = "Done";
  } else if (isActive) {
    durationLabel = "Running...";
  } else if (isFailedStep) {
    durationLabel = "Failed";
  }

  return {
    badgeCount,
    durationLabel,
    hasCoverageGap,
    isActive,
    isDone,
    isFailed: isFailedStep,
    isPending,
    message: progressMessage,
    step4Progress,
    stepNum,
  } satisfies ProgressStepViewModel;
}
