"use client";

import { Database } from "lucide-react";
import { SourceToggle } from "@/components/analysis-wizard/source-toggle";
import type { ConfigState } from "@/stores/config-store";

interface ConfigurationSearchParametersSourcesProps {
  config: ConfigState;
}

export function ConfigurationSearchParametersSources({
  config,
}: ConfigurationSearchParametersSourcesProps) {
  return (
    <div>
      <label className="mb-3 flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)]">
        <Database className="h-3.5 w-3.5" />
        Patent Sources
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <SourceToggle
          label="PubChem SDQ"
          description="Compound-patent cross-references"
          checked={config.enablePubchem}
          onChange={(value) => config.setConfig({ enablePubchem: value })}
        />
        <SourceToggle
          label="BigQuery Patents"
          description="Google full-text patent search"
          checked={config.enableBigquery}
          onChange={(value) => config.setConfig({ enableBigquery: value })}
        />
        <SourceToggle
          label="SureChEMBL"
          description="Configured chemical-patent index"
          checked={config.enableSurechembl}
          onChange={(value) => config.setConfig({ enableSurechembl: value })}
        />
        <SourceToggle
          label="PatCID"
          description="Chemical structure search"
          checked={config.enablePatcid}
          onChange={(value) => config.setConfig({ enablePatcid: value })}
        />
      </div>
    </div>
  );
}
