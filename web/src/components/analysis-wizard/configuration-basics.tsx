"use client";

import { useId } from "react";
import { FolderOpen, Gauge, Layers3, Loader2, Route, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  JURISDICTION_BUNDLE_DEFINITIONS,
  MAJOR_MARKET_JURISDICTIONS,
  formatJurisdictionList,
  getLaunchReadyJurisdictions,
  getStagedJurisdictions,
} from "@/lib/jurisdiction-bundles";
import type { PipelineConfig } from "@/types/pipeline";
import type { ConfigState } from "@/stores/config-store";

interface ConfigPresetOption {
  id: string;
  name: string;
  description: string;
  config: Partial<PipelineConfig>;
}

interface ConfigurationBasicsProps {
  canManagePresets?: boolean;
  config: ConfigState;
  savedPresets?: ConfigPresetOption[];
  showSavePreset: boolean;
  presetName: string;
  presetDescription: string;
  isSavingPreset: boolean;
  sessionReady: boolean;
  sessionError: string | null;
  onLoadPreset: (config: Partial<PipelineConfig>) => void;
  onToggleSavePreset: () => void;
  onPresetNameChange: (value: string) => void;
  onPresetDescriptionChange: (value: string) => void;
  onCancelSavePreset: () => void;
  onSavePreset: () => void;
}

const ADAPTIVE_EXECUTION_ITEMS = [
  {
    icon: Route,
    label: "One adaptive path",
    detail:
      "Starts efficiently, then escalates evidence collection internally.",
  },
  {
    icon: Layers3,
    label: "Evidence gates",
    detail: "Claim, source, and confidence gaps are captured for review.",
  },
  {
    icon: Gauge,
    label: "Reviewer-ready output",
    detail: "Launch metadata records how the matter was handled.",
  },
] as const;

export function ConfigurationBasics({
  canManagePresets = true,
  config,
  savedPresets,
  showSavePreset,
  presetName,
  presetDescription,
  isSavingPreset,
  sessionReady,
  sessionError,
  onLoadPreset,
  onToggleSavePreset,
  onPresetNameChange,
  onPresetDescriptionChange,
  onCancelSavePreset,
  onSavePreset,
}: ConfigurationBasicsProps) {
  const savedPresetId = useId();
  const presetNameId = useId();
  const presetDescriptionId = useId();
  const savePresetPanelId = useId();

  return (
    <>
      <div>
        <label className="mb-3 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          Adaptive Execution
        </label>
        <div className="grid gap-3 rounded-lg border border-brand-primary/15 bg-brand-primary/[0.07] p-4 shadow-[var(--shadow-xs)] sm:grid-cols-3">
          {ADAPTIVE_EXECUTION_ITEMS.map((item) => {
            const Icon = item.icon;

            return (
              <div key={item.label} className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                  <Icon
                    className="h-4 w-4 text-brand-primary"
                    aria-hidden="true"
                  />
                  {item.label}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                  {item.detail}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <label className="mb-3 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          Jurisdiction Bundle
        </label>
        <div
          className="grid gap-3 sm:grid-cols-2"
          role="radiogroup"
          aria-label="Jurisdiction bundle"
        >
          {Object.values(JURISDICTION_BUNDLE_DEFINITIONS).map((bundle) => (
            <button
              key={bundle.value}
              type="button"
              role="radio"
              aria-checked={config.jurisdictionBundle === bundle.value}
              onClick={() => config.applyJurisdictionBundle(bundle.value)}
              className={cn(
                "min-h-24 rounded-lg border p-3 text-left shadow-[var(--shadow-xs)] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60",
                config.jurisdictionBundle === bundle.value
                  ? "border-brand-primary bg-brand-primary/10 shadow-[inset_0_0_0_1px_rgba(var(--brand-primary-rgb),0.12)]"
                  : "border-[var(--border-default)] bg-[var(--surface-muted)] hover:border-[var(--border-emphasis)] hover:bg-[var(--surface-hover)]",
              )}
            >
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                {bundle.label}
              </span>
              <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                {bundle.description}
              </p>
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-[var(--text-tertiary)]">
          Launch-ready lanes:{" "}
          {formatJurisdictionList(
            getLaunchReadyJurisdictions(config.targetJurisdictions),
          )}
        </p>
        {getStagedJurisdictions(config.targetJurisdictions).length > 0 ? (
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            Staged in this frontend slice:{" "}
            {formatJurisdictionList(
              getStagedJurisdictions(config.targetJurisdictions),
            )}
          </p>
        ) : null}
        {config.jurisdictionBundle === "custom" ? (
          <div
            className="mt-3 flex flex-wrap gap-2"
            role="group"
            aria-label="Custom target jurisdictions"
          >
            {MAJOR_MARKET_JURISDICTIONS.map((jurisdiction) => (
              <button
                key={jurisdiction}
                type="button"
                role="checkbox"
                aria-checked={config.targetJurisdictions.includes(jurisdiction)}
                onClick={() => config.toggleTargetJurisdiction(jurisdiction)}
                className={cn(
                  "min-h-11 rounded-md border px-3 text-xs font-medium transition-colors",
                  config.targetJurisdictions.includes(jurisdiction)
                    ? "border-brand-primary bg-brand-primary/10 text-brand-primary"
                    : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-emphasis)]",
                )}
              >
                {jurisdiction}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
        {savedPresets && savedPresets.length > 0 ? (
          <div className="flex flex-1 items-center gap-2">
            <FolderOpen className="h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
            <label htmlFor={savedPresetId} className="sr-only">
              Load saved configuration
            </label>
            <select
              id={savedPresetId}
              value=""
              onChange={(event) => {
                const preset = savedPresets.find(
                  (item) => item.id === event.target.value,
                );
                if (preset) {
                  onLoadPreset(preset.config);
                }
              }}
              className="min-h-11 flex-1 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 text-sm text-[var(--text-secondary)]"
            >
              <option value="" disabled>
                Load saved configuration...
              </option>
              {savedPresets.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.name}
                  {preset.description ? ` — ${preset.description}` : ""}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        {canManagePresets ? (
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 flex-shrink-0 gap-1.5"
            onClick={onToggleSavePreset}
            disabled={!sessionReady}
            aria-expanded={showSavePreset}
            aria-controls={savePresetPanelId}
          >
            <Save className="h-3.5 w-3.5" />
            Save as Preset
          </Button>
        ) : null}
      </div>

      {canManagePresets && !sessionReady ? (
        <div
          className="rounded-lg border border-info/25 bg-info/10 p-3 text-sm text-info"
          role="status"
          aria-live="polite"
        >
          Preparing secure session before presets can be saved.
        </div>
      ) : null}
      {canManagePresets && sessionError ? (
        <div
          className="rounded-lg border border-error/25 bg-error/10 p-3 text-sm text-error"
          role="alert"
        >
          {sessionError}
        </div>
      ) : null}

      {canManagePresets && showSavePreset ? (
        <div
          id={savePresetPanelId}
          className="space-y-3 rounded-lg border border-brand-primary/20 bg-brand-primary/5 p-4 shadow-[var(--shadow-xs)]"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor={presetNameId}
                className="mb-1 block text-xs font-medium text-[var(--text-secondary)]"
              >
                Name
              </label>
              <Input
                id={presetNameId}
                value={presetName}
                onChange={(event) => onPresetNameChange(event.target.value)}
                placeholder="e.g., Counsel review baseline"
                className="min-h-11 text-sm"
              />
            </div>
            <div>
              <label
                htmlFor={presetDescriptionId}
                className="mb-1 block text-xs font-medium text-[var(--text-secondary)]"
              >
                Description (optional)
              </label>
              <Input
                id={presetDescriptionId}
                value={presetDescription}
                onChange={(event) =>
                  onPresetDescriptionChange(event.target.value)
                }
                placeholder="Brief description"
                className="min-h-11 text-sm"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="min-h-11"
              onClick={onCancelSavePreset}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={onSavePreset}
              disabled={!presetName.trim() || isSavingPreset || !sessionReady}
              className="min-h-11 gap-1.5"
            >
              {isSavingPreset ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              Save
            </Button>
          </div>
        </div>
      ) : null}
    </>
  );
}
