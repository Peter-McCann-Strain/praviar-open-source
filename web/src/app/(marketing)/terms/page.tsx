import {
  LegalDocumentPage,
  type LegalDocumentSection,
} from "@/components/marketing/legal-document-page";

export const metadata = {
  title: "Research Preview Use Notice",
  description:
    "A non-binding use and reliance boundary for the Praviar open research preview.",
};

const LINK_CLASS_NAME =
  "inline-flex min-h-11 items-center font-medium text-[var(--brand-primary)] underline decoration-[color:rgba(var(--brand-primary-rgb),0.35)] underline-offset-4 transition-colors hover:decoration-[var(--brand-primary)]";

const TERMS_SECTIONS: LegalDocumentSection[] = [
  {
    id: "notice-status",
    title: "1. Notice status—no contract",
    children: (
      <>
        <p>
          This is a non-binding use notice for an open research preview. Viewing
          this site, opening the local demo, or reading the repository does not
          create a service contract, customer relationship, subscription,
          account, clickwrap agreement, or obligation to pay.
        </p>
        <p>
          No verified contracting entity, registered address, offeror, or legal
          notice channel is published here. This page is not &ldquo;Terms of
          Service&rdquo; for an operating Praviar service and should not be used
          as an order form, procurement agreement, or negotiated term sheet.
        </p>
      </>
    ),
  },
  {
    id: "preview-purpose",
    title: "2. Preview purpose",
    children: (
      <>
        <p>
          Praviar is presented as an open research preview and engineering
          portfolio for evidence-led pharmaceutical patent review. It
          demonstrates a Next.js workbench, FastAPI application, structured
          pipeline, fictional report fixture, review controls, and release
          evidence machinery.
        </p>
        <p>
          The documented local demo uses repository fixtures and does not run a
          legal analysis or call the application API. Operational, billing,
          administration, provider, monitoring, and deployment paths are
          engineering examples, not proof of an available or production-tested
          service.
        </p>
      </>
    ),
  },
  {
    id: "no-legal-advice",
    title: "3. No legal advice or reliance",
    children: (
      <>
        <div className="rounded-lg border border-[var(--color-border-warning)] bg-[var(--color-bg-warning)] p-4">
          <p className="font-semibold text-[var(--color-text-warning)]">
            No service. No contract. No legal advice.
          </p>
          <p className="mt-2 text-sm leading-6">
            Praviar is not a law firm, does not provide legal services, and does
            not issue an FTO conclusion or offer assurance of non-infringement.
            Use the preview only to examine software architecture and
            human-review evidence-triage workflows.
          </p>
        </div>
        <p>
          Patent coverage, publication lag, family data, legal status,
          translations, claim construction, Markush scope, equivalents,
          validity, enforceability, jurisdiction-specific law, and third-party
          model behavior can all be incomplete or wrong. Do not make legal,
          commercial, investment, launch, licensing, or research decisions from
          preview output.
        </p>
        <p>
          The fictional examples are not ground truth, customer work, a case
          study, verified legal research, or evidence of recall, accuracy, or a
          false-clear rate. Qualified patent counsel must independently review
          the underlying matter and authoritative sources.
        </p>
      </>
    ),
  },
  {
    id: "no-commercial-offer",
    title: "4. No accounts, subscriptions, or payment offer",
    children: (
      <>
        <p>
          The public research preview does not offer an account, plan,
          subscription, report credit, paid analysis, refund, renewal, service
          level, support deadline, or hosted checkout. Interface states and code
          for billing or payment providers are illustrative implementation
          surfaces and must not be read as a price, purchase invitation, or
          promise of future availability.
        </p>
        <p>
          Do not submit card, billing, tax, procurement, or customer data to an
          unreviewed deployment. Any future commercial offering would require a
          verified operator, complete terms, privacy disclosures, ordering
          mechanics, and deployment-specific evidence outside this page.
        </p>
      </>
    ),
  },
  {
    id: "licences-and-rights",
    title: "5. Source licence and third-party rights",
    children: (
      <>
        <p>
          The Apache-2.0 licence in the repository—not this notice—governs the
          Praviar-authored source code and documentation identified by that
          licence. Its warranty, liability, attribution, patent, and other terms
          remain unchanged.
        </p>
        <p>
          The software licence does not grant rights to third-party patent
          documents, datasets, model weights, APIs, dependencies, media, or
          trademarks. Their own licences, access terms, data-use rules, and
          applicable law must be reviewed before use. Nothing in the preview
          grants source-access, redistribution, database, model, or trademark
          rights that the repository&apos;s authoritative notices do not grant.
        </p>
      </>
    ),
  },
  {
    id: "responsible-evaluation",
    title: "6. Responsible evaluation",
    children: (
      <>
        <p>For safe evaluation:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Use the canonical fictional fixture or material you are authorised
            to process.
          </li>
          <li>
            Do not enter confidential compounds, inventions, client matters,
            credentials, personal data, or regulated data.
          </li>
          <li>
            Do not treat experimental chemistry, vision, model, or similarity
            output as claim scope.
          </li>
          <li>
            Review provider costs, terms, licences, data handling, and security
            before enabling any external integration.
          </li>
          <li>
            Preserve tenant scoping, provenance, review checkpoints, and visible
            failure behavior when modifying the code.
          </li>
        </ul>
        <p>
          Nothing on this page authorises unlawful access, infringement,
          circumvention, export, sanctions evasion, or violation of source,
          provider, database, or model terms. Applicable law and third-party
          rights operate independently.
        </p>
      </>
    ),
  },
  {
    id: "privacy-boundary",
    title: "7. Privacy and local operation",
    children: (
      <p>
        A person who runs or deploys the code controls that environment and is
        responsible for its accounts, access, providers, logs, backups,
        retention, deletion, notices, and legal basis. Read the{" "}
        <a href="/privacy" className={LINK_CLASS_NAME}>
          research-preview privacy notice
        </a>{" "}
        before evaluation. It is not a substitute for an operator-specific
        privacy policy or data processing agreement.
      </p>
    ),
  },
  {
    id: "security-boundary",
    title: "8. Security and deployment boundary",
    children: (
      <>
        <p>
          Repository controls and passing tests do not prove that a deployment
          is secure, available, monitored, backed up, or recoverable. No
          independent security assessment or regulated-work suitability is
          represented. The public project claims no SOC 2, ISO, GxP,
          penetration-test, uptime, RTO, or RPO result.
        </p>
        <p>
          Review the{" "}
          <a href="/trust" className={LINK_CLASS_NAME}>
            trust and evidence boundary
          </a>{" "}
          for what is implemented and what remains unproven.
        </p>
      </>
    ),
  },
  {
    id: "output-limitations",
    title: "9. Output and source limitations",
    children: (
      <p>
        Search results, rankings, extracted text, computer-vision output,
        structure matches, generated summaries, claim mappings, risk labels,
        citations, legal-status signals, and exports can be incomplete,
        outdated, misclassified, unsupported, or unavailable. Fail-closed gates
        and review records improve inspectability; they do not convert a preview
        into legal advice or prove substantive accuracy.
      </p>
    ),
  },
  {
    id: "no-service-promises",
    title: "10. No service promises or online liability terms",
    children: (
      <>
        <p>
          This page offers no warranty, indemnity, support commitment, uptime,
          maintenance period, remedy, refund, liability cap, confidentiality
          promise, data-return promise, or survival term. It also does not
          attempt to waive rights or limit liability. The repository licence
          contains the terms that apply to licensed source material.
        </p>
        <p>
          Any separate deployment, professional engagement, hosted service, or
          commercial relationship would need its own identified parties and
          complete agreement. None is created by this notice.
        </p>
      </>
    ),
  },
  {
    id: "identity-and-law",
    title: "11. No contracting entity, notice address, or governing law",
    children: (
      <p>
        The project does not publish a verified contracting entity, formation
        jurisdiction, company number, registered office, formal notice address,
        governing law, venue, arbitration process, assignment rule,
        force-majeure term, severability term, or contract-priority clause. No
        such term should be inferred from repository metadata, example domains,
        test fixtures, or this page.
      </p>
    ),
  },
  {
    id: "updates-and-authority",
    title: "12. Updates and authoritative documents",
    children: (
      <>
        <p>
          The date above identifies this repository copy. Updates do not create
          an email-notice promise, acceptance-by-continued-use mechanism, or
          version-archive service.
        </p>
        <p>
          For source use, consult the repository&apos;s licence, third-party
          notices, model terms, asset terms, trademark policy, security
          guidance, and upstream provider terms. For a real patent matter,
          consult qualified counsel. This page publishes no verified legal or
          customer-support inbox.
        </p>
      </>
    ),
  },
];

export default function TermsPage() {
  return (
    <LegalDocumentPage
      documentLabel="Non-binding research-preview notice"
      title="Research Preview Use Notice"
      description="A use and reliance boundary for an open, local research preview—not terms for an operating Praviar service."
      lastUpdated="August 13, 2026"
      primaryActionHref="/methodology"
      primaryActionLabel="Review the methodology"
      postureTitle="Current status"
      postureNote="Viewing the preview creates no service contract or purchase. Use only fictional or authorised material and ask qualified patent counsel before acting."
      highlights={[
        { label: "Service relationship", value: "None represented" },
        { label: "Commercial offer", value: "None represented" },
        {
          label: "Legal boundary",
          value: "No legal advice, opinion, or clearance",
        },
      ]}
      sections={TERMS_SECTIONS}
    />
  );
}
