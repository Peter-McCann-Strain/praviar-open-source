"use client";

import { Clock } from "lucide-react";
import type { LegalEvent } from "@praviar/shared-types";
import { PatentDetailDrawerSection } from "@/components/report/patent-detail-drawer-section";

export function PatentDetailDrawerEventsSection({
  events,
}: {
  events: LegalEvent[];
}) {
  return (
    <PatentDetailDrawerSection
      title="Legal Events"
      icon={Clock}
      defaultOpen={false}
    >
      <div className="space-y-2">
        {events.slice(0, 15).map((event, index) => (
          <div key={index} className="flex items-start gap-2 text-xs">
            <span className="text-[var(--text-tertiary)] tabular-nums flex-shrink-0 w-20">
              {event.event_date ?? "—"}
            </span>
            <span className="text-[var(--text-secondary)]">
              {event.event_description}
              {event.event_code ? (
                <span className="text-[var(--text-disabled)] ml-1">
                  ({event.event_code})
                </span>
              ) : null}
            </span>
          </div>
        ))}
        {events.length > 15 ? (
          <p className="text-xs text-[var(--text-disabled)]">
            + {events.length - 15} more events
          </p>
        ) : null}
      </div>
    </PatentDetailDrawerSection>
  );
}
