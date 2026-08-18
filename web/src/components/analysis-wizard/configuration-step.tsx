"use client";
import {
  FileCheck2,
  Globe2,
  Layers3,
  SearchCheck,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfigurationBasics } from "@/components/analysis-wizard/configuration-basics";
import { ConfigurationAdvancedSettings } from "@/components/analysis-wizard/configuration-advanced-settings";
import { ConfigurationFooter } from "@/components/analysis-wizard/configuration-footer";
import {
  getEnabledSources,
  getConfigValidationIssues,
} from "@/components/config/helpers";
import {
  formatJurisdictionList,
  getLaunchReadyJurisdictions,
  getRuntimeSearchJurisdictions,
} from "@/lib/jurisdiction-bundles";
import type { PipelineConfig } from "@/types/pipeline";
import type { ConfigState } from "@/stores/config-store";

interface ConfigPresetOption {
  id: string;
  name: string;
  description: string;
  config: Partial<PipelineConfig>;
}

interface ConfigurationStepProps {
  canManagePresets?: boolean;
  config: ConfigState;
  savedPresets?: ConfigPresetOption[];
  showSavePreset: boolean;
  presetName: string;
  presetDescription: string;
  isSavingPreset: boolean;
  sessionReady: boolean;
  sessionError: string | null;
  canContinue: boolean;
  continueBlocker: string | null;
  onLoadPreset: (config: Partial<PipelineConfig>) => void;
  onToggleSavePreset: () => void;
  onPresetNameChange: (value: string) => void;
  onPresetDescriptionChange: (value: string) => void;
  onCancelSavePreset: () => void;
  onSavePreset: () => void;
  onBack: () => void;
  onNext: () => void;
}

export function ConfigurationStep({
  canManagePresets = true,
  config,
  savedPresets,
  showSavePreset,
  presetName,
  presetDescription,
  isSavingPreset,
  sessionReady,
  sessionError,
  canContinue,
  continueBlocker,
  onLoadPreset,
  onToggleSavePreset,
  onPresetNameChange,
  onPresetDescriptionChange,
  onCancelSavePreset,
  onSavePreset,
  onBack,
  onNext,
}: ConfigurationStepProps) {
  const enabledSources = getEnabledSources(config);
  const launchReadyJurisdictions = getLaunchReadyJurisdictions(
    config.targetJurisdictions,
  );
  const runtimeSearchJurisdictions = getRuntimeSearchJurisdictions({
    jurisdictionBundle: config.jurisdictionBundle,
    searchJurisdictions: config.searchJurisdictions,
    targetJurisdictions: config.targetJurisdictions,
  });
  const validationIssues = getConfigValidationIssues(config);
  const reviewGateLabel =
    config.hitlEnabled && config.hitlCheckpoints.length > 0
      ? `Identity + ${config.hitlCheckpoints.length} additional gate${
          config.hitlCheckpoints.length === 1 ? "" : "s"
        }`
      : "Resolved identity approval";
  const configurationSignals = [
    {
      icon: SearchCheck,
      label: "Sources",
      value:
        enabledSources.length > 0
          ? `${enabledSources.length} selected`
          : "Action needed",
    },
    {
      icon: Globe2,
      label: "Launch lanes",
      value: formatJurisdictionList(
        launchReadyJurisdictions,
        "No launch-ready lanes",
      ),
    },
    {
      icon: Layers3,
      label: "Search scope",
      value: formatJurisdictionList(runtimeSearchJurisdictions),
    },
    {
      icon: FileCheck2,
      label: "Review packet",
      value: reviewGateLabel,
    },
  ];
  const isConfigurationReady = validationIssues.length === 0;

  return (
    <Card
      className="overflow-hidden border-brand-primary/15"
      data-praviar-configuration-step
    >
      <div className="h-1 bg-gradient-to-r from-brand-primary via-brand-primary/30 to-transparent" />
      <CardHeader className="border-b border-[var(--border-subtle)] bg-[var(--surface-glass)] p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Evidence scope
            </p>
            <CardTitle
              aria-level={2}
              className="mt-1 flex items-center gap-2 text-base"
            >
              <Settings2 className="h-5 w-5 text-brand-primary" />
              Analysis Configuration
            </CardTitle>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
              Set the source, lane, and reviewer handoff policy before the
              adaptive evidence path opens.
            </p>
          </div>
          <span className="inline-flex w-fit items-center gap-2 rounded-md border border-brand-primary/25 bg-brand-primary/10 px-2.5 py-1 text-xs font-medium text-brand-primary">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            {isConfigurationReady ? "Launch-ready scope" : "Scope needs input"}
          </span>
        </div>

        <div
          className="mt-4 grid gap-2 text-xs text-[var(--text-tertiary)] sm:grid-cols-2 xl:grid-cols-4"
          aria-label="Configuration summary"
        >
          {configurationSignals.map((signal) => {
            const Icon = signal.icon;

            return (
              <div
                key={signal.label}
                className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 py-2"
              >
                <p className="flex items-center gap-1.5 font-semibold uppercase tracking-[0.1em]">
                  <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  {signal.label}
                </p>
                <p className="mt-1 line-clamp-2 font-medium normal-case tracking-normal text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                  {signal.value}
                </p>
              </div>
            );
          })}
        </div>
      </CardHeader>
      <CardContent className="space-y-6 p-5">
        <ConfigurationBasics
          canManagePresets={canManagePresets}
          config={config}
          savedPresets={savedPresets}
          showSavePreset={showSavePreset}
          presetName={presetName}
          presetDescription={presetDescription}
          isSavingPreset={isSavingPreset}
          sessionReady={sessionReady}
          sessionError={sessionError}
          onLoadPreset={onLoadPreset}
          onToggleSavePreset={onToggleSavePreset}
          onPresetNameChange={onPresetNameChange}
          onPresetDescriptionChange={onPresetDescriptionChange}
          onCancelSavePreset={onCancelSavePreset}
          onSavePreset={onSavePreset}
        />
        <ConfigurationAdvancedSettings config={config} />
        <ConfigurationFooter
          canContinue={canContinue}
          continueBlocker={continueBlocker}
          onBack={onBack}
          onNext={onNext}
        />
      </CardContent>
    </Card>
  );
}
