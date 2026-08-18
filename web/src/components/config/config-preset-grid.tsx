"use client";

import {
  CheckCircle2,
  ChevronRight,
  Globe2,
  SlidersHorizontal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PRESET_CARDS, type ConfigStore } from "@/components/config/helpers";
import { PRESET_META, PRESETS } from "@/stores/config-store";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";

interface ConfigPresetGridProps {
  config: ConfigStore;
}

export function ConfigPresetGrid({ config }: ConfigPresetGridProps) {
  const selectedPreset = PRESET_CARDS.find((preset) =>
    isPresetSelected(config, preset.key),
  );
  const selectedPresetMeta = selectedPreset
    ? PRESET_META[selectedPreset.key]
    : null;

  return (
    <section aria-labelledby="coverage-profiles-heading" className="space-y-3">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2
            id="coverage-profiles-heading"
            className="type-heading-md text-[var(--text-primary)]"
          >
            Default Policy Profiles
          </h2>
          <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
            Profiles update coverage, review limits, jurisdictions, and
            execution rigor together.
          </p>
        </div>
        <p className="text-xs font-medium text-[var(--text-tertiary)]">
          Applies to new analyses after save
        </p>
      </div>
      <ResponsiveDisclosure
        className="group"
        data-testid="config-policy-profile-disclosure"
        summary={
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:hidden [&::-webkit-details-marker]:hidden">
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-[var(--text-primary)]">
                {selectedPreset
                  ? `${selectedPreset.label} selected`
                  : "Custom policy active"}
              </span>
              <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                {selectedPresetMeta
                  ? `${selectedPresetMeta.jurisdictionCount} jurisdictions · ${selectedPresetMeta.reviewProfile} · compare 3 profiles`
                  : "Compare 3 profiles or keep the current custom defaults"}
              </span>
            </span>
            <ChevronRight
              className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-90"
              aria-hidden="true"
            />
          </summary>
        }
      >
        <div className="mt-3 grid grid-cols-1 gap-3 sm:mt-0 sm:grid-cols-3">
          {PRESET_CARDS.map((preset) => {
            const selected = isPresetSelected(config, preset.key);
            const meta = PRESET_META[preset.key];

            return (
              <button
                key={preset.key}
                type="button"
                aria-pressed={selected}
                aria-label={`${preset.label} profile, ${meta.jurisdictionCount} jurisdictions, ${meta.reviewProfile}`}
                onClick={() => config.applyPreset(preset.key)}
                className={cn(
                  "group relative min-h-[9.5rem] rounded-lg border p-4 text-left shadow-[var(--card-shadow)] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
                  selected
                    ? `${preset.border} shadow-[var(--shadow-md)]`
                    : "border-[var(--border-default)] bg-[var(--surface-muted)] hover:-translate-y-0.5 hover:border-[var(--border-emphasis)] hover:shadow-[var(--shadow-sm)]",
                )}
              >
                <span className="flex items-start justify-between gap-3">
                  <span>
                    <span className="type-label-sm font-semibold text-[var(--text-primary)]">
                      {preset.label}
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">
                      {preset.desc}
                    </span>
                  </span>
                  {selected ? (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-brand-primary/25 bg-brand-primary/10 px-2 py-1 text-xs font-semibold text-brand-primary">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Selected
                    </span>
                  ) : null}
                </span>
                <span className="mt-4 grid gap-2 text-xs text-[var(--text-tertiary)]">
                  <span className="inline-flex items-center gap-2">
                    <Globe2 className="h-3.5 w-3.5 text-brand-primary" />
                    {meta.jurisdictionCount} jurisdictions
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <SlidersHorizontal className="h-3.5 w-3.5 text-brand-primary" />
                    {meta.reviewProfile}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </ResponsiveDisclosure>
    </section>
  );
}

function isPresetSelected(
  config: ConfigStore,
  presetKey: keyof typeof PRESETS,
): boolean {
  const preset = PRESETS[presetKey];

  return Object.entries(preset).every(([key, presetValue]) => {
    const configValue = config[key as keyof ConfigStore];

    if (Array.isArray(presetValue)) {
      return (
        Array.isArray(configValue) &&
        presetValue.length === configValue.length &&
        presetValue.every((value, index) => configValue[index] === value)
      );
    }

    return configValue === presetValue;
  });
}
