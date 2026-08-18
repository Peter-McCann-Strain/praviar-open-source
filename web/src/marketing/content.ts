import { showcaseFixture } from "@praviar/showcase-fixture";
import { PUBLIC_PRIMARY_ACTION } from "@/marketing/public-readiness";

const SHOWCASE = showcaseFixture.payload;

export type ProofStatus = "demo";
export type ProofSourceType = "demo" | "share" | "image" | "pdf";
export type HeroMode = "adaptive";

export interface ProofMetric {
  label: string;
  value: string;
  note?: string;
}

export interface HeroExample {
  label: string;
  compound: string;
  mode: HeroMode;
}

export interface ProofArtifact {
  id: string;
  title: string;
  summary: string;
  status: ProofStatus;
  sourceType: ProofSourceType;
  publicHref: string;
  metrics: ProofMetric[];
  disclaimer: string;
  sourceReference: string;
}

export interface SampleReportEntry {
  slug: string;
  title: string;
  compoundName: string;
  category: string;
  status: ProofStatus;
  sourceType: ProofSourceType;
  publicHref: string;
  previewHref?: string;
  summary: string;
  verdictLabel: string;
  metrics: ProofMetric[];
  teaser: string;
  disclaimer: string;
  sourceReference: string;
}

export interface BenchmarkSnapshot {
  id: string;
  title: string;
  description: string;
  status: ProofStatus;
  value: string;
  lastUpdated: string;
  publicHref: string;
  disclaimer: string;
  sourceReference: string;
}

export interface SegmentPageEntry {
  slug: string;
  eyebrow: string;
  title: string;
  summary: string;
  points: string[];
  ctaLabel: string;
  ctaHref: string;
}

export const BRAND = {
  name: "Praviar",
  shortName: "Praviar",
  tagline: "Patent risk, made easier to act on",
  footerCopy: "An early view of the patents that could shape your next move.",
};

export const MARKETING_DISCLAIMER =
  "Praviar helps organise an early patent-risk review. It is not a legal opinion. It does not replace a legal opinion from qualified patent counsel. Ask counsel to review any decision you plan to act on.";

export const SYNTHETIC_SAMPLE_DISCLAIMER =
  "This sample is fictional. The patent numbers, claims, assignees, and reasoning are here to show how the product works, not to support real legal work.";

export const DEMO_REPORT_SOURCE_REFERENCE = `${showcaseFixture.fixture_id}@${showcaseFixture.fixture_version}`;
const ADAPTIVE_PIPELINE_SOURCE_REFERENCE = "docs/PIPELINE.md";
export const HERO_EXAMPLES: HeroExample[] = [
  {
    label: SHOWCASE.compound.display_name,
    compound: SHOWCASE.compound.submitted_identity,
    mode: "adaptive",
  },
];

export const PROOF_ARTIFACTS: ProofArtifact[] = [
  {
    id: "executive-verdict",
    title: "Review which candidate families were prioritised",
    summary:
      "See why candidate families were prioritised and which questions remain for counsel.",
    status: "demo",
    sourceType: "share",
    publicHref: "/sample-reports/example-molecule-alpha",
    metrics: [
      {
        label: "Fictional families reviewed",
        value: String(SHOWCASE.analysis.families.length),
      },
      {
        label: "Synthetic source records",
        value: String(SHOWCASE.analysis.searched_sources.length),
      },
      { label: "Recorded fixture run", value: "24 min" },
    ],
    disclaimer: MARKETING_DISCLAIMER,
    sourceReference: DEMO_REPORT_SOURCE_REFERENCE,
  },
  {
    id: "claim-map",
    title: "See the claim behind the concern",
    summary:
      "Move past a long patent list. See which claim elements appear relevant, which do not, and where a different product or process might change the picture.",
    status: "demo",
    sourceType: "demo",
    publicHref: "/sample-reports/example-molecule-alpha",
    metrics: [
      {
        label: "Claims surfaced",
        value: String(
          SHOWCASE.analysis.families.reduce(
            (count, family) => count + family.claims.length,
            0,
          ),
        ),
      },
      { label: "Element mapping", value: "Yes" },
      { label: "Research hypotheses", value: "2" },
    ],
    disclaimer: MARKETING_DISCLAIMER,
    sourceReference: DEMO_REPORT_SOURCE_REFERENCE,
  },
  {
    id: "audit-trail",
    title: "Give counsel a useful starting point",
    summary:
      "Keep the search path, citations, source gaps, and open questions together so the next reviewer can pick up the work quickly.",
    status: "demo",
    sourceType: "demo",
    publicHref: "/methodology",
    metrics: [
      {
        label: "Synthetic families",
        value: String(SHOWCASE.analysis.families.length),
      },
      {
        label: "Claims mapped",
        value: String(
          SHOWCASE.analysis.families.reduce(
            (count, family) => count + family.claims.length,
            0,
          ),
        ),
      },
      { label: "Verification step", value: "Included" },
    ],
    disclaimer: MARKETING_DISCLAIMER,
    sourceReference: DEMO_REPORT_SOURCE_REFERENCE,
  },
];

export const SAMPLE_REPORTS: SampleReportEntry[] = [
  {
    slug: "example-molecule-alpha",
    title: `${SHOWCASE.compound.display_name} screening dossier`,
    compoundName: SHOWCASE.compound.display_name,
    category: "Wholly fictional compound placeholder",
    status: "demo",
    sourceType: "share",
    publicHref: "/sample-reports/example-molecule-alpha",
    summary:
      "A deterministic fictional report showing synthetic source coverage, claim mapping, explicit limitations, and a mandatory qualified-review gate.",
    verdictLabel: "Qualified review required",
    metrics: [
      {
        label: "Families reviewed",
        value: String(SHOWCASE.analysis.families.length),
      },
      {
        label: "Sources recorded",
        value: String(SHOWCASE.analysis.searched_sources.length),
      },
      {
        label: "Evidence records",
        value: String(SHOWCASE.analysis.evidence.length),
      },
    ],
    teaser:
      "Follow the story from the initial finding to the claim evidence, research hypotheses, and the final handoff.",
    disclaimer: MARKETING_DISCLAIMER,
    sourceReference: DEMO_REPORT_SOURCE_REFERENCE,
  },
];

export const BENCHMARK_SNAPSHOTS: BenchmarkSnapshot[] = [
  {
    id: "adaptive-agentic",
    title: "How Praviar knows when to look deeper",
    description:
      "A dated product walkthrough showing how an uncertain or incomplete finding receives more scrutiny before it reaches the report.",
    status: "demo",
    value: "Product walkthrough",
    lastUpdated: "July 1, 2026",
    publicHref: "/compare/adaptive-agentic",
    disclaimer: MARKETING_DISCLAIMER,
    sourceReference: ADAPTIVE_PIPELINE_SOURCE_REFERENCE,
  },
];

export const SEGMENT_PAGES: SegmentPageEntry[] = [
  {
    slug: "biotech-founders",
    eyebrow: "For Biotech Founders",
    title:
      "Review patent questions before the development plan becomes harder to change.",
    summary:
      "See how Praviar searches selected sources, prioritises candidate families, and prepares a focused brief for qualified patent counsel.",
    points: [
      "Check a lead before another year of work makes it expensive to revisit.",
      "Give investors and counsel a clear account of what you found.",
      "Use claim evidence and research hypotheses to plan the next legal step.",
    ],
    ctaLabel: PUBLIC_PRIMARY_ACTION.label,
    ctaHref: PUBLIC_PRIMARY_ACTION.href,
  },
];
