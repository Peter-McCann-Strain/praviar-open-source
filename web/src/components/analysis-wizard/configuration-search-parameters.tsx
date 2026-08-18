"use client";

import { Search } from "lucide-react";
import { CollapsibleSection } from "@/components/analysis-wizard/collapsible-section";
import { ConfigurationSearchParametersCitation } from "@/components/analysis-wizard/configuration-search-parameters-citation";
import { ConfigurationSearchParametersExpiredPatents } from "@/components/analysis-wizard/configuration-search-parameters-expired-patents";
import { ConfigurationSearchParametersJurisdictions } from "@/components/analysis-wizard/configuration-search-parameters-jurisdictions";
import { ConfigurationSearchParametersSliders } from "@/components/analysis-wizard/configuration-search-parameters-sliders";
import { ConfigurationSearchParametersSources } from "@/components/analysis-wizard/configuration-search-parameters-sources";
import type { ConfigState } from "@/stores/config-store";

interface ConfigurationSearchParametersProps {
  config: ConfigState;
}

export function ConfigurationSearchParameters({
  config,
}: ConfigurationSearchParametersProps) {
  return (
    <CollapsibleSection title="Search Parameters" icon={Search}>
      <div className="space-y-5 pt-3">
        <ConfigurationSearchParametersSliders config={config} />
        <ConfigurationSearchParametersJurisdictions config={config} />
        <ConfigurationSearchParametersExpiredPatents config={config} />
        <ConfigurationSearchParametersCitation config={config} />
        <ConfigurationSearchParametersSources config={config} />
      </div>
    </CollapsibleSection>
  );
}
