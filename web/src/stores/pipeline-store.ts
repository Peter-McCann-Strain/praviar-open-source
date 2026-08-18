import { create } from "zustand";
import type { RiskLevel } from "@praviar/shared-types";
import type {
  AnyStepPayload,
  StepPayloadMap,
  StepNumber,
} from "@/types/pipeline";

export interface PipelineStep {
  number: number;
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  description?: string;
  startedAt?: string;
  completedAt?: string;
}

export interface CheckpointState {
  checkpoint_id?: string;
  checkpoint_type:
    | "identity_review"
    | "search_review"
    | "triage_review"
    | "analysis_review"
    | "report_review";
  context: Record<string, unknown>;
  requires_response: boolean;
  timeout_minutes: number;
  step: number;
  step_name: string;
  timestamp: string;
}

interface PipelineState {
  steps: PipelineStep[];
  currentStep: number;
  isComplete: boolean;
  error: string | null;
  overallRisk: RiskLevel | null;
  progressPayloads: Partial<{ [K in StepNumber]: StepPayloadMap[K] }>;
  activeCheckpoint: CheckpointState | null;

  initSteps: () => void;
  setStepStatus: (
    step: number,
    status: PipelineStep["status"],
    payload?: { description?: string },
  ) => void;
  setStepProgress: (step: number, payload: AnyStepPayload) => void;
  setComplete: (risk: RiskLevel) => void;
  setError: (error: string) => void;
  setCheckpoint: (checkpoint: CheckpointState) => void;
  clearCheckpoint: () => void;
  reset: () => void;
}

const INITIAL_STEPS: PipelineStep[] = [
  { number: 1, name: "resolve", status: "pending" },
  { number: 2, name: "search", status: "pending" },
  { number: 3, name: "triage", status: "pending" },
  { number: 4, name: "analyze", status: "pending" },
  { number: 5, name: "doe", status: "pending" },
  { number: 6, name: "invalidity", status: "pending" },
  { number: 7, name: "verify", status: "pending" },
  { number: 8, name: "report", status: "pending" },
];

const VALID_STEP_NUMBERS = new Set(INITIAL_STEPS.map((s) => s.number));

/** Type guard: is this a valid pipeline step number (1-8)? */
function isStepNumber(n: number): n is StepNumber {
  return VALID_STEP_NUMBERS.has(n);
}

export { isStepNumber };

export const usePipelineStore = create<PipelineState>((set) => ({
  steps: [...INITIAL_STEPS],
  currentStep: 0,
  isComplete: false,
  error: null,
  overallRisk: null,
  progressPayloads: {},
  activeCheckpoint: null,

  initSteps: () =>
    set({
      steps: [...INITIAL_STEPS],
      currentStep: 0,
      isComplete: false,
      error: null,
      overallRisk: null,
      progressPayloads: {},
      activeCheckpoint: null,
    }),

  setStepStatus: (step, status, payload) => {
    if (!isStepNumber(step)) {
      console.error(`[PipelineStore] Invalid step number: ${step}`);
      return;
    }
    set((state) => {
      const now = new Date().toISOString();
      // When marking a step "running", auto-complete all prior pending steps
      const updatedSteps = state.steps.map((s) => {
        if (s.number === step) {
          return {
            ...s,
            status,
            ...payload,
            ...(status === "running" && !s.startedAt ? { startedAt: now } : {}),
            ...(status === "completed" ? { completedAt: now } : {}),
          };
        }
        if (status === "running" && s.number < step && s.status === "pending") {
          return { ...s, status: "completed" as const, completedAt: now };
        }
        return s;
      });
      return {
        steps: updatedSteps,
        currentStep: status === "running" ? step : state.currentStep,
      };
    });
  },

  setStepProgress: (step, payload) => {
    if (!isStepNumber(step)) return;
    set((state) => ({
      progressPayloads: {
        ...state.progressPayloads,
        [step]: { ...state.progressPayloads[step], ...payload },
      },
    }));
  },

  setComplete: (risk) => set({ isComplete: true, overallRisk: risk }),
  setError: (error) => set({ error }),
  setCheckpoint: (checkpoint) => set({ activeCheckpoint: checkpoint }),
  clearCheckpoint: () => set({ activeCheckpoint: null }),
  reset: () =>
    set({
      steps: [...INITIAL_STEPS],
      currentStep: 0,
      isComplete: false,
      error: null,
      overallRisk: null,
      progressPayloads: {},
      activeCheckpoint: null,
    }),
}));

// ── Atomic Selectors ──────────────────────────────────────────────────
// Use these instead of subscribing to the entire store to prevent
// unnecessary re-renders when unrelated state changes.

export const usePipelineSteps = () => usePipelineStore((s) => s.steps);
export const useCurrentStep = () => usePipelineStore((s) => s.currentStep);
export const useIsComplete = () => usePipelineStore((s) => s.isComplete);
export const usePipelineError = () => usePipelineStore((s) => s.error);
export const useOverallRisk = () => usePipelineStore((s) => s.overallRisk);
export const useActiveCheckpoint = () =>
  usePipelineStore((s) => s.activeCheckpoint);
export const useProgressPayloads = () =>
  usePipelineStore((s) => s.progressPayloads);

// Re-export types for convenience
export type { AnyStepPayload as StepProgressPayload } from "@/types/pipeline";
