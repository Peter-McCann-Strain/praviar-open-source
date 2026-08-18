import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIState {
  sidebarOpen: boolean;
  mobileSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function mergePersistedUIState(
  persistedState: unknown,
  currentState: UIState,
): UIState {
  if (!isRecord(persistedState)) return currentState;

  return {
    ...currentState,
    sidebarOpen:
      typeof persistedState.sidebarOpen === "boolean"
        ? persistedState.sidebarOpen
        : currentState.sidebarOpen,
    mobileSidebarOpen: false,
  };
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      mobileSidebarOpen: false,
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),
    }),
    {
      name: "praviar-ui",
      partialize: ({ sidebarOpen }) => ({
        sidebarOpen,
      }),
      merge: mergePersistedUIState,
    },
  ),
);
