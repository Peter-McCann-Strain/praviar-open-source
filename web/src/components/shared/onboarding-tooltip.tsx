"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { AnimatePresence } from "motion/react";
import {
  ONBOARDING_TOUR_STORAGE_KEY,
  WELCOME_MODAL_STORAGE_KEY,
} from "@/components/shared/welcome-modal-constants";
import { motionAwareScrollBehavior } from "@/lib/motion-preferences";
import { SpotlightOverlay } from "./onboarding-tooltip-spotlight";
import { TooltipCard } from "./onboarding-tooltip-card";
import { hasClerk } from "@/hooks/use-clerk-session";
import { DEMO_MODE_ENABLED, DEV_AUTH_BYPASS_ENABLED } from "@/lib/constants";
import {
  clearLegacyOnboardingFlags,
  nonClerkOnboardingIdentity,
  readOnboardingFlag,
  type OnboardingStorageIdentity,
  writeOnboardingFlag,
} from "@/lib/onboarding-storage";

/* ── Constants ──────────────────────────────────────────────────────── */

function persistTourComplete(identity: OnboardingStorageIdentity | null) {
  try {
    writeOnboardingFlag(ONBOARDING_TOUR_STORAGE_KEY, identity);
  } catch {
    // ignore
  }
}

function isVisibleTourTarget(el: Element) {
  const rect = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);

  return (
    rect.width > 0 &&
    rect.height > 0 &&
    rect.right > 0 &&
    rect.left < window.innerWidth &&
    rect.bottom > 0 &&
    rect.top < window.innerHeight &&
    style.display !== "none" &&
    style.visibility !== "hidden" &&
    style.pointerEvents !== "none"
  );
}

/* ── Types ──────────────────────────────────────────────────────────── */

export interface OnboardingStep {
  /** CSS selector for the target element to highlight */
  target: string;
  /** Tooltip title */
  title: string;
  /** Tooltip description */
  description: string;
}

interface OnboardingTooltipProps {
  /** Array of tour steps */
  steps: OnboardingStep[];
  /** Force the tour to start regardless of localStorage (useful for testing) */
  forceStart?: boolean;
  /** Callback when the tour completes */
  onComplete?: () => void;
  /** Callback when the tour is skipped */
  onSkip?: () => void;
}

/* ── Main Component ─────────────────────────────────────────────────── */

export function OnboardingTooltip(props: OnboardingTooltipProps) {
  if (hasClerk) {
    return <ClerkScopedOnboardingTooltip {...props} />;
  }

  return (
    <OnboardingTooltipContent
      {...props}
      storageIdentity={nonClerkOnboardingIdentity({
        demoMode: DEMO_MODE_ENABLED,
        devAuthBypass: DEV_AUTH_BYPASS_ENABLED,
        nodeEnv: process.env.NODE_ENV,
      })}
    />
  );
}

function ClerkScopedOnboardingTooltip(props: OnboardingTooltipProps) {
  const { isLoaded, isSignedIn, userId, orgId } = useAuth();
  const storageIdentity = useMemo(
    () =>
      isLoaded && isSignedIn && userId && orgId ? { userId, orgId } : null,
    [isLoaded, isSignedIn, orgId, userId],
  );

  return (
    <OnboardingTooltipContent {...props} storageIdentity={storageIdentity} />
  );
}

function OnboardingTooltipContent({
  steps,
  forceStart = false,
  onComplete,
  onSkip,
  storageIdentity,
}: OnboardingTooltipProps & {
  storageIdentity: OnboardingStorageIdentity | null;
}) {
  const [active, setActive] = useState(() => forceStart);
  const [currentStep, setCurrentStep] = useState(0);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  // Check if tour should start
  useEffect(() => {
    let startTimer: ReturnType<typeof setTimeout> | undefined;
    let welcomePoll: ReturnType<typeof setInterval> | undefined;

    const startTour = (delay = 800) => {
      startTimer = setTimeout(() => setActive(true), delay);
    };

    if (forceStart) {
      startTour(0);
      return () => {
        if (startTimer) clearTimeout(startTimer);
      };
    }
    if (!storageIdentity) return;
    try {
      clearLegacyOnboardingFlags();
      const completed = readOnboardingFlag(
        ONBOARDING_TOUR_STORAGE_KEY,
        storageIdentity,
      );
      if (!completed) {
        const startAfterWelcome = () => {
          const welcomed = readOnboardingFlag(
            WELCOME_MODAL_STORAGE_KEY,
            storageIdentity,
          );
          if (welcomed) {
            startTour();
            return true;
          }
          return false;
        };

        if (!startAfterWelcome()) {
          welcomePoll = setInterval(() => {
            if (startAfterWelcome() && welcomePoll) {
              clearInterval(welcomePoll);
              welcomePoll = undefined;
            }
          }, 250);
        }
      }
    } catch {
      // localStorage unavailable — skip tour
    }
    return () => {
      if (startTimer) clearTimeout(startTimer);
      if (welcomePoll) clearInterval(welcomePoll);
    };
  }, [forceStart, storageIdentity]);

  useEffect(() => {
    if (!active) return;

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    return () => {
      previousFocusRef.current?.focus?.({ preventScroll: true });
      previousFocusRef.current = null;
    };
  }, [active]);

  // Find and track the target element
  useEffect(() => {
    if (!active || !steps[currentStep]) return;

    const findTarget = () => {
      const el =
        Array.from(document.querySelectorAll(steps[currentStep].target)).find(
          isVisibleTourTarget,
        ) ?? null;
      if (el) {
        setTargetRect(el.getBoundingClientRect());
        // Scroll into view if needed
        el.scrollIntoView({
          behavior: motionAwareScrollBehavior(),
          block: "nearest",
        });
        requestAnimationFrame(() => {
          setTargetRect(el.getBoundingClientRect());
        });
        return true;
      } else {
        setTargetRect(null);
        return false;
      }
    };

    let rafId: number | null = null;
    let missingTargetPoll: ReturnType<typeof setInterval> | null = null;

    const clearMissingTargetPoll = () => {
      if (!missingTargetPoll) return;
      clearInterval(missingTargetPoll);
      missingTargetPoll = null;
    };

    if (!findTarget()) {
      missingTargetPoll = setInterval(() => {
        if (findTarget()) {
          clearMissingTargetPoll();
        }
      }, 250);
    }

    // Re-measure on scroll/resize, throttled to one measurement per frame
    const handleReposition = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        findTarget();
      });
    };
    window.addEventListener("scroll", handleReposition, true);
    window.addEventListener("resize", handleReposition);

    return () => {
      window.removeEventListener("scroll", handleReposition, true);
      window.removeEventListener("resize", handleReposition);
      if (rafId !== null) cancelAnimationFrame(rafId);
      clearMissingTargetPoll();
    };
  }, [active, currentStep, steps, storageIdentity]);

  const markComplete = useCallback(() => {
    persistTourComplete(storageIdentity);
  }, [storageIdentity]);

  const handleNext = useCallback(() => {
    if (currentStep < steps.length - 1) {
      setCurrentStep((s) => s + 1);
    } else {
      // Tour complete
      setActive(false);
      markComplete();
      onComplete?.();
    }
  }, [currentStep, steps.length, markComplete, onComplete]);

  const handleSkip = useCallback(() => {
    setActive(false);
    markComplete();
    onSkip?.();
  }, [markComplete, onSkip]);

  if (!active || !steps.length) return null;

  return (
    <AnimatePresence>
      {targetRect && (
        <>
          <SpotlightOverlay rect={targetRect} />
          <TooltipCard
            step={steps[currentStep]}
            stepIndex={currentStep}
            totalSteps={steps.length}
            targetRect={targetRect}
            onNext={handleNext}
            onSkip={handleSkip}
            isLastStep={currentStep === steps.length - 1}
          />
        </>
      )}
    </AnimatePresence>
  );
}
