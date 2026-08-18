"use client";

export type SearchParameterSliderKey =
  | "searchTanimotoThreshold"
  | "searchMaxRankedResults";

export interface SearchParameterSliderSpec {
  key: SearchParameterSliderKey;
  label: string;
  min: number;
  max: number;
  step: number;
  formatValue?: (value: number) => string;
}

export const SEARCH_PARAMETER_SLIDERS = [
  {
    key: "searchTanimotoThreshold",
    label: "Tanimoto Threshold",
    min: 0.3,
    max: 0.9,
    step: 0.05,
    formatValue: (value: number) => value.toFixed(2),
  },
  {
    key: "searchMaxRankedResults",
    label: "Ranked Result Budget",
    min: 50,
    max: 500,
    step: 25,
  },
] as const satisfies readonly SearchParameterSliderSpec[];
