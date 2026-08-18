"use client";

import { X, CheckCircle, Info, AlertTriangle, XCircle } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { usePathname } from "next/navigation";
import { useToastStore } from "@/stores/toast-store";
import { cn } from "@/lib/utils";

const TOAST_STYLES = {
  success: {
    bg: "bg-success/10 border-success/25",
    text: "text-success",
    Icon: CheckCircle,
  },
  info: {
    bg: "bg-info/10 border-info/25",
    text: "text-info",
    Icon: Info,
  },
  warning: {
    bg: "bg-warning/10 border-warning/25",
    text: "text-warning",
    Icon: AlertTriangle,
  },
  error: {
    bg: "bg-error/10 border-error/25",
    text: "text-error",
    Icon: XCircle,
  },
};

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore();
  const pathname = usePathname();
  const isReportRoute = pathname?.includes("/report") ?? false;

  return (
    <div
      role="region"
      className={cn(
        "fixed z-50 flex flex-col gap-2",
        isReportRoute
          ? "inset-x-3 bottom-[calc(10.75rem+env(safe-area-inset-bottom))] max-w-none sm:left-auto sm:right-6 sm:bottom-6 sm:max-w-sm"
          : "inset-x-3 top-[calc(4.75rem+env(safe-area-inset-top))] max-w-none sm:inset-x-auto sm:bottom-6 sm:right-6 sm:top-auto sm:max-w-sm",
      )}
      aria-label="Notifications"
    >
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => {
          const style = TOAST_STYLES[toast.type];
          const isAssertive =
            toast.type === "error" || toast.type === "warning";
          return (
            <motion.div
              key={toast.id}
              layout
              initial={{ opacity: 0, x: 50, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 50, scale: 0.95 }}
              transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1.0] }}
              className={cn(
                "relative flex items-start gap-2 rounded-lg border px-3 py-2 shadow-xl shadow-[var(--shadow-md)] backdrop-blur-sm sm:items-center sm:gap-3 sm:px-4 sm:py-3",
                style.bg,
              )}
            >
              <style.Icon
                className={cn("mt-1 h-4 w-4 flex-shrink-0 sm:mt-0", style.text)}
              />
              <p
                role={isAssertive ? "alert" : "status"}
                aria-live={isAssertive ? "assertive" : "polite"}
                aria-atomic="true"
                className="min-w-0 flex-1 pr-9 text-sm leading-5 text-[var(--text-primary)] sm:pr-0"
              >
                {toast.message}
              </p>
              <button
                type="button"
                onClick={() => removeToast(toast.id)}
                className="absolute right-1 top-1 inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-md text-[var(--text-disabled)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:static"
                aria-label="Close notification"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
