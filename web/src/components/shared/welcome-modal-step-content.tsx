import type { WelcomeStep } from "@/components/shared/welcome-modal-constants";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { SHOWCASE_PAYLOAD } from "@/lib/showcase-report";
import {
  CheckCircle2,
  ChevronRight,
  Database,
  FileText,
  Globe2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

export function WelcomeModalStepContent({ step }: { step: WelcomeStep }) {
  const Icon = step.icon;
  const isPraviarStep = step.preview === "packet";

  return (
    <div className="grid gap-5 px-1 text-left md:grid-cols-[minmax(0,0.95fr)_1px_minmax(300px,1fr)] md:items-center md:gap-7">
      <div className="min-w-0">
        {isPraviarStep ? (
          <PraviarMarkFrame className="mb-3 md:mb-4" size="md" />
        ) : (
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 md:mb-4 md:h-12 md:w-12">
            <Icon className="h-5 w-5 text-brand-primary md:h-6 md:w-6" />
          </div>
        )}

        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)] md:text-xs">
          {step.eyebrow}
        </p>
        <h3 className="mb-2 type-heading-sm text-[var(--text-primary)]">
          {step.title}
        </h3>
        <p className="mb-3 max-w-md text-sm leading-6 text-[var(--text-secondary)] md:mb-4">
          {step.description}
        </p>

        <ul className="w-full space-y-2 text-left md:space-y-2.5">
          {step.details.map((detail) => (
            <li key={detail} className="flex items-start gap-2.5 text-sm">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
              <span className="leading-snug text-[var(--text-secondary)]">
                {detail}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div
        aria-hidden="true"
        className="hidden h-full min-h-72 w-px bg-[var(--border-default)] md:block"
      />
      <WelcomeStepPreview preview={step.preview} />
    </div>
  );
}

function WelcomeStepPreview({ preview }: { preview: WelcomeStep["preview"] }) {
  if (preview === "launch") {
    return <LaunchPreview />;
  }

  if (preview === "report") {
    return <ReportPreview />;
  }

  return <PacketPreview />;
}

function PacketPreview() {
  const rows = [
    {
      icon: Database,
      label: "Sources",
      value: String(SHOWCASE_PAYLOAD.analysis.searched_sources.length),
    },
    {
      icon: Globe2,
      label: "Jurisdictions",
      value: String(SHOWCASE_PAYLOAD.compound.jurisdictions.length),
    },
    {
      icon: ShieldCheck,
      label: "Limitations",
      value: String(SHOWCASE_PAYLOAD.analysis.limitations.length),
    },
  ];

  return (
    <div
      className="light praviar-share-handoff-field overflow-hidden rounded-lg border border-[var(--border-default)] shadow-[var(--shadow-md)]"
      data-testid="welcome-packet-preview"
    >
      <div className="flex items-start justify-between gap-4 border-b border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_78%,transparent)] px-4 py-4 backdrop-blur-xl">
        <div className="min-w-0">
          <p className="mt-1 text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
            Sample FTO packet
          </p>
          <p className="mt-1 truncate text-lg font-semibold text-[var(--text-primary)]">
            {SHOWCASE_PAYLOAD.compound.display_name}
          </p>
          <span className="mt-2 inline-flex rounded-full border border-warning/30 bg-warning/10 px-2.5 py-1 text-xs font-semibold text-warning">
            Not a legal opinion
          </span>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full border border-error/25 bg-error/10 px-2.5 py-1 text-xs font-bold uppercase text-error">
          <ShieldAlert className="h-3 w-3" />
          Review
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 px-4 py-3">
        <PreviewMetric
          label="Families"
          value={String(SHOWCASE_PAYLOAD.analysis.families.length)}
        />
        <PreviewMetric
          label="Evidence"
          value={String(SHOWCASE_PAYLOAD.analysis.evidence.length)}
        />
        <PreviewMetric
          label="Sources"
          value={String(SHOWCASE_PAYLOAD.analysis.searched_sources.length)}
        />
      </div>
      <div className="border-t border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_62%,transparent)] px-4 py-2">
        {rows.map(({ icon: Icon, label, value }) => (
          <div
            key={label}
            className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-2 border-b border-[var(--border-subtle)] py-2 text-xs last:border-b-0"
          >
            <Icon
              className="h-3.5 w-3.5 text-brand-primary"
              aria-hidden="true"
            />
            <span className="min-w-0 font-medium text-[var(--text-secondary)]">
              {label}
            </span>
            <span className="font-semibold text-[var(--text-primary)]">
              {value}
            </span>
            <ChevronRight
              className="h-3.5 w-3.5 text-[var(--text-tertiary)]"
              aria-hidden="true"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function LaunchPreview() {
  const rows = [
    ["Compound", SHOWCASE_PAYLOAD.compound.display_name],
    ["Sources", "Fictional registers A / B"],
    ["Evidence path", "Synthetic records / adaptive triage"],
  ];

  return (
    <div
      className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4 shadow-[var(--shadow-sm)]"
      data-testid="welcome-launch-preview"
    >
      <div className="mb-4 flex items-center gap-3">
        <PraviarMarkFrame size="sm" />
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Launch brief
          </p>
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Evidence path prepared
          </p>
        </div>
      </div>
      <div className="space-y-2">
        {rows.map(([label, value], index) => (
          <div
            key={label}
            className="praviar-glass-chip grid grid-cols-[1.4rem_minmax(0,1fr)] items-start gap-2 rounded-lg px-3 py-2"
          >
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-primary/10 text-xs font-bold text-brand-primary">
              {index + 1}
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                {label}
              </p>
              <p className="mt-0.5 truncate text-sm text-[var(--text-primary)]">
                {value}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReportPreview() {
  return (
    <div
      className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4 shadow-[var(--shadow-sm)]"
      data-testid="welcome-report-preview"
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Report handoff
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            Claim 1 review context
          </p>
        </div>
        <FileText className="h-5 w-5 text-brand-primary" />
      </div>
      <div className="mt-4 space-y-2">
        <div className="rounded-lg border border-error/20 bg-error/10 px-3 py-2">
          <p className="font-mono text-xs font-semibold text-error">
            {SHOWCASE_PAYLOAD.analysis.families[0]?.publications[0]}
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            Fictional claim mapping requires qualified-counsel review.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
          <span className="praviar-glass-chip rounded-lg px-2 py-2">
            Source linked
          </span>
          <span className="praviar-glass-chip rounded-lg px-2 py-2">
            Review context
          </span>
        </div>
      </div>
    </div>
  );
}

function PreviewMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="praviar-glass-chip rounded-lg px-2 py-2">
      <p className="text-lg font-semibold text-[var(--text-primary)]">
        {value}
      </p>
      <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
        {label}
      </p>
    </div>
  );
}
