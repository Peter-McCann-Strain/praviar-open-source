"use client";

import { motion } from "motion/react";

interface SpotlightOverlayProps {
  rect: DOMRect | null;
}

export function SpotlightOverlay({ rect }: SpotlightOverlayProps) {
  if (!rect) return null;

  const padding = 8;
  const borderRadius = 12;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      data-praviar-onboarding-spotlight
      className="fixed inset-0 z-[9998] pointer-events-auto"
      style={{
        background: `radial-gradient(circle at ${rect.left + rect.width / 2}px ${rect.top + rect.height / 2}px, transparent ${Math.max(rect.width, rect.height) / 2 + padding}px, color-mix(in srgb, var(--brand-ink) 60%, transparent) ${Math.max(rect.width, rect.height) / 2 + padding + 2}px)`,
      }}
    >
      <div
        className="absolute border-2 border-brand-primary/60 transition-all duration-300"
        style={{
          top: rect.top - padding,
          left: rect.left - padding,
          width: rect.width + padding * 2,
          height: rect.height + padding * 2,
          borderRadius,
          boxShadow:
            "0 0 0 9999px color-mix(in srgb, var(--brand-ink) 50%, transparent), 0 0 20px rgba(var(--brand-primary-rgb), 0.3)",
        }}
      />
    </motion.div>
  );
}
