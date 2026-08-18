"use client";

import { RangeSlider } from "@/components/analysis-wizard/range-slider";
import {
  SEARCH_PARAMETER_SLIDERS,
  type SearchParameterSliderKey,
} from "@/components/analysis-wizard/configuration-search-parameters-slider-specs";
import type { ConfigState } from "@/stores/config-store";

interface ConfigurationSearchParametersSlidersProps {
  config: ConfigState;
}

export function ConfigurationSearchParametersSliders({
  config,
}: ConfigurationSearchParametersSlidersProps) {
  return (
    <>
      {SEARCH_PARAMETER_SLIDERS.map((slider) => {
        const formatValue =
          "formatValue" in slider ? slider.formatValue : undefined;

        return (
          <RangeSlider
            key={slider.key}
            label={slider.label}
            value={config[slider.key]}
            onChange={(value) =>
              config.setConfig({ [slider.key]: value } as Pick<
                ConfigState,
                SearchParameterSliderKey
              >)
            }
            min={slider.min}
            max={slider.max}
            step={slider.step}
            formatValue={formatValue}
          />
        );
      })}
    </>
  );
}
