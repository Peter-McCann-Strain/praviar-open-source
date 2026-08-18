import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { useToastStore } from "@/stores/toast-store";

beforeEach(() => {
  vi.useFakeTimers();
  useToastStore.setState({ toasts: [] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("toast-store (extended)", () => {
  describe("addToast creates toast with unique ID", () => {
    it("generates an ID starting with 'toast-'", () => {
      useToastStore.getState().addToast("Test message");
      const { toasts } = useToastStore.getState();
      expect(toasts[0].id).toMatch(/^toast-/);
    });

    it("generates unique IDs for consecutive toasts", () => {
      const store = useToastStore.getState();
      store.addToast("First");
      store.addToast("Second");
      store.addToast("Third");

      const ids = useToastStore.getState().toasts.map((t) => t.id);
      const uniqueIds = new Set(ids);
      expect(uniqueIds.size).toBe(3);
    });

    it("stores the correct message", () => {
      useToastStore.getState().addToast("Pipeline completed successfully");
      expect(useToastStore.getState().toasts[0].message).toBe(
        "Pipeline completed successfully",
      );
    });
  });

  describe("removeToast removes specific toast", () => {
    it("removes only the toast with the matching ID", () => {
      const store = useToastStore.getState();
      store.addToast("Keep");
      store.addToast("Remove");
      store.addToast("Also keep");

      const toasts = useToastStore.getState().toasts;
      expect(toasts).toHaveLength(3);

      useToastStore.getState().removeToast(toasts[1].id);
      const remaining = useToastStore.getState().toasts;
      expect(remaining).toHaveLength(2);
      expect(remaining[0].message).toBe("Keep");
      expect(remaining[1].message).toBe("Also keep");
    });

    it("is a no-op for a non-existent ID", () => {
      useToastStore.getState().addToast("Existing");
      useToastStore.getState().removeToast("fake-id-12345");
      expect(useToastStore.getState().toasts).toHaveLength(1);
    });
  });

  describe("max 5 toasts (oldest evicted)", () => {
    it("evicts the oldest toast when exceeding 5", () => {
      const store = useToastStore.getState();
      store.addToast("Toast 1");
      store.addToast("Toast 2");
      store.addToast("Toast 3");
      store.addToast("Toast 4");
      store.addToast("Toast 5");
      expect(useToastStore.getState().toasts).toHaveLength(5);

      // Adding a 6th should evict the first
      useToastStore.getState().addToast("Toast 6");
      const toasts = useToastStore.getState().toasts;
      expect(toasts).toHaveLength(5);
      expect(toasts[0].message).toBe("Toast 2");
      expect(toasts[4].message).toBe("Toast 6");
    });

    it("evicts multiple oldest toasts correctly", () => {
      const store = useToastStore.getState();
      for (let i = 1; i <= 5; i++) {
        store.addToast(`Toast ${i}`);
      }
      // Add two more
      useToastStore.getState().addToast("Toast 6");
      useToastStore.getState().addToast("Toast 7");

      const toasts = useToastStore.getState().toasts;
      expect(toasts).toHaveLength(5);
      expect(toasts[0].message).toBe("Toast 3");
      expect(toasts[4].message).toBe("Toast 7");
    });

    it("keeps exactly MAX_TOASTS (5) after many additions", () => {
      const store = useToastStore.getState();
      for (let i = 0; i < 20; i++) {
        store.addToast(`Toast ${i}`);
      }
      expect(useToastStore.getState().toasts).toHaveLength(5);
      // Should have the last 5
      expect(useToastStore.getState().toasts[0].message).toBe("Toast 15");
      expect(useToastStore.getState().toasts[4].message).toBe("Toast 19");
    });
  });

  describe("auto-dismiss after 3s", () => {
    it("removes toast after exactly 3000ms", () => {
      useToastStore.getState().addToast("Temporary");
      expect(useToastStore.getState().toasts).toHaveLength(1);

      vi.advanceTimersByTime(3000);
      expect(useToastStore.getState().toasts).toHaveLength(0);
    });

    it("does not remove toast before 3000ms", () => {
      useToastStore.getState().addToast("Still here");
      vi.advanceTimersByTime(2999);
      expect(useToastStore.getState().toasts).toHaveLength(1);
    });

    it("auto-removes toasts independently with staggered timing", () => {
      useToastStore.getState().addToast("First");
      vi.advanceTimersByTime(1000);
      useToastStore.getState().addToast("Second");

      // At 3000ms: first should be removed, second still has 2s left
      vi.advanceTimersByTime(2000);
      const toasts = useToastStore.getState().toasts;
      expect(toasts).toHaveLength(1);
      expect(toasts[0].message).toBe("Second");

      // At 4000ms: second should be removed
      vi.advanceTimersByTime(1000);
      expect(useToastStore.getState().toasts).toHaveLength(0);
    });
  });

  describe("default type is 'success'", () => {
    it("defaults to success type when no type is provided", () => {
      useToastStore.getState().addToast("Completed");
      expect(useToastStore.getState().toasts[0].type).toBe("success");
    });

    it("respects explicit error type", () => {
      useToastStore.getState().addToast("Failed", "error");
      expect(useToastStore.getState().toasts[0].type).toBe("error");
    });

    it("respects explicit warning type", () => {
      useToastStore.getState().addToast("Caution", "warning");
      expect(useToastStore.getState().toasts[0].type).toBe("warning");
    });

    it("respects explicit info type", () => {
      useToastStore.getState().addToast("Note", "info");
      expect(useToastStore.getState().toasts[0].type).toBe("info");
    });
  });
});
