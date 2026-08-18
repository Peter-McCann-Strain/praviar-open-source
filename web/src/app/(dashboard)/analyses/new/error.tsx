"use client";

import { RouteError as SharedRouteError } from "@/components/shared/route-error";

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <SharedRouteError
      error={error}
      reset={reset}
      section="New analysis"
      backHref="/analyses"
      backLabel="Analyses"
    />
  );
}
