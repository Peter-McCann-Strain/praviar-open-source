import { describe, it, expect, beforeEach, vi } from "vitest";
import { usePipelineStore } from "@/stores/pipeline-store";

beforeEach(() => {
  usePipelineStore.getState().reset();
  vi.restoreAllMocks();
});

describe("pipeline-store (extended)", () => {
  describe("initSteps creates 8 steps", () => {
    it("creates exactly 8 steps", () => {
      usePipelineStore.getState().initSteps();
      expect(usePipelineStore.getState().steps).toHaveLength(8);
    });

    it("creates steps numbered 1 through 8", () => {
      usePipelineStore.getState().initSteps();
      const numbers = usePipelineStore.getState().steps.map((s) => s.number);
      expect(numbers).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    });

    it("names steps correctly", () => {
      usePipelineStore.getState().initSteps();
      const names = usePipelineStore.getState().steps.map((s) => s.name);
      expect(names).toEqual([
        "resolve",
        "search",
        "triage",
        "analyze",
        "doe",
        "invalidity",
        "verify",
        "report",
      ]);
    });

    it("initializes all steps as pending", () => {
      usePipelineStore.getState().initSteps();
      usePipelineStore.getState().steps.forEach((step) => {
        expect(step.status).toBe("pending");
      });
    });

    it("resets currentStep to 0", () => {
      usePipelineStore.getState().setStepStatus(3, "running");
      usePipelineStore.getState().initSteps();
      expect(usePipelineStore.getState().currentStep).toBe(0);
    });

    it("clears error state", () => {
      usePipelineStore.getState().setError("something broke");
      usePipelineStore.getState().initSteps();
      expect(usePipelineStore.getState().error).toBeNull();
    });

    it("clears progress payloads", () => {
      usePipelineStore
        .getState()
        .setStepProgress(1, { compound_name: "aspirin" });
      usePipelineStore.getState().initSteps();
      expect(usePipelineStore.getState().progressPayloads).toEqual({});
    });
  });

  describe("setStepStatus validates step number", () => {
    it("updates status for valid step number", () => {
      usePipelineStore.getState().setStepStatus(1, "running");
      const step1 = usePipelineStore
        .getState()
        .steps.find((s) => s.number === 1);
      expect(step1?.status).toBe("running");
    });

    it("updates status for step 8 (last valid step)", () => {
      usePipelineStore.getState().setStepStatus(8, "completed");
      const step8 = usePipelineStore
        .getState()
        .steps.find((s) => s.number === 8);
      expect(step8?.status).toBe("completed");
    });

    it("supports 'failed' status", () => {
      usePipelineStore.getState().setStepStatus(4, "failed");
      const step4 = usePipelineStore
        .getState()
        .steps.find((s) => s.number === 4);
      expect(step4?.status).toBe("failed");
    });
  });

  describe("invalid step number logs error", () => {
    it("logs error for step 0", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      usePipelineStore.getState().setStepStatus(0, "running");
      expect(spy).toHaveBeenCalledWith(
        "[PipelineStore] Invalid step number: 0",
      );
    });

    it("logs error for step 9", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      usePipelineStore.getState().setStepStatus(9, "running");
      expect(spy).toHaveBeenCalledWith(
        "[PipelineStore] Invalid step number: 9",
      );
    });

    it("logs error for negative step number", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      usePipelineStore.getState().setStepStatus(-1, "running");
      expect(spy).toHaveBeenCalledWith(
        "[PipelineStore] Invalid step number: -1",
      );
    });

    it("does not modify state for invalid step number", () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      const _stepsBefore = [...usePipelineStore.getState().steps];
      usePipelineStore.getState().setStepStatus(99, "running");
      const stepsAfter = usePipelineStore.getState().steps;
      // All steps should still be pending
      stepsAfter.forEach((step) => {
        expect(step.status).toBe("pending");
      });
    });
  });

  describe("setting step to running auto-completes prior pending steps", () => {
    it("auto-completes step 1 when step 2 starts running", () => {
      usePipelineStore.getState().setStepStatus(2, "running");
      const step1 = usePipelineStore
        .getState()
        .steps.find((s) => s.number === 1);
      expect(step1?.status).toBe("completed");
    });

    it("auto-completes steps 1-3 when step 4 starts running", () => {
      usePipelineStore.getState().setStepStatus(4, "running");
      const steps = usePipelineStore.getState().steps;
      expect(steps.find((s) => s.number === 1)?.status).toBe("completed");
      expect(steps.find((s) => s.number === 2)?.status).toBe("completed");
      expect(steps.find((s) => s.number === 3)?.status).toBe("completed");
      expect(steps.find((s) => s.number === 4)?.status).toBe("running");
    });

    it("does not auto-complete steps that are already failed", () => {
      usePipelineStore.getState().setStepStatus(2, "failed");
      usePipelineStore.getState().setStepStatus(3, "running");
      const step2 = usePipelineStore
        .getState()
        .steps.find((s) => s.number === 2);
      // Failed status should not be overwritten
      expect(step2?.status).toBe("failed");
    });

    it("does not auto-complete steps that are already completed", () => {
      usePipelineStore.getState().setStepStatus(1, "running");
      usePipelineStore.getState().setStepStatus(1, "completed");
      usePipelineStore.getState().setStepStatus(3, "running");
      const step1 = usePipelineStore
        .getState()
        .steps.find((s) => s.number === 1);
      // Should still be completed (not changed)
      expect(step1?.status).toBe("completed");
    });

    it("does not auto-complete later steps", () => {
      usePipelineStore.getState().setStepStatus(3, "running");
      const steps = usePipelineStore.getState().steps;
      expect(steps.find((s) => s.number === 4)?.status).toBe("pending");
      expect(steps.find((s) => s.number === 5)?.status).toBe("pending");
    });

    it("updates currentStep to the running step number", () => {
      usePipelineStore.getState().setStepStatus(5, "running");
      expect(usePipelineStore.getState().currentStep).toBe(5);
    });

    it("does not update currentStep for completed status", () => {
      usePipelineStore.getState().setStepStatus(2, "running");
      usePipelineStore.getState().setStepStatus(2, "completed");
      // currentStep stays at 2 (set when running)
      expect(usePipelineStore.getState().currentStep).toBe(2);
    });
  });

  describe("setComplete sets isComplete and overallRisk", () => {
    it("sets isComplete to true", () => {
      usePipelineStore.getState().setComplete("high");
      expect(usePipelineStore.getState().isComplete).toBe(true);
    });

    it("sets overallRisk to the provided value", () => {
      usePipelineStore.getState().setComplete("medium");
      expect(usePipelineStore.getState().overallRisk).toBe("medium");
    });

    it("works with low risk", () => {
      usePipelineStore.getState().setComplete("low");
      expect(usePipelineStore.getState().overallRisk).toBe("low");
      expect(usePipelineStore.getState().isComplete).toBe(true);
    });

    it("works with clear risk", () => {
      usePipelineStore.getState().setComplete("clear");
      expect(usePipelineStore.getState().overallRisk).toBe("clear");
    });
  });

  describe("reset returns to initial state", () => {
    it("resets steps to 8 pending steps", () => {
      const store = usePipelineStore.getState();
      store.setStepStatus(1, "running");
      store.setStepStatus(2, "completed");
      store.setComplete("high");
      store.setError("failure");
      store.setStepProgress(1, { compound_name: "test" });

      usePipelineStore.getState().reset();

      const state = usePipelineStore.getState();
      expect(state.steps).toHaveLength(8);
      state.steps.forEach((step) => {
        expect(step.status).toBe("pending");
      });
      expect(state.currentStep).toBe(0);
      expect(state.isComplete).toBe(false);
      expect(state.error).toBeNull();
      expect(state.overallRisk).toBeNull();
      expect(state.progressPayloads).toEqual({});
    });

    it("allows re-use after reset", () => {
      usePipelineStore.getState().setComplete("high");
      usePipelineStore.getState().reset();
      usePipelineStore.getState().setStepStatus(1, "running");
      expect(usePipelineStore.getState().currentStep).toBe(1);
      expect(
        usePipelineStore.getState().steps.find((s) => s.number === 1)?.status,
      ).toBe("running");
    });
  });

  describe("setStepProgress", () => {
    it("ignores invalid step numbers silently", () => {
      usePipelineStore.getState().setStepProgress(99, { message: "bad" });
      expect(usePipelineStore.getState().progressPayloads).toEqual({});
    });
  });
});
