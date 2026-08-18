"use client";

import { useId } from "react";
import { CheckCircle2, HandMetal, LockKeyhole } from "lucide-react";
import { CollapsibleCard } from "@/components/config/collapsible-card";
import {
  CONFIG_COMPACT_SELECT_CLASS,
  CONFIG_FORM_ROW_CLASS,
  CONFIG_SWITCH_LABEL_CLASS,
  HITL_CHECKPOINTS,
  type ConfigStore,
} from "@/components/config/helpers";
import { cn } from "@/lib/utils";

interface HitlSectionProps {
  config: ConfigStore;
}

export function HitlSection({ config }: HitlSectionProps) {
  const enableHitlId = useId();
  const hitlHintId = useId();
  const autoSkipId = useId();

  return (
    <CollapsibleCard title="Human-in-the-Loop Checkpoints" icon={HandMetal}>
      <div className="flex items-start gap-3 rounded-lg border border-brand-primary/25 bg-brand-primary/[0.05] p-3">
        <LockKeyhole
          className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
          aria-hidden="true"
        />
        <div>
          <p className="type-label-sm font-semibold text-[var(--text-primary)]">
            Resolved identity approval is always required
          </p>
          <p className="mt-1 type-label-sm leading-5 text-[var(--text-secondary)]">
            Patent search stays blocked until a reviewer accepts the
            fingerprint-bound canonical identity, derived structure lanes, and
            disclosed salt, stereo, tautomer, and prodrug limitations.
          </p>
        </div>
      </div>
      <div className={CONFIG_FORM_ROW_CLASS}>
        <div className="min-w-0">
          <label
            htmlFor={enableHitlId}
            className="type-body-md font-medium text-[var(--text-primary)]"
          >
            Enable additional review checkpoints
          </label>
          <p
            id={hitlHintId}
            className="type-label-sm text-[var(--text-tertiary)]"
          >
            Add search, triage, analysis, or report gates after identity
            approval
          </p>
        </div>
        <label className={CONFIG_SWITCH_LABEL_CLASS}>
          <input
            id={enableHitlId}
            type="checkbox"
            checked={config.hitlEnabled}
            aria-describedby={hitlHintId}
            onChange={(e) =>
              config.setConfig({ hitlEnabled: e.target.checked })
            }
            className="peer sr-only"
          />
          <div className="h-6 w-11 rounded-full bg-[var(--border-default)] after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-[var(--text-secondary)] after:transition-all peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-brand-primary/70 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-[var(--bg-base)] peer-checked:bg-brand-primary-dim peer-checked:after:translate-x-full peer-checked:after:bg-[var(--brand-paper)]" />
        </label>
      </div>
      {config.hitlEnabled ? (
        <>
          <div>
            <label className="mb-2 block type-label-sm font-medium text-[var(--text-secondary)]">
              Active Checkpoints
            </label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {HITL_CHECKPOINTS.map((checkpoint) => {
                const checked = config.hitlCheckpoints.includes(checkpoint.id);
                const disableRemoval =
                  checked && config.hitlCheckpoints.length === 1;

                return (
                  <label
                    key={checkpoint.id}
                    className={cn(
                      "flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border p-2.5 transition-colors focus-within:ring-2 focus-within:ring-brand-primary/60 focus-within:ring-offset-2 focus-within:ring-offset-[var(--bg-base)]",
                      checked
                        ? "border-brand-primary/40 bg-brand-primary/5"
                        : "border-[var(--border-default)] bg-[var(--surface-muted)] hover:border-[var(--border-emphasis)]",
                      disableRemoval && "cursor-not-allowed opacity-80",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disableRemoval}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...config.hitlCheckpoints, checkpoint.id]
                          : config.hitlCheckpoints.filter(
                              (value) => value !== checkpoint.id,
                            );
                        config.setConfig({ hitlCheckpoints: next });
                      }}
                      className="h-4 w-4 shrink-0 accent-brand-primary focus-visible:outline-none disabled:cursor-not-allowed"
                    />
                    <span className="type-label-sm text-[var(--text-primary)]">
                      {checkpoint.label}
                    </span>
                    {checked ? (
                      <CheckCircle2 className="ml-auto h-3.5 w-3.5 text-brand-primary" />
                    ) : null}
                  </label>
                );
              })}
            </div>
          </div>
          <div className={CONFIG_FORM_ROW_CLASS}>
            <div className="min-w-0">
              <label
                htmlFor={autoSkipId}
                className="type-body-md font-medium text-[var(--text-primary)]"
              >
                Auto-skip Timeout
              </label>
              <p className="type-label-sm text-[var(--text-tertiary)]">
                Minutes to wait before auto-approving
              </p>
            </div>
            <select
              id={autoSkipId}
              value={config.hitlAutoSkipMinutes}
              onChange={(e) =>
                config.setConfig({
                  hitlAutoSkipMinutes: Number.parseInt(e.target.value, 10),
                })
              }
              className={CONFIG_COMPACT_SELECT_CLASS}
            >
              <option value="5">5 min</option>
              <option value="10">10 min</option>
              <option value="15">15 min</option>
              <option value="30">30 min</option>
            </select>
          </div>
        </>
      ) : null}
    </CollapsibleCard>
  );
}
