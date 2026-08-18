import { DIGEST_FREQUENCY_OPTIONS } from "./notification-settings-constants";
import type { DigestFrequency } from "@/hooks/use-notifications";

interface NotificationSettingsFrequencySelectorProps {
  value: DigestFrequency;
  onChange: (value: DigestFrequency) => void;
  disabled?: boolean;
}

export function NotificationSettingsFrequencySelector({
  value,
  onChange,
  disabled = false,
}: NotificationSettingsFrequencySelectorProps) {
  return (
    <div className="py-4">
      <p className="mb-1 text-sm font-medium text-[var(--text-primary)]">
        Digest Frequency
      </p>
      <p className="mb-3 text-xs text-[var(--text-tertiary)]">
        How often to receive a summary of your platform activity.
      </p>
      <div
        className="grid grid-cols-1 gap-2 sm:grid-cols-2"
        aria-label="Digest frequency"
      >
        {DIGEST_FREQUENCY_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={value === option.value}
            disabled={disabled}
            onClick={() => {
              if (!disabled) {
                onChange(option.value);
              }
            }}
            className={`flex min-h-16 flex-col items-center justify-center gap-1 rounded-lg border px-3 py-3 text-center transition-all focus:outline-none focus:ring-2 focus:ring-brand-primary/70 focus:ring-offset-2 focus:ring-offset-[var(--bg-base)] disabled:cursor-not-allowed disabled:opacity-60 ${
              value === option.value
                ? "border-brand-primary bg-brand-primary/5 text-brand-primary"
                : "border-[var(--border-default)] text-[var(--text-secondary)] hover:border-[var(--border-emphasis)] hover:text-[var(--text-primary)]"
            }`}
          >
            <span className="text-sm font-medium">{option.label}</span>
            <span className="text-xs leading-tight opacity-70">
              {option.description}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
