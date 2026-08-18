import {
  Atom,
  ClipboardCheck,
  Clock,
  FileText,
  MessageSquare,
  Search,
  Scale,
  ScrollText,
  Settings2,
  Shield,
  ShieldX,
  type LucideIcon,
} from "lucide-react";

export interface ReportTabConfig {
  id: ReportTabId;
  label: string;
  shortLabel?: string;
  icon: LucideIcon;
}

export type ReportTabId =
  | "overview"
  | "patents"
  | "claims"
  | "evidence"
  | "drawings"
  | "invalidity"
  | "regulatory"
  | "comments"
  | "audit"
  | "meta"
  | "reasoning";

export const PRIMARY_TABS: ReadonlyArray<ReportTabConfig> = [
  { id: "overview", label: "Outcome", icon: FileText },
  { id: "patents", label: "Patents", icon: Shield },
  { id: "claims", label: "Claims", icon: Scale },
  { id: "evidence", label: "Evidence", icon: Search },
  { id: "invalidity", label: "Validity", icon: ShieldX },
];

const BASE_OVERFLOW_TABS: ReadonlyArray<ReportTabConfig> = [
  { id: "comments", label: "Comments", icon: MessageSquare },
  { id: "drawings", label: "Structures", icon: Atom },
  { id: "regulatory", label: "Regulatory", icon: ScrollText },
  { id: "audit", label: "Audit trail", icon: Clock },
  {
    id: "meta",
    label: "Coverage & quality",
    shortLabel: "Coverage",
    icon: Settings2,
  },
];

const REASONING_TAB: ReportTabConfig = {
  id: "reasoning",
  label: "Decision notes",
  shortLabel: "Decision",
  icon: ClipboardCheck,
};

export function getOverflowTabs(
  hasReasoningTraces: boolean,
): ReportTabConfig[] {
  return hasReasoningTraces
    ? [...BASE_OVERFLOW_TABS, REASONING_TAB]
    : [...BASE_OVERFLOW_TABS];
}

export function resolveReportTab(
  rawTab: string | null,
  overflowTabs: ReportTabConfig[],
): ReportTabId {
  const requestedTab = rawTab ?? "overview";
  const mappedTab =
    requestedTab === "summary"
      ? "overview"
      : requestedTab === "validity"
        ? "invalidity"
        : requestedTab;
  const validTabs = new Set<string>([
    ...PRIMARY_TABS.map((tab) => tab.id),
    ...overflowTabs.map((tab) => tab.id),
  ]);

  return validTabs.has(mappedTab) ? (mappedTab as ReportTabId) : "overview";
}
