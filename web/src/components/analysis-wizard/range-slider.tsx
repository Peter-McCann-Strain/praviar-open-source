"use client";

import { useId, type CSSProperties } from "react";

interface RangeSliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  formatValue?: (value: number) => string;
}

export function RangeSlider({
  label,
  value,
  onChange,
  min,
  max,
  step,
  suffix,
  formatValue,
}: RangeSliderProps) {
  const inputId = useId();
  const displayValue = formatValue ? formatValue(value) : `${value}`;
  const progress = ((value - min) / (max - min)) * 100;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <label
          htmlFor={inputId}
          className="type-label-sm text-[var(--text-secondary)]"
        >
          {label}
        </label>
        <span className="type-mono-sm text-brand-primary">
          {displayValue}
          {suffix ? ` ${suffix}` : ""}
        </span>
      </div>
      <input
        id={inputId}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-valuetext={`${displayValue}${suffix ? ` ${suffix}` : ""}`}
        onChange={(e) => onChange(Number.parseFloat(e.target.value))}
        style={{ "--range-progress": `${progress}%` } as CSSProperties}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-[var(--border-default)] accent-brand-primary [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-brand-primary [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-primary [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:transition-colors [&::-webkit-slider-thumb]:hover:bg-brand-primary"
      />
      <div className="mt-1 flex justify-between">
        <span className="text-xs text-[var(--text-disabled)]">{min}</span>
        <span className="text-xs text-[var(--text-disabled)]">{max}</span>
      </div>
    </div>
  );
}
