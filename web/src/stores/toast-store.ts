import { create } from "zustand";
import { TOAST_AUTO_DISMISS_MS } from "@/lib/constants";

export interface Toast {
  id: string;
  message: string;
  type: "success" | "info" | "warning" | "error";
}

interface ToastState {
  toasts: Toast[];
  addToast: (message: string, type?: Toast["type"]) => void;
  removeToast: (id: string) => void;
}

/** Maximum concurrent toasts. Oldest removed when exceeded. */
const MAX_TOASTS = 5;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (message, type = "success") => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    set((s) => {
      const next = [...s.toasts, { id, message, type }];
      // Evict oldest if over limit
      return {
        toasts: next.length > MAX_TOASTS ? next.slice(-MAX_TOASTS) : next,
      };
    });
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, TOAST_AUTO_DISMISS_MS);
  },
  removeToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
