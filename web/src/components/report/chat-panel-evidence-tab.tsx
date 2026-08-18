"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import {
  AlertCircle,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  Shield,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import type { ChatWorkspaceMetadata } from "@/hooks/use-report-chat";
import {
  useReportEvidenceSearch,
  type EvidenceSearchRetrievalMode,
  type EvidenceSearchFollowUpTarget as GovernedFollowUpTarget,
  type EvidenceSearchProviderCapability as GovernedProviderCapability,
  type EvidenceSearchProvenanceItem as GovernedProvenanceItem,
} from "@/hooks/use-report-evidence-search";
import { REVIEW_HANDOFF_ERROR_MESSAGE } from "@/hooks/report-interaction-copy";
import {
  useReviewHandoff,
  type ReviewHandoffResponse,
} from "@/hooks/use-review-handoff";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SkeletonCard } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const EVIDENCE_QUERY_MIN_LENGTH = 2;
const EVIDENCE_QUERY_MAX_LENGTH = 200;

type EvidenceScope = {
  label?: string;
  mode?: string;
  jurisdiction?: string[];
  jurisdictions?: string[];
  coverage?: string;
  sources_considered?: string[];
  source_name?: string;
  artifact_type?: string;
  status?: string;
  summary?: string;
  governed_note?: string;
  external_live_retrieval?: boolean;
  comment_routing_available?: boolean;
  provider_capabilities?: GovernedProviderCapability[];
  providers?: GovernedProviderCapability[];
  hybrid_evidence_ready?: boolean;
};

type EvidenceProvenanceItem = GovernedProvenanceItem | string;
type EvidenceFollowUpTarget = GovernedFollowUpTarget | string;

type EvidenceResult = {
  result_id?: string;
  title?: string;
  summary?: string;
  source_name?: string;
  authority_tier?: string;
  freshness?: string;
  artifact_type?: string;
  section?: string;
  patent_id?: string;
  relevance?: number;
  provenance?: EvidenceProvenanceItem[] | string;
  follow_up_target?: EvidenceFollowUpTarget | null;
};

type EvidenceSearchData = {
  query?: string;
  interpreted_query?: string;
  results?: EvidenceResult[];
  scope?: EvidenceScope | null;
};

function titleize(value?: string) {
  if (!value) return undefined;
  return value
    .replaceAll("_", " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

type EvidenceSearchState = {
  data?: EvidenceSearchData | null;
  search: (
    query: string,
    options?: { retrievalMode?: EvidenceSearchRetrievalMode },
  ) => Promise<void>;
  clear: () => void;
  isSearching: boolean;
  error: string | null;
  resultQuery?: string;
  failedQuery?: string | null;
  isShowingPreviousResults?: boolean;
};

type EvidenceSearchHookState = EvidenceSearchState & {
  interpretedQuery?: string;
  results?: Array<{ patent_id: string; section: string; snippet: string }>;
  totalResults?: number;
};

interface ChatPanelEvidenceTabProps {
  analysisId: string;
  token: string | null;
  patentId?: string;
  initialQuery?: string;
  workspaceMeta?: ChatWorkspaceMetadata | null;
  suggestedQueries?: string[];
  className?: string;
  queryInputId?: string;
  onReviewHandoffSuccess?: (response: ReviewHandoffResponse) => void;
}

function labelForTrustMode(
  trustMode: ChatWorkspaceMetadata["trust_mode"] | undefined,
) {
  if (!trustMode) return "Report-grounded";
  return trustMode.charAt(0).toUpperCase() + trustMode.slice(1);
}

function formatSection(section?: string) {
  if (!section) return "Unknown section";
  return section.replaceAll("_", " ");
}

function formatAuthorityTier(value?: string) {
  return titleize(value);
}

function formatFreshness(value?: string) {
  return titleize(value);
}

function formatRelevance(value?: number) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Relevance unavailable";
  }
  const normalized = value > 1 ? value / 100 : value;
  const bounded = Math.max(0, Math.min(1, normalized));
  return `${Math.round(bounded * 100)}% relevance`;
}

function formatRankLabel(index: number) {
  return `Rank ${index + 1}`;
}

function getEvidenceArtifactId(result: EvidenceResult, index: number) {
  return result.result_id?.trim() || `evidence-${index + 1}`;
}

function normalizeList(value?: string[] | string | null) {
  if (!value) return [];
  return Array.isArray(value) ? value.filter(Boolean) : [value].filter(Boolean);
}

function normalizeProviderCapabilities(
  scope?: EvidenceScope | null,
): GovernedProviderCapability[] {
  const provided = scope?.provider_capabilities ?? scope?.providers;
  if (provided?.length) {
    return provided.flatMap((provider) => {
      if (!provider?.provider_name?.trim()) {
        return [];
      }

      return [
        {
          provider_id: provider.provider_id?.trim() || "",
          provider_name: provider.provider_name.trim(),
          provider_class: provider.provider_class?.trim() || "report_derived",
          provider_status: provider.provider_status?.trim() || "active",
          live_retrieval_supported: Boolean(provider.live_retrieval_supported),
          configured: Boolean(provider.configured),
          configured_for_org: Boolean(provider.configured_for_org),
          materialized_in_report: Boolean(provider.materialized_in_report),
          execution_mode:
            provider.execution_mode?.trim() || "placeholder_contract",
          modality_coverage: normalizeList(provider.modality_coverage),
          jurisdiction_coverage: normalizeList(provider.jurisdiction_coverage),
          governance_note: provider.governance_note?.trim() || "",
          retrieved_at: provider.retrieved_at?.trim() || "",
          source_as_of: provider.source_as_of?.trim() || "",
          dataset_version: provider.dataset_version?.trim() || "",
        },
      ];
    });
  }

  if (!scope?.governed_note && !scope?.sources_considered?.length) {
    return [];
  }

  return [
    {
      provider_id: "report_derived",
      provider_name:
        scope?.source_name?.trim() || "Report-derived evidence layer",
      provider_class: "report_derived",
      provider_status: "active",
      live_retrieval_supported: false,
      configured: true,
      configured_for_org: true,
      materialized_in_report: true,
      execution_mode: "report_materialized",
      modality_coverage: [],
      jurisdiction_coverage: normalizeList(
        scope?.jurisdiction ?? scope?.jurisdictions,
      ),
      governance_note:
        scope?.governed_note?.trim() ||
        "Current evidence search is limited to report-derived provenance and artifacts.",
    },
  ];
}

function evidenceScopeHasLiveProvider(scope?: EvidenceScope | null) {
  if (scope?.external_live_retrieval !== true) {
    return false;
  }
  return normalizeProviderCapabilities(scope).some(
    (provider) => provider.live_retrieval_supported === true,
  );
}

function formatProviderClass(value?: string) {
  return titleize(value);
}

function formatProviderStatus(value?: string) {
  if (!value) return "Active";
  return titleize(value);
}

function formatProviderExecutionMode(value?: string) {
  if (value === "live_api") return "Live API";
  if (value === "report_materialized") return "Report materialized";
  if (value === "bundled_dataset") return "Bundled dataset";
  if (value === "placeholder_contract") return "Placeholder contract";
  return titleize(value) ?? "Execution not declared";
}

function getProviderStatusVariant(value?: string) {
  if (value === "active") return "success" as const;
  if (value === "caution_only" || value === "declared_only") {
    return "warning" as const;
  }
  return "outline" as const;
}

function describeProviderConfiguration(provider: GovernedProviderCapability) {
  if (provider.configured && provider.configured_for_org) {
    return "Configured for org";
  }
  if (provider.configured && provider.configured_for_org === false) {
    return "Configured, org gated";
  }
  return "Not configured";
}

function describeProviderExecutionBasis(provider: GovernedProviderCapability) {
  if (provider.live_retrieval_supported) return "Live retrieval eligible";
  if (provider.materialized_in_report) return "Materialized in report";
  if (provider.execution_mode === "bundled_dataset") return "Bundled dataset";
  if (provider.execution_mode === "placeholder_contract") {
    return "Declared contract";
  }
  return "No execution declared";
}

function isExternalEvidenceMode(mode?: string) {
  return mode === "external_evidence";
}

function formatEvidenceModeLabel(mode?: string) {
  if (mode === "report_evidence") {
    return "Report-grounded evidence";
  }
  if (mode === "external_evidence") {
    return "Governed external expansion";
  }
  return titleize(mode);
}

function describeRetrievalMode(mode: EvidenceSearchRetrievalMode) {
  if (isExternalEvidenceMode(mode)) {
    return "External expansion can query only live governed provider layers declared active in this report scope.";
  }
  return "Report-grounded search stays inside collected report artifacts, provenance, and evidence logs; no fresh external retrieval runs in this mode.";
}

function describeExternalGovernance(scope?: EvidenceScope | null) {
  if (evidenceScopeHasLiveProvider(scope)) {
    return "Live-capable provider layers are available for this workspace; execution basis is shown per provider and returned result.";
  }
  return "External expansion is unavailable for this workspace because no live governed provider is active for this report scope. Report-grounded search remains available; no fresh external retrieval will run.";
}

function normalizeProvenance(
  provenance: EvidenceResult["provenance"],
): GovernedProvenanceItem[] {
  if (!provenance) return [];
  if (typeof provenance === "string") {
    return provenance.trim()
      ? [{ label: "Provenance", value: provenance.trim() }]
      : [];
  }

  return provenance.flatMap((item) => {
    if (typeof item === "string") {
      return item.trim() ? [{ label: "Provenance", value: item.trim() }] : [];
    }
    if (!item?.label?.trim() || !item.value?.trim()) {
      return [];
    }
    return [{ label: item.label.trim(), value: item.value.trim() }];
  });
}

function describeFollowUpTarget(
  target: EvidenceFollowUpTarget | null | undefined,
) {
  if (!target) return "";
  if (typeof target === "string") return target.trim();
  const segments = [
    target.target_type ? target.target_type.replaceAll("_", " ") : "",
    target.target_id,
    target.suggested_note,
  ].filter((item): item is string => Boolean(item?.trim()));
  return segments.join(" · ");
}

function hasFollowUpTarget(
  target: EvidenceFollowUpTarget | string | null | undefined,
) {
  return Boolean(
    (typeof target === "string" && target.trim()) ||
    (typeof target === "object" && target !== null && target.target_id.trim()),
  );
}

function canRouteEvidenceResult(result: EvidenceResult) {
  return (
    hasFollowUpTarget(result.follow_up_target) &&
    normalizeProvenance(result.provenance).length > 0
  );
}

function routeFirstRoutableEvidenceResult(
  results: EvidenceResult[],
  onRouteFollowUp: RouteEvidenceFollowUp,
) {
  const resultIndex = results.findIndex(canRouteEvidenceResult);
  if (resultIndex < 0) return;
  const result = results[resultIndex];
  const target = result?.follow_up_target;
  if (!result || !target) return;
  onRouteFollowUp(result, target, resultIndex);
}

function buildRankingRationale(
  result: EvidenceResult,
  provenanceCount: number,
) {
  const details = [
    typeof result.relevance === "number"
      ? formatRelevance(result.relevance)
      : "",
    result.authority_tier?.trim()
      ? `${formatAuthorityTier(result.authority_tier)} authority`
      : "",
    result.freshness?.trim()
      ? `${formatFreshness(result.freshness)} source posture`
      : "",
    provenanceCount
      ? `${provenanceCount} provenance item${provenanceCount === 1 ? "" : "s"}`
      : "no traceable provenance",
  ].filter(Boolean);

  return details.length
    ? `Ranked from ${details.join(", ")}.`
    : "Ranked from available report evidence metadata.";
}

function buildReviewHandoffBody(
  result: EvidenceResult,
  target: GovernedFollowUpTarget | string | null | undefined,
  interpretedQuery: string,
  fallbackQuery: string,
) {
  const provenanceItems = normalizeProvenance(result.provenance);
  if (typeof target === "string") {
    return (
      target.trim() ||
      result.summary?.trim() ||
      result.title?.trim() ||
      "Review follow-up from evidence search"
    );
  }

  const note = target?.suggested_note?.trim();
  const provenanceSummary = provenanceItems
    .map((item) => `${item.label}: ${item.value}`)
    .join("\n");
  const sourceSummary = [
    result.source_name?.trim() ? `Source: ${result.source_name.trim()}` : "",
    result.authority_tier?.trim()
      ? `Authority: ${formatAuthorityTier(result.authority_tier)}`
      : "",
    result.freshness?.trim()
      ? `Freshness: ${formatFreshness(result.freshness)}`
      : "",
    typeof result.relevance === "number"
      ? `Relevance: ${formatRelevance(result.relevance)}`
      : "",
  ]
    .filter(Boolean)
    .join("\n");
  const parts = [
    note,
    result.result_id?.trim()
      ? `Evidence result ID: ${result.result_id.trim()}`
      : undefined,
    result.title?.trim(),
    result.patent_id?.trim() ? `Patent ${result.patent_id.trim()}` : undefined,
    sourceSummary ? `Source posture:\n${sourceSummary}` : undefined,
    result.summary?.trim()
      ? `Evidence summary:\n${result.summary.trim()}`
      : undefined,
    interpretedQuery.trim()
      ? `Interpreted query: ${interpretedQuery.trim()}`
      : undefined,
    fallbackQuery.trim() ? `Search query: ${fallbackQuery.trim()}` : undefined,
    provenanceSummary ? `Provenance:\n${provenanceSummary}` : undefined,
  ].filter((item): item is string => Boolean(item?.trim()));

  return parts.join("\n\n") || "Review follow-up from evidence search";
}

function buildReviewHandoffNote(
  result: EvidenceResult,
  target: GovernedFollowUpTarget | string | null | undefined,
) {
  if (typeof target === "string") {
    return result.title?.trim() || "Escalated from governed evidence handoff.";
  }

  return (
    target?.suggested_note?.trim() ||
    result.title?.trim() ||
    "Escalated from governed evidence handoff."
  );
}

function buildScopeBadges(
  scope: EvidenceScope | null | undefined,
  patentId?: string,
) {
  const jurisdictions = normalizeList(
    scope?.jurisdiction ?? scope?.jurisdictions,
  );
  const sourceCount = scope?.sources_considered?.length
    ? `${scope.sources_considered.length} governed source${scope.sources_considered.length === 1 ? "" : "s"}`
    : undefined;
  const badges = [
    scope?.label ?? (patentId ? `Patent ${patentId}` : "Full report"),
    scope?.mode,
    jurisdictions.length ? jurisdictions.join(" / ") : undefined,
    scope?.coverage,
    sourceCount,
    scope?.source_name,
    scope?.artifact_type,
    scope?.status,
  ].filter((item): item is string => Boolean(item?.trim()));

  return badges.length
    ? badges
    : [patentId ? `Patent ${patentId}` : "Full report"];
}

function ProviderCapabilityStack({
  providers,
}: {
  providers: GovernedProviderCapability[];
}) {
  if (!providers.length) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Shield className="h-3.5 w-3.5 text-brand-primary" />
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
          Provider governance
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {providers.map((provider) => {
          const modalityCoverage = normalizeList(provider.modality_coverage);
          const jurisdictionCoverage = normalizeList(
            provider.jurisdiction_coverage,
          );
          const providerId = provider.provider_id?.trim();
          const providerStatus = provider.provider_status || "active";
          const configurationLabel = describeProviderConfiguration(provider);
          const executionBasis = describeProviderExecutionBasis(provider);
          const executionMode = formatProviderExecutionMode(
            provider.execution_mode,
          );
          const timestampItems = [
            provider.source_as_of?.trim()
              ? { label: "Source as of", value: provider.source_as_of.trim() }
              : null,
            provider.retrieved_at?.trim()
              ? { label: "Retrieved", value: provider.retrieved_at.trim() }
              : null,
            provider.dataset_version?.trim()
              ? { label: "Dataset", value: provider.dataset_version.trim() }
              : null,
          ].filter(
            (item): item is { label: string; value: string } => item !== null,
          );

          return (
            <div
              key={`${providerId || provider.provider_name}-${provider.provider_class}`}
              className={cn(
                "praviar-glass-chip space-y-3 rounded-lg border p-3",
                providerStatus === "active"
                  ? "border-brand-primary/15 bg-brand-primary/[0.03]"
                  : "border-warning/25 bg-warning/[0.06]",
              )}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {provider.provider_name}
                  </p>
                  {providerId ? (
                    <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      {providerId}
                    </p>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    <Badge
                      variant="outline"
                      className="text-xs uppercase tracking-wide"
                    >
                      {formatProviderClass(provider.provider_class) ??
                        "Provider"}
                    </Badge>
                    <Badge
                      variant={getProviderStatusVariant(providerStatus)}
                      className="text-xs uppercase tracking-wide"
                    >
                      {formatProviderStatus(providerStatus)}
                    </Badge>
                    <Badge
                      variant={
                        provider.live_retrieval_supported ||
                        provider.materialized_in_report
                          ? "success"
                          : providerStatus === "active"
                            ? "secondary"
                            : "warning"
                      }
                      className="text-xs uppercase tracking-wide"
                    >
                      {executionBasis}
                    </Badge>
                    <Badge
                      variant={
                        provider.configured_for_org
                          ? "success"
                          : provider.configured
                            ? "warning"
                            : "outline"
                      }
                      className="text-xs uppercase tracking-wide"
                    >
                      {configurationLabel}
                    </Badge>
                    <Badge
                      variant="outline"
                      className="text-xs uppercase tracking-wide"
                    >
                      {executionMode}
                    </Badge>
                  </div>
                </div>
              </div>

              <div className="grid gap-2 text-xs leading-5 text-[var(--text-secondary)] sm:grid-cols-2">
                <p>
                  <span className="font-medium text-[var(--text-primary)]">
                    Execution:
                  </span>{" "}
                  {executionMode}
                </p>
                <p>
                  <span className="font-medium text-[var(--text-primary)]">
                    Workspace:
                  </span>{" "}
                  {configurationLabel}
                </p>
                <p>
                  <span className="font-medium text-[var(--text-primary)]">
                    Source basis:
                  </span>{" "}
                  {executionBasis}
                </p>
                <p>
                  <span className="font-medium text-[var(--text-primary)]">
                    Provider ID:
                  </span>{" "}
                  {providerId || "Not declared"}
                </p>
                {timestampItems.map((item) => (
                  <p key={`${item.label}-${item.value}`}>
                    <span className="font-medium text-[var(--text-primary)]">
                      {item.label}:
                    </span>{" "}
                    {item.value}
                  </p>
                ))}
              </div>

              <div className="flex flex-wrap gap-2">
                {modalityCoverage.length ? (
                  <Badge
                    variant="outline"
                    className="text-xs uppercase tracking-wide"
                  >
                    {modalityCoverage.join(" / ")}
                  </Badge>
                ) : (
                  <Badge
                    variant="outline"
                    className="text-xs uppercase tracking-wide"
                  >
                    Modality coverage pending
                  </Badge>
                )}
                {jurisdictionCoverage.length ? (
                  <Badge
                    variant="outline"
                    className="text-xs uppercase tracking-wide"
                  >
                    {jurisdictionCoverage.join(" / ")}
                  </Badge>
                ) : (
                  <Badge
                    variant="outline"
                    className="text-xs uppercase tracking-wide"
                  >
                    Jurisdiction coverage pending
                  </Badge>
                )}
              </div>

              {provider.governance_note ? (
                <p className="text-xs leading-5 text-[var(--text-secondary)]">
                  {provider.governance_note}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EvidenceMetadataStrip({
  patentId,
  workspaceMeta,
  scope,
}: {
  patentId?: string;
  workspaceMeta?: ChatWorkspaceMetadata | null;
  scope?: EvidenceScope | null;
}) {
  const scopeLabel =
    scope?.label ??
    workspaceMeta?.scope_label ??
    (patentId ? `Patent ${patentId}` : "Full report");
  const trustLabel = labelForTrustMode(workspaceMeta?.trust_mode);
  const capabilityLabel =
    workspaceMeta?.capability_label ?? "Governed evidence search";
  const evidenceLabel =
    workspaceMeta?.evidence_mode ??
    formatEvidenceModeLabel(scope?.mode) ??
    "Read-only evidence search";
  const coverageLabel =
    scope?.coverage ??
    workspaceMeta?.source_coverage ??
    (scope?.sources_considered?.length
      ? `${scope.sources_considered.length} governed sources`
      : "Report-grounded evidence");
  const scopeBadges = buildScopeBadges(scope, patentId);
  const providerCapabilities = normalizeProviderCapabilities(scope);
  const hybridReadiness = scope?.hybrid_evidence_ready
    ? "Hybrid evidence layers ready"
    : providerCapabilities.length > 1
      ? "Hybrid evidence layers declared"
      : "Report-derived provider active";

  return (
    <div className="praviar-glass-panel-soft space-y-3 rounded-lg p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="default" className="text-xs uppercase tracking-wide">
          {scopeLabel}
        </Badge>
        <Badge variant="secondary" className="text-xs uppercase tracking-wide">
          {trustLabel}
        </Badge>
        <Badge variant="outline" className="text-xs uppercase tracking-wide">
          {capabilityLabel}
        </Badge>
        <Badge variant="secondary" className="text-xs uppercase tracking-wide">
          {evidenceLabel}
        </Badge>
        <Badge variant="outline" className="text-xs uppercase tracking-wide">
          {coverageLabel}
        </Badge>
        <Badge variant="outline" className="text-xs uppercase tracking-wide">
          {hybridReadiness}
        </Badge>
      </div>

      <div className="flex flex-wrap gap-2">
        {scopeBadges.slice(0, 6).map((badge) => (
          <Badge
            key={badge}
            variant="outline"
            className="text-xs uppercase tracking-wide"
          >
            {badge}
          </Badge>
        ))}
      </div>

      {workspaceMeta?.tool_access?.length ? (
        <div className="flex flex-wrap gap-2">
          {workspaceMeta.tool_access.slice(0, 4).map((tool) => (
            <Badge
              key={tool}
              variant="outline"
              className="text-xs uppercase tracking-wide"
            >
              {tool.replaceAll("_", " ")}
            </Badge>
          ))}
        </div>
      ) : null}

      {scope?.sources_considered?.length ? (
        <div className="flex flex-wrap gap-2">
          {scope.sources_considered.slice(0, 4).map((source) => (
            <Badge
              key={source}
              variant="outline"
              className="text-xs uppercase tracking-wide"
            >
              {source.replaceAll("_", " ")}
            </Badge>
          ))}
        </div>
      ) : null}

      <ProviderCapabilityStack providers={providerCapabilities} />
    </div>
  );
}

function SearchStateCard({
  title,
  description,
  icon,
  accentClassName,
  role,
}: {
  title: string;
  description: string;
  icon: ReactNode;
  accentClassName: string;
  role?: "alert" | "status";
}) {
  return (
    <Card className={cn("border-dashed", accentClassName)} role={role}>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start gap-3">
          <div className="praviar-glass-chip flex h-9 w-9 items-center justify-center rounded-full text-brand-primary">
            {icon}
          </div>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </p>
            <p className="text-xs text-[var(--text-secondary)]">
              {description}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function EvidenceBadgeRow({
  items,
}: {
  items: Array<string | undefined | null>;
}) {
  const badges = items.filter((item): item is string => Boolean(item?.trim()));
  if (!badges.length) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {badges.map((item) => (
        <Badge
          key={item}
          variant="outline"
          className="text-xs uppercase tracking-wide"
        >
          {item}
        </Badge>
      ))}
    </div>
  );
}

function getEvidenceReviewUiState({
  canHandoff,
  hasReviewableProvenance,
  hasReviewTarget,
  isAnyHandoffPending,
  isHandoffPendingForCard,
  isPreviousResultSet,
}: {
  canHandoff: boolean;
  hasReviewableProvenance: boolean;
  hasReviewTarget: boolean;
  isAnyHandoffPending: boolean;
  isHandoffPendingForCard: boolean;
  isPreviousResultSet: boolean;
}) {
  const isReviewReady =
    hasReviewTarget && hasReviewableProvenance && canHandoff;
  const isPendingForCard = isHandoffPendingForCard && isReviewReady;

  let reviewStatusLabel = "Needs provenance";
  if (isReviewReady) reviewStatusLabel = "Review-ready artifact";
  else if (!canHandoff) reviewStatusLabel = "Routing unavailable";

  let actionLabel = "Send to review";
  let actionAriaPrefix = "Send to review";
  if (isPreviousResultSet) {
    actionLabel = "Refresh required";
    actionAriaPrefix = "Refresh required before sending";
  } else if (!canHandoff) {
    actionLabel = "Routing unavailable";
    actionAriaPrefix = "Review routing unavailable";
  } else if (!hasReviewableProvenance) {
    actionLabel = "Provenance required";
    actionAriaPrefix = "Provenance required before sending";
  } else if (isPendingForCard) {
    actionLabel = "Sending to review...";
  }

  return {
    actionAriaPrefix,
    actionLabel,
    isActionDisabled:
      isAnyHandoffPending ||
      isPreviousResultSet ||
      !hasReviewableProvenance ||
      !canHandoff,
    isPendingForCard,
    isReviewReady,
    reviewStatusLabel,
  };
}

function EvidenceResultCard({
  result,
  resultIndex,
  isHandoffPendingForCard,
  isAnyHandoffPending,
  isPreviousResultSet,
  canHandoff,
  onRouteFollowUp,
}: {
  result: EvidenceResult;
  resultIndex: number;
  isHandoffPendingForCard: boolean;
  isAnyHandoffPending: boolean;
  isPreviousResultSet: boolean;
  canHandoff: boolean;
  onRouteFollowUp: (
    result: EvidenceResult,
    target: EvidenceFollowUpTarget | null | undefined,
    resultIndex: number,
  ) => void;
}) {
  const followUpLabel = describeFollowUpTarget(result.follow_up_target);
  const provenanceItems = normalizeProvenance(result.provenance);
  const artifactId = getEvidenceArtifactId(result, resultIndex);
  const title = result.title || result.patent_id || "Evidence result";
  const hasReviewTarget = hasFollowUpTarget(result.follow_up_target);
  const hasReviewableProvenance = provenanceItems.length > 0;
  const reviewUi = getEvidenceReviewUiState({
    canHandoff,
    hasReviewableProvenance,
    hasReviewTarget,
    isAnyHandoffPending,
    isHandoffPendingForCard,
    isPreviousResultSet,
  });
  const relevanceLabel = formatRelevance(result.relevance);
  const rankLabel = formatRankLabel(resultIndex);
  const rankingRationale = buildRankingRationale(
    result,
    provenanceItems.length,
  );

  return (
    <Card
      className={cn(
        "overflow-hidden border-[var(--border-default)]",
        reviewUi.isReviewReady
          ? "border-l-2 border-l-brand-primary/70"
          : "border-l-2 border-l-warning/60",
      )}
    >
      <CardContent className="space-y-4 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant="default"
                className="text-xs uppercase tracking-wide"
              >
                {rankLabel}
              </Badge>
              <Badge
                variant="outline"
                className="font-mono text-xs uppercase tracking-wide"
                title={artifactId}
              >
                Result {artifactId}
              </Badge>
              <Badge
                variant={reviewUi.isReviewReady ? "success" : "warning"}
                className="text-xs uppercase tracking-wide"
              >
                {reviewUi.reviewStatusLabel}
              </Badge>
              <Badge
                variant="secondary"
                className="text-xs uppercase tracking-wide"
              >
                {relevanceLabel}
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                {title}
              </h4>
              {result.patent_id ? (
                <Badge
                  variant="secondary"
                  className="text-xs uppercase tracking-wide"
                >
                  {result.patent_id}
                </Badge>
              ) : null}
            </div>
            <EvidenceBadgeRow
              items={[
                result.source_name,
                formatAuthorityTier(result.authority_tier),
                formatFreshness(result.freshness),
                result.artifact_type,
                formatSection(result.section),
              ]}
            />
          </div>

          {hasReviewTarget ? (
            <Button
              type="button"
              variant="outline"
              className="min-h-11 shrink-0"
              loading={reviewUi.isPendingForCard}
              aria-label={`${reviewUi.actionAriaPrefix}: ${title} (${artifactId})`}
              disabled={reviewUi.isActionDisabled}
              onClick={() =>
                onRouteFollowUp(result, result.follow_up_target, resultIndex)
              }
            >
              <ArrowUpRight className="h-4 w-4" />
              {reviewUi.actionLabel}
            </Button>
          ) : null}
        </div>

        <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--text-secondary)]">
          {result.summary || "No summary available for this evidence item."}
        </p>

        <p className="rounded-lg border border-brand-primary/15 bg-brand-primary/[0.04] px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">
            Ranking rationale:
          </span>{" "}
          {rankingRationale}
        </p>

        {!hasReviewableProvenance && hasReviewTarget ? (
          <div
            className="flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]"
            role="status"
          >
            <TriangleAlert
              className="mt-0.5 h-4 w-4 shrink-0 text-warning"
              aria-hidden="true"
            />
            <p>
              Add or refresh source provenance before routing this evidence into
              review. Counsel handoff is intentionally gated until the artifact
              can be traced.
            </p>
          </div>
        ) : null}

        {!canHandoff && hasReviewTarget && hasReviewableProvenance ? (
          <div
            className="flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]"
            role="status"
          >
            <TriangleAlert
              className="mt-0.5 h-4 w-4 shrink-0 text-warning"
              aria-hidden="true"
            />
            <p>
              Comment routing is unavailable for this evidence scope. Review the
              artifact in place or refresh after routing is enabled.
            </p>
          </div>
        ) : null}

        <div className="praviar-glass-panel-soft grid gap-3 rounded-lg p-3 md:grid-cols-3">
          <div className="space-y-1">
            <p className="flex items-center gap-1 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              <Shield className="h-3.5 w-3.5" />
              Source posture
            </p>
            <div className="space-y-1 text-sm text-[var(--text-secondary)]">
              <p>
                <span className="font-medium text-[var(--text-primary)]">
                  Authority:
                </span>{" "}
                {formatAuthorityTier(result.authority_tier) ?? "Not declared"}
              </p>
              <p>
                <span className="font-medium text-[var(--text-primary)]">
                  Freshness:
                </span>{" "}
                {formatFreshness(result.freshness) ?? "Not declared"}
              </p>
              <p>
                <span className="font-medium text-[var(--text-primary)]">
                  Match:
                </span>{" "}
                {relevanceLabel}
              </p>
            </div>
          </div>

          <div className="space-y-1">
            <p className="flex items-center gap-1 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              <FileText className="h-3.5 w-3.5" />
              Provenance
            </p>
            {provenanceItems.length ? (
              <div className="space-y-1.5">
                {provenanceItems.map((item, index) => (
                  <p
                    key={`${item.label}-${item.value}-${index}`}
                    className="text-sm text-[var(--text-secondary)]"
                  >
                    <span className="font-medium text-[var(--text-primary)]">
                      {item.label}:
                    </span>{" "}
                    {item.value}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-secondary)]">
                Provenance unavailable
              </p>
            )}
          </div>

          <div className="space-y-1">
            <p className="flex items-center gap-1 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              <BookOpen className="h-3.5 w-3.5" />
              Follow-up target
            </p>
            <p className="text-sm text-[var(--text-secondary)]">
              {followUpLabel || "No follow-up target attached"}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function normalizeLegacySearchData(
  state: Pick<EvidenceSearchState, "data" | "error" | "isSearching"> & {
    interpretedQuery?: string;
    results?: Array<{
      patent_id: string;
      section: string;
      snippet: string;
    }>;
    totalResults?: number;
  },
  patentId?: string,
  workspaceMeta?: ChatWorkspaceMetadata | null,
): EvidenceSearchData {
  if (state.data) {
    return {
      query: state.data.query,
      interpreted_query: state.data.interpreted_query,
      scope: {
        ...state.data.scope,
        summary: state.data.scope?.governed_note,
      },
      results: state.data.results ?? [],
    };
  }

  const scope: EvidenceScope = {
    label:
      workspaceMeta?.scope_label ??
      (patentId ? `Patent ${patentId}` : "Full report"),
    mode: workspaceMeta?.evidence_mode ?? "Read-only report search",
    coverage: workspaceMeta?.source_coverage ?? "Report-grounded evidence",
  };

  return {
    interpreted_query: state.interpretedQuery,
    scope,
    results:
      state.results?.map((result) => ({
        title: result.patent_id || "Report match",
        summary: result.snippet,
        artifact_type: result.section,
        section: result.section,
        patent_id: result.patent_id,
        result_id: `${result.patent_id}-${result.section}`,
        provenance: [],
      })) ?? [],
  };
}

function ReviewHandoffStatusCard({
  response,
  pending,
  error,
  onOpenComments,
}: {
  response?: ReviewHandoffResponse | null;
  pending: boolean;
  error: string | null;
  onOpenComments?: () => void;
}) {
  if (pending) {
    return (
      <SearchStateCard
        title="Sending to review"
        description="Creating a governed handoff comment and escalating the evidence item into the review workflow."
        icon={
          <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
        }
        accentClassName="border-brand-primary/15 bg-brand-primary/[0.04]"
      />
    );
  }

  if (error) {
    return (
      <SearchStateCard
        title="Review handoff failed"
        description={REVIEW_HANDOFF_ERROR_MESSAGE}
        icon={<AlertCircle className="h-4 w-4 text-error" />}
        accentClassName="border-error/20 bg-error/5"
        role="alert"
      />
    );
  }

  if (!response) {
    return null;
  }

  return (
    <Card className="border-brand-primary/15 bg-brand-primary/[0.04]">
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="default" className="text-xs uppercase tracking-wide">
            Review handoff created
          </Badge>
          <Badge
            variant="secondary"
            className="text-xs uppercase tracking-wide"
          >
            {titleize(response.review_status.status) ??
              response.review_status.status}
          </Badge>
          <Badge variant="outline" className="text-xs uppercase tracking-wide">
            {response.escalated_to_review ? "Escalated" : "Not escalated"}
          </Badge>
        </div>

        <p className="text-sm text-[var(--text-secondary)]">
          Comment{" "}
          <span className="font-medium text-[var(--text-primary)]">
            {response.comment_id}
          </span>{" "}
          was routed for{" "}
          <span className="font-medium text-[var(--text-primary)]">
            {titleize(response.target_type) ?? response.target_type}
          </span>
          {response.target_id ? ` (${response.target_id})` : ""}.
        </p>

        {onOpenComments ? (
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={onOpenComments}>
              Open comments tab
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

type RouteEvidenceFollowUp = (
  result: EvidenceResult,
  target: EvidenceFollowUpTarget | null | undefined,
  resultIndex: number,
) => void;

function EvidenceSearchHeader({ canSearch }: { canSearch: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-1">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
          Evidence search
        </p>
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">
          Governed evidence search
        </h3>
        <p className="max-w-2xl text-sm text-[var(--text-secondary)]">
          Search governed evidence with provenance, source authority, and
          explicit scope boundaries.
        </p>
      </div>
      <Badge
        variant={canSearch ? "success" : "warning"}
        className="text-xs uppercase tracking-wide"
      >
        {canSearch ? "Ready" : "Missing auth/context"}
      </Badge>
    </div>
  );
}

function EvidenceSearchForm({
  canSearch,
  displayMode,
  externalExpansionAllowed,
  externalModeDisplayed,
  externalModeRef,
  externalModeSelected,
  hasSubmittedQuery,
  isSearching,
  onClear,
  onModeKeyDown,
  onQueryChange,
  onSelectRetrievalMode,
  onSubmit,
  placeholder,
  primarySearchLabel,
  query,
  queryInputId,
  queryValidationError,
  queryValidationErrorId,
  reportModeRef,
  retrievalModeLabelId,
  scope,
}: {
  canSearch: boolean;
  displayMode: EvidenceSearchRetrievalMode;
  externalExpansionAllowed: boolean;
  externalModeDisplayed: boolean;
  externalModeRef: RefObject<HTMLButtonElement | null>;
  externalModeSelected: boolean;
  hasSubmittedQuery: boolean;
  isSearching: boolean;
  onClear: () => void;
  onModeKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
  onQueryChange: (value: string) => void;
  onSelectRetrievalMode: (mode: EvidenceSearchRetrievalMode) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  placeholder: string;
  primarySearchLabel: string;
  query: string;
  queryInputId: string;
  queryValidationError: string | null;
  queryValidationErrorId: string;
  reportModeRef: RefObject<HTMLButtonElement | null>;
  retrievalModeLabelId: string;
  scope?: EvidenceScope | null;
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="space-y-2">
        <p
          id={retrievalModeLabelId}
          className="text-xs font-medium uppercase tracking-[0.22em] text-[var(--text-tertiary)]"
        >
          Evidence retrieval mode
        </p>
        <div
          role="radiogroup"
          aria-labelledby={retrievalModeLabelId}
          className="flex flex-wrap gap-2"
          onKeyDown={onModeKeyDown}
        >
          <Button
            ref={reportModeRef}
            type="button"
            role="radio"
            aria-checked={!externalModeSelected}
            variant={externalModeSelected ? "outline" : "secondary"}
            className="min-h-11"
            tabIndex={!externalModeSelected && canSearch ? 0 : -1}
            onClick={() => onSelectRetrievalMode("report_evidence")}
            disabled={!canSearch}
          >
            Report-grounded
          </Button>
          <Button
            ref={externalModeRef}
            type="button"
            role="radio"
            aria-checked={externalModeSelected}
            aria-disabled={!canSearch || !externalExpansionAllowed}
            variant={externalModeSelected ? "secondary" : "outline"}
            className="min-h-11"
            tabIndex={externalModeSelected && canSearch ? 0 : -1}
            onClick={() => onSelectRetrievalMode("external_evidence")}
            disabled={!canSearch || !externalExpansionAllowed}
          >
            External expansion
          </Button>
        </div>
        <div className="praviar-glass-chip rounded-lg px-3 py-2 text-xs text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">
            {formatEvidenceModeLabel(displayMode) ?? "Governed evidence search"}
            :
          </span>{" "}
          {describeRetrievalMode(displayMode)}
          {externalModeDisplayed ? (
            <span className="mt-1 block text-[var(--text-tertiary)]">
              {describeExternalGovernance(scope)}
            </span>
          ) : null}
          {!externalExpansionAllowed ? (
            <span className="mt-1 block text-[var(--text-tertiary)]">
              External expansion is unavailable because no live governed
              provider is active for this report scope. No fresh external
              retrieval will run.
            </span>
          ) : null}
        </div>
      </div>

      <div className="space-y-1.5">
        <label
          htmlFor={queryInputId}
          className="text-xs font-medium uppercase tracking-[0.22em] text-[var(--text-tertiary)]"
        >
          Query
        </label>
        <Input
          id={queryInputId}
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={placeholder}
          aria-label="Evidence search query"
          aria-invalid={Boolean(queryValidationError)}
          aria-describedby={
            queryValidationError ? queryValidationErrorId : undefined
          }
          disabled={!canSearch}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="submit"
          loading={isSearching}
          disabled={!canSearch}
          className="min-h-11"
        >
          <Search className="h-4 w-4" />
          {primarySearchLabel}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={onClear}
          disabled={!query && !hasSubmittedQuery}
          className="min-h-11"
        >
          <RefreshCw className="h-4 w-4" />
          Clear
        </Button>
      </div>
    </form>
  );
}

function getIdleGuidance(
  externalModeSelected: boolean,
  scope?: EvidenceScope | null,
  workspaceMeta?: ChatWorkspaceMetadata | null,
) {
  if (externalModeSelected) return describeExternalGovernance(scope);
  return (
    scope?.summary ??
    scope?.governed_note ??
    workspaceMeta?.evidence_mode ??
    "This surface stays read-only and governed."
  );
}

function EvidenceIdleGuidance({
  externalModeSelected,
  hasSubmittedQuery,
  isSearching,
  onSuggestion,
  scope,
  suggestions,
  workspaceMeta,
}: {
  externalModeSelected: boolean;
  hasSubmittedQuery: boolean;
  isSearching: boolean;
  onSuggestion: (suggestion: string) => void;
  scope?: EvidenceScope | null;
  suggestions: string[];
  workspaceMeta?: ChatWorkspaceMetadata | null;
}) {
  if (hasSubmittedQuery || isSearching) return null;

  return (
    <div className="space-y-3">
      <div className="praviar-glass-chip rounded-lg px-3 py-2 text-xs text-[var(--text-secondary)]">
        {getIdleGuidance(externalModeSelected, scope, workspaceMeta)}
      </div>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onSuggestion(suggestion)}
            className="min-h-11 rounded-full border border-[var(--border-default)] px-3 py-1.5 text-xs text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

function buildPreviousResultsDescription({
  failedQuery,
  interpretedQuery,
  query,
  resultQuery,
}: {
  failedQuery: string | null;
  interpretedQuery: string;
  query: string;
  resultQuery: string;
}) {
  const attemptedQuery = failedQuery || query || "your latest query";
  const previousQuery = resultQuery || interpretedQuery || "the prior query";
  return `The search for "${attemptedQuery}" did not complete. These results are still from "${previousQuery}" and cannot be sent to review until the search refreshes.`;
}

function buildNoResultsDescription({
  externalModeActive,
  interpretedQuery,
  query,
}: {
  externalModeActive: boolean;
  interpretedQuery: string;
  query: string;
}) {
  const displayedQuery = interpretedQuery || query || "your query";
  if (externalModeActive) {
    return `No governed external evidence matched "${displayedQuery}". Try broader claim language, provider names, or patent identifiers.`;
  }
  return `No evidence matched "${displayedQuery}". Try broader claim language, source names, or patent identifiers.`;
}

function EvidenceSearchAlerts({
  error,
  externalModeActive,
  failedQuery,
  hasSubmittedQuery,
  interpretedQuery,
  isSearching,
  isShowingPreviousResults,
  query,
  queryValidationError,
  queryValidationErrorId,
  resultQuery,
  resultsLength,
}: {
  error: string | null;
  externalModeActive: boolean;
  failedQuery: string | null;
  hasSubmittedQuery: boolean;
  interpretedQuery: string;
  isSearching: boolean;
  isShowingPreviousResults: boolean;
  query: string;
  queryValidationError: string | null;
  queryValidationErrorId: string;
  resultQuery: string;
  resultsLength: number;
}) {
  const noResults =
    !isSearching &&
    !error &&
    !queryValidationError &&
    hasSubmittedQuery &&
    resultsLength === 0;

  return (
    <>
      {isSearching ? (
        <div className="space-y-3" aria-live="polite">
          <SearchStateCard
            title="Searching evidence"
            description={
              externalModeActive
                ? "Interpreting the query and expanding into governed external evidence layers, provider policy, and scope boundaries."
                : "Interpreting the query and scanning governed evidence, provenance, and scope boundaries."
            }
            icon={
              <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
            }
            accentClassName="border-brand-primary/15 bg-brand-primary/[0.04]"
          />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : null}

      {queryValidationError ? (
        <div id={queryValidationErrorId}>
          <SearchStateCard
            title="Adjust evidence query"
            description={queryValidationError}
            icon={<AlertCircle className="h-4 w-4 text-warning" />}
            accentClassName="border-warning/20 bg-warning/5"
            role="alert"
          />
        </div>
      ) : null}

      {error ? (
        <SearchStateCard
          title="Search failed"
          description={error}
          icon={<AlertCircle className="h-4 w-4 text-error" />}
          accentClassName="border-error/20 bg-error/5"
          role="alert"
        />
      ) : null}

      {isShowingPreviousResults ? (
        <SearchStateCard
          title="Showing previous evidence results"
          description={buildPreviousResultsDescription({
            failedQuery,
            interpretedQuery,
            query,
            resultQuery,
          })}
          icon={<TriangleAlert className="h-4 w-4 text-warning" />}
          accentClassName="border-warning/20 bg-warning/5"
          role="status"
        />
      ) : null}

      {noResults ? (
        <SearchStateCard
          title="No matching evidence"
          description={buildNoResultsDescription({
            externalModeActive,
            interpretedQuery,
            query,
          })}
          icon={<Sparkles className="h-4 w-4" />}
          accentClassName="praviar-glass-panel-soft"
        />
      ) : null}
    </>
  );
}

function InterpretedQuerySummary({
  activeMode,
  interpretedQuery,
  isSearching,
  isShowingPreviousResults,
  totalResults,
}: {
  activeMode: EvidenceSearchRetrievalMode;
  interpretedQuery: string;
  isSearching: boolean;
  isShowingPreviousResults: boolean;
  totalResults?: number;
}) {
  if (isSearching || !interpretedQuery) return null;

  return (
    <div className="praviar-glass-chip rounded-lg px-3 py-2 text-xs text-[var(--text-secondary)]">
      <span className="mr-2 inline-flex">
        <Badge variant="outline" className="text-xs uppercase tracking-wide">
          {formatEvidenceModeLabel(activeMode) ?? "Governed evidence search"}
        </Badge>
      </span>
      <span className="font-semibold text-[var(--text-primary)]">
        {isShowingPreviousResults
          ? "Previous interpreted query:"
          : "Interpreted query:"}
      </span>{" "}
      {interpretedQuery}
      {typeof totalResults === "number" ? (
        <span className="ml-2 text-[var(--text-tertiary)]">
          ({totalResults} result{totalResults === 1 ? "" : "s"})
        </span>
      ) : null}
    </div>
  );
}

function EvidenceResultsList({
  canHandoff,
  isHandoffPending,
  isSearching,
  isShowingPreviousResults,
  onRouteFollowUp,
  pendingHandoffArtifactId,
  results,
}: {
  canHandoff: boolean;
  isHandoffPending: boolean;
  isSearching: boolean;
  isShowingPreviousResults: boolean;
  onRouteFollowUp: RouteEvidenceFollowUp;
  pendingHandoffArtifactId: string | null;
  results: EvidenceResult[];
}) {
  if (isSearching || results.length === 0) return null;

  return (
    <div className="space-y-3" role="list" aria-label="Evidence results">
      {results.map((result, index) => {
        const artifactId = getEvidenceArtifactId(result, index);
        const fallbackKey = `${result.patent_id || result.title || "evidence"}-${result.section || index}-${index}`;

        return (
          <div key={result.result_id || fallbackKey} role="listitem">
            <EvidenceResultCard
              result={result}
              resultIndex={index}
              isHandoffPendingForCard={
                isHandoffPending && pendingHandoffArtifactId === artifactId
              }
              isAnyHandoffPending={isHandoffPending}
              isPreviousResultSet={isShowingPreviousResults}
              canHandoff={canHandoff}
              onRouteFollowUp={onRouteFollowUp}
            />
          </div>
        );
      })}
    </div>
  );
}

function EvidenceReviewRoute({
  canHandoff,
  hasSubmittedQuery,
  isHandoffPending,
  isSearching,
  isShowingPreviousResults,
  onRouteFirstResult,
  results,
}: {
  canHandoff: boolean;
  hasSubmittedQuery: boolean;
  isHandoffPending: boolean;
  isSearching: boolean;
  isShowingPreviousResults: boolean;
  onRouteFirstResult: () => void;
  results: EvidenceResult[];
}) {
  if (isSearching || !hasSubmittedQuery || results.length === 0) return null;
  const hasRoutableResult = results.some(canRouteEvidenceResult);

  return (
    <div className="praviar-glass-panel-soft space-y-3 rounded-lg p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-tertiary)]">
        <ArrowRight className="h-3.5 w-3.5" />
        Evidence stays scoped to the current workspace until a governed review
        handoff is created.
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Review handoff route
          </p>
          <p className="text-xs text-[var(--text-secondary)]">
            {isShowingPreviousResults
              ? "Refresh the failed search before routing evidence into the comments workflow."
              : "Send the highest-ranked review-ready artifact into the comments workflow so counsel can pick it up in context."}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={onRouteFirstResult}
          disabled={
            isHandoffPending ||
            isShowingPreviousResults ||
            !canHandoff ||
            !hasRoutableResult
          }
        >
          <ArrowUpRight className="h-4 w-4" />
          {isShowingPreviousResults ? "Refresh required" : "Send to review"}
        </Button>
      </div>
    </div>
  );
}

type EvidenceSearchCardProps = {
  activeMode: EvidenceSearchRetrievalMode;
  canHandoff: boolean;
  canSearch: boolean;
  displayMode: EvidenceSearchRetrievalMode;
  error: string | null;
  externalExpansionAllowed: boolean;
  externalModeActive: boolean;
  externalModeDisplayed: boolean;
  externalModeRef: RefObject<HTMLButtonElement | null>;
  externalModeSelected: boolean;
  failedQuery: string | null;
  hasSubmittedQuery: boolean;
  interpretedQuery: string;
  isHandoffPending: boolean;
  isSearching: boolean;
  isShowingPreviousResults: boolean;
  onClear: () => void;
  onModeKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
  onQueryChange: (value: string) => void;
  onRouteFirstResult: () => void;
  onRouteFollowUp: RouteEvidenceFollowUp;
  onSelectRetrievalMode: (mode: EvidenceSearchRetrievalMode) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  pendingHandoffArtifactId: string | null;
  placeholder: string;
  primarySearchLabel: string;
  query: string;
  queryInputId: string;
  queryValidationError: string | null;
  queryValidationErrorId: string;
  reportModeRef: RefObject<HTMLButtonElement | null>;
  resultQuery: string;
  results: EvidenceResult[];
  retrievalModeLabelId: string;
  scope?: EvidenceScope | null;
  suggestions: string[];
  totalResults?: number;
  workspaceMeta?: ChatWorkspaceMetadata | null;
};

function EvidenceSearchCard(props: EvidenceSearchCardProps) {
  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <EvidenceSearchForm
          canSearch={props.canSearch}
          displayMode={props.displayMode}
          externalExpansionAllowed={props.externalExpansionAllowed}
          externalModeDisplayed={props.externalModeDisplayed}
          externalModeRef={props.externalModeRef}
          externalModeSelected={props.externalModeSelected}
          hasSubmittedQuery={props.hasSubmittedQuery}
          isSearching={props.isSearching}
          onClear={props.onClear}
          onModeKeyDown={props.onModeKeyDown}
          onQueryChange={props.onQueryChange}
          onSelectRetrievalMode={props.onSelectRetrievalMode}
          onSubmit={props.onSubmit}
          placeholder={props.placeholder}
          primarySearchLabel={props.primarySearchLabel}
          query={props.query}
          queryInputId={props.queryInputId}
          queryValidationError={props.queryValidationError}
          queryValidationErrorId={props.queryValidationErrorId}
          reportModeRef={props.reportModeRef}
          retrievalModeLabelId={props.retrievalModeLabelId}
          scope={props.scope}
        />

        {!props.canSearch ? (
          <p className="rounded-lg border border-warning/20 bg-warning/5 px-3 py-2 text-xs text-[var(--text-secondary)]">
            Search is disabled until analysis context and authentication are
            available.
          </p>
        ) : null}

        <EvidenceIdleGuidance
          externalModeSelected={props.externalModeSelected}
          hasSubmittedQuery={props.hasSubmittedQuery}
          isSearching={props.isSearching}
          onSuggestion={props.onQueryChange}
          scope={props.scope}
          suggestions={props.suggestions}
          workspaceMeta={props.workspaceMeta}
        />
        <EvidenceSearchAlerts
          error={props.error}
          externalModeActive={props.externalModeActive}
          failedQuery={props.failedQuery}
          hasSubmittedQuery={props.hasSubmittedQuery}
          interpretedQuery={props.interpretedQuery}
          isSearching={props.isSearching}
          isShowingPreviousResults={props.isShowingPreviousResults}
          query={props.query}
          queryValidationError={props.queryValidationError}
          queryValidationErrorId={props.queryValidationErrorId}
          resultQuery={props.resultQuery}
          resultsLength={props.results.length}
        />
        <InterpretedQuerySummary
          activeMode={props.activeMode}
          interpretedQuery={props.interpretedQuery}
          isSearching={props.isSearching}
          isShowingPreviousResults={props.isShowingPreviousResults}
          totalResults={props.totalResults}
        />
        <EvidenceResultsList
          canHandoff={props.canHandoff}
          isHandoffPending={props.isHandoffPending}
          isSearching={props.isSearching}
          isShowingPreviousResults={props.isShowingPreviousResults}
          onRouteFollowUp={props.onRouteFollowUp}
          pendingHandoffArtifactId={props.pendingHandoffArtifactId}
          results={props.results}
        />
        <EvidenceReviewRoute
          canHandoff={props.canHandoff}
          hasSubmittedQuery={props.hasSubmittedQuery}
          isHandoffPending={props.isHandoffPending}
          isSearching={props.isSearching}
          isShowingPreviousResults={props.isShowingPreviousResults}
          onRouteFirstResult={props.onRouteFirstResult}
          results={props.results}
        />
      </CardContent>
    </Card>
  );
}

function getEvidenceSearchSnapshot(
  evidenceSearch: EvidenceSearchHookState,
  normalizedData: EvidenceSearchData,
  queryValidationError: string | null,
) {
  const results = normalizedData.results ?? [];
  const interpretedQuery =
    normalizedData.interpreted_query ?? evidenceSearch.interpretedQuery ?? "";
  const failedQuery = evidenceSearch.failedQuery?.trim() || null;
  const resultQuery =
    evidenceSearch.resultQuery?.trim() ||
    normalizedData.query?.trim() ||
    interpretedQuery;
  const isShowingPreviousResults = Boolean(
    evidenceSearch.isShowingPreviousResults && results.length,
  );
  const hasSubmittedQuery = Boolean(
    interpretedQuery ||
    results.length ||
    evidenceSearch.error ||
    queryValidationError,
  );

  return {
    failedQuery,
    hasSubmittedQuery,
    interpretedQuery,
    isShowingPreviousResults,
    resultQuery,
    results,
  };
}

export function ChatPanelEvidenceTab({
  analysisId,
  token,
  patentId,
  initialQuery = "",
  workspaceMeta,
  suggestedQueries,
  className,
  queryInputId,
  onReviewHandoffSuccess,
}: ChatPanelEvidenceTabProps) {
  const generatedQueryInputId = useId();
  const resolvedQueryInputId =
    queryInputId ?? `report-evidence-query-${generatedQueryInputId}`;
  const retrievalModeLabelId = `${resolvedQueryInputId}-retrieval-mode-label`;
  const queryValidationErrorId = `${resolvedQueryInputId}-error`;
  const normalizedInitialQuery = initialQuery
    .trim()
    .slice(0, EVIDENCE_QUERY_MAX_LENGTH);
  const [query, setQuery] = useState(normalizedInitialQuery);
  const [retrievalMode, setRetrievalMode] =
    useState<EvidenceSearchRetrievalMode>("report_evidence");
  const [submittedRetrievalMode, setSubmittedRetrievalMode] =
    useState<EvidenceSearchRetrievalMode>("report_evidence");
  const [queryValidationError, setQueryValidationError] = useState<
    string | null
  >(null);
  const [pendingHandoffArtifactId, setPendingHandoffArtifactId] = useState<
    string | null
  >(null);
  const reportModeRef = useRef<HTMLButtonElement>(null);
  const externalModeRef = useRef<HTMLButtonElement>(null);
  const handoffSuccessTimer = useRef<number | null>(null);
  const deliveredHandoffCommentRef = useRef<string | null>(null);
  const evidenceSearch = useReportEvidenceSearch(
    analysisId,
    token,
  ) as EvidenceSearchHookState;
  const reviewHandoff = useReviewHandoff(analysisId, token);
  const appliedInitialQueryRef = useRef<string | null>(null);
  const normalizedData = normalizeLegacySearchData(
    evidenceSearch,
    patentId,
    workspaceMeta ?? null,
  );

  const search = evidenceSearch.search;
  const clear = evidenceSearch.clear;
  const isSearching = evidenceSearch.isSearching;
  const error = evidenceSearch.error;
  const {
    failedQuery,
    hasSubmittedQuery,
    interpretedQuery,
    isShowingPreviousResults,
    resultQuery,
    results,
  } = getEvidenceSearchSnapshot(
    evidenceSearch,
    normalizedData,
    queryValidationError,
  );
  const scope = normalizedData.scope ?? null;
  const reviewHandoffResponse = reviewHandoff.data ?? null;

  const canSearch = Boolean(analysisId && token);
  const canHandoff = Boolean(
    analysisId &&
    token &&
    !isShowingPreviousResults &&
    scope?.comment_routing_available !== false,
  );
  const externalExpansionAllowed = evidenceScopeHasLiveProvider(scope);
  const activeMode =
    (scope?.mode as EvidenceSearchRetrievalMode | undefined) ??
    submittedRetrievalMode;
  const displayMode = hasSubmittedQuery ? activeMode : retrievalMode;
  const externalModeSelected = isExternalEvidenceMode(retrievalMode);
  const externalModeActive = isExternalEvidenceMode(activeMode);
  const externalModeDisplayed = isExternalEvidenceMode(displayMode);
  const primarySearchLabel = externalModeSelected
    ? "Expand externally"
    : "Search report evidence";
  const placeholder = patentId
    ? "Search evidence for claims, prior art, provenance, or design-around notes..."
    : "Search evidence for claims, risk factors, provenance, or recommendations...";

  useEffect(() => {
    if (!canSearch) return;
    if (normalizedInitialQuery.length < EVIDENCE_QUERY_MIN_LENGTH) return;
    if (appliedInitialQueryRef.current === normalizedInitialQuery) return;

    appliedInitialQueryRef.current = normalizedInitialQuery;
    void search(normalizedInitialQuery, { retrievalMode: "report_evidence" });
  }, [canSearch, normalizedInitialQuery, search]);

  const selectRetrievalMode = (mode: EvidenceSearchRetrievalMode) => {
    if (mode === "external_evidence" && !externalExpansionAllowed) return;
    setRetrievalMode(mode);
    requestAnimationFrame(() => {
      (mode === "external_evidence"
        ? externalModeRef.current
        : reportModeRef.current
      )?.focus();
    });
  };

  const handleRetrievalModeKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (
      ![
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "ArrowDown",
        "Home",
        "End",
      ].includes(event.key)
    ) {
      return;
    }

    event.preventDefault();
    if (
      event.key === "ArrowRight" ||
      event.key === "ArrowDown" ||
      event.key === "End"
    ) {
      selectRetrievalMode(
        externalExpansionAllowed ? "external_evidence" : "report_evidence",
      );
      return;
    }
    selectRetrievalMode("report_evidence");
  };

  const resetPrivateEvidenceInput = useCallback(() => {
    setQuery("");
    setRetrievalMode("report_evidence");
    setSubmittedRetrievalMode("report_evidence");
    setPendingHandoffArtifactId(null);
    reviewHandoff.reset();
  }, [reviewHandoff]);
  useAuthBoundaryReset(resetPrivateEvidenceInput);

  useEffect(
    () => () => {
      if (handoffSuccessTimer.current !== null) {
        window.clearTimeout(handoffSuccessTimer.current);
      }
    },
    [],
  );

  const notifyReviewHandoffSuccess = useCallback(
    (response: ReviewHandoffResponse) => {
      if (!onReviewHandoffSuccess) return;
      if (deliveredHandoffCommentRef.current === response.comment_id) return;
      deliveredHandoffCommentRef.current = response.comment_id;

      if (handoffSuccessTimer.current !== null) {
        window.clearTimeout(handoffSuccessTimer.current);
        handoffSuccessTimer.current = null;
      }

      onReviewHandoffSuccess(response);
    },
    [onReviewHandoffSuccess],
  );

  useEffect(() => {
    if (!reviewHandoffResponse || !onReviewHandoffSuccess) return;

    if (handoffSuccessTimer.current !== null) {
      window.clearTimeout(handoffSuccessTimer.current);
    }

    handoffSuccessTimer.current = window.setTimeout(() => {
      notifyReviewHandoffSuccess(reviewHandoffResponse);
    }, 650);

    return () => {
      if (handoffSuccessTimer.current !== null) {
        window.clearTimeout(handoffSuccessTimer.current);
      }
    };
  }, [
    notifyReviewHandoffSuccess,
    onReviewHandoffSuccess,
    reviewHandoffResponse,
  ]);

  const handleSearch = async (
    modeOverride: EvidenceSearchRetrievalMode = retrievalMode,
  ) => {
    if (isExternalEvidenceMode(modeOverride) && !externalExpansionAllowed) {
      return;
    }
    const trimmed = query.trim();
    setQuery(trimmed);

    if (trimmed.length > 0 && trimmed.length < EVIDENCE_QUERY_MIN_LENGTH) {
      setQueryValidationError(
        "Enter at least 2 characters to search evidence.",
      );
      return;
    }

    if (trimmed.length > EVIDENCE_QUERY_MAX_LENGTH) {
      setQueryValidationError("Keep evidence searches under 200 characters.");
      return;
    }

    setQueryValidationError(null);
    setSubmittedRetrievalMode(modeOverride);
    reviewHandoff.reset();
    await search(trimmed, { retrievalMode: modeOverride });
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await handleSearch();
  };

  const handleClear = () => {
    setQuery("");
    setQueryValidationError(null);
    setSubmittedRetrievalMode("report_evidence");
    setPendingHandoffArtifactId(null);
    reviewHandoff.reset();
    clear();
  };

  const handleRouteFollowUp = async (
    result: EvidenceResult,
    target: EvidenceFollowUpTarget | null | undefined,
    resultIndex: number,
  ) => {
    if (!target || !canHandoff || !canRouteEvidenceResult(result)) return;
    const artifactId = getEvidenceArtifactId(result, resultIndex);

    const payload = {
      body: buildReviewHandoffBody(
        result,
        target,
        interpretedQuery,
        resultQuery,
      ),
      review_note: buildReviewHandoffNote(result, target),
      target_type:
        typeof target === "string"
          ? "analysis"
          : target.target_type || "analysis",
      target_id:
        typeof target === "string"
          ? target.trim() || analysisId
          : target.target_id.trim() || analysisId,
      promote_to_under_review: true,
    };

    try {
      setPendingHandoffArtifactId(artifactId);
      await reviewHandoff.mutateAsync(payload);
    } catch {
      // Mutation state drives the error card; keep the UI responsive.
    } finally {
      setPendingHandoffArtifactId(null);
    }
  };
  const defaultSuggestions = patentId
    ? [
        "Where does this patent discuss claims?",
        "Show provenance-rich prior art",
        "Find design-around language",
      ]
    : [
        "Which evidence items are most relevant?",
        "Show the strongest provenance",
        "Find items ready for follow-up review",
      ];
  const suggestions = [
    ...new Set([...(suggestedQueries ?? []), ...defaultSuggestions]),
  ].slice(0, 4);

  return (
    <div className={cn("space-y-4", className)}>
      <EvidenceSearchHeader canSearch={canSearch} />

      <EvidenceMetadataStrip
        patentId={patentId}
        workspaceMeta={workspaceMeta ?? null}
        scope={scope}
      />

      <ReviewHandoffStatusCard
        response={reviewHandoffResponse}
        pending={reviewHandoff.isPending}
        error={reviewHandoff.error ? REVIEW_HANDOFF_ERROR_MESSAGE : null}
        onOpenComments={
          reviewHandoffResponse && onReviewHandoffSuccess
            ? () => notifyReviewHandoffSuccess(reviewHandoffResponse)
            : undefined
        }
      />

      {!workspaceMeta ? (
        <SearchStateCard
          title="Report-grounded scope"
          description="This tab is using the current report record until governed workspace scope is available."
          icon={<Shield className="h-4 w-4" />}
          accentClassName="bg-[linear-gradient(180deg,var(--bg-surface),var(--bg-base))]"
        />
      ) : null}

      <EvidenceSearchCard
        activeMode={activeMode}
        canHandoff={canHandoff}
        canSearch={canSearch}
        displayMode={displayMode}
        error={error}
        externalExpansionAllowed={externalExpansionAllowed}
        externalModeActive={externalModeActive}
        externalModeDisplayed={externalModeDisplayed}
        externalModeRef={externalModeRef}
        externalModeSelected={externalModeSelected}
        failedQuery={failedQuery}
        hasSubmittedQuery={hasSubmittedQuery}
        interpretedQuery={interpretedQuery}
        isHandoffPending={reviewHandoff.isPending}
        isSearching={isSearching}
        isShowingPreviousResults={isShowingPreviousResults}
        onClear={handleClear}
        onModeKeyDown={handleRetrievalModeKeyDown}
        onQueryChange={setQuery}
        onRouteFirstResult={() =>
          routeFirstRoutableEvidenceResult(results, handleRouteFollowUp)
        }
        onRouteFollowUp={handleRouteFollowUp}
        onSelectRetrievalMode={selectRetrievalMode}
        onSubmit={handleSubmit}
        pendingHandoffArtifactId={pendingHandoffArtifactId}
        placeholder={placeholder}
        primarySearchLabel={primarySearchLabel}
        query={query}
        queryInputId={resolvedQueryInputId}
        queryValidationError={queryValidationError}
        queryValidationErrorId={queryValidationErrorId}
        reportModeRef={reportModeRef}
        resultQuery={resultQuery}
        results={results}
        retrievalModeLabelId={retrievalModeLabelId}
        scope={scope}
        suggestions={suggestions}
        totalResults={evidenceSearch.totalResults}
        workspaceMeta={workspaceMeta}
      />
    </div>
  );
}
