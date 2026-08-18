import type {
  DigestFrequency,
  NotificationPreferences,
} from "@/hooks/use-notifications";

export const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  email_on_analysis_complete: true,
  email_on_monitor_alert: true,
  email_digest_frequency: "weekly",
};

export const DIGEST_FREQUENCY_OPTIONS: {
  value: DigestFrequency;
  label: string;
  description: string;
}[] = [
  { value: "off", label: "Off", description: "No digest emails" },
  {
    value: "weekly",
    label: "Weekly",
    description: "Weekly summary on Mondays",
  },
];
