"use client";

import { OrganizationSwitcher, UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Building2, LogIn, ShieldAlert, ShieldCheck } from "lucide-react";
import {
  buildSessionRecoverySignInHref,
  SESSION_RECOVERY_TITLE,
  SESSION_RECOVERY_UNCHANGED_COPY,
} from "@/components/auth/session-recovery-banner";
import { PraviarLockup } from "@/components/brand/praviar-lockup";
import { Button } from "@/components/ui/button";
import { hasClerk } from "@/hooks/use-clerk-session";

export function OrganizationWorkspaceBoundary({
  children,
}: {
  children: React.ReactNode;
}) {
  if (!hasClerk) return children;
  return (
    <ClerkOrganizationWorkspaceBoundary>
      {children}
    </ClerkOrganizationWorkspaceBoundary>
  );
}

function ClerkOrganizationWorkspaceBoundary({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isLoaded, isSignedIn, orgId } = useAuth();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  if (!isLoaded) {
    return (
      <main
        id="main-content"
        className="flex min-h-screen items-center justify-center bg-[var(--bg-base)] p-6"
      >
        <div className="text-center" role="status">
          <PraviarLockup size="hero" surface="light" />
          <p className="mt-5 text-sm text-[var(--text-secondary)]">
            Verifying your organization workspace…
          </p>
        </div>
      </main>
    );
  }

  if (!isSignedIn) {
    const signInHref = buildSessionRecoverySignInHref(
      pathname,
      searchParams.toString(),
    );

    return (
      <main
        id="main-content"
        className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[var(--bg-base)] px-4 py-10 sm:px-6"
      >
        <section
          aria-label="Session recovery"
          className="relative w-full max-w-xl rounded-2xl border border-warning/30 bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-lg)] sm:p-8"
          role="alert"
        >
          <PraviarLockup size="topbar" surface="light" />
          <div className="mt-8 flex h-12 w-12 items-center justify-center rounded-xl bg-warning/10 text-warning">
            <ShieldAlert className="h-6 w-6" aria-hidden="true" />
          </div>
          <h1 className="mt-5 text-2xl font-semibold text-[var(--text-primary)] sm:text-3xl">
            {SESSION_RECOVERY_TITLE}
          </h1>
          <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
            {SESSION_RECOVERY_UNCHANGED_COPY}
          </p>
          <Button asChild className="mt-6 min-h-11 w-full sm:w-auto">
            <Link href={signInHref}>
              <LogIn className="h-4 w-4" aria-hidden="true" />
              Sign in again
            </Link>
          </Button>
        </section>
      </main>
    );
  }
  if (orgId) return children;

  return (
    <main
      id="main-content"
      className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[var(--bg-base)] px-4 py-10 sm:px-6"
    >
      <div
        className="absolute inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_top,color-mix(in_srgb,var(--brand-mint)_24%,transparent),transparent_68%)]"
        aria-hidden="true"
      />
      <section className="relative w-full max-w-xl rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-lg)] sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <PraviarLockup size="topbar" surface="light" />
          <UserButton />
        </div>
        <div className="mt-8 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-primary/10 text-brand-primary">
          <Building2 className="h-6 w-6" aria-hidden="true" />
        </div>
        <h1 className="mt-5 text-2xl font-semibold text-[var(--text-primary)] sm:text-3xl">
          Select your organization
        </h1>
        <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
          Praviar opens private analyses, reports, credits, and settings only
          after your active Clerk organization is explicit. Personal workspaces
          are not available for enterprise evidence.
        </p>
        <div className="mt-6 rounded-xl border border-[var(--border-default)] bg-[var(--surface-muted)] p-4">
          <OrganizationSwitcher
            hidePersonal
            afterSelectOrganizationUrl="/dashboard"
            afterCreateOrganizationUrl="/dashboard"
            appearance={{
              elements: {
                rootBox: "w-full",
                organizationSwitcherTrigger:
                  "min-h-11 w-full justify-between border border-[var(--border-emphasis)] bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-[var(--shadow-xs)]",
              },
            }}
          />
        </div>
        <div className="mt-5 flex items-start gap-3 rounded-xl border border-success/20 bg-success/10 p-4">
          <ShieldCheck
            className="mt-0.5 h-5 w-5 flex-none text-success"
            aria-hidden="true"
          />
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            Changing organizations clears private caches, in-flight requests,
            launch drafts, and report state before the new workspace opens.
          </p>
        </div>
      </section>
    </main>
  );
}
