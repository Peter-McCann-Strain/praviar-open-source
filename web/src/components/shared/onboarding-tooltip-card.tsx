"use client";

import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";
import { SPRING_SNAPPY } from "@/lib/spring-presets";
import type { OnboardingStep } from "./onboarding-tooltip";
import {
  calculateTooltipPosition,
  type TooltipPosition,
} from "./onboarding-tooltip-position";
import { TooltipArrow } from "./onboarding-tooltip-arrow";

interface TooltipCardProps {
  step: OnboardingStep;
  stepIndex: number;
  totalSteps: number;
  targetRect: DOMRect;
  onNext: () => void;
  onSkip: () => void;
  isLastStep: boolean;
}

export function TooltipCard({
  step,
  stepIndex,
  totalSteps,
  targetRect,
  onNext,
  onSkip,
  isLastStep,
}: TooltipCardProps) {
  const titleId = useId();
  const descriptionId = useId();
  const tooltipRef = useRef<HTMLDivElement>(null);
  const primaryActionRef = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState<TooltipPosition | null>(null);

  useEffect(() => {
    if (!tooltipRef.current) return;
    const rect = tooltipRef.current.getBoundingClientRect();
    setPosition(
      calculateTooltipPosition(
        targetRect,
        rect.width,
        rect.height,
        window.innerWidth,
        window.innerHeight,
      ),
    );
  }, [targetRect]);

  useEffect(() => {
    if (position) {
      primaryActionRef.current?.focus({ preventScroll: true });
    }
  }, [position, stepIndex]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onSkip();
      return;
    }

    if (event.key !== "Tab" || !tooltipRef.current) return;

    const focusable = Array.from(
      tooltipRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((element) => !element.hasAttribute("disabled"));

    if (!focusable.length) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <motion.div
      ref={tooltipRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onKeyDown={handleKeyDown}
      initial={{ opacity: 0, scale: 0.95, y: 8 }}
      animate={{
        opacity: 1,
        scale: 1,
        y: 0,
        ...(position ? { top: position.top, left: position.left } : {}),
      }}
      exit={{ opacity: 0, scale: 0.95, y: 8 }}
      transition={SPRING_SNAPPY}
      className={cn(
        "fixed z-[9999] w-[min(320px,calc(100vw-24px))] max-w-[calc(100vw-24px)] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-4 shadow-2xl shadow-[var(--shadow-lg)]",
        !position && "opacity-0",
      )}
      style={
        position
          ? { top: position.top, left: position.left }
          : { top: 0, left: 0 }
      }
    >
      {position && <TooltipArrow placement={position.placement} />}

      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-primary text-xs font-bold text-[var(--brand-paper)]">
            {stepIndex + 1}
          </span>
          <h4
            id={titleId}
            className="text-sm font-semibold text-[var(--text-primary)]"
          >
            {step.title}
          </h4>
        </div>
        <button
          type="button"
          onClick={onSkip}
          className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-md transition-colors hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          aria-label="Skip tour"
        >
          <X
            className="h-4 w-4 text-[var(--text-tertiary)]"
            aria-hidden="true"
          />
        </button>
      </div>

      <p
        id={descriptionId}
        className="mb-4 text-xs leading-relaxed text-[var(--text-secondary)]"
      >
        {step.description}
      </p>

      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-disabled)]">
          {stepIndex + 1} of {totalSteps}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onSkip}
            className="min-h-11 rounded-md px-3 text-xs text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          >
            Skip tour
          </button>
          <Button
            ref={primaryActionRef}
            size="sm"
            onClick={onNext}
            className="min-h-11 px-4 text-xs"
          >
            {isLastStep ? "Finish" : "Next"}
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
