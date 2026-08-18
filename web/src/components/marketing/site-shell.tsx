import Link from "next/link";
import { BRAND } from "@/marketing/content";
import { MarketingNav } from "@/components/marketing/marketing-nav";
import { PraviarLockup } from "@/components/brand/praviar-lockup";

export function MarketingSiteShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="light praviar-marketing-shell min-h-screen text-[var(--text-primary)]">
      <MarketingNav />
      <main id="main-content">{children}</main>
      <footer
        className="border-t border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-8 sm:px-6 sm:py-12"
        data-marketing-footer
      >
        <div className="mx-auto grid max-w-7xl gap-7 md:grid-cols-[1.2fr_1fr] md:gap-10">
          <div className="space-y-2 sm:space-y-3">
            <PraviarLockup
              size="marketing"
              tagline={BRAND.tagline}
              wordmark={BRAND.name}
            />
            <h2 className="max-w-xl text-xl font-semibold leading-7 text-[var(--text-primary)] sm:text-2xl">
              {BRAND.footerCopy}
            </h2>
            <p className="max-w-xl text-sm leading-6 text-[var(--text-secondary)]">
              Explore the wholly fictional sample, learn how the screening
              works, and review the public research-preview boundary. Real and
              confidential matters are not accepted here.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-5 sm:gap-8">
            <div className="space-y-1 sm:space-y-3">
              <h3 className="type-marketing-label pb-1">Explore</h3>
              <div className="flex flex-col text-sm text-[var(--text-secondary)] sm:gap-1">
                <Link
                  href="/demo"
                  className="inline-flex min-h-11 items-center hover:text-[var(--text-primary)]"
                >
                  Demo
                </Link>
                <Link
                  href="/sample-reports/example-molecule-alpha"
                  className="inline-flex min-h-11 items-center hover:text-[var(--text-primary)]"
                >
                  Sample Dossier
                </Link>
                <Link
                  href="/methodology"
                  className="inline-flex min-h-11 items-center hover:text-[var(--text-primary)]"
                >
                  Methodology
                </Link>
                <Link
                  href="/#project"
                  className="inline-flex min-h-11 items-center hover:text-[var(--text-primary)]"
                >
                  Open source
                </Link>
                <Link
                  href="/trust"
                  className="inline-flex min-h-11 items-center hover:text-[var(--text-primary)]"
                >
                  Trust and security
                </Link>
                <Link
                  href="/compare/adaptive-agentic"
                  className="inline-flex min-h-11 items-center hover:text-[var(--text-primary)]"
                >
                  How deeper checks work
                </Link>
              </div>
            </div>
            <div className="space-y-1 sm:space-y-3">
              <h3 className="type-marketing-label pb-1">Company</h3>
              <div className="flex flex-col text-sm text-[var(--text-secondary)] sm:gap-1">
                <Link
                  href="/for-biotech-founders"
                  className="inline-flex min-h-11 items-center hover:text-[var(--text-primary)]"
                >
                  For Biotech Founders
                </Link>
                <Link
                  href="/privacy"
                  className="inline-flex min-h-11 items-center hover:text-[var(--text-primary)]"
                >
                  Privacy
                </Link>
                <Link
                  href="/terms"
                  className="inline-flex min-h-11 items-center hover:text-[var(--text-primary)]"
                >
                  Terms
                </Link>
              </div>
            </div>
          </div>
        </div>

        <div className="mx-auto mt-7 flex max-w-7xl flex-col gap-2 border-t border-[var(--border-subtle)] pt-5 text-xs leading-5 text-[var(--text-tertiary)] sm:mt-10 sm:gap-3 sm:pt-6 md:flex-row md:items-center md:justify-between">
          <p>
            &copy; {new Date().getFullYear()} {BRAND.name}. All rights reserved.
          </p>
          <p className="max-w-3xl leading-5">
            Praviar helps organise an early patent-risk review. It does not
            replace legal advice.
          </p>
        </div>
      </footer>
    </div>
  );
}
