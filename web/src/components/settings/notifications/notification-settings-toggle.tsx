interface NotificationSettingsToggleProps {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description: string;
  disabled?: boolean;
}

export function NotificationSettingsToggle({
  checked,
  onChange,
  label,
  description,
  disabled = false,
}: NotificationSettingsToggleProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-4">
      <div className="flex-1 pr-4">
        <p className="text-sm font-medium text-[var(--text-primary)]">
          {label}
        </p>
        <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">
          {description}
        </p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => {
          if (!disabled) {
            onChange(!checked);
          }
        }}
        className={`relative inline-flex h-11 w-16 flex-shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent p-1 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-brand-primary/70 focus:ring-offset-2 focus:ring-offset-[var(--bg-base)] disabled:cursor-not-allowed disabled:opacity-60 ${
          checked ? "bg-brand-primary-dim" : "bg-[var(--surface-active)]"
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-7 w-7 transform rounded-full bg-[var(--brand-paper)] shadow ring-0 transition duration-200 ${
            checked ? "translate-x-6" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}
