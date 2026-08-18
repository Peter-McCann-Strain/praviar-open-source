import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";

import { PraviarLockup } from "@/components/brand/praviar-lockup";
import {
  DIGEST_UNSUBSCRIBE_COOKIE,
  hasUsableDigestUnsubscribeToken,
} from "@/lib/digest-unsubscribe";

export const metadata: Metadata = {
  title: "Weekly digest preferences | Praviar",
  referrer: "no-referrer",
  robots: {
    index: false,
    follow: false,
  },
};

type SearchParams = Promise<{
  result?: string;
  token?: string;
}>;

const RESULT_COPY: Record<
  string,
  { title: string; description: string; tone: string }
> = {
  processed: {
    title: "Request received",
    description:
      "If this link matched a current digest, recurring weekly summaries are now off. Essential account and requested workflow messages are unchanged.",
    tone: "border-success/25 bg-success/10",
  },
  retry: {
    title: "We could not confirm the change",
    description:
      "No outcome was inferred. Retry from the email or update Notification Settings after signing in.",
    tone: "border-danger/25 bg-danger/10",
  },
};

export default async function DigestUnsubscribePage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const result = params.result ? RESULT_COPY[params.result] : undefined;
  const cookieStore = await cookies();
  const cookieToken = cookieStore.get(DIGEST_UNSUBSCRIBE_COOKIE)?.value ?? "";
  const hasUsableToken =
    hasUsableDigestUnsubscribeToken(cookieToken) ||
    hasUsableDigestUnsubscribeToken(params.token ?? "");

  return (
    <main className="relative isolate flex min-h-dvh items-center justify-center overflow-hidden bg-[var(--bg-base)] px-4 py-8 sm:px-6 sm:py-10">
      <div
        aria-hidden="true"
        className="praviar-evidence-field-pattern pointer-events-none absolute inset-0 -z-10"
      />
      <section
        data-testid="digest-preference-surface"
        className="grid w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-xl md:grid-cols-[0.82fr_1.18fr]"
      >
        <aside
          data-testid="digest-preference-context"
          className="border-b border-[var(--border-default)] bg-[var(--surface-muted)]/55 p-6 md:border-b-0 md:border-r md:p-8"
        >
          <PraviarLockup size="marketing" tagline="Email preferences" />

          <div className="mt-6 hidden md:block">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--brand-primary)]">
              Account messaging
            </p>
            <h2 className="mt-2 text-2xl font-semibold leading-tight text-[var(--text-primary)]">
              Change one email stream. Keep the rest intact.
            </h2>
            <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
              This one-purpose link controls the weekly activity digest without
              changing workflow alerts or account access.
            </p>
            <div className="mt-6 grid gap-3">
              {[
                ["Digest only", "Recurring weekly activity summaries"],
                ["Alerts preserved", "Analysis and monitor notifications"],
                ["Account unchanged", "Security and access messages"],
              ].map(([label, description]) => (
                <div
                  key={label}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)]/70 px-4 py-3"
                >
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {label}
                  </p>
                  <p className="mt-0.5 text-xs leading-5 text-[var(--text-secondary)]">
                    {description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </aside>

        <div className="min-w-0 p-6 sm:p-8">
          {result ? (
            <div className={`rounded-xl border p-5 ${result.tone}`}>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                Weekly digest
              </p>
              <h1 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
                {result.title}
              </h1>
              <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                {result.description}
              </p>
            </div>
          ) : (
            <>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--brand-primary)]">
                Weekly digest
              </p>
              <h1 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
                Stop weekly digest emails?
              </h1>
              <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                This turns off recurring weekly activity summaries only.
                Analysis completion, monitor alerts, security, and account
                messages keep their existing settings.
              </p>

              {hasUsableToken ? (
                <form
                  action="/api/email/unsubscribe"
                  method="post"
                  className="mt-6"
                >
                  <input
                    type="hidden"
                    name="List-Unsubscribe"
                    value="One-Click"
                  />
                  <input type="hidden" name="source" value="footer" />
                  <button
                    type="submit"
                    className="min-h-12 w-full rounded-lg bg-brand-primary px-5 py-3 text-sm font-semibold text-[var(--brand-paper)] transition-colors hover:bg-brand-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2"
                  >
                    Turn off weekly digests
                  </button>
                </form>
              ) : (
                <div className="mt-6 rounded-xl border border-warning/25 bg-warning/10 p-4 text-sm leading-6 text-[var(--text-secondary)]">
                  This unsubscribe link is incomplete. No preferences were
                  changed.
                </div>
              )}
            </>
          )}

          <div className="mt-6 flex flex-col gap-2 text-center text-sm sm:flex-row sm:justify-start sm:gap-3">
            <Link
              href={result ? "/settings/notifications" : "/"}
              className="inline-flex min-h-11 items-center justify-center rounded-lg px-4 font-medium text-brand-primary transition-colors hover:bg-brand-primary/10 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2"
            >
              {result ? "Notification Settings" : "Keep weekly digests"}
            </Link>
            <Link
              href={result ? "/" : "/settings/notifications"}
              className="inline-flex min-h-11 items-center justify-center rounded-lg px-4 text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2"
            >
              {result ? "Return to Praviar" : "Manage all email preferences"}
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
