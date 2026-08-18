import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileSearch,
  KeyRound,
  Scale,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PraviarMark } from "@/components/icons/praviar-mark";
import { SyntheticEditorialDisclosure } from "@/components/marketing/synthetic-editorial-disclosure";
import { buttonVariants } from "@/components/ui/button";
import {
  PUBLIC_METHODOLOGY_ACTION,
  PUBLIC_PRIMARY_ACTION,
  PUBLIC_PURCHASING_NOTICE,
} from "@/marketing/public-readiness";
import { cn } from "@/lib/utils";

const IMPLEMENTED_CONTROLS: Array<{
  body: string;
  icon: LucideIcon;
  title: string;
}> = [
  {
    icon: KeyRound,
    title: "Keep each workspace separate",
    body: "Signed-in access ties data and actions to the active organisation. Roles control who can start work, manage workspace settings or record a review.",
  },
  {
    icon: FileSearch,
    title: "Trace the evidence",
    body: "A report keeps its citations, source status, run details and internal consistency results beside the finding. Reviewers can inspect the reasons behind the priority label.",
  },
  {
    icon: ClipboardCheck,
    title: "Record the review",
    body: "Decisions, notes and reviewer identity stay with the matter. The human review is part of the work, not a footnote added at the end.",
  },
];

const DOSSIER_EVIDENCE = [
  "The compound and commercial question you submitted",
  "Which sources ran, and which were missing or unavailable",
  "The patent families, claim elements and cited passages behind the finding",
  "How the search was narrowed and which internal checks were recorded",
  "Reviewer notes and the questions that still need an answer",
];

const PUBLIC_BOUNDARIES = [
  "Praviar searches configured sources and organises candidate families for review. It does not issue a legal clearance opinion.",
  "Each dossier shows which sources ran, where coverage was incomplete and which questions still need human judgement.",
  "Public samples use fictional patent data. They show how the product works, not customer work or legal research.",
];

const REVIEW_ROUTES = [
  {
    label: "Product method",
    title: "See how the search works",
    body: "Follow the search, the narrowing steps and the evidence that reaches the final report.",
    href: PUBLIC_METHODOLOGY_ACTION.href,
    cta: PUBLIC_METHODOLOGY_ACTION.label,
  },
  {
    label: "Research boundary",
    title: "Read the privacy boundary",
    body: "See what the fictional local preview contains, which integrations exist in code, and what a future operator would still need to disclose.",
    href: "/privacy",
    cta: "Read the privacy notice",
  },
  {
    label: "Security review",
    title: "Check the evidence boundary",
    body: "Use the current assurance table to separate repository evidence from deployment-specific items that an operator must still verify.",
    href: "#assurance-heading",
    cta: "Review current status",
  },
];

const ASSURANCE_RESOURCES = [
  {
    area: "Confidential matter data",
    state: "Review before use",
    body: "Do not upload confidential molecule or legal-matter details to this research preview. It is not presented as an operated confidential-data service.",
  },
  {
    area: "Evidence trail",
    state: "Built into the product",
    body: "Reports keep citations, source status, run details and reviewer decisions beside the finding.",
  },
  {
    area: "Workspace access",
    state: "Built into the product",
    body: "Signed-in work is scoped to an organisation, with role-based product actions.",
  },
  {
    area: "Data handling",
    state: "Research-preview notice",
    body: "The privacy notice separates the fictional local fixture and repository capabilities from deployment-specific processing. It is not an operator policy or production data-flow register.",
  },
  {
    area: "Legal entity and controller",
    state: "Not yet published",
    body: "The public privacy and contract documents do not yet identify a completed contracting entity, controller record or registered address.",
  },
  {
    area: "DPA and transfers",
    state: "Not publicly available",
    body: "A completed DPA, transfer mechanism and production-specific processor allocation are not published here.",
  },
  {
    area: "Subprocessors and residency",
    state: "No operator register",
    body: "The privacy notice identifies integration references in source code, not active subprocessors, processing locations or an operator-approved residency register.",
  },
  {
    area: "Provider training and retention",
    state: "Deployment evidence required",
    body: "A future deployment operator would need to document provider terms, training use and retention for its exact configuration. None is represented here.",
  },
  {
    area: "Security review",
    state: "No operator response offered",
    body: "Any deployment review would require an identified operator, exact scope and evidence packet. This research preview offers no security-review service.",
  },
  {
    area: "Enterprise controls",
    state: "Code capability only",
    body: "SSO and dedicated-infrastructure references describe code paths, not an offered enterprise service or order form.",
  },
  {
    area: "Independent assurance",
    state: "Not currently available",
    body: "Praviar does not claim SOC 2, ISO certification, external attestation or GxP validation on this site.",
  },
  {
    area: "Operational testing",
    state: "No public evidence",
    body: "Praviar does not publish completed penetration testing, incident exercises, backup restore testing or disaster-recovery evidence on this site.",
  },
  {
    area: "Status and service levels",
    state: "Not publicly available",
    body: "No public status history, measured uptime, SLA, RTO, RPO or enterprise service term is offered here.",
  },
  {
    area: "Vulnerability disclosure",
    state: "Repository policy published",
    body: "SECURITY.md publishes a best-effort private GitHub security-advisory reporting path. No security.txt endpoint or response SLA is claimed.",
  },
  {
    area: "Performance evidence",
    state: "No public result yet",
    body: "The fictional dossier shows the product format. It is not evidence of recall, accuracy or legal quality.",
  },
] as const;

const MOBILE_ASSURANCE_GROUPS = [
  {
    id: "product-control-records",
    title: "Product controls",
    description: "Controls visible in the signed-in product",
    resources: ASSURANCE_RESOURCES.slice(1, 3),
  },
  {
    id: "data-deployment-records",
    title: "Data and deployment records",
    description: "Public records and matters requiring signed scope",
    resources: ASSURANCE_RESOURCES.slice(3, 10),
  },
  {
    id: "independent-evidence-records",
    title: "Independent evidence",
    description: "Assurance and operational evidence not claimed here",
    resources: ASSURANCE_RESOURCES.slice(10),
  },
] as const;

export function TrustPageContent() {
  return (
    <div className="light overflow-x-clip bg-[var(--bg-base)] text-[var(--text-primary)]">
      <section className="praviar-trust-hero-field px-4 py-10 sm:px-6 md:py-16">
        <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[0.92fr_1.08fr] lg:items-center">
          <div className="max-w-3xl space-y-6">
            <div className="space-y-4">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                Trust and deployment
              </p>
              <h1 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)] sm:text-5xl md:text-6xl">
                Know what Praviar can protect and prove before you use it.
              </h1>
              <p className="text-base leading-8 text-[var(--text-secondary)] sm:text-lg md:text-xl">
                See the controls built into each report, the evidence available
                today, and the deployment questions the repository cannot
                answer. Do not upload confidential matter data to this research
                preview.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Link
                href={PUBLIC_METHODOLOGY_ACTION.href}
                className={cn(buttonVariants({ size: "lg" }), "rounded-lg")}
              >
                {PUBLIC_METHODOLOGY_ACTION.label}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                href={PUBLIC_PRIMARY_ACTION.href}
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "rounded-lg text-center",
                )}
              >
                {PUBLIC_PRIMARY_ACTION.label}
              </Link>
            </div>
          </div>

          <TrustControlVisual />
        </div>
      </section>

      <section className="border-b border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-12 sm:px-6 md:py-16">
        <div className="mx-auto grid max-w-7xl gap-7 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
          <figure
            className="overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] shadow-[var(--shadow-md)]"
            aria-describedby="trust-editorial-disclosure"
            data-ai-generated="true"
            data-provenance="/brand/editorial/provenance.public.webmanifest#deployment-conversation-v1.webp"
          >
            <div className="relative aspect-[16/9]">
              <Image
                src="/brand/editorial/deployment-conversation-v1.webp"
                alt="Two experienced colleagues pause for a calm conversation beside a plain limestone wall"
                fill
                sizes="(min-width: 1024px) 58vw, 100vw"
                className="object-cover object-left"
              />
            </div>
            <figcaption className="border-t border-[var(--border-subtle)] px-4 py-3 text-[var(--text-tertiary)]">
              <SyntheticEditorialDisclosure id="trust-editorial-disclosure" />
            </figcaption>
          </figure>
          <div className="max-w-xl space-y-4">
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Review before confidential use
            </p>
            <h2 className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl">
              Deployment review is a team decision.
            </h2>
            <p className="text-lg leading-8 text-[var(--text-secondary)]">
              This repository is not an operated confidential-data service. A
              future operator would need to document data handling, available
              evidence, and every deployment-specific control before use.
            </p>
            <Link
              href="#assurance-heading"
              className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
            >
              Review the current assurance status
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </section>

      <div>
        <section
          id="current-assurance"
          className="border-b border-[var(--border-default)] px-4 py-14 sm:px-6 md:py-20"
          aria-labelledby="assurance-heading"
        >
          <div className="mx-auto max-w-7xl space-y-8">
            <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
              <div className="max-w-3xl space-y-4">
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  Current assurance status
                </p>
                <h2
                  id="assurance-heading"
                  className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl"
                >
                  What you can verify today.
                </h2>
                <p className="text-lg leading-8 text-[var(--text-secondary)]">
                  Product controls, public information and deployment evidence
                  are different kinds of evidence. This table keeps them
                  separate.
                </p>
              </div>
              <p className="font-mono text-xs uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Last reviewed 4 August 2026
              </p>
            </div>
            <div className="space-y-3 md:hidden">
              <article className="rounded-xl border border-warning/25 bg-warning/5 p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="font-semibold text-[var(--text-primary)]">
                    {ASSURANCE_RESOURCES[0].area}
                  </h3>
                  <p className="w-fit rounded-full border border-warning/25 bg-warning/10 px-3 py-1 font-mono text-xs font-semibold uppercase tracking-[0.1em] text-warning-emphasis">
                    {ASSURANCE_RESOURCES[0].state}
                  </p>
                </div>
                <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                  {ASSURANCE_RESOURCES[0].body}
                </p>
              </article>
              {MOBILE_ASSURANCE_GROUPS.map((group) => (
                <details
                  key={group.title}
                  aria-labelledby={`${group.id}-title`}
                  className="group rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 shadow-[var(--shadow-xs)]"
                  data-assurance-group={group.id}
                >
                  <summary className="flex min-h-16 cursor-pointer list-none items-center justify-between gap-4 py-3 marker:content-none">
                    <span>
                      <span
                        id={`${group.id}-title`}
                        className="block font-semibold text-[var(--text-primary)]"
                      >
                        {group.title}
                      </span>
                      <span className="mt-1 block text-xs text-[var(--text-tertiary)]">
                        {group.description} · {group.resources.length} records
                      </span>
                    </span>
                    <span
                      aria-hidden="true"
                      className="text-xl text-brand-primary"
                    >
                      <span className="group-open:hidden">＋</span>
                      <span className="hidden group-open:inline">−</span>
                    </span>
                  </summary>
                  <div className="divide-y divide-[var(--border-subtle)] border-t border-[var(--border-subtle)]">
                    {group.resources.map((resource) => (
                      <article key={resource.area} className="py-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                            {resource.area}
                          </h3>
                          <p className="w-fit rounded-full border border-brand-primary/20 bg-brand-primary/8 px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-[0.08em] text-brand-primary">
                            {resource.state}
                          </p>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                          {resource.body}
                        </p>
                      </article>
                    ))}
                  </div>
                </details>
              ))}
            </div>
            <div className="hidden overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[var(--shadow-sm)] md:block">
              <div className="divide-y divide-[var(--border-subtle)]">
                {ASSURANCE_RESOURCES.map((resource) => (
                  <article
                    key={resource.area}
                    className="grid gap-3 p-5 md:grid-cols-[12rem_13rem_minmax(0,1fr)] md:items-start md:gap-6 md:p-6"
                  >
                    <h3 className="font-semibold text-[var(--text-primary)]">
                      {resource.area}
                    </h3>
                    <p className="w-fit rounded-full border border-brand-primary/20 bg-brand-primary/8 px-3 py-1 font-mono text-xs font-semibold uppercase tracking-[0.1em] text-brand-primary">
                      {resource.state}
                    </p>
                    <p className="text-sm leading-7 text-[var(--text-secondary)]">
                      {resource.body}
                    </p>
                  </article>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <Link
                href="/privacy"
                className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
              >
                Read the public data-handling overview
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <span
                className="hidden text-[var(--text-tertiary)] sm:inline"
                aria-hidden="true"
              >
                ·
              </span>
              <Link
                href="#boundaries-heading"
                className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
              >
                Review evidence boundaries
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>

        <section
          className="px-4 py-14 sm:px-6 md:py-20"
          aria-labelledby="controls-heading"
        >
          <div className="mx-auto max-w-7xl space-y-10">
            <div className="max-w-3xl space-y-4">
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Built into the product
              </p>
              <h2
                id="controls-heading"
                className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl"
              >
                The useful controls are part of the work.
              </h2>
              <p className="text-lg leading-8 text-[var(--text-secondary)]">
                These controls are visible in the research-preview interface.
                They are implementation references, not evidence that a hosted
                deployment is available or suitable for confidential data.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {IMPLEMENTED_CONTROLS.map((control) => {
                const Icon = control.icon;
                return (
                  <article
                    key={control.title}
                    className="praviar-surface-premium rounded-lg p-6"
                  >
                    <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-[var(--bg-elevated)] text-[var(--brand-primary)]">
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <h3 className="mt-5 text-xl font-semibold text-[var(--text-primary)]">
                      {control.title}
                    </h3>
                    <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                      {control.body}
                    </p>
                  </article>
                );
              })}
            </div>
            <p
              className="rounded-lg border border-warning/25 bg-warning/10 px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]"
              role="note"
            >
              {PUBLIC_PURCHASING_NOTICE}
            </p>
          </div>
        </section>

        <section
          className="praviar-section-band px-4 py-14 sm:px-6 md:py-20"
          aria-labelledby="packet-heading"
        >
          <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[0.88fr_1.12fr] lg:items-center">
            <div className="space-y-4">
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                A better handoff
              </p>
              <h2
                id="packet-heading"
                className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl"
              >
                Give counsel the trail behind the risk label.
              </h2>
              <p className="text-lg leading-8 text-[var(--text-secondary)]">
                The report keeps each finding next to the claims, citations and
                gaps that shaped it.
              </p>
              <ul className="space-y-3 pt-2">
                {DOSSIER_EVIDENCE.map((item) => (
                  <li
                    key={item}
                    className="flex gap-3 text-sm leading-7 text-[var(--text-secondary)]"
                  >
                    <CheckCircle2
                      className="mt-1 h-4 w-4 shrink-0 text-success"
                      aria-hidden="true"
                    />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <TrustBoundaryArtifact />
          </div>
        </section>

        <section
          className="px-4 py-14 sm:px-6 md:py-20"
          aria-labelledby="boundaries-heading"
        >
          <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[0.8fr_1.2fr]">
            <div className="space-y-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-brand-primary/25 bg-brand-primary/10 text-brand-primary">
                <Scale className="h-5 w-5" aria-hidden="true" />
              </div>
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Where Praviar fits
              </p>
              <h2
                id="boundaries-heading"
                className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl"
              >
                A head start for counsel, not a substitute for counsel.
              </h2>
              <p className="text-lg leading-8 text-[var(--text-secondary)]">
                Use Praviar to find the records worth discussing and prepare a
                brief that is easier to review. Your patent counsel still makes
                the legal call.
              </p>
            </div>
            <div className="space-y-4">
              <ul className="space-y-3">
                {PUBLIC_BOUNDARIES.map((boundary) => (
                  <li
                    key={boundary}
                    className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] p-4 text-sm leading-7 text-[var(--text-secondary)]"
                  >
                    {boundary}
                  </li>
                ))}
              </ul>
              <details className="group rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4">
                <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 font-semibold text-[var(--text-primary)] marker:content-none">
                  Security and assurance details
                  <span
                    aria-hidden="true"
                    className="text-[var(--text-tertiary)]"
                  >
                    <span className="group-open:hidden">＋</span>
                    <span className="hidden group-open:inline">−</span>
                  </span>
                </summary>
                <div className="space-y-3 border-t border-[var(--border-subtle)] pt-4 text-sm leading-7 text-[var(--text-secondary)]">
                  <p>
                    We do not present Praviar as SOC 2 certified, externally
                    attested, GxP validated or regulator approved on this site.
                    Do not use confidential matter data without an identified
                    operator and independently reviewed deployment evidence.
                  </p>
                  <p>
                    Provider training, retention and confidential-data terms
                    would need to be established by an identified deployment
                    operator. This research preview makes no such offer or
                    response commitment.
                  </p>
                </div>
              </details>
            </div>
          </div>
        </section>

        <section
          className="px-4 pb-16 sm:px-6 md:pb-20"
          aria-labelledby="review-heading"
        >
          <div className="mx-auto max-w-7xl space-y-8">
            <div className="max-w-3xl space-y-4">
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Want to go deeper?
              </p>
              <h2
                id="review-heading"
                className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl"
              >
                Choose the reference you want to inspect.
              </h2>
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              {REVIEW_ROUTES.map((route) => (
                <article
                  key={route.title}
                  className="praviar-surface-premium flex flex-col rounded-lg p-6"
                >
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                    {route.label}
                  </p>
                  <h3 className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
                    {route.title}
                  </h3>
                  <p className="mt-3 flex-1 text-sm leading-7 text-[var(--text-secondary)]">
                    {route.body}
                  </p>
                  <Link
                    href={route.href}
                    className="mt-5 inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
                  >
                    {route.cta}
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </article>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function TrustControlVisual() {
  const rows = [
    ["Scope", "Organization and matter context"],
    ["Evidence", "Claims, citations, source health"],
    ["Review", "Decision, notes, unresolved gaps"],
  ];

  return (
    <div
      className="relative min-h-[31rem] overflow-hidden rounded-2xl border border-[var(--border-emphasis)] bg-[radial-gradient(circle_at_18%_22%,rgba(238,183,122,0.28),transparent_30%),radial-gradient(circle_at_78%_28%,rgba(31,111,109,0.2),transparent_38%),linear-gradient(135deg,#faf5eb_0%,#eaf2ed_100%)] shadow-[var(--shadow-lg)]"
      data-testid="trust-control-visual"
    >
      <div
        aria-hidden="true"
        className="absolute left-[10%] top-[12%] h-44 w-44 rounded-full border border-white/60 bg-white/22"
      />
      <div
        aria-hidden="true"
        className="absolute bottom-[12%] left-[20%] h-28 w-64 rounded-full border border-brand-primary/10 bg-white/24 blur-sm"
      />
      <div className="relative ml-auto flex min-h-[31rem] max-w-sm flex-col justify-end p-5 sm:p-7">
        <div className="rounded-2xl border border-white/70 bg-white/88 p-5 text-[var(--text-primary)] shadow-[var(--shadow-md)] backdrop-blur-md">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-brand-primary text-white">
              <PraviarMark size={28} variant="onDark" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                Inside each report
              </p>
              <h2 className="mt-1 text-xl font-semibold">
                The work stays visible
              </h2>
            </div>
          </div>
          <div className="mt-5 grid gap-2">
            {rows.map(([label, value]) => (
              <div
                key={label}
                className="grid gap-1 rounded-lg border border-[var(--border-subtle)] bg-white/72 p-3 sm:grid-cols-[78px_1fr] sm:items-center"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  {label}
                </p>
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {value}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs leading-6 text-[var(--text-secondary)]">
            Ask for deployment-specific evidence before uploading confidential
            matter data.
          </p>
        </div>
      </div>
    </div>
  );
}

function TrustBoundaryArtifact() {
  return (
    <div
      className="praviar-ink-frame relative overflow-hidden rounded-lg p-5 text-[var(--surface-inverted-fg)] shadow-[var(--shadow-md)]"
      data-testid="trust-boundary-artifact"
    >
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--surface-inverted-fg-subtle)]">
              What counsel receives
            </p>
            <h3 className="mt-2 text-2xl font-semibold">
              A useful starting point
            </h3>
          </div>
          <Scale
            className="h-6 w-6 text-[var(--surface-inverted-accent)]"
            aria-hidden="true"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {[
            ["Finding", "Family flagged for review"],
            ["Support", "Claim elements and citations"],
            ["Gap", "Unhealthy source lane visible"],
            ["Next step", "Qualified counsel review"],
          ].map(([label, value]) => (
            <div key={label} className="praviar-ink-chip rounded-lg p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--surface-inverted-fg-subtle)]">
                {label}
              </p>
              <p className="mt-2 text-sm font-semibold leading-6 text-[var(--surface-inverted-fg)]">
                {value}
              </p>
            </div>
          ))}
        </div>
        <p className="praviar-ink-glass rounded-lg p-4 text-sm leading-7 text-[var(--surface-inverted-fg-muted)]">
          Praviar organises the search and shows its work. Counsel interprets
          the claims and makes the legal call.
        </p>
      </div>
    </div>
  );
}
