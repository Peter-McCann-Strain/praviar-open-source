"use client";

import { useEffect } from "react";
import {
  type MarketingEventName,
  trackMarketingEvent,
} from "@/lib/marketing-analytics";

interface PageEventBeaconProps {
  eventName: MarketingEventName;
  properties?: Record<string, unknown>;
}

export function PageEventBeacon({
  eventName,
  properties,
}: PageEventBeaconProps) {
  useEffect(() => {
    trackMarketingEvent(eventName, properties);
  }, [eventName, properties]);

  return null;
}
