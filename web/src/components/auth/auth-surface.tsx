"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  Building2,
  CheckCircle2,
  EyeOff,
  FileSearch,
  KeyRound,
  Loader2,
  LockKeyhole,
  ReceiptText,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import type { AuthCheckoutIntent } from "@/components/auth/auth-checkout-intent";
import { PraviarLockup } from "@/components/brand/praviar-lockup";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { Button } from "@/components/ui/button";
import { BRAND } from "@/marketing/content";
import { PUBLIC_ASSURANCE_BOUNDARY_HREF } from "@/lib/support-boundary";

interface AuthSurfaceProps {
  children: ReactNode;
  checkoutIntent?: AuthCheckoutIntent | null;
  showIdentityReadiness?: boolean;
  showMobileProof?: boolean;
}

interface AuthUnavailableStateProps {
  title: string;
  checkoutIntent?: AuthCheckoutIntent | null;
  context?: "entry" | "sso-callback";
}

interface DemoSignInStateProps {
  checkoutIntent?: AuthCheckoutIntent | null;
  returnPath: string;
}

const AUTH_PROOF_ITEMS = [
  {
    label: "Tenant boundary",
    copy: "Compound evidence, patent citations, and reviewer decisions stay sealed inside your organization workspace.",
    icon: ShieldCheck,
  },
  {
    label: "Identity provider required",
    copy: "Workspace access opens only after the configured sign-in flow confirms identity.",
    icon: LockKeyhole,
  },
  {
    label: "Audit context after sign-in",
    copy: "Reviewer decisions and access-sensitive actions attach to a verified workspace identity.",
    icon: FileSearch,
  },
] as const;

const AUTH_ACCESS_LEDGER_ITEMS: Array<{
  label: string;
  copy: string;
  status: string;
  icon: LucideIcon;
}> = [
  {
    label: "Tenant boundary",
    copy: "Compound evidence, citations, and reviewer decisions remain sealed inside your organization workspace.",
    status: "Sealed",
    icon: ShieldCheck,
  },
  {
    label: "Evidence remains sealed",
    copy: "Source-linked reports, claim charts, and reviewer notes are not exposed.",
    status: "Sealed",
    icon: EyeOff,
  },
  {
    label: "Identity provider required",
    copy: "Workspace data opens only after the configured sign-in flow is available.",
    status: "Required",
    icon: UsersRound,
  },
] as const;

const AUTH_SEALED_DOSSIER_ITEMS = [
  ["Compound", "Sealed"],
  ["Citations", "Hidden"],
  ["Decision", "Scoped"],
] as const;

const AUTH_TRACE_ITEMS = [
  {
    label: "Tenant boundary",
    value: "Workspace sealed",
  },
  {
    label: "Identity check",
    value: "Provider required",
  },
  {
    label: "Audit context",
    value: "After sign-in",
  },
] as const;

const AUTH_IDENTITY_READINESS_ITEMS: Array<{
  label: string;
  value: string;
  copy: string;
  icon: LucideIcon;
}> = [
  {
    label: "Identity methods",
    value: "Provider controlled",
    copy: "SSO, email-code, and passkey policies follow the configured identity provider.",
    icon: KeyRound,
  },
  {
    label: "Workspace route",
    value: "Tenant scoped",
    copy: "Return paths stay local before the session opens an organization workspace.",
    icon: Building2,
  },
  {
    label: "Audit session",
    value: "Attached after sign-in",
    copy: "Reviewer actions and exports bind to the verified workspace identity.",
    icon: ScrollText,
  },
] as const;

const AUTH_PACKET_ROWS = [
  ["Compound evidence", "Sealed"],
  ["Claim chart", "Locked"],
  ["Reviewer decision", "Pending sign-in"],
] as const;

export function AuthSurface({
  children,
  checkoutIntent,
  showIdentityReadiness = true,
  showMobileProof = true,
}: AuthSurfaceProps) {
  return (
    <section
      aria-label="Praviar access"
      className="praviar-auth-field min-h-screen px-4 py-4 sm:px-6 sm:py-8"
    >
      <div className="mx-auto grid min-h-[calc(100dvh-4rem)] w-full max-w-6xl items-center gap-8 lg:grid-cols-[minmax(0,0.94fr)_minmax(360px,440px)]">
        <section
          aria-labelledby="auth-proof-title"
          className="hidden lg:block"
          data-testid="auth-desktop-proof"
        >
          <div className="praviar-auth-visual max-w-xl overflow-hidden rounded-lg border border-[var(--border-default)] shadow-[var(--shadow-lg)]">
            <div className="border-b border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)] p-7 backdrop-blur-xl">
              <div className="flex items-start justify-between gap-4">
                <PraviarLockup
                  size="marketing"
                  tagline={BRAND.tagline}
                  wordmark={BRAND.name}
                  className="shrink-0"
                />
                <span className="rounded-full border border-brand-primary/25 bg-brand-primary/10 px-2.5 py-1 text-xs font-semibold text-brand-primary">
                  Identity gated
                </span>
              </div>
              <h2
                id="auth-proof-title"
                className="mt-6 max-w-md [font-family:var(--font-newsreader)] text-3xl font-semibold leading-tight text-[var(--text-primary)]"
              >
                Protected evidence workspace
              </h2>
              <p className="mt-3 max-w-md text-sm leading-6 text-[var(--text-secondary)]">
                Sign in to your Praviar workspace to open compound evidence,
                patent citations, reviewer decisions, and audit context inside
                your organization boundary.
              </p>
            </div>

            <div className="grid gap-3 p-5">
              <div className="praviar-glass-panel-soft rounded-lg p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="type-label-sm text-[var(--text-tertiary)]">
                      Workspace evidence state
                    </p>
                    <p className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                      Compound evidence remains sealed
                    </p>
                  </div>
                  <PraviarMarkFrame size="sm" />
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  {AUTH_SEALED_DOSSIER_ITEMS.map(([label, value]) => (
                    <div
                      key={label}
                      className="rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_76%,transparent)] px-3 py-2"
                    >
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {value}
                      </p>
                      <p className="type-label-sm mt-1 text-[var(--text-tertiary)]">
                        {label}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid gap-3 rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--surface-muted)_64%,transparent)] p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="type-label-sm text-[var(--text-tertiary)]">
                      Sealed dossier packet
                    </p>
                    <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                      Evidence sealed until the identity check passes
                    </p>
                  </div>
                  <LockKeyhole
                    className="h-5 w-5 shrink-0 text-[var(--brand-primary)]"
                    aria-hidden="true"
                  />
                </div>
                <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)]">
                  {AUTH_PACKET_ROWS.map(([label, value]) => (
                    <div
                      key={label}
                      className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-[var(--border-subtle)] px-3 py-2 last:border-b-0"
                    >
                      <span className="min-w-0 text-xs font-medium text-[var(--text-secondary)]">
                        {label}
                      </span>
                      <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-1 text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                        {value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div
                aria-label="Authentication assurance controls"
                className="grid gap-2 sm:grid-cols-3"
              >
                {AUTH_TRACE_ITEMS.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)] px-3 py-2 backdrop-blur-xl"
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                      {item.label}
                    </p>
                    <p className="mt-1 text-xs font-semibold text-[var(--text-primary)]">
                      {item.value}
                    </p>
                  </div>
                ))}
              </div>

              <div className="grid gap-3">
                {AUTH_PROOF_ITEMS.map(({ label, copy, icon: Icon }) => (
                  <div
                    key={label}
                    className="praviar-glass-chip rounded-lg p-4"
                  >
                    <div className="flex gap-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[var(--surface-muted)] text-[var(--brand-primary)]">
                        <Icon className="h-4 w-4" aria-hidden="true" />
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {label}
                        </p>
                        <p className="mt-1 text-sm text-[var(--text-secondary)]">
                          {copy}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-2 px-1 text-xs font-medium text-[var(--text-tertiary)]">
                <CheckCircle2
                  className="h-4 w-4 text-[var(--brand-primary)]"
                  aria-hidden="true"
                />
                Access opens only after tenant and identity context are
                available.
              </div>
            </div>
          </div>
        </section>

        <section className="flex min-w-0 flex-col items-center justify-center gap-5">
          {checkoutIntent ? (
            <AuthCheckoutIntentPanel intent={checkoutIntent} />
          ) : null}

          {children}

          {showIdentityReadiness ? <AuthIdentityReadiness /> : null}

          {showMobileProof ? (
            <div
              data-testid="auth-mobile-proof"
              className="praviar-auth-visual w-full max-w-md overflow-hidden rounded-lg border border-[var(--border-default)] shadow-[var(--shadow-md)] lg:hidden"
            >
              <div className="bg-[color-mix(in_srgb,var(--bg-surface)_78%,transparent)] p-5 backdrop-blur-xl">
                <div className="grid gap-3">
                  <PraviarLockup
                    size="topbar"
                    tagline={BRAND.tagline}
                    wordmark={BRAND.name}
                    className="shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="mt-1 text-base font-semibold leading-6 text-[var(--text-primary)]">
                      Protected evidence workspace
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                      Compound evidence, patent citations, and reviewer
                      decisions stay sealed inside your organization workspace.
                    </p>
                  </div>
                </div>
              </div>
              <div className="grid gap-2 border-t border-[var(--border-subtle)] px-4 py-3 text-xs sm:grid-cols-3">
                {AUTH_TRACE_ITEMS.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_76%,transparent)] px-3 py-2 backdrop-blur-xl"
                  >
                    <p className="font-semibold text-[var(--text-primary)]">
                      {item.label}
                    </p>
                    <p className="mt-0.5 text-[var(--text-tertiary)]">
                      {item.value}
                    </p>
                  </div>
                ))}
              </div>
              <div className="grid gap-2 p-4 text-xs text-[var(--text-secondary)]">
                {AUTH_PROOF_ITEMS.map(({ label, icon: Icon }) => (
                  <div
                    key={label}
                    className="flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_76%,transparent)] px-3 py-2 font-medium backdrop-blur-xl"
                  >
                    <Icon
                      className="h-3.5 w-3.5 text-[var(--brand-primary)]"
                      aria-hidden="true"
                    />
                    {label}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </section>
  );
}

function AuthCheckoutIntentPanel({ intent }: { intent: AuthCheckoutIntent }) {
  return (
    <section
      aria-label="Selected checkout context"
      className="w-full max-w-md overflow-hidden rounded-lg border border-brand-primary/20 bg-[color-mix(in_srgb,var(--bg-surface)_78%,transparent)] shadow-[var(--shadow-sm)] backdrop-blur-xl"
      data-pack-id={intent.packId}
      data-testid="auth-checkout-intent"
    >
      <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] p-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Selected before sign-in
          </p>
          <h2 className="mt-1 text-base font-semibold leading-6 text-[var(--text-primary)]">
            {intent.packLabel}
          </h2>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {intent.packDescription}
          </p>
        </div>
        <span className="rounded-full border border-brand-primary/25 bg-brand-primary/10 px-2.5 py-1 text-xs font-semibold text-brand-primary">
          {intent.savingsLabel}
        </span>
      </div>

      <dl className="grid grid-cols-3 divide-x divide-[var(--border-subtle)] border-b border-[var(--border-subtle)]">
        <CheckoutIntentMetric label="Capacity" value={intent.reportCredits} />
        <CheckoutIntentMetric label="Total" value={intent.totalPrice} />
        <CheckoutIntentMetric label="Rate" value={intent.effectiveRate} />
      </dl>

      <div className="grid gap-2 p-4 text-xs leading-5 text-[var(--text-secondary)]">
        <CheckoutIntentAssurance
          icon={CheckCircle2}
          text="Included Report Credits are checked first after sign-in."
        />
        <CheckoutIntentAssurance
          icon={ReceiptText}
          text="Stripe checkout opens only if extra prepaid capacity is needed."
        />
        <CheckoutIntentAssurance icon={FileSearch} text={intent.contractCopy} />
      </div>
    </section>
  );
}

function CheckoutIntentMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 px-3 py-3">
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm font-semibold leading-5 text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}

function CheckoutIntentAssurance({
  icon: Icon,
  text,
}: {
  icon: LucideIcon;
  text: string;
}) {
  return (
    <div className="flex min-w-0 items-start gap-2">
      <Icon
        className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand-primary)]"
        aria-hidden="true"
      />
      <span className="min-w-0">{text}</span>
    </div>
  );
}

function AuthIdentityReadiness() {
  return (
    <section
      aria-label="Identity readiness"
      className="w-full max-w-md overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)] shadow-[var(--shadow-xs)] backdrop-blur-xl"
      data-testid="auth-identity-readiness"
    >
      <div className="grid gap-2 p-3">
        {AUTH_IDENTITY_READINESS_ITEMS.map(
          ({ label, value, copy, icon: Icon }) => (
            <div
              key={label}
              className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--surface-muted)_58%,transparent)] px-3 py-2"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    {label}
                  </p>
                  <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">
                    {value}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                  {copy}
                </p>
              </div>
            </div>
          ),
        )}
      </div>
    </section>
  );
}

export function AuthLoadingState({
  title,
  checkoutIntent,
}: AuthUnavailableStateProps) {
  return (
    <AuthSurface checkoutIntent={checkoutIntent} showMobileProof={false}>
      <div
        className="praviar-surface-premium w-full max-w-md overflow-hidden rounded-lg shadow-[var(--shadow-lg)]"
        data-praviar-app-state="loading"
        role="status"
        aria-live="polite"
      >
        <div className="flex items-start gap-4 border-b border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)] px-5 py-5 backdrop-blur-xl sm:px-6">
          <PraviarMarkFrame className="mt-0.5" size="lg" />
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Protected workspace
            </p>
            <h1 className="mt-1 text-xl font-bold text-[var(--text-primary)]">
              {title}
            </h1>
            <p className="mt-2 text-sm font-medium leading-6 text-[var(--text-secondary)]">
              Preparing the identity check before opening private evidence.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 px-5 py-5 text-sm text-[var(--text-secondary)] sm:px-6">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
            <Loader2
              className="h-4 w-4 animate-spin motion-reduce:animate-none"
              aria-hidden="true"
            />
          </span>
          <span>Checking secure workspace configuration...</span>
        </div>
      </div>
    </AuthSurface>
  );
}

export function DemoSignInState({
  checkoutIntent,
  returnPath,
}: DemoSignInStateProps) {
  return (
    <AuthSurface
      checkoutIntent={checkoutIntent}
      showIdentityReadiness={false}
      showMobileProof={false}
    >
      <div
        className="praviar-surface-premium w-full max-w-md overflow-hidden rounded-lg shadow-[var(--shadow-lg)]"
        data-testid="demo-sign-in-state"
      >
        <div className="border-b border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)] px-5 py-5 backdrop-blur-xl sm:px-6">
          <div className="flex items-start gap-4">
            <PraviarMarkFrame className="mt-0.5" size="hero" />
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
                Synthetic demonstration
              </p>
              <h1 className="mt-1 text-xl font-bold text-[var(--text-primary)]">
                Sign In
              </h1>
              <p className="mt-2 text-sm font-medium leading-6 text-[var(--text-secondary)]">
                Explore a preloaded evidence workspace without opening a
                customer tenant or creating an authenticated identity session.
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-4 px-5 py-5 sm:px-6">
          <section
            aria-label="Demonstration boundary"
            className="rounded-lg border border-brand-primary/20 bg-brand-primary/10 p-4"
          >
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-[var(--bg-surface)] text-brand-primary">
                <EyeOff className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                  Demo data only
                </h2>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  Compounds, patents, decisions, users, billing, and audit
                  events are synthetic. Changes stay inside this local demo and
                  are not legal advice or a clearance opinion.
                </p>
              </div>
            </div>
          </section>

          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
            <Button asChild className="min-h-11 gap-2">
              <Link href={returnPath}>
                <FileSearch className="h-4 w-4" aria-hidden="true" />
                Enter demo workspace
              </Link>
            </Button>
            <Button asChild variant="outline" className="min-h-11">
              <Link href="/">Back to public site</Link>
            </Button>
          </div>

          <p className="text-xs leading-5 text-[var(--text-tertiary)]">
            Production workspaces remain sealed behind their configured identity
            provider. This demo path cannot authenticate into one.
          </p>
        </div>
      </div>
    </AuthSurface>
  );
}

export function AuthUnavailableState({
  title,
  checkoutIntent,
  context = "entry",
}: AuthUnavailableStateProps) {
  const isSSOCallback = context === "sso-callback";
  return (
    <AuthSurface checkoutIntent={checkoutIntent}>
      <div
        className="praviar-surface-premium w-full max-w-md overflow-hidden rounded-lg shadow-[var(--shadow-lg)]"
        data-auth-unavailable-context={context}
        data-testid="auth-unavailable-state"
      >
        <div className="border-b border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)] px-4 py-4 backdrop-blur-xl sm:px-6 sm:py-5">
          <div className="flex items-start gap-3 sm:gap-4">
            <PraviarMarkFrame className="mt-0.5" size="hero" />
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)] sm:text-xs">
                {isSSOCallback ? "SSO return blocked" : "Protected workspace"}
              </p>
              <h1 className="mt-1 text-lg font-bold text-[var(--text-primary)] sm:text-xl">
                {title}
              </h1>
              <p className="mt-1 text-sm font-medium leading-5 text-[var(--text-secondary)] sm:mt-2 sm:leading-6">
                <span className="sm:hidden">
                  {isSSOCallback
                    ? "The SSO return cannot finish. Evidence remains sealed."
                    : "Authentication is unavailable. Compound evidence remains sealed."}
                </span>
                <span className="hidden sm:inline">
                  {isSSOCallback
                    ? "The identity-provider return cannot finish because the authentication connection is unavailable. Evidence remains sealed, and no workspace session was created."
                    : "Authentication check is unavailable. Evidence remains sealed until the workspace identity provider is configured. Compound evidence, patent citations, and reviewer decisions stay inside your organization workspace."}
                </span>
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-2.5 px-4 py-3 sm:space-y-5 sm:px-6 sm:py-5">
          <section
            aria-label="Authentication trust ledger"
            className="hidden overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--surface-muted)_54%,transparent)] sm:block"
          >
            {AUTH_ACCESS_LEDGER_ITEMS.map(
              ({ label, copy, status, icon: Icon }) => (
                <div
                  key={label}
                  className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-b border-[var(--border-subtle)] px-4 py-3 last:border-b-0 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center"
                >
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      {label}
                    </p>
                    <p className="mt-0.5 text-xs leading-5 text-[var(--text-secondary)]">
                      {copy}
                    </p>
                  </div>
                  <span className="col-start-2 w-fit rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2 py-1 text-xs font-semibold uppercase text-[var(--text-tertiary)] sm:col-start-auto">
                    {status}
                  </span>
                </div>
              ),
            )}
          </section>

          <div className="rounded-lg border border-warning/25 bg-warning/10 px-3 py-2 sm:px-4 sm:py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-warning">
              Next step
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] sm:text-sm sm:leading-6">
              <span className="sm:hidden">
                {isSSOCallback
                  ? `Restart ${title.toLowerCase()}, or ask an admin to verify the identity provider.`
                  : "Retry, or ask an admin to verify the identity provider."}
              </span>
              <span className="hidden sm:inline">
                {isSSOCallback
                  ? `Return to ${title.toLowerCase()} and restart the identity-provider handoff, or ask your Praviar administrator to verify the connection.`
                  : "Ask your Praviar administrator to verify the identity provider connection, or retry after access configuration is available."}
              </span>
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              className="min-h-11 gap-1.5 px-2 text-xs sm:gap-2 sm:text-sm"
              onClick={() => window.location.reload()}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {isSSOCallback ? "Retry callback" : "Try again"}
            </Button>
            <Button
              asChild
              variant="outline"
              className="min-h-11 gap-1.5 px-2 text-xs sm:gap-2 sm:text-sm"
            >
              <Link href={PUBLIC_ASSURANCE_BOUNDARY_HREF}>
                <FileSearch className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="sm:hidden">Review setup</span>
                <span className="hidden sm:inline">
                  Review deployment setup
                </span>
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </AuthSurface>
  );
}
