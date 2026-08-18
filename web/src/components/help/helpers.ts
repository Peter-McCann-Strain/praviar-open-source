import type { RiskLevel } from "@praviar/shared-types";
import {
  Atom,
  BellRing,
  CheckCircle,
  CreditCard,
  FileText,
  Filter,
  HelpCircle,
  KeyRound,
  LifeBuoy,
  Microscope,
  Scale,
  Search,
  Settings,
  ShieldX,
  type LucideIcon,
} from "lucide-react";
import { PIPELINE_STEPS } from "@/lib/constants";
import {
  canAccessWorkspaceHref,
  type PrincipalCapabilities,
} from "@/hooks/use-principal-capabilities";

export const STEP_DESCRIPTIONS: Record<number, string> = {
  1: "Identifies your compound using PubChem, resolves SMILES, InChI, CAS numbers to a canonical structure",
  2: "Searches PubChem, BigQuery Patents, SureChEMBL, and PatCID databases in parallel",
  3: "AI-assisted relevance screening to identify potentially blocking patents",
  4: "Deterministic claim pre-parsing followed by element-by-element analysis with confidence scores, evidence citations, and consistency verification",
  5: "Function-Way-Result analysis with prosecution history estoppel checks",
  6: "Prior art search, anticipation, obviousness, and 35 U.S.C. § 112 analysis",
  7: "Automated coverage and consistency checks across the generated analysis record",
  8: "Structured first-pass FTO report with executive summary, claim charts, caveats, and audit trail",
};

export const STEP_ICONS: Record<number, LucideIcon> = {
  1: Atom,
  2: Search,
  3: Filter,
  4: Microscope,
  5: Scale,
  6: ShieldX,
  7: CheckCircle,
  8: FileText,
};

export const DEFAULT_STEP_ICON = HelpCircle;

export const SECTION_LINKS = [
  { href: "#common-tasks", label: "Common Tasks" },
  { href: "#getting-started", label: "Getting Started" },
  { href: "#pipeline-steps", label: "Pipeline" },
  { href: "#faq", label: "FAQ" },
  { href: "#glossary", label: "Glossary" },
  { href: "#risk-levels", label: "Risk Levels" },
  { href: "#shortcuts", label: "Shortcuts" },
  { href: "#contact", label: "Contact" },
] as const;

export const HELP_WORKFLOWS = [
  {
    href: "/analyses/new",
    label: "Start an FTO analysis",
    desc: "Open the compound-first workflow for a new clearance question.",
    icon: Search,
  },
  {
    href: "/analyses",
    label: "Review analysis library",
    desc: "Find reports, running work, and review status across compounds.",
    icon: FileText,
  },
  {
    href: "/config",
    label: "Tune default coverage",
    desc: "Adjust source, jurisdiction, and review defaults before launch.",
    icon: Settings,
  },
  {
    href: "/billing",
    label: "Inspect billing architecture",
    desc: "Review the illustrative plan, credit, checkout, and invoice states implemented in the research-preview interface. No purchase is offered.",
    icon: CreditCard,
    requiresBillingManagement: true,
  },
] as const;

export function canAccessHelpWorkflow(
  capabilities: PrincipalCapabilities | null | undefined,
  item: (typeof HELP_WORKFLOWS)[number],
) {
  if (
    "requiresBillingManagement" in item &&
    item.requiresBillingManagement === true
  ) {
    return capabilities?.can_manage_billing === true;
  }
  return canAccessWorkspaceHref(capabilities, item.href);
}

export const HELP_AUDIENCE_TASKS = [
  {
    audience: "Counsel",
    title: "Verify material risk",
    desc: "Jump to risk semantics, claim-analysis pipeline steps, and evidence review cues.",
    href: "#risk-levels",
    tags: ["risk", "claims", "evidence", "attorney", "counsel"],
  },
  {
    audience: "Scientist",
    title: "Understand compound inputs",
    desc: "Review accepted identifiers, structure resolution, and patent-source search behavior.",
    href: "#pipeline-steps",
    tags: ["compound", "SMILES", "InChI", "CAS", "sources"],
  },
  {
    audience: "Admin",
    title: "Govern access and defaults",
    desc: "Move from help into settings and configuration controls for organization policy.",
    href: "/settings",
    tags: ["settings", "SSO", "API keys", "configuration", "admin"],
  },
  {
    audience: "Founder",
    title: "Get to first answer",
    desc: "Start with a compound, inspect the report, and know when counsel review is needed.",
    href: "#getting-started",
    tags: ["start", "first analysis", "report", "founder", "diligence"],
  },
] as const;

export const HELP_SUPPORT_ITEMS = [
  {
    label: "Support boundary",
    value: "Not published in preview",
    desc: "A deployment operator must provide its own approved support channel.",
    href: "#contact",
    icon: LifeBuoy,
  },
  {
    label: "Access controls",
    value: "Settings",
    desc: "Review API keys, SSO handoff, and organization-scoped access.",
    href: "/settings",
    icon: KeyRound,
  },
  {
    label: "Monitoring",
    value: "Watch lists",
    desc: "Check patent-change monitoring and alert posture.",
    href: "/monitors",
    icon: BellRing,
  },
] as const;

export const GETTING_STARTED_STEPS = [
  {
    step: 1,
    title: "Enter a compound",
    desc: "Type a name, SMILES, CAS number, or InChI identifier.",
  },
  {
    step: 2,
    title: "Set matter context",
    desc: "Praviar selects the right analysis scope from the compound, claims, and risk signals.",
  },
  {
    step: 3,
    title: "Review results",
    desc: "Inspect a structured screening artifact, claim maps, evidence links, and review limitations.",
  },
] as const;

const READ_ONLY_GETTING_STARTED_STEPS = [
  {
    step: 1,
    title: "Open a shared analysis",
    desc: "Use the analysis library to find packets your team has made available.",
  },
  {
    step: 2,
    title: "Read the decision summary",
    desc: "Review the permitted conclusion, caveats, and current handoff state.",
  },
  {
    step: 3,
    title: "Ask the workspace owner",
    desc: "Request counsel clarification or access when a governed detail is restricted.",
  },
] as const;

export function getGettingStartedSteps(
  capabilities?: PrincipalCapabilities | null,
) {
  if (capabilities && capabilities.can_create_analysis !== true) {
    return READ_ONLY_GETTING_STARTED_STEPS;
  }
  return GETTING_STARTED_STEPS;
}

export const GLOSSARY = [
  {
    term: "FTO (Freedom to Operate)",
    definition:
      "An assessment of whether a product or process can be commercialized without infringing third-party patent rights. The core deliverable of a Praviar analysis.",
  },
  {
    term: "Markush Structure",
    definition:
      "A chemical notation used in patent claims to describe a class of compounds with variable substituents at defined positions, covering broad structural families.",
  },
  {
    term: "Claim Chart",
    definition:
      "A structured comparison mapping each element of a patent claim to corresponding features of the target compound, used to assess literal infringement.",
  },
  {
    term: "Doctrine of Equivalents",
    definition:
      "A legal doctrine that extends patent infringement beyond literal claim language to cover variations that perform substantially the same function, in substantially the same way, to achieve substantially the same result.",
  },
  {
    term: "Prosecution History Estoppel",
    definition:
      "A limitation on the Doctrine of Equivalents where claim scope narrowed during patent prosecution cannot be recaptured through equivalents arguments.",
  },
  {
    term: "Prior Art",
    definition:
      "Any publicly available information (patents, publications, products) that existed before the patent's priority date. Used to challenge patent validity.",
  },
  {
    term: "CPC Classification",
    definition:
      "Cooperative Patent Classification — a hierarchical system for categorizing patents by technology area, used to focus search scope on relevant patent classes.",
  },
  {
    term: "Tanimoto Similarity",
    definition:
      "A metric (0–1) measuring structural similarity between two molecules based on their chemical fingerprints. Higher values indicate greater similarity.",
  },
  {
    term: "SMILES Notation",
    definition:
      "Simplified Molecular-Input Line-Entry System — a string-based representation of chemical structures (e.g., O=C(/C=C/CN(C)S(=O)(=O)c1cc(F)c(Cl)c(F)c1)N... for a KRAS G12C inhibitor).",
  },
  {
    term: "InChI / InChIKey",
    definition:
      "IUPAC International Chemical Identifier — a canonical, machine-readable representation of molecular structure. InChIKey is a fixed-length hash for database lookups.",
  },
  {
    term: "Claim Pre-Parsing",
    definition:
      "Structured extraction of claim elements from patent text using syntactic rules before LLM analysis. The parsed artifact is recorded so reviewers can inspect and reproduce the claim structure used in the report.",
  },
  {
    term: "Differential Verification",
    definition:
      "A cost-effective consistency technique where borderline patent assessments are verified by a second, independent model. Disagreements are flagged as uncertain rather than forcing a potentially incorrect determination.",
  },
] as const;

export const RISK_EXPLANATIONS: ReadonlyArray<{
  level: RiskLevel;
  meaning: string;
}> = [
  {
    level: "high",
    meaning:
      "One or more granted patents have claims that may cover your compound in the reviewed record. Commercialization could carry substantial litigation risk. Immediate IP/legal review recommended.",
  },
  {
    level: "medium",
    meaning:
      "Patent claims may cover your compound under certain interpretations or through the Doctrine of Equivalents. Further analysis or design-around strategies should be explored.",
  },
  {
    level: "low",
    meaning:
      "The reviewed record indicates lower blocking risk. Minor claim overlaps or source gaps may remain and should be reviewed before relying on the result.",
  },
  {
    level: "clear",
    meaning:
      "No blocking claims were surfaced in the configured source set. This is not a freedom-to-operate opinion; periodic re-monitoring and qualified counsel review are still recommended.",
  },
] as const;

export const SHORTCUTS = [
  { keys: "⌘K / Ctrl+K", action: "Open command palette" },
  { keys: "Esc", action: "Close modal or panel" },
] as const;

export const FAQ = [
  {
    q: "How should I read the AI analysis?",
    a: "Praviar uses layered verification for material and borderline findings when configured evidence is available. The primary claim analysis is checked by an independent verification pass, and disagreements are flagged as uncertainty. Findings include confidence scores, source-health caveats, and evidence citations so reviewers can inspect the basis. The system is designed as a first-pass screening tool — expert review is always recommended.",
  },
  {
    q: "What compound input formats are supported?",
    a: "Praviar accepts compound names (e.g., 'succinic acid'), CAS registry numbers (e.g., '110-15-6'), SMILES strings (e.g., 'OC(=O)CCC(O)=O'), and InChI identifiers. The system resolves all formats to a canonical structure via PubChem.",
  },
  {
    q: "Which patent databases are searched?",
    a: "Configured workspaces can search PubChem patent cross-references (SDQ), Google BigQuery Patents, SureChEMBL, and PatCID when those sources are enabled and healthy. Reports show source-health status and coverage caveats, and results are deduplicated across completed sources.",
  },
  {
    q: "Can I export reports?",
    a: "The research-preview interface demonstrates PDF, DOCX, XLSX, and JSON export paths. Availability in any deployment depends on an identified operator, configured storage, access policy, and reviewed evidence boundaries.",
  },
  {
    q: "How do credits and billing work?",
    a: "The repository contains illustrative Report Credit, plan, checkout, invoice, and portal code paths. The public research preview does not offer a subscription, credit purchase, hosted checkout, invoice, refund policy, or order form.",
  },
  {
    q: "What does the Doctrine of Equivalents analysis do?",
    a: "For potentially relevant claim elements, the system surfaces Function-Way-Result (FWR) and prosecution-history review cues when source context supports them. These cues help counsel evaluate equivalents questions; they are not infringement conclusions.",
  },
  {
    q: "Is my data kept confidential?",
    a: "No confidentiality assurance is made for the public research preview. Do not enter confidential matter data. Organization scoping and integration references are implementation controls, not evidence of an operated service, active subprocessors, provider contracts, or a production data-use policy.",
  },
  {
    q: "How does Praviar ensure consistent results?",
    a: "Praviar uses structured parsing, fixed risk rules, and differential verification to make report behavior inspectable. Claim parsing and risk scoring are recorded as evidence artifacts, while borderline patents can be checked by a second model and flagged for expert review rather than presented as definitive conclusions.",
  },
] as const;

export function getFaqForCapabilities(
  capabilities?: PrincipalCapabilities | null,
) {
  if (!capabilities) {
    return [...FAQ];
  }

  return FAQ.map((item) => {
    if (item.q === "Can I export reports?") {
      if (capabilities.can_export_report !== true) {
        return {
          ...item,
          a:
            capabilities.role === "scientist"
              ? "Your current scientist role cannot export while the restricted-risk gate is active. Complete the evidence and review handoff, then ask an attorney or authorized owner to generate the governed artifact."
              : "Your current role cannot export governed report artifacts. Review the shared summary and ask an attorney or authorized workspace owner for an approved export.",
        };
      }
      if (capabilities.role === "scientist") {
        return {
          ...item,
          a: "When the workspace risk policy permits scientist exports, the report view supports PDF, CSV, XLSX, and JSON. DOCX and PPTX remain counsel formats.",
        };
      }
    }

    if (
      item.q === "How do credits and billing work?" &&
      capabilities.can_manage_billing !== true
    ) {
      return {
        ...item,
        a: "The billing page demonstrates role-restricted usage, invoice, credit, and plan states. It is illustrative and does not offer purchases or subscription changes.",
      };
    }

    return item;
  });
}

const FAQ_HIGHLIGHT_PATTERN =
  /\b(layered verification|confidence scores|source-health caveats|evidence citations|compound names|CAS registry numbers|SMILES strings|InChI identifiers|Configured workspaces|enabled and healthy|completed sources|PDF|DOCX|XLSX|JSON|one Report Credit|Report Credits?|included Report Credits|pay as you go|pay-as-you-go|Stripe|hosted invoices|non-refundable|Function-Way-Result|prosecution history estoppel|organization-scoped|subprocessors|provider contracts|structured parsing|fixed risk rules|differential verification)\b/gi;

export interface HighlightedFaqAnswerSegment {
  highlighted: boolean;
  text: string;
}

export const HELP_SECTION_SEARCH_TERMS = {
  audience: [
    "Help command layer",
    "What are you trying to do?",
    "Start from the workflow, not the manual",
    "Choose the closest role and jump to the right guidance.",
    "Choose the closest role and jump to guidance that matches the decision you are trying to make.",
    "Command brief",
    "Route, verify, hand off",
    "Common tasks",
  ],
  contact: [
    "Support is deployment-specific",
    "Review deployment boundary",
    "hosted support mailbox",
    "deployment operator",
    "product access",
    "workflow questions",
    "approved support channel",
    "confidential molecule",
    "report details",
    "matter details",
  ],
  faq: [
    "FAQ",
    "Frequently Asked Questions",
    "Common questions about Praviar's capabilities and workflow",
  ],
  gettingStarted: ["Getting Started", "Three steps to your first FTO analysis"],
  glossary: [
    "Glossary",
    "Glossary of Patent Terms",
    "Key terms used throughout Praviar and FTO analysis",
  ],
  pipeline: [
    "Pipeline",
    "Pipeline Steps",
    "The 8-step FTO analysis pipeline, from compound resolution to final report",
  ],
  risks: [
    "Risk Levels",
    "Risk Levels Explained",
    "How Praviar classifies patent infringement risk",
  ],
  shortcuts: ["Keyboard Shortcuts", "Shortcut keys", "Command shortcuts"],
  support: [
    "Support posture",
    "Help content is safe to browse",
    "Operational changes happen only from the linked workspaces.",
  ],
  workflows: [
    "Common workflows",
    "Move from guidance to action",
    "Guidance to action",
  ],
} as const;

export function highlightFaqAnswer(
  answer: string,
): HighlightedFaqAnswerSegment[] {
  const segments: HighlightedFaqAnswerSegment[] = [];
  let cursor = 0;

  for (const match of answer.matchAll(FAQ_HIGHLIGHT_PATTERN)) {
    const index = match.index ?? 0;
    const text = match[0] ?? "";
    if (!text) continue;

    if (index > cursor) {
      segments.push({
        highlighted: false,
        text: answer.slice(cursor, index),
      });
    }

    segments.push({
      highlighted: true,
      text,
    });
    cursor = index + text.length;
  }

  if (cursor < answer.length) {
    segments.push({
      highlighted: false,
      text: answer.slice(cursor),
    });
  }

  return segments.length > 0
    ? segments
    : [
        {
          highlighted: false,
          text: answer,
        },
      ];
}

export function matchesHelpQuery(query: string, ...values: string[]): boolean {
  if (!query) {
    return true;
  }

  return values.some((value) => value.toLowerCase().includes(query));
}

export function getHelpResultCounts(
  query: string,
  capabilities?: PrincipalCapabilities | null,
) {
  const normalizedQuery = query.trim().toLowerCase();
  const gettingStarted = getGettingStartedSteps(capabilities).filter((item) =>
    matchesHelpQuery(
      normalizedQuery,
      ...HELP_SECTION_SEARCH_TERMS.gettingStarted,
      item.title,
      item.desc,
    ),
  ).length;
  const pipeline = PIPELINE_STEPS.filter((step) =>
    matchesHelpQuery(
      normalizedQuery,
      ...HELP_SECTION_SEARCH_TERMS.pipeline,
      step.label,
      STEP_DESCRIPTIONS[step.number] ?? "",
    ),
  ).length;
  const faq = getFaqForCapabilities(capabilities).filter((item) =>
    matchesHelpQuery(
      normalizedQuery,
      ...HELP_SECTION_SEARCH_TERMS.faq,
      item.q,
      item.a,
    ),
  ).length;
  const glossary = GLOSSARY.filter((item) =>
    matchesHelpQuery(
      normalizedQuery,
      ...HELP_SECTION_SEARCH_TERMS.glossary,
      item.term,
      item.definition,
    ),
  ).length;
  const risks = RISK_EXPLANATIONS.filter((item) =>
    matchesHelpQuery(
      normalizedQuery,
      ...HELP_SECTION_SEARCH_TERMS.risks,
      item.level,
      item.meaning,
    ),
  ).length;
  const shortcuts = SHORTCUTS.filter((item) =>
    matchesHelpQuery(
      normalizedQuery,
      ...HELP_SECTION_SEARCH_TERMS.shortcuts,
      item.keys,
      item.action,
    ),
  ).length;
  const workflows = HELP_WORKFLOWS.filter(
    (item) =>
      (capabilities === undefined ||
        canAccessHelpWorkflow(capabilities, item)) &&
      matchesHelpQuery(
        normalizedQuery,
        ...HELP_SECTION_SEARCH_TERMS.workflows,
        item.label,
        item.desc,
      ),
  ).length;
  const support = HELP_SUPPORT_ITEMS.filter(
    (item) =>
      (capabilities === undefined ||
        canAccessWorkspaceHref(capabilities, item.href)) &&
      matchesHelpQuery(
        normalizedQuery,
        ...HELP_SECTION_SEARCH_TERMS.support,
        item.label,
        item.value,
        item.desc,
      ),
  ).length;
  const contact = matchesHelpQuery(
    normalizedQuery,
    ...HELP_SECTION_SEARCH_TERMS.contact,
  )
    ? 1
    : 0;
  const audience = HELP_AUDIENCE_TASKS.filter(
    (item) =>
      (capabilities === undefined ||
        canAccessWorkspaceHref(capabilities, item.href)) &&
      matchesHelpQuery(
        normalizedQuery,
        ...HELP_SECTION_SEARCH_TERMS.audience,
        item.audience,
        item.title,
        item.desc,
        ...item.tags,
      ),
  ).length;
  const staticGuidance =
    gettingStarted +
    risks +
    shortcuts +
    workflows +
    support +
    contact +
    audience;
  const total = pipeline + faq + glossary + staticGuidance;

  return {
    audience,
    contact,
    faq,
    gettingStarted,
    glossary,
    hasResults: total > 0,
    pipeline,
    risks,
    shortcuts,
    staticGuidance,
    support,
    total,
    workflows,
  };
}
