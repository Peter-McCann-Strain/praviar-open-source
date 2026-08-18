import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  CalendarClock,
  ChevronDown,
  Database,
  FileSearch,
  Fingerprint,
  GitBranch,
  ListChecks,
  Scale,
  ShieldCheck,
} from "lucide-react";
import { SearchFunnel } from "@/components/charts/search-funnel";
import { TimingWaterfall } from "@/components/charts/timing-waterfall";
import { sanitizeReportDiagnosticText } from "@/components/report/report-diagnostic-copy";
import { cn } from "@/lib/utils";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";
import type {
  DemoArtifactPayload,
  DemoEvidenceRow,
} from "@/marketing/live-demo";

function formatRiskLabel(riskLevel: DemoEvidenceRow["riskLevel"]): string {
  const normalizedRisk = String(riskLevel).toLowerCase();
  if (normalizedRisk === "high" || normalizedRisk === "critical") {
    return "High sample priority";
  }
  if (normalizedRisk === "medium" || normalizedRisk === "moderate") {
    return "Medium sample priority";
  }
  if (normalizedRisk === "low") return "Low sample priority";
  return "No overlap in sample";
}

function formatPublicExecutionProfile(profile: string): string {
  const normalizedProfile = profile.trim().toLowerCase();

  if (!normalizedProfile) {
    return "Fictional adaptive sample";
  }

  if (normalizedProfile === "world_class_adaptive") {
    return "Illustrative adaptive profile";
  }

  return `Illustrative ${profile.replace(/_/g, " ")}`;
}

function formatSampleMappingStatus(status: string): string {
  const normalizedStatus = status.trim().toLowerCase().replace(/_/g, " ");

  if (normalizedStatus === "met") {
    return "Mapped in fictional sample";
  }
  if (normalizedStatus === "partially met") {
    return "Partially mapped in fictional sample";
  }
  if (normalizedStatus === "not met") {
    return "Not mapped in fictional sample";
  }

  return `Fictional mapping: ${normalizedStatus || "not recorded"}`;
}

function formatSampleClaimReference(value: string): string {
  return value
    .replace(/\bpartially[_ ]met\b/giu, "partially mapped in fictional sample")
    .replace(/\bnot[_ ]met\b/giu, "not mapped in fictional sample")
    .replace(/\bmet\b/giu, "mapped in fictional sample");
}

function formatSampleCheckStatus(
  check: DemoArtifactPayload["verification"]["checks"][number],
): string {
  if (check.severity === "warning") {
    return "Review warning in sample";
  }
  if (check.severity === "fail" || !check.passed) {
    return "Issue shown in sample";
  }
  return "Internally consistent in sample";
}

function formatSampleSourceStatus(status: string): string {
  return status === "ok" ? "Available in sample" : "Sample source warning";
}

function getRiskToneClasses(riskLevel: DemoEvidenceRow["riskLevel"]): string {
  const normalizedRisk = String(riskLevel).toLowerCase();

  if (normalizedRisk === "high" || normalizedRisk === "critical") {
    return "border-error/25 bg-error/15 text-error-emphasis";
  }

  if (normalizedRisk === "medium" || normalizedRisk === "moderate") {
    return "border-warning/25 bg-warning/10 text-warning";
  }

  return "border-success/25 bg-success/10 text-success";
}

function getSupportStatus(row: DemoEvidenceRow): string {
  const normalizedRisk = String(row.riskLevel).toLowerCase();

  if (normalizedRisk === "high" || normalizedRisk === "critical") {
    return "Sample priority rationale";
  }

  if (normalizedRisk === "medium" || normalizedRisk === "moderate") {
    return "Sample review rationale";
  }

  return "Sample context rationale";
}

function getFunnelAuditNote(stage: string): string {
  const normalizedStage = stage.toLowerCase();

  if (normalizedStage.includes("discover")) {
    return "Raw source retrieval across patent and chemistry sources before pruning.";
  }

  if (normalizedStage.includes("filter")) {
    return "Jurisdiction, family, publication, and scope filters remove records that cannot support the question.";
  }

  if (normalizedStage.includes("rank")) {
    return "Similarity, assignee, claim-language, and family signals order the remaining fictional records.";
  }

  if (normalizedStage.includes("triage")) {
    return "Low-signal records become audit context while material candidates move to claim review.";
  }

  if (normalizedStage.includes("analy")) {
    return "Retained candidates receive claim-element review and risk rationale generation.";
  }

  return "Retained records stay visible so users can inspect how the sample narrowed.";
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

function formatSourceName(value: string): string {
  return value.replace(/_/g, " ");
}

function formatCheckName(value: string): string {
  if (value.trim().toLowerCase() === "doe_consistency") {
    return "Doctrine of equivalents consistency";
  }
  return value.replace(/_/g, " ");
}

function getCheckToneClasses(severity?: string): string {
  if (severity === "warning") {
    return "border-warning/25 bg-warning/10 text-warning";
  }

  if (severity === "fail") {
    return "border-error/25 bg-error/15 text-error-emphasis";
  }

  return "border-brand-primary/20 bg-brand-primary/8 text-brand-primary";
}

function MobileReportDisclosure({
  anchorId,
  title,
  description,
  initiallyOpen = false,
  children,
}: {
  anchorId: string;
  title: string;
  description: string;
  initiallyOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <ResponsiveDisclosure
      id={anchorId}
      initiallyOpen={initiallyOpen}
      className="group scroll-mt-24 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-[var(--shadow-xs)] sm:overflow-visible sm:border-0 sm:bg-transparent sm:shadow-none"
      summary={
        <summary className="flex min-h-16 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 marker:content-none sm:hidden [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </span>
            <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
              {description}
            </span>
          </span>
          <ChevronDown
            className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
            aria-hidden="true"
          />
        </summary>
      }
    >
      <div className="sm:block">{children}</div>
    </ResponsiveDisclosure>
  );
}

export function SampleReportDetailLiveSections({
  demoArtifact,
}: {
  demoArtifact: DemoArtifactPayload;
}) {
  const evidenceRows = demoArtifact.evidenceRows ?? [];
  const warningChecks = demoArtifact.verification.checks.filter(
    (check) => check.severity === "warning" || !check.passed,
  );
  const failedSources = demoArtifact.sourceHealth.filter(
    (source) => source.status !== "ok",
  );
  const funnelAuditRows = demoArtifact.searchFunnel.map((stage, index) => {
    const previousCount = demoArtifact.searchFunnel[index - 1]?.count;
    const removedCount =
      previousCount == null ? null : Math.max(previousCount - stage.count, 0);

    return {
      ...stage,
      removedCount,
      auditNote: getFunnelAuditNote(stage.stage),
    };
  });
  const firstFunnelCount = demoArtifact.searchFunnel[0]?.count ?? 0;
  const finalFunnelCount =
    demoArtifact.searchFunnel[demoArtifact.searchFunnel.length - 1]?.count ?? 0;
  const totalFunnelRemoved = Math.max(firstFunnelCount - finalFunnelCount, 0);
  const funnelReductionPercent =
    firstFunnelCount > 0
      ? Math.round((totalFunnelRemoved / firstFunnelCount) * 1000) / 10
      : 0;

  return (
    <>
      <MobileReportDisclosure
        anchorId="sample-trace-packet"
        title="Fictional run record"
        description="Illustrative metadata and the limits of this synthetic record."
        initiallyOpen
      >
        <section
          aria-labelledby="sample-trace-packet-title"
          data-testid="sample-trace-packet"
        >
          <div className="praviar-surface-premium min-w-0 rounded-lg p-4 sm:p-6">
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,0.48fr)] lg:items-start">
              <div className="min-w-0">
                <div className="flex items-start gap-3">
                  <Fingerprint
                    className="mt-1 h-5 w-5 text-brand-primary"
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      Fictional run record
                    </p>
                    <h2
                      id="sample-trace-packet-title"
                      className="mt-3 text-2xl font-semibold leading-tight text-[var(--text-primary)]"
                    >
                      See how run metadata is presented in the sample
                    </h2>
                    <p className="mt-3 max-w-3xl text-sm leading-7 text-[var(--text-secondary)]">
                      These illustrative fields show how run metadata would
                      appear. They are fictional and are not evidence of a
                      production execution, performance result or external
                      validation.
                    </p>
                  </div>
                </div>

                <dl className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    {
                      label: "Sample report ID",
                      value: demoArtifact.provenance.reportId,
                      icon: Fingerprint,
                    },
                    {
                      label: "Illustrative date",
                      value: formatDateTime(
                        demoArtifact.provenance.generatedAt,
                      ),
                      icon: CalendarClock,
                    },
                    {
                      label: "Sample build",
                      value: `v${demoArtifact.provenance.pipelineVersion}`,
                      icon: GitBranch,
                    },
                    {
                      label: "Illustrative profile",
                      value: formatPublicExecutionProfile(
                        demoArtifact.provenance.executionProfile,
                      ),
                      icon: ListChecks,
                    },
                  ].map((item) => {
                    const Icon = item.icon;

                    return (
                      <div
                        key={item.label}
                        className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3"
                      >
                        <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                          {item.label}
                        </dt>
                        <dd className="mt-2 break-words text-sm font-semibold text-[var(--text-primary)]">
                          {item.value}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
              </div>

              <div
                aria-label="Sample trace caveats"
                role="note"
                className="rounded-lg border border-warning/25 bg-warning/10 p-4"
              >
                <div className="flex items-start gap-3">
                  <AlertTriangle
                    className="mt-0.5 h-5 w-5 shrink-0 text-warning"
                    aria-hidden="true"
                  />
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                      About this sample
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                      This fictional report shows how the product works. It is
                      not attorney-reviewed legal research and must not be cited
                      as a real patent record.
                    </p>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 text-xs font-semibold text-[var(--text-primary)] sm:grid-cols-3 lg:grid-cols-1">
                  <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2">
                    {demoArtifact.sourceHealth.length} illustrative source lanes
                  </span>
                  <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2">
                    {warningChecks.length} sample check warning
                    {warningChecks.length === 1 ? "" : "s"}
                  </span>
                  <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2">
                    {demoArtifact.dataLimitations.length} sample limitation
                    {demoArtifact.dataLimitations.length === 1 ? "" : "s"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </MobileReportDisclosure>

      <MobileReportDisclosure
        anchorId="sample-claim-chart"
        title="Fictional claim chart"
        description="Illustrative element mapping, rationale, and handoff context."
      >
        <section className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1.24fr)_minmax(20rem,0.76fr)]">
          <div className="praviar-surface-premium min-w-0 rounded-lg p-4 sm:p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Fictional claim chart
            </p>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <div className="min-w-0">
                <h2 className="break-words text-xl font-semibold text-[var(--text-primary)]">
                  {demoArtifact.claimSnapshot.patentId}
                </h2>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  Claim {demoArtifact.claimSnapshot.claimNumber}
                </p>
              </div>
              <div className="inline-flex w-fit max-w-full items-center gap-2 rounded-full bg-[var(--bg-elevated)] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
                <Scale className="h-3.5 w-3.5" aria-hidden="true" />
                <span className="min-w-0 break-words">
                  {formatSampleMappingStatus(
                    demoArtifact.claimSnapshot.claimStatus,
                  )}
                </span>
              </div>
            </div>

            <div
              className="mt-5 grid gap-3 xl:hidden"
              data-testid="sample-claim-card-list"
            >
              {demoArtifact.claimSnapshot.elements.map((element) => (
                <article
                  key={element.label}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-xs)]"
                >
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                        {element.label}
                      </h3>
                      <p className="mt-1 text-xs font-medium text-[var(--text-tertiary)]">
                        Claim {demoArtifact.claimSnapshot.claimNumber} /{" "}
                        {demoArtifact.claimSnapshot.patentId}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "inline-flex w-fit max-w-full rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em]",
                        element.status === "met"
                          ? "bg-error/15 text-error-emphasis"
                          : "bg-success/15 text-success-emphasis",
                      )}
                    >
                      <span className="break-words">
                        {formatSampleMappingStatus(element.status)}
                      </span>
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                    {element.evidence}
                  </p>
                  <dl className="mt-3 grid gap-2 rounded-md bg-[var(--surface-muted)] p-3 text-xs sm:grid-cols-2">
                    <div>
                      <dt className="font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                        Claim text
                      </dt>
                      <dd className="mt-1 leading-5 text-[var(--text-secondary)]">
                        {element.elementText}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                        Sample trace
                      </dt>
                      <dd className="mt-1 font-mono text-[var(--text-primary)] [overflow-wrap:anywhere]">
                        {element.traceId}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                        Source span
                      </dt>
                      <dd className="mt-1 text-[var(--text-secondary)]">
                        {element.sourceCitation}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                        Sample support
                      </dt>
                      <dd className="mt-1 text-[var(--text-secondary)]">
                        Internal link present in fictional record
                      </dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>

            <div className="mt-5 hidden min-w-0 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-[var(--shadow-xs)] xl:block">
              <div
                aria-label="Claim chart table"
                className="max-w-full overflow-hidden"
                role="region"
              >
                <table
                  className="w-full table-fixed border-collapse text-left text-sm"
                  data-testid="sample-claim-chart-table"
                >
                  <caption className="sr-only">
                    Claim chart for {demoArtifact.claimSnapshot.patentId}
                  </caption>
                  <colgroup>
                    <col className="w-[18%]" />
                    <col className="w-[18%]" />
                    <col className="w-[40%]" />
                    <col className="w-[24%]" />
                  </colgroup>
                  <thead className="bg-[var(--surface-muted)] text-xs uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    <tr>
                      <th scope="col" className="px-4 py-3 font-semibold">
                        Element
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold">
                        Status
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold">
                        Evidence excerpt
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold">
                        Source trace
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-subtle)]">
                    {demoArtifact.claimSnapshot.elements.map((element) => (
                      <tr key={element.label} className="align-top">
                        <th
                          scope="row"
                          className="min-w-0 px-4 py-4 text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]"
                        >
                          <span className="block break-words">
                            {element.label}
                          </span>
                          <span className="mt-1 block text-xs font-medium text-[var(--text-tertiary)]">
                            Claim {demoArtifact.claimSnapshot.claimNumber}
                          </span>
                        </th>
                        <td className="min-w-0 px-4 py-4 [overflow-wrap:anywhere]">
                          <span
                            className={cn(
                              "inline-flex w-fit max-w-full rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em]",
                              element.status === "met"
                                ? "bg-error/15 text-error-emphasis"
                                : "bg-success/15 text-success-emphasis",
                            )}
                          >
                            <span className="break-words">
                              {formatSampleMappingStatus(element.status)}
                            </span>
                          </span>
                        </td>
                        <td className="min-w-0 px-4 py-4 text-sm leading-6 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                          <p>{element.evidence}</p>
                          <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                            Claim text: {element.elementText}
                          </p>
                        </td>
                        <td className="min-w-0 px-4 py-4 [overflow-wrap:anywhere]">
                          <span className="block break-words text-xs font-semibold text-[var(--text-primary)]">
                            {element.sourceCitation}
                          </span>
                          <span className="mt-1 block font-mono text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                            {element.traceId}
                          </span>
                          <span className="mt-2 block text-xs leading-5 text-[var(--text-secondary)]">
                            Internal link present in fictional record
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="praviar-surface-premium min-w-0 space-y-6 rounded-lg p-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Research hypothesis for counsel
              </p>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {demoArtifact.designAround}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Prior-art question for counsel
              </p>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {demoArtifact.invalidityTeaser}
              </p>
            </div>
            <div className="rounded-lg bg-[var(--surface-muted)] p-5">
              <div className="flex items-start gap-3">
                <ShieldCheck
                  className="mt-1 h-5 w-5 text-success"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Evidence-led handoff
                  </p>
                  <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                    This sample is designed to make the next legal step more
                    focused, not to replace it.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </MobileReportDisclosure>

      <MobileReportDisclosure
        anchorId="sample-evidence-ledger"
        title="Source records"
        description="The records and claim support behind the sample finding."
      >
        <section
          aria-labelledby="sample-evidence-ledger-title"
          data-testid="sample-evidence-traceability-ledger"
        >
          <div className="praviar-surface-premium min-w-0 rounded-lg p-4 sm:p-6">
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.45fr)] lg:items-start">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  Source records
                </p>
                <h2
                  id="sample-evidence-ledger-title"
                  className="mt-3 text-2xl font-semibold leading-tight text-[var(--text-primary)]"
                >
                  Follow the sample finding back to its support
                </h2>
                <p className="mt-3 max-w-3xl text-sm leading-7 text-[var(--text-secondary)]">
                  Each row ties a fictional patent family to the relevant claim
                  support and the next action. Links stay inside the sample so
                  no one mistakes it for external legal research.
                </p>
              </div>
              <div className="grid gap-2 text-sm sm:grid-cols-3 lg:grid-cols-1">
                {[
                  ["Sample source", demoArtifact.sourceReference],
                  ["Human review", "Counsel review required"],
                  ["User action", "Inspect claim chart before relying"],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3"
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                      {label}
                    </p>
                    <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                      {value}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {evidenceRows.length > 0 ? (
              <>
                <div className="mt-6 grid gap-4 lg:grid-cols-2 2xl:hidden">
                  {evidenceRows.map((row, index) => (
                    <article
                      key={row.patentId}
                      className={cn(
                        "rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-xs)]",
                        evidenceRows.length % 2 === 1 &&
                          index === evidenceRows.length - 1 &&
                          "lg:col-span-2",
                      )}
                    >
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0">
                          <p className="font-mono text-xs font-semibold text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                            {row.patentId}
                          </p>
                          <h3 className="mt-1 text-sm font-semibold leading-6 text-[var(--text-primary)]">
                            {row.title}
                          </h3>
                          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                            {row.assignee}
                          </p>
                        </div>
                        <span
                          className={cn(
                            "inline-flex w-fit max-w-full rounded-md border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em]",
                            getRiskToneClasses(row.riskLevel),
                          )}
                        >
                          <span className="break-words">
                            {formatRiskLabel(row.riskLevel)}
                          </span>
                        </span>
                      </div>
                      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                        <div>
                          <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                            Claim basis
                          </dt>
                          <dd className="mt-1 text-[var(--text-primary)]">
                            {formatSampleClaimReference(row.claimReference)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                            Support status
                          </dt>
                          <dd className="mt-1 text-[var(--text-primary)]">
                            {getSupportStatus(row)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                            Sample rank
                          </dt>
                          <dd className="mt-1 text-[var(--text-primary)]">
                            {row.rank ? `#${row.rank}` : "Unranked"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                            Expiry
                          </dt>
                          <dd className="mt-1 text-[var(--text-primary)]">
                            {row.expiryDate ?? "Not available"}
                          </dd>
                        </div>
                      </dl>
                      <p className="mt-4 text-sm leading-6 text-[var(--text-secondary)]">
                        {row.rationale}
                      </p>
                      <p className="mt-3 rounded-md bg-[var(--surface-muted)] p-3 text-xs leading-5 text-[var(--text-secondary)]">
                        {row.triageReason}
                      </p>
                      <a
                        href="#sample-claim-chart"
                        className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:border-[var(--border-emphasis)] hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
                      >
                        Inspect claim basis
                        <ArrowRight className="h-4 w-4" aria-hidden="true" />
                      </a>
                    </article>
                  ))}
                </div>

                <div className="mt-6 hidden min-w-0 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-[var(--shadow-xs)] 2xl:block">
                  <div
                    aria-label="Scrollable evidence traceability ledger"
                    className="max-w-full overflow-x-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                    role="region"
                    tabIndex={0}
                  >
                    <table
                      className="w-full min-w-[1180px] table-fixed border-collapse text-left text-sm"
                      data-testid="sample-evidence-ledger-table"
                    >
                      <caption className="sr-only">
                        Evidence traceability ledger for the public sample
                        report
                      </caption>
                      <colgroup>
                        <col className="w-[22%]" />
                        <col className="w-[8%]" />
                        <col className="w-[14%]" />
                        <col className="w-[14%]" />
                        <col className="w-[11%]" />
                        <col className="w-[23%]" />
                        <col className="w-[8%]" />
                      </colgroup>
                      <thead className="bg-[var(--surface-muted)] text-xs uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                        <tr>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Source record
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Risk
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Claim basis
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Support status
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Illustrative rank
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Rationale
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Action
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--border-subtle)]">
                        {evidenceRows.map((row) => (
                          <tr key={row.patentId} className="align-top">
                            <th
                              scope="row"
                              className="px-4 py-4 text-sm font-semibold text-[var(--text-primary)]"
                            >
                              <span className="block font-mono text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                                {row.patentId}
                              </span>
                              <span className="mt-1 block leading-6">
                                {row.title}
                              </span>
                              <span className="mt-1 block text-xs font-medium text-[var(--text-tertiary)]">
                                {row.assignee}
                              </span>
                            </th>
                            <td className="px-4 py-4">
                              <span
                                className={cn(
                                  "inline-flex w-fit max-w-full rounded-md border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em]",
                                  getRiskToneClasses(row.riskLevel),
                                )}
                              >
                                <span className="break-words">
                                  {formatRiskLabel(row.riskLevel)}
                                </span>
                              </span>
                            </td>
                            <td className="px-4 py-4 text-sm leading-6 text-[var(--text-primary)]">
                              {formatSampleClaimReference(row.claimReference)}
                              <span className="mt-1 block text-xs text-[var(--text-tertiary)]">
                                Expiry: {row.expiryDate ?? "Not available"}
                              </span>
                            </td>
                            <td className="px-4 py-4 text-sm font-semibold text-[var(--text-primary)]">
                              {getSupportStatus(row)}
                              <span className="mt-1 block text-xs font-medium text-[var(--text-tertiary)]">
                                {row.sourcePosture}
                              </span>
                              <span className="mt-1 block font-mono text-xs font-medium text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                                {row.sourceTraceId}
                              </span>
                            </td>
                            <td className="px-4 py-4 text-sm text-[var(--text-primary)]">
                              <span className="font-mono font-semibold">
                                {row.rank ? `#${row.rank}` : "Unranked"}
                              </span>
                              <span className="mt-1 block text-xs text-[var(--text-tertiary)]">
                                Illustrative rank only
                              </span>
                              <span className="mt-1 block text-xs text-[var(--text-tertiary)]">
                                {row.sourcesFoundIn.length > 0
                                  ? row.sourcesFoundIn
                                      .map(formatSourceName)
                                      .join(", ")
                                  : "No source list"}
                              </span>
                            </td>
                            <td className="px-4 py-4 text-sm leading-6 text-[var(--text-secondary)]">
                              <p>{row.rationale}</p>
                              <p className="mt-2 rounded-md bg-[var(--surface-muted)] p-2 text-xs leading-5">
                                {row.triageReason}
                              </p>
                            </td>
                            <td className="px-4 py-4">
                              <a
                                href="#sample-claim-chart"
                                className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:border-[var(--border-emphasis)] hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
                              >
                                Inspect
                                <ArrowRight
                                  className="h-3.5 w-3.5"
                                  aria-hidden="true"
                                />
                              </a>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            ) : (
              <div className="mt-6 rounded-lg border border-warning/20 bg-warning/10 p-4 text-sm leading-6 text-[var(--text-secondary)]">
                Evidence rows are not attached to this sample yet. The claim
                chart remains visible, but the public ledger needs records
                before users can audit the finding path.
              </div>
            )}
          </div>
        </section>
      </MobileReportDisclosure>

      <MobileReportDisclosure
        anchorId="sample-evidence-profile"
        title="Illustrative search profile"
        description="Fictional retained-count sequence and illustrative timing."
      >
        <section className="grid min-w-0 gap-6 lg:grid-cols-2">
          <div className="praviar-surface-premium min-w-0 rounded-lg p-6">
            <div className="flex items-start gap-3">
              <FileSearch
                className="mt-0.5 h-5 w-5 text-brand-primary"
                aria-hidden="true"
              />
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  Illustrative search funnel
                </p>
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  These purpose-written counts demonstrate the interface. They
                  are not measured recall, throughput or production coverage.
                </p>
              </div>
            </div>
            <div className="mt-4 h-[320px]">
              <SearchFunnel data={demoArtifact.searchFunnel} height={320} />
            </div>
            <div
              className="mt-5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4"
              data-testid="sample-funnel-audit-table"
            >
              <div className="flex items-start gap-3">
                <GitBranch
                  className="mt-0.5 h-4 w-4 text-brand-primary"
                  aria-hidden="true"
                />
                <div>
                  <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                    Illustrative funnel record
                  </h3>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                    Counts are internally derived within this fictional record
                    to show where the example narrows. They are not benchmark or
                    production-run results.
                  </p>
                </div>
              </div>
              <dl
                className="mt-4 grid gap-2 md:hidden"
                data-testid="sample-funnel-audit-summary"
              >
                {[
                  {
                    label: "Illustrative narrowing",
                    value: `${totalFunnelRemoved.toLocaleString()} records`,
                  },
                  {
                    label: "Illustrative reduction",
                    value: `${funnelReductionPercent.toLocaleString()}%`,
                  },
                  {
                    label: "Illustrative final review",
                    value: `${finalFunnelCount.toLocaleString()} patents`,
                  },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3"
                  >
                    <dt className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                      {item.label}
                    </dt>
                    <dd className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                      {item.value}
                    </dd>
                  </div>
                ))}
              </dl>
              <div
                className="mt-4 grid gap-3 md:hidden"
                data-testid="sample-funnel-audit-card-list"
                aria-label="Mobile search funnel audit trail"
              >
                {funnelAuditRows.map((stage, index) => {
                  const retainedShare =
                    firstFunnelCount > 0
                      ? Math.max((stage.count / firstFunnelCount) * 100, 4)
                      : 0;

                  return (
                    <article
                      key={stage.stage}
                      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-xs)]"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                            Stage {String(index + 1).padStart(2, "0")}
                          </p>
                          <h4 className="mt-1 break-words text-sm font-semibold text-[var(--text-primary)]">
                            {stage.stage}
                          </h4>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="font-mono text-lg font-semibold leading-none text-[var(--text-primary)]">
                            {stage.count.toLocaleString()}
                          </p>
                          <p className="mt-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                            retained
                          </p>
                        </div>
                      </div>
                      <div
                        className="mt-3 h-2 rounded-full bg-[var(--surface-muted)]"
                        aria-hidden="true"
                      >
                        <div
                          className="h-full rounded-full bg-brand-primary"
                          style={{ width: `${retainedShare}%` }}
                        />
                      </div>
                      <dl className="mt-3 grid gap-2 text-xs">
                        <div className="flex items-start justify-between gap-3 rounded-md bg-[var(--surface-muted)] px-3 py-2">
                          <dt className="font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                            Removed
                          </dt>
                          <dd className="text-right font-mono font-semibold text-[var(--text-primary)]">
                            {stage.removedCount == null
                              ? "baseline"
                              : stage.removedCount.toLocaleString()}
                          </dd>
                        </div>
                        <div>
                          <dt className="sr-only">Audit note</dt>
                          <dd className="leading-5 text-[var(--text-secondary)]">
                            {stage.auditNote}
                          </dd>
                        </div>
                      </dl>
                    </article>
                  );
                })}
              </div>
              <div
                className="mt-4 hidden max-w-full overflow-x-auto rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] md:block"
                aria-label="Scrollable search funnel audit table"
                data-testid="sample-funnel-audit-desktop-table-wrap"
                role="region"
                tabIndex={0}
              >
                <table
                  className="w-full min-w-[620px] border-collapse text-left text-xs"
                  data-testid="sample-funnel-audit-desktop-table"
                >
                  <caption className="sr-only">
                    Search funnel audit table for the sample report
                  </caption>
                  <thead className="bg-[var(--bg-elevated)] uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    <tr>
                      <th scope="col" className="px-3 py-2 font-semibold">
                        Stage
                      </th>
                      <th scope="col" className="px-3 py-2 font-semibold">
                        Retained
                      </th>
                      <th scope="col" className="px-3 py-2 font-semibold">
                        Removed
                      </th>
                      <th scope="col" className="px-3 py-2 font-semibold">
                        Audit note
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-subtle)]">
                    {funnelAuditRows.map((stage) => (
                      <tr key={stage.stage} className="align-top">
                        <th
                          scope="row"
                          className="px-3 py-3 font-semibold text-[var(--text-primary)]"
                        >
                          {stage.stage}
                        </th>
                        <td className="px-3 py-3 font-mono font-semibold text-[var(--text-primary)]">
                          {stage.count.toLocaleString()}
                        </td>
                        <td className="px-3 py-3 font-mono text-[var(--text-secondary)]">
                          {stage.removedCount == null
                            ? "baseline"
                            : stage.removedCount.toLocaleString()}
                        </td>
                        <td className="px-3 py-3 leading-5 text-[var(--text-secondary)]">
                          {stage.auditNote}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div className="praviar-surface-premium min-w-0 rounded-lg p-6">
            <div className="flex items-start gap-3">
              <ListChecks
                className="mt-0.5 h-5 w-5 text-brand-primary"
                aria-hidden="true"
              />
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  Illustrative workflow timing
                </p>
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  This fictional timing shows the report format only. It is not
                  evidence of production speed, cost, service level or legal
                  quality.
                </p>
              </div>
            </div>
            <div className="mt-4 min-h-[320px]">
              <TimingWaterfall data={demoArtifact.timing} height={320} />
            </div>
          </div>
        </section>
      </MobileReportDisclosure>

      <MobileReportDisclosure
        anchorId="sample-verification-limits"
        title="Consistency and limits"
        description="Internal sample consistency, source availability, and counsel questions."
      >
        <section
          aria-labelledby="sample-verification-limits-title"
          data-testid="sample-verification-limits"
        >
          <div className="praviar-surface-premium min-w-0 rounded-lg p-4 sm:p-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  Sample consistency and limitations
                </p>
                <h2
                  id="sample-verification-limits-title"
                  className="mt-3 text-2xl font-semibold leading-tight text-[var(--text-primary)]"
                >
                  What the fictional checks show and what counsel must still
                  review
                </h2>
                <p className="mt-3 max-w-3xl text-sm leading-7 text-[var(--text-secondary)]">
                  These internal checks apply only to the synthetic record. They
                  are not external validation and do not establish accuracy,
                  completeness or legal quality.
                </p>
              </div>
              <div className="grid w-full gap-2 text-sm sm:grid-cols-3 md:max-w-md">
                <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    Internal sample links
                  </p>
                  <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                    {demoArtifact.verification.unsupportedVisibleClaims === 0
                      ? "Complete within fictional record"
                      : `${demoArtifact.verification.unsupportedVisibleClaims} sample statements lack an internal link`}
                  </p>
                </div>
                <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    Sample warnings
                  </p>
                  <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                    {demoArtifact.verification.issues.length} warning
                    {demoArtifact.verification.issues.length === 1 ? "" : "s"}
                  </p>
                </div>
                <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    Counsel review prompts
                  </p>
                  <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                    {demoArtifact.verification.reviewNeededClaims} item
                    {demoArtifact.verification.reviewNeededClaims === 1
                      ? ""
                      : "s"}
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-2 xl:items-start">
              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
                <div className="flex items-start gap-3">
                  <BadgeCheck
                    className="mt-0.5 h-5 w-5 text-success"
                    aria-hidden="true"
                  />
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                      Internal sample consistency checks
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                      These labels describe internal sample consistency only.
                    </p>
                  </div>
                </div>
                <div className="mt-4 grid gap-2">
                  {demoArtifact.verification.checks.map((check) => (
                    <article
                      key={check.check_name}
                      className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3"
                    >
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                        <h4 className="text-sm font-semibold capitalize text-[var(--text-primary)]">
                          {formatCheckName(check.check_name)}
                        </h4>
                        <span
                          className={cn(
                            "inline-flex w-fit rounded-md border px-2 py-0.5 text-xs font-semibold uppercase tracking-[0.12em]",
                            getCheckToneClasses(check.severity),
                          )}
                        >
                          {formatSampleCheckStatus(check)}
                        </span>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                        {check.details}
                      </p>
                    </article>
                  ))}
                </div>
              </div>

              <div className="grid gap-4">
                <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
                  <div className="flex items-start gap-3">
                    <Database
                      className="mt-0.5 h-5 w-5 text-brand-primary"
                      aria-hidden="true"
                    />
                    <div>
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                        Source health
                      </h3>
                      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                        Failed or partial sources stay visible because missing
                        sources can change confidence.
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 grid gap-2 sm:grid-cols-2">
                    {demoArtifact.sourceHealth.map((source) => (
                      <div
                        key={source.source}
                        className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-sm font-semibold capitalize text-[var(--text-primary)]">
                            {formatSourceName(source.source)}
                          </p>
                          <span
                            className={cn(
                              "rounded-md border px-2 py-0.5 text-xs font-semibold uppercase tracking-[0.12em]",
                              source.status === "ok"
                                ? "border-success/25 bg-success/10 text-success"
                                : "border-warning/25 bg-warning/10 text-warning",
                            )}
                          >
                            {formatSampleSourceStatus(source.status)}
                          </span>
                        </div>
                        <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                          {(source.patent_count ?? 0).toLocaleString()} records
                        </p>
                        {source.error_message ? (
                          <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                            {sanitizeReportDiagnosticText(
                              source.error_message,
                              "Source returned a diagnostic message for support review.",
                            )}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-warning/25 bg-warning/10 p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle
                      className="mt-0.5 h-5 w-5 text-warning"
                      aria-hidden="true"
                    />
                    <div>
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                        Limitations and recoverable failures
                      </h3>
                      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                        The sample keeps imperfect evidence visible so review
                        can focus on exactly what may affect reliance.
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 grid gap-3">
                    {demoArtifact.dataLimitations.map((limitation, index) => (
                      <article
                        key={`${limitation.category}-${index}`}
                        className="rounded-md border border-warning/20 bg-[var(--bg-surface)] p-3"
                      >
                        <h4 className="text-sm font-semibold capitalize text-[var(--text-primary)]">
                          {limitation.category.replace(/_/g, " ")}
                        </h4>
                        <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                          {limitation.description}
                        </p>
                        <p className="mt-2 text-xs leading-5 text-[var(--text-primary)]">
                          Impact: {limitation.impact}
                        </p>
                      </article>
                    ))}
                    {demoArtifact.analysisFailures.map((failure) => (
                      <article
                        key={`${failure.patent_id}-${failure.step}`}
                        className="rounded-md border border-warning/20 bg-[var(--bg-surface)] p-3"
                      >
                        <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                          {failure.patent_id} · {failure.step}
                        </h4>
                        <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                          {failure.error_type}:{" "}
                          {sanitizeReportDiagnosticText(
                            failure.error_message,
                            "Analysis step did not complete; diagnostic details are available to support.",
                          )}
                        </p>
                        <p className="mt-2 text-xs font-semibold text-[var(--text-primary)]">
                          {failure.recoverable
                            ? "Recoverable in follow-up review"
                            : "Not recoverable in this run"}
                        </p>
                      </article>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {failedSources.length > 0 || warningChecks.length > 0 ? (
              <div className="mt-5 rounded-lg border border-warning/25 bg-warning/10 p-4 text-sm leading-6 text-[var(--text-secondary)]">
                This sample intentionally shows warnings beside the finding:
                {failedSources.length > 0
                  ? ` ${failedSources.map((source) => formatSourceName(source.source)).join(", ")} had source-health caveats.`
                  : ""}
                {warningChecks.length > 0
                  ? ` ${warningChecks.map((check) => formatCheckName(check.check_name)).join(", ")} requires review.`
                  : ""}
              </div>
            ) : null}
          </div>
        </section>
      </MobileReportDisclosure>
    </>
  );
}
