import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore } from "@/stores/ui-store";

beforeEach(() => {
  localStorage.removeItem("praviar-ui");
  useUIStore.setState({ sidebarOpen: true, mobileSidebarOpen: false });
  document.documentElement.className = "light";
});

describe("ui-store", () => {
  describe("default state", () => {
    it("sidebarOpen is true by default", () => {
      expect(useUIStore.getState().sidebarOpen).toBe(true);
    });

    it("does not expose a persisted theme preference", () => {
      const state = useUIStore.getState() as Record<string, unknown>;

      expect(state.theme).toBeUndefined();
      expect(state.setTheme).toBeUndefined();
    });
  });

  describe("toggleSidebar", () => {
    it("toggles sidebar from open to closed", () => {
      useUIStore.getState().toggleSidebar();
      expect(useUIStore.getState().sidebarOpen).toBe(false);
    });

    it("toggles sidebar from closed to open", () => {
      useUIStore.setState({ sidebarOpen: false });
      useUIStore.getState().toggleSidebar();
      expect(useUIStore.getState().sidebarOpen).toBe(true);
    });

    it("toggles back and forth", () => {
      useUIStore.getState().toggleSidebar();
      expect(useUIStore.getState().sidebarOpen).toBe(false);

      useUIStore.getState().toggleSidebar();
      expect(useUIStore.getState().sidebarOpen).toBe(true);
    });
  });

  describe("setSidebarOpen", () => {
    it("sets sidebar to closed", () => {
      useUIStore.getState().setSidebarOpen(false);
      expect(useUIStore.getState().sidebarOpen).toBe(false);
    });

    it("sets sidebar to open", () => {
      useUIStore.setState({ sidebarOpen: false });
      useUIStore.getState().setSidebarOpen(true);
      expect(useUIStore.getState().sidebarOpen).toBe(true);
    });

    it("can be called with the same value", () => {
      useUIStore.getState().setSidebarOpen(true);
      expect(useUIStore.getState().sidebarOpen).toBe(true);
    });
  });

  describe("premium light palette contract", () => {
    it("leaves the document theme class untouched by UI state changes", () => {
      useUIStore.getState().toggleSidebar();
      useUIStore.getState().setMobileSidebarOpen(true);

      expect(document.documentElement.className).toBe("light");
    });

    it("does not persist transient mobile drawer state", () => {
      useUIStore.getState().setMobileSidebarOpen(true);

      const stored = JSON.parse(localStorage.getItem("praviar-ui") ?? "{}");

      expect(stored.state.sidebarOpen).toBe(true);
      expect(stored.state.mobileSidebarOpen).toBeUndefined();
    });

    it("drops stale persisted theme and mobile drawer keys from old localStorage records", async () => {
      localStorage.setItem(
        "praviar-ui",
        JSON.stringify({
          state: {
            sidebarOpen: false,
            mobileSidebarOpen: true,
            theme: "dark",
          },
          version: 0,
        }),
      );

      await useUIStore.persist.rehydrate();
      const state = useUIStore.getState() as Record<string, unknown>;

      expect(state.sidebarOpen).toBe(false);
      expect(state.mobileSidebarOpen).toBe(false);
      expect(state.theme).toBeUndefined();
      expect(document.documentElement.className).toBe("light");
    });
  });
});
