export type ReportChatLaunchIntent = "report" | "section" | "patent";

export interface ReportChatLaunchContext {
  actionLabel?: string;
  description: string;
  intent: ReportChatLaunchIntent;
  launchId?: string;
  metadata?: Array<{
    label: string;
    value: string;
  }>;
  prompt: string;
  title: string;
}
