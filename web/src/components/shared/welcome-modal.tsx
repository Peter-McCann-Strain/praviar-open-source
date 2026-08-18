"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useAuth } from "@clerk/nextjs";
import { usePathname, useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ArrowRight, ArrowLeft, Rocket, X } from "lucide-react";
import { motion } from "motion/react";
import { SPRING_SNAPPY } from "@/lib/spring-presets";
import {
  ONBOARDING_TOUR_STORAGE_KEY,
  WELCOME_MODAL_STORAGE_KEY,
  WELCOME_STEPS,
} from "@/components/shared/welcome-modal-constants";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { WelcomeModalStepContent } from "@/components/shared/welcome-modal-step-content";
import { WelcomeModalStepIndicator } from "@/components/shared/welcome-modal-step-indicator";
import { useAuthToken } from "@/hooks/use-auth-token";
import { hasClerk } from "@/hooks/use-clerk-session";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { DEMO_MODE_ENABLED, DEV_AUTH_BYPASS_ENABLED } from "@/lib/constants";
import {
  clearLegacyOnboardingFlags,
  nonClerkOnboardingIdentity,
  readOnboardingFlag,
  type OnboardingStorageIdentity,
  writeOnboardingFlag,
} from "@/lib/onboarding-storage";

/* ── Main Component ─────────────────────────────────────────────────── */

const WELCOME_MODAL_OPEN_DELAY_MS = 600;

interface WelcomeModalProps {
  /** Force the modal open regardless of localStorage (useful for testing) */
  forceOpen?: boolean;
  /** Keep onboarding from interrupting billing and purchase handoffs. */
  suppressBillingRoutes?: boolean;
  /** Keep the onboarding tour from blocking counsel-facing report surfaces. */
  suppressReportRoutes?: boolean;
  /** Keep onboarding from blocking admin, settings, and config control surfaces. */
  suppressControlPlaneRoutes?: boolean;
  /** Keep onboarding from blocking demo/showcase command-center surfaces. */
  suppressShowcaseRoutes?: boolean;
}

export function WelcomeModal(props: WelcomeModalProps) {
  if (hasClerk) {
    return <ClerkScopedWelcomeModal {...props} />;
  }

  return (
    <WelcomeModalContent
      {...props}
      storageIdentity={nonClerkOnboardingIdentity({
        demoMode: DEMO_MODE_ENABLED,
        devAuthBypass: DEV_AUTH_BYPASS_ENABLED,
        nodeEnv: process.env.NODE_ENV,
      })}
    />
  );
}

function ClerkScopedWelcomeModal(props: WelcomeModalProps) {
  const { isLoaded, isSignedIn, userId, orgId } = useAuth();
  const storageIdentity = useMemo(
    () =>
      isLoaded && isSignedIn && userId && orgId ? { userId, orgId } : null,
    [isLoaded, isSignedIn, orgId, userId],
  );

  return <WelcomeModalContent {...props} storageIdentity={storageIdentity} />;
}

function WelcomeModalContent({
  forceOpen,
  suppressBillingRoutes = false,
  suppressReportRoutes = false,
  suppressControlPlaneRoutes = false,
  suppressShowcaseRoutes = false,
  storageIdentity,
}: WelcomeModalProps & { storageIdentity: OnboardingStorageIdentity | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const analysisLaunchAccessSuppressed =
    principal.data?.can_create_analysis !== true;
  const billingRouteSuppressed =
    suppressBillingRoutes &&
    !forceOpen &&
    /^\/billing(?:\/|$)/.test(pathname ?? "");
  const reportRouteSuppressed =
    suppressReportRoutes &&
    !forceOpen &&
    /^\/analyses\/[^/]+\/report(?:\/|$)/.test(pathname ?? "");
  const analysisLaunchSuppressed =
    !forceOpen && /^\/analyses\/new(?:\/|$)/.test(pathname ?? "");
  const controlPlaneRouteSuppressed =
    suppressControlPlaneRoutes &&
    !forceOpen &&
    /^\/(?:admin|settings|config)(?:\/|$)/.test(pathname ?? "");
  const showcaseRouteSuppressed =
    suppressShowcaseRoutes &&
    !forceOpen &&
    /^\/capabilities(?:\/|$)/.test(pathname ?? "");
  const routeSuppressed =
    analysisLaunchAccessSuppressed ||
    billingRouteSuppressed ||
    reportRouteSuppressed ||
    analysisLaunchSuppressed ||
    controlPlaneRouteSuppressed ||
    showcaseRouteSuppressed;
  const [open, setOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [direction, setDirection] = useState(1); // 1 = forward, -1 = backward

  useEffect(() => {
    if (routeSuppressed || (!forceOpen && !storageIdentity)) {
      return;
    }
    if (forceOpen) {
      const timer = setTimeout(() => setOpen(true), 0);
      return () => clearTimeout(timer);
    }
    try {
      clearLegacyOnboardingFlags();
      const welcomed = readOnboardingFlag(
        WELCOME_MODAL_STORAGE_KEY,
        storageIdentity,
      );
      if (!welcomed) {
        const timer = setTimeout(
          () => setOpen(true),
          WELCOME_MODAL_OPEN_DELAY_MS,
        );
        return () => clearTimeout(timer);
      }
    } catch {
      // localStorage unavailable — show modal
      const timer = setTimeout(
        () => setOpen(true),
        WELCOME_MODAL_OPEN_DELAY_MS,
      );
      return () => clearTimeout(timer);
    }
  }, [forceOpen, routeSuppressed, storageIdentity]);

  const handleClose = useCallback(() => {
    setOpen(false);
    // Always persist dismissal so a hard reload or new tab does not re-show
    // the tour. Skipping is an explicit intent to dismiss; require no checkbox.
    try {
      writeOnboardingFlag(WELCOME_MODAL_STORAGE_KEY, storageIdentity);
      writeOnboardingFlag(ONBOARDING_TOUR_STORAGE_KEY, storageIdentity);
    } catch {
      // localStorage write failed — ignore
    }
  }, [storageIdentity]);

  const handleGetStarted = useCallback(() => {
    setOpen(false);
    try {
      writeOnboardingFlag(WELCOME_MODAL_STORAGE_KEY, storageIdentity);
      writeOnboardingFlag(ONBOARDING_TOUR_STORAGE_KEY, storageIdentity);
    } catch {
      // localStorage write failed — ignore
    }
    if (pathname !== "/analyses/new") {
      router.push("/analyses/new");
    }
  }, [pathname, router, storageIdentity]);

  const goToStep = useCallback(
    (step: number) => {
      setDirection(step > currentStep ? 1 : -1);
      setCurrentStep(step);
    },
    [currentStep],
  );

  const nextStep = useCallback(() => {
    if (currentStep < WELCOME_STEPS.length - 1) {
      setDirection(1);
      setCurrentStep((s) => s + 1);
    }
  }, [currentStep]);

  const prevStep = useCallback(() => {
    if (currentStep > 0) {
      setDirection(-1);
      setCurrentStep((s) => s - 1);
    }
  }, [currentStep]);

  const isLastStep = currentStep === WELCOME_STEPS.length - 1;
  const isFirstStep = currentStep === 0;

  if (routeSuppressed) {
    return null;
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) handleClose();
        else setOpen(true);
      }}
    >
      <DialogContent
        className="!flex max-h-[min(94dvh,760px)] w-[calc(100vw-1.5rem)] !flex-col overflow-hidden rounded-lg p-0 shadow-[0_24px_80px_rgba(11,31,36,0.24)] sm:max-w-[760px] [&>button]:hidden"
        onInteractOutside={(event) => event.preventDefault()}
      >
        <div className="praviar-share-handoff-field shrink-0 border-b border-[var(--border-default)] px-5 pb-4 pt-5 sm:px-6">
          <DialogHeader>
            <DialogTitle className="sr-only">Welcome to Praviar</DialogTitle>
            <DialogDescription className="sr-only">
              A guided walkthrough of the Praviar platform.
            </DialogDescription>
          </DialogHeader>
          <div className="mb-4 flex items-start justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <PraviarMarkFrame size="dialog" />
              <div className="min-w-0">
                <span className="block text-xs font-semibold text-brand-primary">
                  Step {currentStep + 1} of {WELCOME_STEPS.length}
                </span>
                <span className="block text-sm font-semibold leading-snug text-[var(--text-primary)] sm:text-base">
                  Praviar first-run briefing
                </span>
              </div>
            </div>
            <button
              onClick={handleClose}
              aria-label="Close first-run briefing"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <WelcomeModalStepIndicator
            total={WELCOME_STEPS.length}
            current={currentStep}
            onStepClick={goToStep}
          />
        </div>

        {/* Animated step content */}
        <div
          className="flex min-h-0 flex-1 items-start justify-center overflow-y-auto px-5 py-5 sm:items-center sm:px-6 sm:py-7"
          role="region"
          tabIndex={0}
          aria-label="Welcome tour content"
        >
          <motion.div
            key={currentStep}
            initial={{ opacity: 0, x: direction * 28 }}
            animate={{ opacity: 1, x: 0 }}
            transition={SPRING_SNAPPY}
            className="w-full"
          >
            <WelcomeModalStepContent step={WELCOME_STEPS[currentStep]} />
          </motion.div>
        </div>

        {/* Footer */}
        <DialogFooter className="shrink-0 border-t border-[var(--border-default)] bg-[color-mix(in_srgb,var(--surface-muted)_48%,transparent)] px-5 pb-5 pt-4 sm:px-6">
          <div className="flex w-full flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="button"
              onClick={handleClose}
              className="min-h-11 w-full rounded-md px-3 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:w-auto"
            >
              Skip tour
            </button>
            <div className="flex items-center justify-between gap-3 sm:justify-end">
              <Button
                variant="ghost"
                onClick={prevStep}
                disabled={isFirstStep}
                className="min-h-11 gap-1.5"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Previous
              </Button>

              {isLastStep ? (
                <Button onClick={handleGetStarted} className="min-h-11 gap-1.5">
                  Start analysis
                  <Rocket className="h-3.5 w-3.5" />
                </Button>
              ) : (
                <Button onClick={nextStep} className="min-h-11 gap-1.5">
                  Next
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
