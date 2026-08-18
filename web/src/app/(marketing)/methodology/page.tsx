import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  FileSearch,
  GitBranch,
  ListFilter,
  Microscope,
  Scale,
  Search,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageEventBeacon } from "@/components/marketing/page-event-beacon";
import { SecondaryEvidenceHero } from "@/components/marketing/secondary-evidence-hero";
import { SyntheticEditorialDisclosure } from "@/components/marketing/synthetic-editorial-disclosure";
import {
  PUBLIC_PRIMARY_ACTION,
  PUBLIC_PURCHASING_NOTICE,
} from "@/marketing/public-readiness";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Methodology",
  description:
    "See how Praviar organises a compound and commercial plan into a structured preliminary brief with claim evidence, source gaps, and questions for counsel.",
};

const PIPELINE_STAGES: Array<{
  body: string;
  icon: LucideIcon;
  number: string;
  title: string;
}> = [
  {
    number: "01",
    title: "Confirm the compound",
    body: "Praviar keeps the value you submitted, checks the identity, and adds useful chemical structure context when it is available.",
    icon: Microscope,
  },
  {
    number: "02",
    title: "Search the selected sources",
    body: "The search runs across the patent and chemical sources available for the matter and records any source that was unavailable.",
    icon: Search,
  },
  {
    number: "03",
    title: "Narrow the field",
    body: "Broad results are grouped and ordered so candidate patent families can be prioritised for claim review.",
    icon: ListFilter,
  },
  {
    number: "04",
    title: "Read the claims",
    body: "The proposed product or process is compared with individual claim elements, with cited support kept beside each finding.",
    icon: FileSearch,
  },
  {
    number: "05",
    title: "Flag close calls",
    body: "Borderline language and equivalence questions are flagged for counsel instead of being forced into a confident answer.",
    icon: GitBranch,
  },
  {
    number: "06",
    title: "Find research leads",
    body: "Prior-art and claim-support leads are gathered as starting points for expert follow-up, with uncertainty kept visible.",
    icon: Scale,
  },
  {
    number: "07",
    title: "Check the work",
    body: "The product runs configured checks on required fields, citations, source health and analysis failures. These are internal controls, not external validation, and the output can still be wrong.",
    icon: ShieldCheck,
  },
  {
    number: "08",
    title: "Prepare the brief",
    body: "The main findings, claim support, source gaps, and open questions are brought together for your team and patent counsel.",
    icon: FileCheck2,
  },
];

const PIPELINE_CHAPTERS = [
  {
    number: "01",
    label: "Define the matter",
    title: "Start with the decision, not a keyword.",
    body: "The compound, planned activity, territory, and timing set the boundaries for the work.",
    stageIndexes: [0, 1],
  },
  {
    number: "02",
    label: "Reduce the noise",
    title: "Move from a broad search to the claims worth reading.",
    body: "Families are grouped and ranked before the proposed product or process is compared with claim language.",
    stageIndexes: [2, 3],
  },
  {
    number: "03",
    label: "Challenge the first answer",
    title: "Keep uncertainty visible when the language is not clear.",
    body: "Close calls and research leads stay open for expert review instead of being forced into a neat conclusion.",
    stageIndexes: [4, 5],
  },
  {
    number: "04",
    label: "Prepare the handoff",
    title: "Check the evidence, then show the reviewer what remains.",
    body: "The final brief brings the finding, its support, source gaps, and open questions into one review trail.",
    stageIndexes: [6, 7],
  },
] as const;

const SCOPE_INPUTS = [
  "The exact compound or project identifier submitted",
  "Territories and the patent-source lanes enabled for the matter",
  "Planned acts, product context, development stage, and decision timing",
  "Any known patents, assignees, formulations, uses, or process constraints",
];

const REVIEW_LIMITS = [
  "No patent search can prove that every relevant record was found.",
  "Material status, expiry, ownership, and jurisdiction details need to be checked against official registers.",
  "Infringement, validity, licensing, and enforceability remain legal questions for qualified counsel.",
  "If a source is missing or unavailable, the report shows the gap.",
];

const COVERAGE_LANES = [
  {
    lane: "Patent office targets",
    scope: "US, EP, WO, JP, KR, CN, IN, CA and AU",
    evidence:
      "The selected office targets and any unavailable source lane are recorded in the report.",
    check:
      "Confirm material records and status in the relevant official register.",
  },
  {
    lane: "Chemical identity",
    scope: "PubChem and SureChEMBL when enabled for the matter",
    evidence:
      "Submitted identity, synonyms and available structure context stay with the search record.",
    check:
      "Confirm salts, stereochemistry, prodrugs and metabolites for the real product.",
  },
  {
    lane: "Literature leads",
    scope: "OpenAlex and Semantic Scholar when enabled for the matter",
    evidence:
      "Research leads are separated from patent claim findings and keep their source references.",
    check:
      "Qualified reviewers decide whether a reference changes validity or scope questions.",
  },
  {
    lane: "Family and legal status",
    scope: "Available provider records, with source and retrieval context",
    evidence:
      "Family and status fields remain tied to their source. Missing context is shown as a gap.",
    check:
      "Ownership, status, expiry and local effect require official-register review.",
  },
] as const;

const PUBLIC_EVALUATION_MEASURES = [
  "Family-level retrieval recall at a declared cut-off",
  "False-clear rate and required abstention or escalation",
  "Claim-element citation support and source-gap detection",
  "Jurisdiction, date and legal-status accuracy",
  "Reviewer correction rate and agreement between qualified reviewers",
  "Review time and cost, reported separately from legal quality",
];

export default function MethodologyPage() {
  return (
    <div className="light">
      <PageEventBeacon
        eventName="methodology_opened"
        properties={{ source: "page" }}
      />

      <SecondaryEvidenceHero
        eyebrow="Methodology"
        title="See how a compound becomes a patent-risk brief."
        description="Praviar scopes the question, searches the selected sources, narrows the results, and links each concern to the claim evidence behind it."
        proofItems={[
          { label: "Scope", value: "Territory, acts, timing" },
          { label: "Search", value: "Sources and gaps" },
          { label: "Handoff", value: "Evidence and open questions" },
        ]}
        visualEyebrow="The review trail"
        visualTitle="Every finding stays connected to the search, the claim, and the questions still open."
        visualItems={[
          { label: "Start", value: "Compound and commercial context" },
          { label: "Review", value: "Families, claims, sources, gaps" },
          {
            label: "Finish",
            value: "A structured brief for counsel to review",
          },
        ]}
        visualFooter="The public example is fictional and shows the product, not real legal research."
      />

      <div className="mx-auto max-w-7xl space-y-12 px-4 py-14 sm:px-6 md:space-y-16 md:py-20">
        <section
          aria-labelledby="scope-heading"
          className="grid gap-6 lg:grid-cols-2"
        >
          <div className="praviar-surface-premium rounded-lg p-7 md:p-8">
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Start with the real question
            </p>
            <h2
              id="scope-heading"
              className="mt-3 [font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)]"
            >
              A compound alone is not enough.
            </h2>
            <p className="mt-4 text-base leading-8 text-[var(--text-secondary)]">
              Where you plan to operate, what you plan to do, and when you plan
              to launch all change the search.
            </p>
            <p
              className="mt-4 rounded-lg border border-warning/25 bg-warning/8 px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]"
              role="note"
            >
              Confidential or real-matter use is unavailable in this public
              research preview. An independent deployer must establish its own
              legal, security, privacy, and data-handling controls before any
              such use.
            </p>
            <ul className="mt-6 space-y-3">
              {SCOPE_INPUTS.map((item) => (
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

          <div className="rounded-lg border border-[var(--surface-inverted)] bg-[var(--surface-inverted)] p-7 text-[var(--surface-inverted-fg)] shadow-[var(--shadow-lg)] md:p-8">
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--surface-inverted-accent)]">
              What the report cannot settle
            </p>
            <h2 className="mt-3 [font-family:var(--font-newsreader)] text-4xl leading-tight">
              The gaps matter too.
            </h2>
            <ul className="mt-6 space-y-4">
              {REVIEW_LIMITS.map((item) => (
                <li
                  key={item}
                  className="flex gap-3 text-sm leading-7 text-[var(--surface-inverted-fg-muted)]"
                >
                  <ShieldCheck
                    className="mt-1 h-4 w-4 shrink-0 text-[var(--surface-inverted-accent)]"
                    aria-hidden="true"
                  />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <figure
          className="relative overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-md)]"
          aria-describedby="method-editorial-disclosure"
          data-ai-generated="true"
          data-provenance="/brand/editorial/provenance.public.webmanifest#method-conversation-v1.webp"
        >
          <div className="relative min-h-[13rem] md:min-h-[31rem]">
            <Image
              src="/brand/editorial/method-conversation-v1.webp"
              alt="Three experienced professionals align through a thoughtful conversation in a contemporary atrium"
              fill
              sizes="(min-width: 1280px) 80rem, 100vw"
              className="object-cover object-[68%_center] md:object-center"
            />
          </div>
          <figcaption className="grid gap-4 border-t border-white/10 bg-[var(--surface-inverted)] p-5 text-[var(--surface-inverted-fg)] md:grid-cols-[1fr_0.9fr_auto] md:items-center md:p-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--surface-inverted-fg-subtle)]">
                One method · different disciplines
              </p>
              <p className="mt-2 [font-family:var(--font-newsreader)] text-3xl leading-tight">
                Make the handoff easier to question.
              </p>
            </div>
            <p className="text-sm leading-6 text-[var(--surface-inverted-fg-muted)]">
              Praviar organises the trail. A qualified reviewer decides what it
              means for the matter.
            </p>
            <Link
              href={PUBLIC_PRIMARY_ACTION.href}
              className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[var(--surface-inverted-accent)] underline-offset-4 hover:underline md:justify-self-end"
            >
              {PUBLIC_PRIMARY_ACTION.label}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </figcaption>
          <div className="border-t border-[var(--border-subtle)] px-4 py-3 text-[var(--text-tertiary)]">
            <SyntheticEditorialDisclosure id="method-editorial-disclosure" />
          </div>
        </figure>

        <section aria-labelledby="coverage-heading" className="space-y-8">
          <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
            <div className="max-w-3xl space-y-4">
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Coverage and evaluation
              </p>
              <h2
                id="coverage-heading"
                className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl"
              >
                Know the scope before you judge the result.
              </h2>
              <p className="text-lg leading-8 text-[var(--text-secondary)]">
                A target jurisdiction is not a promise that every source ran or
                every relevant family was found. The report must show the
                selected lanes, their source health and the checks still left to
                a qualified reviewer.
              </p>
            </div>
            <p className="font-mono text-xs uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Public method note · reviewed 4 August 2026
            </p>
          </div>

          <div className="space-y-3 lg:hidden">
            {COVERAGE_LANES.map((item) => (
              <details
                key={item.lane}
                className="group rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 shadow-[var(--shadow-xs)]"
              >
                <summary className="flex min-h-16 cursor-pointer list-none items-center justify-between gap-4 py-3 marker:content-none">
                  <span>
                    <span className="block font-semibold text-[var(--text-primary)]">
                      {item.lane}
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-[var(--text-tertiary)]">
                      {item.scope}
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
                <div className="space-y-4 border-t border-[var(--border-subtle)] py-4 text-sm leading-6 text-[var(--text-secondary)]">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                      What the report records
                    </p>
                    <p className="mt-2">{item.evidence}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                      What still needs review
                    </p>
                    <p className="mt-2">{item.check}</p>
                  </div>
                </div>
              </details>
            ))}
          </div>

          <div className="hidden overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[var(--shadow-sm)] lg:block">
            <div className="hidden grid-cols-[12rem_1fr_1.15fr_1.15fr] gap-5 border-b border-[var(--border-default)] bg-[var(--surface-muted)] px-6 py-4 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] lg:grid">
              <span>Lane</span>
              <span>Public scope</span>
              <span>What the report records</span>
              <span>What still needs review</span>
            </div>
            <div className="divide-y divide-[var(--border-subtle)]">
              {COVERAGE_LANES.map((item) => (
                <article
                  key={item.lane}
                  className="grid gap-3 p-5 lg:grid-cols-[12rem_1fr_1.15fr_1.15fr] lg:gap-5 lg:px-6"
                >
                  <h3 className="font-semibold text-[var(--text-primary)]">
                    {item.lane}
                  </h3>
                  <p className="text-sm leading-7 text-[var(--text-secondary)]">
                    {item.scope}
                  </p>
                  <p className="text-sm leading-7 text-[var(--text-secondary)]">
                    {item.evidence}
                  </p>
                  <p className="text-sm leading-7 text-[var(--text-secondary)]">
                    {item.check}
                  </p>
                </article>
              ))}
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-[0.82fr_1.18fr]">
            <article className="rounded-2xl border border-warning/25 bg-warning/5 p-6">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-warning-emphasis">
                Public evidence status
              </p>
              <h3 className="mt-3 text-2xl font-semibold text-[var(--text-primary)]">
                No public performance result yet.
              </h3>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                The fictional dossier demonstrates the report format only. It
                does not establish recall, accuracy, legal quality or customer
                outcomes. Praviar will not publish one headline accuracy number
                without a declared method and qualified review.
              </p>
            </article>
            <details className="group rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 lg:hidden">
              <summary className="flex min-h-16 cursor-pointer list-none items-center justify-between gap-4 py-3 marker:content-none">
                <span>
                  <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    Measures for a public evaluation
                  </span>
                  <span className="mt-1 block text-sm text-[var(--text-secondary)]">
                    See the six measures Praviar would publish
                  </span>
                </span>
                <span aria-hidden="true" className="text-xl text-brand-primary">
                  <span className="group-open:hidden">＋</span>
                  <span className="hidden group-open:inline">−</span>
                </span>
              </summary>
              <ul className="space-y-3 border-t border-[var(--border-subtle)] py-4">
                {PUBLIC_EVALUATION_MEASURES.map((measure) => (
                  <li
                    key={measure}
                    className="flex gap-3 text-sm leading-6 text-[var(--text-secondary)]"
                  >
                    <CheckCircle2
                      className="mt-1 h-4 w-4 shrink-0 text-success"
                      aria-hidden="true"
                    />
                    <span>{measure}</span>
                  </li>
                ))}
              </ul>
            </details>
            <article className="hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-6 lg:block">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Measures for a public evaluation
              </p>
              <ul className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
                {PUBLIC_EVALUATION_MEASURES.map((measure) => (
                  <li
                    key={measure}
                    className="flex gap-3 text-sm leading-6 text-[var(--text-secondary)]"
                  >
                    <CheckCircle2
                      className="mt-1 h-4 w-4 shrink-0 text-success"
                      aria-hidden="true"
                    />
                    <span>{measure}</span>
                  </li>
                ))}
              </ul>
            </article>
          </div>
        </section>

        <section aria-labelledby="pipeline-heading">
          <div className="max-w-3xl space-y-4">
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Pipeline
            </p>
            <h2
              id="pipeline-heading"
              className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl"
            >
              One path from compound to counsel.
            </h2>
            <p className="text-lg leading-8 text-[var(--text-secondary)]">
              The sources and depth change with the matter. The report records
              what happened so a reviewer can follow the work.
            </p>
          </div>
          <figure className="relative mt-8 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[radial-gradient(circle_at_16%_20%,rgba(238,183,122,0.24),transparent_28%),radial-gradient(circle_at_82%_24%,rgba(31,111,109,0.18),transparent_34%),linear-gradient(135deg,#fbf7ef_0%,#edf3ef_100%)] p-5 shadow-[var(--shadow-md)] md:mt-10 md:p-8">
            <figcaption className="sr-only">
              Three stages from a scoped input to qualified counsel review
            </figcaption>
            <div className="relative">
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  ["Input", "Compound, activity, place, timing"],
                  ["Exception", "Missing source stays visible"],
                  ["Human decision", "Counsel resolves the legal call"],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="rounded-xl border border-white/70 bg-white/72 p-4 shadow-[var(--shadow-sm)] backdrop-blur-sm"
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand-primary)]">
                      {label}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
                      {value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </figure>
          <ol className="mt-6 space-y-3 md:hidden">
            {PIPELINE_CHAPTERS.map((chapter) => (
              <li key={chapter.number}>
                <details
                  className="group rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-5 shadow-[var(--shadow-xs)]"
                  open={chapter.number === "01"}
                >
                  <summary className="flex min-h-20 cursor-pointer list-none items-center gap-4 py-3 marker:content-none">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-brand-primary/25 bg-[var(--bg-base)] text-sm font-semibold text-brand-primary">
                      {chapter.number}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                        {chapter.label}
                      </span>
                      <span className="mt-1 block [font-family:var(--font-newsreader)] text-xl leading-tight text-[var(--text-primary)]">
                        {chapter.title}
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
                  <div className="border-t border-[var(--border-subtle)] py-4">
                    <p className="text-sm leading-6 text-[var(--text-secondary)]">
                      {chapter.body}
                    </p>
                    <div className="mt-4 grid gap-2">
                      {chapter.stageIndexes.map((stageIndex) => {
                        const stage = PIPELINE_STAGES[stageIndex];
                        const Icon = stage.icon;
                        return (
                          <div
                            key={stage.number}
                            className="flex items-center gap-3 rounded-lg bg-[var(--surface-muted)] p-3"
                          >
                            <Icon
                              className="h-4 w-4 shrink-0 text-[var(--brand-primary)]"
                              aria-hidden="true"
                            />
                            <span className="text-sm font-semibold text-[var(--text-primary)]">
                              {stage.title}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </details>
              </li>
            ))}
          </ol>
          <ol className="relative mt-10 hidden space-y-4 before:absolute before:bottom-8 before:left-[2rem] before:top-8 before:w-px before:bg-[var(--border-emphasis)] md:block">
            {PIPELINE_CHAPTERS.map((chapter) => (
              <li
                key={chapter.number}
                className="relative grid gap-5 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 pl-16 shadow-[var(--shadow-sm)] md:grid-cols-[minmax(15rem,0.72fr)_minmax(0,1.28fr)] md:gap-8 md:p-7 md:pl-20"
              >
                <span className="absolute left-3 top-6 flex h-11 w-11 items-center justify-center rounded-full border border-brand-primary/25 bg-[var(--bg-base)] text-sm font-semibold text-brand-primary shadow-[var(--shadow-xs)] md:left-3.5 md:top-7 md:h-12 md:w-12">
                  {chapter.number}
                </span>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                    {chapter.label}
                  </p>
                  <h3 className="mt-3 [font-family:var(--font-newsreader)] text-2xl leading-tight text-[var(--text-primary)] md:text-3xl">
                    {chapter.title}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                    {chapter.body}
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {chapter.stageIndexes.map((stageIndex) => {
                    const stage = PIPELINE_STAGES[stageIndex];
                    const Icon = stage.icon;
                    return (
                      <article
                        key={stage.number}
                        className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                            Stage {stage.number}
                          </span>
                          <Icon
                            className="h-4 w-4 text-[var(--brand-primary)]"
                            aria-hidden="true"
                          />
                        </div>
                        <h4 className="mt-4 font-semibold text-[var(--text-primary)]">
                          {stage.title}
                        </h4>
                        <p className="mt-2 hidden text-sm leading-6 text-[var(--text-secondary)] md:block">
                          {stage.body}
                        </p>
                      </article>
                    );
                  })}
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="praviar-section-band -mx-4 rounded-none border-y border-[var(--border-default)] px-4 py-10 sm:mx-0 sm:rounded-lg sm:border sm:px-8">
          <div className="grid min-w-0 gap-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <div className="min-w-0 max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                See it in the product
              </p>
              <h2 className="mt-3 [font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)]">
                Follow one concern from finding to evidence.
              </h2>
              <p className="mt-4 text-base leading-8 text-[var(--text-secondary)]">
                The sample is clearly marked as fictional, so you can explore
                the product without mistaking it for real legal research.
              </p>
              <p
                className="mt-4 rounded-lg border border-warning/25 bg-warning/10 px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]"
                role="note"
              >
                {PUBLIC_PURCHASING_NOTICE}
              </p>
            </div>
            <div className="flex min-w-0 flex-col gap-3">
              <Link
                href={PUBLIC_PRIMARY_ACTION.href}
                className={cn(
                  buttonVariants({ size: "lg" }),
                  "h-auto min-h-11 w-full min-w-0 whitespace-normal rounded-lg px-4 py-2 text-center leading-tight sm:w-auto",
                )}
              >
                {PUBLIC_PRIMARY_ACTION.label}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                href="/trust#assurance-heading"
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "h-auto min-h-11 w-full min-w-0 whitespace-normal rounded-lg px-4 py-2 text-center leading-tight sm:w-auto",
                )}
              >
                Review current assurance status
              </Link>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
