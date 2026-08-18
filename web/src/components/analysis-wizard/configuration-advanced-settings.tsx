"use client";

import { Settings2 } from "lucide-react";
import { CollapsibleSection } from "@/components/analysis-wizard/collapsible-section";
import { ConfigurationAnalysisParameters } from "@/components/analysis-wizard/configuration-analysis-parameters";
import { ConfigurationSearchParameters } from "@/components/analysis-wizard/configuration-search-parameters";
import type { ConfigState } from "@/stores/config-store";

interface ConfigurationAdvancedSettingsProps {
  config: ConfigState;
}

export function ConfigurationAdvancedSettings({
  config,
}: ConfigurationAdvancedSettingsProps) {
  return (
    <CollapsibleSection title="Expert Settings" icon={Settings2}>
      <ConfigurationSearchParameters config={config} />
      <ConfigurationAnalysisParameters config={config} />
    </CollapsibleSection>
  );
}
