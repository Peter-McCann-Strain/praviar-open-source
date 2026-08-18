import {
  LegalDocumentPage,
  type LegalDocumentSection,
} from "@/components/marketing/legal-document-page";

export const metadata = {
  title: "Research Preview Privacy Notice",
  description:
    "A non-binding privacy boundary for Praviar's local research preview, including what the repository proves and what remains deployment-specific.",
};

const LINK_CLASS_NAME =
  "inline-flex min-h-11 items-center font-medium text-[var(--brand-primary)] underline decoration-[color:rgba(var(--brand-primary-rgb),0.35)] underline-offset-4 transition-colors hover:decoration-[var(--brand-primary)]";

const SUBHEADING_CLASS_NAME =
  "text-lg font-semibold text-[var(--text-primary)]";

const INTEGRATION_REFERENCES = [
  {
    name: "Anthropic",
    repositorySurface: "Optional AI-assisted analysis paths",
    possibleData: "Prompt and analysis context if an operator enables it",
    boundary:
      "Code reference only. No production activation, contract, training posture, transfer mechanism, or retention term is represented here.",
  },
  {
    name: "Clerk",
    repositorySurface: "Authentication and organisation-access code",
    possibleData: "Account, organisation, session, and authentication metadata",
    boundary:
      "Code reference only. The local fixture walkthrough does not establish an active identity service or customer account relationship.",
  },
  {
    name: "Stripe",
    repositorySurface: "Illustrative billing and checkout integration",
    possibleData: "Billing and checkout metadata if configured by an operator",
    boundary:
      "Code reference only. No public purchase flow, subscription, processor appointment, or payment-data practice is represented here.",
  },
  {
    name: "Postmark",
    repositorySurface: "Transactional-notification integration",
    possibleData: "Recipient address and notification content if enabled",
    boundary:
      "Code reference only. No active notification service, delivery geography, or retention schedule is represented here.",
  },
  {
    name: "Sentry",
    repositorySurface: "Optional diagnostics integration",
    possibleData: "Error and performance metadata if enabled",
    boundary:
      "Code reference only. A deployment operator must establish redaction, sampling, residency, access, and retention controls.",
  },
] as const;

const PRIVACY_SECTIONS: LegalDocumentSection[] = [
  {
    id: "status-and-scope",
    title: "1. Status and scope",
    children: (
      <>
        <p>
          This page describes the privacy boundary of the Praviar open research
          preview. It is not represented as the privacy policy of an operating
          service, a customer agreement, a data processing agreement, or a
          complete statutory privacy notice.
        </p>
        <p>
          The public repository does not identify a verified contracting legal
          entity, data controller, registered address, representative, data
          protection officer, or privacy inbox. No such identity or contact
          detail should be inferred from the project name or source code.
        </p>
      </>
    ),
  },
  {
    id: "preview-data",
    title: "2. What the preview contains",
    children: (
      <>
        <h3 className={SUBHEADING_CLASS_NAME}>Canonical fictional material</h3>
        <p>
          The documented local demo mode reads a versioned, wholly fictional
          showcase fixture. Its example compound, patent families, citations,
          review events, exports, and report content are demonstration material,
          not customer data or verified legal research.
        </p>
        <h3 className={SUBHEADING_CLASS_NAME}>Local evaluation boundary</h3>
        <p>
          The documented fixture walkthrough is designed for local evaluation
          and does not run a legal analysis or call the application API. Do not
          enter names, contact details, confidential compounds, invention
          disclosures, client matters, or other sensitive information into a
          public or unreviewed deployment.
        </p>
      </>
    ),
  },
  {
    id: "operator-processing",
    title: "3. If someone deploys the code",
    children: (
      <>
        <p>
          A person or organisation that runs or deploys the repository chooses
          the hosting environment, providers, configuration, logging, access
          model, data sources, retention, and legal basis. That operator is
          responsible for explaining its own processing and for providing any
          notices, contracts, consent choices, and rights channels required by
          law.
        </p>
        <p>
          Depending on those choices, a deployment could process account,
          organisation, network, diagnostic, compound, patent, analysis, report,
          review, sharing, export, billing, or notification data. This list
          describes capabilities visible in the codebase; it does not say that
          any category is currently collected by a public Praviar service.
        </p>
      </>
    ),
  },
  {
    id: "roles-and-legal-bases",
    title: "4. Controller, processor, and legal-basis status",
    children: (
      <>
        <p>
          The repository alone cannot establish who is a controller or
          processor, which jurisdiction applies, or which legal basis supports a
          particular deployment. Those conclusions depend on the actual
          operator, purpose, data flow, users, agreements, and location.
        </p>
        <p>
          No public DPA, controller record, legitimate-interest assessment,
          consent record, international-transfer assessment, or executed
          customer agreement is represented by this page.
        </p>
      </>
    ),
  },
  {
    id: "integration-inventory",
    title: "5. Integration inventory",
    children: (
      <>
        <h3 className={SUBHEADING_CLASS_NAME}>
          Repository references, not a subprocessor list
        </h3>
        <p>
          The codebase contains integration surfaces for the named projects
          below. Presence in source code does not prove that an integration is
          enabled, appointed as a processor, covered by a production contract,
          or suitable for a particular data category or jurisdiction.
        </p>
        <div
          className="space-y-2 md:hidden"
          data-testid="integration-status-mobile-cards"
        >
          {INTEGRATION_REFERENCES.map((row) => (
            <details
              key={row.name}
              className="group/integration rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-4 py-2"
            >
              <summary
                role="button"
                className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 font-semibold text-[var(--text-primary)] marker:content-none"
              >
                <span>{row.name}</span>
                <span
                  aria-hidden="true"
                  className="text-[var(--text-tertiary)]"
                >
                  <span className="group-open/integration:hidden">＋</span>
                  <span className="hidden group-open/integration:inline">
                    −
                  </span>
                </span>
              </summary>
              <div className="space-y-3 border-t border-[var(--border-subtle)] pb-3 pt-4 text-sm leading-6">
                <p>
                  <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    Repository surface
                  </span>
                  {row.repositorySurface}
                </p>
                <p>
                  <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    Possible data
                  </span>
                  {row.possibleData}
                </p>
                <p>
                  <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    Boundary
                  </span>
                  {row.boundary}
                </p>
              </div>
            </details>
          ))}
        </div>
        <div
          className="hidden overflow-hidden rounded-lg border border-[var(--border-subtle)] md:block"
          data-testid="integration-status-table"
        >
          <table className="w-full table-fixed text-left text-sm">
            <colgroup className="hidden md:table-column-group">
              <col className="w-32" />
              <col className="w-48" />
              <col className="w-60" />
              <col />
            </colgroup>
            <thead className="hidden bg-[var(--surface-muted)] text-xs uppercase tracking-[0.12em] text-[var(--text-tertiary)] md:table-header-group">
              <tr>
                <th scope="col" className="whitespace-nowrap px-3 py-2">
                  Reference
                </th>
                <th scope="col" className="px-3 py-2">
                  Repository surface
                </th>
                <th scope="col" className="px-3 py-2">
                  Possible data
                </th>
                <th scope="col" className="px-3 py-2">
                  Boundary
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-subtle)]">
              {INTEGRATION_REFERENCES.map((row) => (
                <tr key={row.name}>
                  <th
                    scope="row"
                    className="whitespace-nowrap px-3 py-3 align-top font-semibold text-[var(--text-primary)]"
                  >
                    {row.name}
                  </th>
                  <td className="px-3 py-3 align-top">
                    {row.repositorySurface}
                  </td>
                  <td className="px-3 py-3 align-top">{row.possibleData}</td>
                  <td className="px-3 py-3 align-top">{row.boundary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    ),
  },
  {
    id: "data-security",
    title: "6. Security and confidentiality boundary",
    children: (
      <>
        <p>
          The repository implements and tests controls such as
          organisation-scoped access, row-level security, validation, audit
          records, and fail-closed evidence gates. Those engineering controls
          are not proof of a particular deployment, independent assurance,
          penetration-test outcome, certification, uptime level, or incident
          response capability.
        </p>
        <p>
          Treat every public or unreviewed instance as unsuitable for
          confidential or regulated information. Review the{" "}
          <a href="/trust" className={LINK_CLASS_NAME}>
            current evidence boundaries
          </a>{" "}
          before evaluating a deployment.
        </p>
      </>
    ),
  },
  {
    id: "data-retention",
    title: "7. Retention, deletion, and backups",
    children: (
      <>
        <p>
          This page publishes no production retention schedule. Values found in
          configuration, infrastructure templates, tests, or historical
          documentation are engineering inputs, not a promise that an operating
          service retains or deletes data on those timelines.
        </p>
        <p>
          Local fixture files, generated artefacts, browser state, databases,
          logs, backups, and provider records remain wherever the person running
          the software places them until that operator or provider removes them.
          The public preview does not offer an account-deletion or erasure
          service.
        </p>
      </>
    ),
  },
  {
    id: "browser-storage",
    title: "8. Browser and network data",
    children: (
      <p>
        The codebase contains browser-storage, authentication, analytics,
        diagnostics, and network-request capabilities. What a browser sends or
        stores depends on the build mode and deployment configuration. An
        operator must inventory those behaviors, separate essential from
        optional storage, and provide any consent controls its jurisdiction
        requires.
      </p>
    ),
  },
  {
    id: "rights-and-contacts",
    title: "9. Rights requests and contacts",
    children: (
      <>
        <p>
          Privacy rights attach to actual processing and should be directed to
          the operator that collected or received the data. A local operator
          controls its own files and environment; a third-party host or provider
          controls the channels it publishes for its services.
        </p>
        <p>
          This research-preview page does not publish a verified controller or
          privacy contact and cannot accept access, correction, deletion,
          objection, portability, or complaint requests. If a distribution of
          this code identifies an operator, consult that operator&apos;s own
          verified privacy notice.
        </p>
      </>
    ),
  },
  {
    id: "changes-and-boundary",
    title: "10. Updates and legal boundary",
    children: (
      <>
        <p>
          This notice can change as repository capabilities and public evidence
          change. The date above identifies this copy; it does not create an
          email-notice promise, version-archive service, or continuing customer
          relationship.
        </p>
        <p>
          This page is informational and cannot substitute for qualified legal
          advice, establish a data-handling warranty, or authorize processing of
          personal or confidential data. The source licence and applicable law
          operate independently of this non-binding notice.
        </p>
      </>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <LegalDocumentPage
      documentLabel="Non-binding research-preview notice"
      title="Research Preview Privacy Notice"
      description="A candid boundary for a local, fictional research preview—not the privacy policy of an operating Praviar service."
      lastUpdated="August 13, 2026"
      primaryActionHref="/trust"
      primaryActionLabel="Review evidence boundaries"
      postureTitle="Current status"
      postureNote="Do not submit personal, confidential, client, or invention data. Any operator deploying this code must publish and honor its own privacy terms."
      highlights={[
        { label: "Operating service", value: "Not represented by this page" },
        { label: "Controller identity", value: "Not verified or published" },
        {
          label: "Safe preview input",
          value: "Repository-provided fictional fixture only",
        },
      ]}
      sections={PRIVACY_SECTIONS}
    />
  );
}
