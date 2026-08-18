"use client";

import { useId } from "react";
import type { ConfigState } from "@/stores/config-store";

interface ConfigurationSearchParametersExpiredPatentsProps {
  config: ConfigState;
}

export function ConfigurationSearchParametersExpiredPatents({
  config,
}: ConfigurationSearchParametersExpiredPatentsProps) {
  const includeExpiredId = useId();
  const gracePeriodId = useId();

  return (
    <div className="flex items-center gap-4">
      <label
        htmlFor={includeExpiredId}
        className="flex cursor-pointer items-center gap-2"
      >
        <input
          id={includeExpiredId}
          type="checkbox"
          checked={config.includeExpired}
          onChange={(event) =>
            config.setConfig({ includeExpired: event.target.checked })
          }
          className="h-4 w-4 accent-brand-primary"
        />
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          Include Expired Patents
        </span>
      </label>
      {config.includeExpired ? (
        <div className="flex items-center gap-2">
          <label
            htmlFor={gracePeriodId}
            className="text-xs text-[var(--text-tertiary)]"
          >
            Grace period:
          </label>
          <select
            id={gracePeriodId}
            value={config.expiredGraceYears}
            onChange={(event) =>
              config.setConfig({
                expiredGraceYears: Number.parseInt(event.target.value, 10),
              })
            }
            className="h-8 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-2 text-xs text-[var(--text-secondary)]"
          >
            <option value={3}>3 years</option>
            <option value={5}>5 years</option>
            <option value={7}>7 years</option>
          </select>
        </div>
      ) : null}
    </div>
  );
}
