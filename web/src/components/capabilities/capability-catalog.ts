import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  BriefcaseBusiness,
  ClipboardCheck,
  FileArchive,
  FileSearch,
  GitBranch,
  KeyRound,
  MessageSquare,
  Radar,
  Scale,
  Share2,
  ShieldCheck,
  Users,
} from "lucide-react";

export const DEMO_ANALYSIS_ID = "ana_demo_001";
export const DEMO_PUBLIC_SAMPLE_HREF = "/sample-reports/example-molecule-alpha";
export const DEMO_COUNSEL_WORKSPACE_HREF = `/analyses/${DEMO_ANALYSIS_ID}/report?audience=counsel&ai_context=blocker_brief&tab=overview`;
export const DEMO_FOUNDER_WORKSPACE_HREF =
  "/analyses/ana_demo_003/report?audience=founder&ai_context=external_readout&tab=overview";
export const DEMO_EVIDENCE_WORKSPACE_HREF = `/analyses/${DEMO_ANALYSIS_ID}/report?audience=counsel&ai_context=review_questions&tab=evidence`;
export const DEMO_MONITOR_WORKSPACE_HREF = `/analyses/${DEMO_ANALYSIS_ID}/report?audience=counsel&ai_context=external_readout&tab=overview`;
export const DEMO_DILIGENCE_WORKSPACE_HREF = `/analyses/${DEMO_ANALYSIS_ID}/report?audience=diligence&ai_context=review_questions&tab=patents`;

interface CapabilityWorkspaceHrefs {
  counsel: string;
  founder: string;
  runningPipeline: string;
  diligence: string;
  evidence: string;
  monitor: string;
  reportSearch: string;
}

interface CapabilityCatalogOptions {
  localDemoWorkspaceEnabled?: boolean;
}

const DEMO_WORKSPACE_HREFS: CapabilityWorkspaceHrefs = {
  counsel: DEMO_COUNSEL_WORKSPACE_HREF,
  founder: DEMO_FOUNDER_WORKSPACE_HREF,
  runningPipeline: "/analyses/ana_demo_002",
  diligence: "/batch",
  evidence: DEMO_EVIDENCE_WORKSPACE_HREF,
  monitor: DEMO_MONITOR_WORKSPACE_HREF,
  reportSearch: `${DEMO_COUNSEL_WORKSPACE_HREF}&search=report`,
};

const LIVE_WORKSPACE_HREFS: CapabilityWorkspaceHrefs = {
  counsel: "/analyses",
  founder: "/analyses",
  runningPipeline: "/analyses/new",
  diligence: "/batch",
  evidence: "/analyses",
  monitor: "/monitors",
  reportSearch: "/analyses",
};

export interface CapabilityItem {
  label: string;
  description: string;
  href: string;
  endpoints: string[];
  commandValue: string;
}

export interface CapabilityGroup {
  title: string;
  icon: LucideIcon;
  items: CapabilityItem[];
}

export interface DemoStory {
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  audience: "Counsel" | "Founder" | "Diligence" | "Operations";
}

export const WORKFLOW_STEPS: Array<{ label: string; icon: LucideIcon }> = [
  { label: "Analyze", icon: FileSearch },
  { label: "Stream", icon: Activity },
  { label: "Report", icon: FileSearch },
  { label: "Ask AI", icon: MessageSquare },
  { label: "Review", icon: ClipboardCheck },
  { label: "Monitor", icon: Radar },
  { label: "Export", icon: FileArchive },
  { label: "Share", icon: Share2 },
  { label: "Notify", icon: Bell },
  { label: "Govern", icon: KeyRound },
];

function getCapabilityWorkspaceHrefs({
  localDemoWorkspaceEnabled = true,
}: CapabilityCatalogOptions = {}): CapabilityWorkspaceHrefs {
  return localDemoWorkspaceEnabled
    ? DEMO_WORKSPACE_HREFS
    : LIVE_WORKSPACE_HREFS;
}

function buildDemoStories(hrefs: CapabilityWorkspaceHrefs): DemoStory[] {
  return [
    {
      title: "Example Molecule Alpha — counsel review",
      description:
        "Canonical fictional research preview, not legal advice, with review readiness, claim mapping, source limits, and a governed handoff.",
      href: hrefs.counsel,
      icon: BriefcaseBusiness,
      audience: "Counsel",
    },
    {
      title: "Example Molecule Alpha — partial source",
      description:
        "A fictional partial-source state that keeps uncertainty visible in a plain-language founder packet.",
      href: hrefs.founder,
      icon: Users,
      audience: "Founder",
    },
    {
      title: "Example Molecule Alpha — running replay",
      description:
        "A deterministic fictional replay for pipeline progress, stage state, and operational visibility.",
      href: hrefs.runningPipeline,
      icon: Activity,
      audience: "Operations",
    },
    {
      title: "Diligence portfolio",
      description:
        "Batch and dashboard surfaces for comparing multiple compounds and review workload.",
      href: hrefs.diligence,
      icon: BarChart3,
      audience: "Diligence",
    },
  ];
}

function buildCapabilityGroups(
  hrefs: CapabilityWorkspaceHrefs,
): CapabilityGroup[] {
  return [
    {
      title: "Case Creation",
      icon: FileSearch,
      items: [
        {
          label: "Adaptive analysis launch",
          description:
            "Compound-first launch into the single adaptive FTO pipeline.",
          href: "/analyses/new",
          endpoints: ["POST /analyses"],
          commandValue:
            "adaptive analysis launch compound triage create analysis backend POST analyses",
        },
        {
          label: "Counsel configuration",
          description:
            "Jurisdiction, source, review, and evidence settings for the adaptive pipeline.",
          href: "/analyses/new",
          endpoints: ["POST /analyses", "GET /analyses/{id}/stream"],
          commandValue:
            "counsel configuration jurisdiction source review evidence settings pipeline stream",
        },
        {
          label: "Batch diligence",
          description:
            "Portfolio-style compound runs for diligence or BD comparison.",
          href: "/batch",
          endpoints: ["POST /batch", "GET /batch"],
          commandValue:
            "batch diligence portfolio compounds investor BD comparison backend batch",
        },
      ],
    },
    {
      title: "Report Workspace",
      icon: FileSearch,
      items: [
        {
          label: "High-risk demo case",
          description:
            "Full report, verdict, claim matrix, patents, invalidity, audit, reasoning, and AI workspace.",
          href: hrefs.counsel,
          endpoints: [
            "GET /reports/{analysis_id}",
            "GET /reports/{analysis_id}/workspace-summary",
          ],
          commandValue:
            "high risk demo case report workspace verdict claim matrix patents invalidity audit reasoning",
        },
        {
          label: "Report search",
          description:
            "Search inside report content with interpreted query and result counts.",
          href: hrefs.reportSearch,
          endpoints: ["POST /reports/{analysis_id}/search"],
          commandValue:
            "report search interpreted query evidence inside report backend search",
        },
        {
          label: "Governed evidence search",
          description:
            "Report-grounded or governed external evidence expansion with provenance.",
          href: hrefs.evidence,
          endpoints: ["POST /reports/{analysis_id}/evidence-search"],
          commandValue:
            "governed evidence search external sources provenance report grounded",
        },
      ],
    },
    {
      title: "AI And Review",
      icon: Bot,
      items: [
        {
          label: "AI review workspace",
          description:
            "Streaming report chat with citations and workspace governance metadata.",
          href: hrefs.counsel,
          endpoints: ["POST /analyses/{analysis_id}/chat"],
          commandValue:
            "AI review workspace report chat citations governance metadata assistant",
        },
        {
          label: "Review queue",
          description:
            "Comment assignment, escalation, resolution, and reviewer workload.",
          href: "/reviews",
          endpoints: [
            "GET /comments/review-queue",
            "PATCH /comments/{id}/assignment",
          ],
          commandValue:
            "review queue comments assignment escalation resolution reviewer workload",
        },
        {
          label: "Reviewer decisions",
          description:
            "Accept, reject, or edit findings with persisted per-analysis decisions.",
          href: hrefs.evidence,
          endpoints: ["POST /analyses/{analysis_id}/decisions"],
          commandValue:
            "reviewer decisions accept reject edit findings persisted decisions",
        },
      ],
    },
    {
      title: "Post-Report Operations",
      icon: Radar,
      items: [
        {
          label: "Patent monitors",
          description:
            "Create watchlists from a report and review alerts over time.",
          href: "/monitors",
          endpoints: ["POST /monitors", "GET /monitors/{id}/alerts"],
          commandValue:
            "patent monitors watchlist alerts monitor create report seeded",
        },
        {
          label: "Exports and sharing",
          description:
            "Audience-specific report packaging plus public share links.",
          href: hrefs.diligence,
          endpoints: ["POST /reports/{id}/export", "GET /reports/{id}/share"],
          commandValue:
            "exports sharing counsel binder founder brief diligence memo share link",
        },
        {
          label: "Notifications",
          description: "Unread counts, preferences, and operational alerts.",
          href: "/settings/notifications",
          endpoints: ["GET /notifications", "PUT /notifications/preferences"],
          commandValue:
            "notifications unread counts preferences alerts settings",
        },
      ],
    },
    {
      title: "Platform Controls",
      icon: ShieldCheck,
      items: [
        {
          label: "Admin analytics",
          description:
            "Costs, usage, model activity, audit logs, system health, and task queues.",
          href: "/admin/analytics",
          endpoints: ["GET /admin/health", "GET /admin/analytics/usage"],
          commandValue:
            "admin analytics costs usage model activity audit logs system health task queues",
        },
        {
          label: "Billing",
          description:
            "Plan status, usage, invoices, checkout, and customer portal.",
          href: "/billing",
          endpoints: ["GET /billing/status", "GET /billing/usage"],
          commandValue:
            "billing plan status usage invoices checkout customer portal",
        },
        {
          label: "API keys",
          description:
            "Generate and revoke org-scoped API access for integrations.",
          href: "/settings",
          endpoints: ["POST /api-keys", "GET /api-keys"],
          commandValue:
            "API keys generate revoke org scoped API access integrations settings",
        },
      ],
    },
  ];
}

function buildDemoScriptSteps(hrefs: CapabilityWorkspaceHrefs) {
  return [
    {
      label: "Open the high-risk counsel case",
      href: hrefs.counsel,
      description:
        "Start from a blocked verdict and use the case map to inspect the claim matrix, material families, review status, and audit trail.",
      icon: Scale,
    },
    {
      label: "Ask the AI workspace",
      href: hrefs.evidence,
      description:
        "Use report-grounded answers with citations, then convert outputs into evidence search, review handoff, monitor, or export actions.",
      icon: Bot,
    },
    {
      label: "Move work into review",
      href: "/reviews",
      description:
        "Show reviewer queue, assignment, escalation, and decision workflow instead of leaving comments as dead-end notes.",
      icon: ClipboardCheck,
    },
    {
      label: "Create monitoring and export",
      href: "/monitors",
      description:
        "Turn the report into a patent watch and package the same record as counsel binder, founder brief, or diligence memo.",
      icon: GitBranch,
    },
  ];
}

export const MARKET_BAR = [
  {
    title: "Task-specific AI, not generic chat",
    description:
      "Every assistant answer should map to a governed action: search evidence, create review work, draft a design-around, monitor, or export.",
  },
  {
    title: "Context layer users can inspect",
    description:
      "Show source coverage, routing mode, citations, review status, and limitations directly in the workspace.",
  },
  {
    title: "Human oversight by design",
    description:
      "Counsel decisions, reviewer approvals, audit trail, and export readiness must be first-class UI objects.",
  },
];

function buildCommandCapabilityItems(capabilityGroups: CapabilityGroup[]) {
  return capabilityGroups.flatMap((group) =>
    group.items.map((item) => ({
      ...item,
      groupTitle: group.title,
      icon: group.icon,
    })),
  );
}

export function getCapabilityCatalog(options: CapabilityCatalogOptions = {}) {
  const hrefs = getCapabilityWorkspaceHrefs(options);
  const demoStories = buildDemoStories(hrefs);
  const capabilityGroups = buildCapabilityGroups(hrefs);
  const demoScriptSteps = buildDemoScriptSteps(hrefs);
  const commandCapabilityItems = buildCommandCapabilityItems(capabilityGroups);

  return {
    capabilityGroups,
    commandCapabilityItems,
    demoScriptSteps,
    demoStories,
    showcaseHref: hrefs.counsel,
  };
}

const demoCatalog = getCapabilityCatalog({ localDemoWorkspaceEnabled: true });

export const DEMO_STORIES = demoCatalog.demoStories;
export const CAPABILITY_GROUPS = demoCatalog.capabilityGroups;
export const DEMO_SCRIPT_STEPS = demoCatalog.demoScriptSteps;
export const COMMAND_CAPABILITY_ITEMS = demoCatalog.commandCapabilityItems;
